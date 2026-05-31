import sys, json, re, argparse

import tls_client, httpx


def extract_token(raw):
    raw = raw.strip()
    try:
        d = json.loads(raw)
        for k in ("accessToken", "access_token", "token"):
            if d.get(k): return d[k]
    except: pass
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', raw)
    return m.group(1) if m else raw


def generate_checkout(session_raw, proxy_url):
    token = extract_token(session_raw)
    sess  = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
    sess.proxies = {"http": proxy_url, "https": proxy_url}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Referer":       "https://chatgpt.com/",
        "Origin":        "https://chatgpt.com",
    }

    promo_id = "plus-1-month-free"
    try:
        rc = sess.get("https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
                      headers=headers, timeout_seconds=10)
        if rc.status_code == 200:
            for _, info in rc.json().get("accounts", {}).items():
                camp = info.get("eligible_promo_campaigns", {})
                if "plus" in camp:
                    promo_id = camp["plus"].get("id", promo_id)
                    break
    except: pass

    r = sess.post("https://chatgpt.com/backend-api/payments/checkout", headers=headers, json={
        "plan_name": "chatgptplusplan",
        "entry_point": "all_plans_pricing_modal",
        "checkout_ui_mode": "hosted",
        "billing_details": {"country": "ID", "currency": "IDR"},
        "promo_campaign": {"promo_campaign_id": promo_id, "is_coupon_from_query_param": False},
    }, timeout_seconds=20)

    if r.status_code != 200:
        raise Exception(f"Checkout API {r.status_code}: {r.text[:200]}")

    resp   = r.json()
    hosted = resp.get("url", "")
    cs_id  = resp.get("checkout_session_id") or (hosted.rstrip("/").split("/")[-1] if hosted else "")

    long_url = None
    if cs_id:
        try:
            hdrs = {**headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            del hdrs["Content-Type"]
            with httpx.Client(follow_redirects=True, timeout=15, verify=False) as c:
                final = str(c.get(f"https://chatgpt.com/checkout/openai_llc/{cs_id}", headers=hdrs).url)
                if "pay.openai.com" in final or "checkout.stripe.com" in final:
                    long_url = final
        except: pass

    return long_url or hosted, promo_id

def main():
    parser = argparse.ArgumentParser(
        description="OpenAI Promo Bypass — generate Rp0 checkout URL with JP proxy"
    )
    parser.add_argument("--session-file", required=True, metavar="PATH",
                        help="path to file containing auth session JSON from chatgpt.com/api/auth/session")
    parser.add_argument("--proxy", required=True, metavar="URL",
                        help="Japanese proxy URL (e.g. http://user:pass@host:port)")
    args = parser.parse_args()

    try:
        session_raw = open(args.session_file).read()
    except OSError as e:
        print(f"Error reading session file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        url, promo = generate_checkout(session_raw, args.proxy)
        print(url)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
