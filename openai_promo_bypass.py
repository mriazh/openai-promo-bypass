import sys, json, re, argparse, time, base64

import tls_client, httpx


def verbose(msg, verbose_flag):
    if verbose_flag:
        print(f"[verbose] {msg}", file=sys.stderr)


def retry(fn, attempts=3, backoff=2, label="request"):
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
            else:
                raise Exception(f"{label} failed after {attempts} attempts: {exc}") from exc


def extract_token(raw):
    raw = raw.strip()
    try:
        d = json.loads(raw)
        for k in ("accessToken", "access_token", "token"):
            if d.get(k):
                return d[k]
    except Exception:
        pass
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', raw)
    return m.group(1) if m else raw


def check_token_expiry(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return
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
    except Exception:
        pass


def validate_session(raw):
    raw = raw.strip()
    try:
        d = json.loads(raw)
    except Exception:
        raise ValueError(
            "Session file does not contain valid JSON. "
            "Expected output from chatgpt.com/api/auth/session"
        )
    for k in ("accessToken", "access_token", "token"):
        if d.get(k):
            return d[k]
    raise ValueError(
        "Session JSON does not contain an expected token key "
        "(accessToken, access_token, or token). "
        f"Found keys: {list(d.keys())}"
    )


def validate_proxy(url):
    if not url or not (
        url.startswith("http://")
        or url.startswith("https://")
        or url.startswith("socks")
    ):
        safe = re.sub(r'://[^@]+@', '://***@', url) if url else url
        raise ValueError(
            f"Invalid proxy URL: {safe!r}. "
            "Must start with http://, https://, or socks"
        )


def _make_session(session_raw, proxy_url):
    token = extract_token(session_raw)
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
    return sess, headers, token


def generate_checkout(session_raw, proxy_url, country="ID", currency="IDR", verbose_flag=False):
    sess, headers, _ = _make_session(session_raw, proxy_url)

    promo_id = "plus-1-month-free"
    try:
        def _check_accounts():
            return sess.get(
                "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
                headers=headers,
                timeout_seconds=10,
            )

        rc = retry(_check_accounts, label="Accounts check")
        verbose(f"Account check response status: {rc.status_code}", verbose_flag)
        if rc.status_code == 200:
            for _, info in rc.json().get("accounts", {}).items():
                camp = info.get("eligible_promo_campaigns", {})
                if "plus" in camp:
                    promo_id = camp["plus"].get("id", promo_id)
                    break
    except Exception:
        pass

    verbose(f"Using promo campaign: {promo_id}", verbose_flag)

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

    r = retry(_checkout, label="Checkout POST")

    if r.status_code != 200:
        raise Exception(
            f"Checkout API {r.status_code} (promo_id={promo_id!r}): {r.text[:200]}"
        )

    resp = r.json()
    hosted = resp.get("url", "")
    cs_id = resp.get("checkout_session_id") or (
        hosted.rstrip("/").split("/")[-1] if hosted else ""
    )

    verbose(f"Checkout session ID: {cs_id}", verbose_flag)

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
        except Exception:
            pass

    return long_url or hosted, promo_id, cs_id


def main():
    parser = argparse.ArgumentParser(
        description="OpenAI Promo Bypass"
    )
    parser.add_argument(
        "--session-file", required=True, metavar="PATH",
        help="path to file containing auth session JSON from chatgpt.com/api/auth/session",
    )
    parser.add_argument(
        "--proxy", required=True, metavar="URL",
        help="Japanese proxy URL (e.g. http://user:pass@host:port)",
    )
    parser.add_argument(
        "--country", default="ID", metavar="CODE",
        help="Billing country code (default: ID)",
    )
    parser.add_argument(
        "--currency", default="IDR", metavar="CODE",
        help="Billing currency code (default: IDR)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print diagnostic info to stderr",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON object",
    )
    args = parser.parse_args()

    try:
        validate_proxy(args.proxy)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.session_file == "-":
            session_raw = sys.stdin.read()
        else:
            with open(args.session_file) as f:
                session_raw = f.read()
    except OSError as e:
        print(f"Error reading session file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        token = validate_session(session_raw)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    check_token_expiry(token)

    try:
        url, promo_id, cs_id = generate_checkout(
            session_raw,
            args.proxy,
            country=args.country,
            currency=args.currency,
            verbose_flag=args.verbose,
        )
        if args.json:
            print(json.dumps({
                "url": url,
                "promo_id": promo_id,
                "checkout_session_id": cs_id,
            }))
        else:
            print(url)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
