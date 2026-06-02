import sys
import json
import re
import argparse
import time
import base64

import tls_client
import httpx

# ==========================================
# Helpers & Sanitization
# ==========================================

def verbose(msg, verbose_flag):
    if verbose_flag:
        print(f"[verbose] {msg}", file=sys.stderr)

def sanitize_proxy(url):
    """Hide credentials in the proxy URL."""
    if url:
        return re.sub(r'://[^@]+@', '://***@', url)
    return url

def sanitize_token(token):
    """Completely hide the token for safety."""
    if token:
        return "<VALID_TOKEN_HIDDEN>"
    return "<NO_TOKEN>"

def sanitize_error(err_str, token=None, proxy=None):
    """Scrub sensitive strings from error messages."""
    res = err_str
    # Universally scrub any URL credentials
    res = re.sub(r'://[^@]+@', '://***@', res)
    
    if token and token in res:
        res = res.replace(token, sanitize_token(token))
    return res

def error_exit(message, code=1):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)

# ==========================================
# Validation & File I/O
# ==========================================

def read_session_file(filepath):
    try:
        if filepath == "-":
            return sys.stdin.read()
        with open(filepath, 'r') as f:
            return f.read()
    except OSError as e:
        error_exit(f"Unable to read session file: {e}")

def extract_and_validate_session(raw):
    raw = raw.strip()
    if not raw:
        error_exit("Session file is empty.")
    
    try:
        d = json.loads(raw)
        for k in ("accessToken", "access_token", "token"):
            if d.get(k):
                return d[k]
    except Exception:
        pass

    # Fallback to regex if simple json parse fails
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', raw)
    if m:
        return m.group(1)

    error_exit("Session JSON does not contain an expected token key (accessToken, access_token, or token).")

def check_token_expiry(token, verbose_flag=False):
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            if len(payload_b64) % 4:
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            if exp is not None:
                now = time.time()
                if now > exp:
                    print(
                        f"Warning: access token appears to have expired at "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(exp))}. "
                        f"Proceeding anyway.",
                        file=sys.stderr,
                    )
    except Exception as e:
        verbose(f"Failed to parse token expiry: {sanitize_error(str(e), token=token)}", verbose_flag)

def validate_proxy(url):
    if not url or not (
        url.startswith("http://")
        or url.startswith("https://")
        or url.startswith("socks")
    ):
        safe_url = sanitize_proxy(url)
        error_exit(f"Invalid proxy URL format: '{safe_url}'. Must start with http://, https://, or socks")

def validate_country(country):
    if not re.match(r'^[A-Za-z]{2}$', country):
        error_exit(f"Invalid country code '{country}'. It must be exactly 2 letters.")

def validate_currency(currency):
    if not re.match(r'^[A-Za-z]{3}$', currency):
        error_exit(f"Invalid currency code '{currency}'. It must be exactly 3 letters.")

# ==========================================
# API Logic
# ==========================================

def retry(fn, attempts=3, backoff=2, label="request", verbose_flag=False):
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if i < attempts - 1:
                verbose(f"{label} attempt {i+1} failed. Retrying in {backoff * (i + 1)}s...", verbose_flag)
                time.sleep(backoff * (i + 1))
            else:
                raise RuntimeError(f"{label} failed after {attempts} attempts.") from exc

def _make_session(token, proxy_url):
    sess = tls_client.Session(
        client_identifier="chrome_120", random_tls_extension_order=True
    )
    sess.proxies = {"http": proxy_url, "https": proxy_url}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://chatgpt.com/",
        "Origin": "https://chatgpt.com",
    }
    return sess, headers

def generate_checkout(token, proxy_url, country, currency, verbose_flag=False):
    sess, headers = _make_session(token, proxy_url)
    promo_id = "plus-1-month-free"

    # 1. Check Accounts (Optional, non-fatal)
    try:
        def _check_accounts():
            return sess.get(
                "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
                headers=headers,
                timeout_seconds=10,
            )
        rc = retry(_check_accounts, label="Accounts check", verbose_flag=verbose_flag)
        verbose(f"Account check response status: {rc.status_code}", verbose_flag)
        if rc.status_code == 200:
            for _, info in rc.json().get("accounts", {}).items():
                camp = info.get("eligible_promo_campaigns", {})
                if "plus" in camp:
                    promo_id = camp["plus"].get("id", promo_id)
                    break
    except Exception as e:
        safe_e = sanitize_error(str(e), proxy=proxy_url)
        verbose(f"Account check failed (proceeding with default promo ID): {safe_e}", verbose_flag)

    verbose(f"Using promo campaign: {promo_id}", verbose_flag)

    # 2. Execute Checkout (Fatal if fails)
    def _checkout():
        return sess.post(
            "https://chatgpt.com/backend-api/payments/checkout",
            headers=headers,
            json={
                "plan_name": "chatgptplusplan",
                "entry_point": "all_plans_pricing_modal",
                "checkout_ui_mode": "hosted",
                "billing_details": {"country": country, "currency": currency},
                "promo_campaign": {
                    "promo_campaign_id": promo_id,
                    "is_coupon_from_query_param": False,
                },
            },
            timeout_seconds=20,
        )

    try:
        r = retry(_checkout, label="Checkout POST", verbose_flag=verbose_flag)
    except Exception as e:
        safe_e = sanitize_error(str(e), proxy=proxy_url)
        print(f"Error during checkout API call: {safe_e}", file=sys.stderr)
        sys.exit(1)

    if r.status_code != 200:
        print(f"Error: Checkout API returned status {r.status_code} (promo_id={promo_id}).", file=sys.stderr)
        verbose(f"Response preview: {sanitize_error(r.text[:200], proxy=proxy_url, token=token)}", verbose_flag)
        sys.exit(1)

    try:
        resp = r.json()
    except Exception:
        print("Error: Failed to parse checkout API response as JSON.", file=sys.stderr)
        sys.exit(1)

    hosted = resp.get("url", "")
    cs_id = resp.get("checkout_session_id") or (
        hosted.rstrip("/").split("/")[-1] if hosted else ""
    )

    verbose(f"Checkout session ID: {cs_id}", verbose_flag)

    # 3. Resolve Redirects (Optional, non-fatal)
    long_url = None
    if cs_id:
        try:
            hdrs = {
                **headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            del hdrs["Content-Type"]
            verbose("SSL verification disabled for redirect resolution", verbose_flag)
            with httpx.Client(
                proxy=proxy_url, follow_redirects=True, timeout=15, verify=False
            ) as c:
                final = str(
                    c.get(
                        f"https://chatgpt.com/checkout/openai_llc/{cs_id}",
                        headers=hdrs,
                    ).url
                )
                verbose(f"Redirect chain URL: {final}", verbose_flag)
                if "pay.openai.com" in final or "checkout.stripe.com" in final:
                    long_url = final
        except Exception as e:
            safe_e = sanitize_error(str(e), proxy=proxy_url)
            verbose(f"Redirect resolution failed: {safe_e}", verbose_flag)

    return long_url or hosted, promo_id, cs_id

# ==========================================
# Main Execution
# ==========================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="OpenAI Promo Bypass - Safely automates promotional checkout flow.",
        epilog=(
            "Examples:\n"
            "  # Basic usage with JSON session\n"
            "  python openai_promo_bypass.py --session-file session.json --proxy http://user:pass@127.0.0.1:8080\n"
            "\n"
            "  # Perform a dry-run to validate settings without making requests\n"
            "  python openai_promo_bypass.py --session-file session.json --proxy http://user:pass@127.0.0.1:8080 --dry-run\n"
            "\n"
            "  # Specify custom country and currency\n"
            "  python openai_promo_bypass.py --session-file session.json --proxy http://user:pass@127.0.0.1:8080 --country US --currency USD\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--session-file", required=True, metavar="PATH",
        help="Path to file containing auth session JSON from chatgpt.com/api/auth/session",
    )
    parser.add_argument(
        "--proxy", required=True, metavar="URL",
        help="Proxy URL (e.g. http://user:pass@host:port)",
    )
    parser.add_argument(
        "--country", default="ID", metavar="CODE",
        help="Billing country code (2 letters, default: ID)",
    )
    parser.add_argument(
        "--currency", default="IDR", metavar="CODE",
        help="Billing currency code (3 letters, default: IDR)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print diagnostic info to stderr",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON object",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate inputs and display configuration without making network requests",
    )
    return parser.parse_args()

def handle_dry_run(args):
    print("--- DRY RUN ---")
    print(f"Proxy    : {sanitize_proxy(args.proxy)}")
    print(f"Token    : <VALID_TOKEN_HIDDEN>")
    print(f"Country  : {args.country}")
    print(f"Currency : {args.currency}")
    print("All inputs validated successfully. No network requests were made.")

def output_result(url, promo_id, cs_id, as_json=False):
    if as_json:
        print(json.dumps({
            "url": url,
            "promo_id": promo_id,
            "checkout_session_id": cs_id,
        }))
    else:
        print(url)

def main():
    args = parse_args()

    # 1. Input Validation
    validate_proxy(args.proxy)
    validate_country(args.country)
    validate_currency(args.currency)

    # 2. Read and Validate Session
    session_raw = read_session_file(args.session_file)
    token = extract_and_validate_session(session_raw)
    
    # Only check expiry logic locally, it won't crash the script but warns if expired
    check_token_expiry(token, verbose_flag=args.verbose)

    # 3. Handle Dry Run
    if args.dry_run:
        handle_dry_run(args)
        sys.exit(0)

    # 4. Execute Checkout
    url, promo_id, cs_id = generate_checkout(
        token=token,
        proxy_url=args.proxy,
        country=args.country,
        currency=args.currency,
        verbose_flag=args.verbose,
    )

    # 5. Output Result
    output_result(url, promo_id, cs_id, as_json=args.json)

if __name__ == "__main__":
    main()
