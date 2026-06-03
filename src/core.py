import time
import tls_client
import httpx
from src.utils import log_error, sanitize_proxy

def _classify_error(exc: Exception) -> str:
    """Translate raw exceptions into human-readable failure reasons."""
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "Proxy tidak merespons (timeout)"
    if "400 bad request" in msg:
        return "Proxy menolak request (400 Bad Request) — proxy tidak mendukung tunneling HTTPS"
    if "407" in msg:
        return "Proxy butuh autentikasi (407 Proxy Auth Required)"
    if "403" in msg:
        return "Akses ditolak server (403 Forbidden)"
    if "connectionerror" in msg or "connection refused" in msg or "eof" in msg:
        return "Koneksi gagal (proxy mati / port salah)"
    if "ssl" in msg or "certificate" in msg:
        return "Error SSL/TLS dari proxy"
    return f"Error tidak dikenal: {exc}"

def retry(fn, attempts=3, backoff=2, logger_callback=None):
    last_reason = ""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_reason = _classify_error(exc)
            if i < attempts - 1:
                if logger_callback:
                    logger_callback(f"Attempt {i+1} failed → {last_reason}. Retrying in {backoff * (i + 1)}s...")
                time.sleep(backoff * (i + 1))
            else:
                raise RuntimeError(f"Operation failed after {attempts} attempts: {exc}  [Alasan: {last_reason}]") from exc


def _make_session(token, proxy_url):
    sess = tls_client.Session(
        client_identifier="chrome_120", random_tls_extension_order=True
    )
    sess.proxies = {"http": proxy_url, "https": proxy_url}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://chatgpt.com/",
        "Origin": "https://chatgpt.com",
    }
    return sess, headers

def generate_checkout(token, proxy_url, country, currency, logger_callback=None):
    sess, headers = _make_session(token, proxy_url)
    promo_id = "plus-1-month-free"

    def log(msg):
        if logger_callback:
            logger_callback(msg)

    # 1. Check Accounts
    log("Starting account check...")
    try:
        def _check_accounts():
            return sess.get(
                "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
                headers=headers,
                timeout_seconds=10,
            )
        rc = retry(_check_accounts, logger_callback=logger_callback)
        log(f"Account check response status: {rc.status_code}")
        if rc.status_code == 200:
            for _, info in rc.json().get("accounts", {}).items():
                camp = info.get("eligible_promo_campaigns", {})
                if "plus" in camp:
                    promo_id = camp["plus"].get("id", promo_id)
                    break
    except Exception as e:
        safe_e = str(e).replace(proxy_url, sanitize_proxy(proxy_url)) if proxy_url else str(e)
        msg = f"Account check failed (proceeding with default promo ID): {safe_e}"
        log(msg)
        log_error("Account Check", msg)

    log(f"Using promo campaign: {promo_id}")

    # 2. Execute Checkout
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

    log("Executing checkout request...")
    try:
        r = retry(_checkout, logger_callback=logger_callback)
    except Exception as e:
        safe_e = str(e).replace(proxy_url, sanitize_proxy(proxy_url)) if proxy_url else str(e)
        log_error("Checkout POST", safe_e)
        return False, f"Checkout API request failed: {safe_e}", None, None

    if r.status_code != 200:
        safe_resp = r.text[:200].replace(proxy_url, sanitize_proxy(proxy_url)) if proxy_url else r.text[:200]
        msg = f"Checkout API returned status {r.status_code}. Response: {safe_resp}"
        log_error("Checkout API", msg)
        return False, msg, None, None

    try:
        resp = r.json()
    except Exception as e:
        log_error("Parse Checkout JSON", str(e))
        return False, "Failed to parse checkout API response as JSON.", None, None

    hosted = resp.get("url", "")
    cs_id = resp.get("checkout_session_id") or (
        hosted.rstrip("/").split("/")[-1] if hosted else ""
    )

    log(f"Checkout session ID: {cs_id}")

    # 3. Resolve Redirects
    long_url = None
    if cs_id:
        try:
            hdrs = {
                **headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            del hdrs["Content-Type"]
            log("Resolving redirect URL (SSL verification disabled)...")
            with httpx.Client(
                proxy=proxy_url, follow_redirects=True, timeout=15, verify=False
            ) as c:
                final = str(
                    c.get(
                        f"https://chatgpt.com/checkout/openai_llc/{cs_id}",
                        headers=hdrs,
                    ).url
                )
                log(f"Redirect chain URL resolved: {final}")
                long_url = final
        except Exception as e:
            safe_e = str(e).replace(proxy_url, sanitize_proxy(proxy_url)) if proxy_url else str(e)
            log(f"Redirect resolution failed: {safe_e}")
            log_error("Redirect Resolution", safe_e)

    final_url = long_url or hosted
    if not final_url:
        return False, "Failed to resolve a valid checkout URL. See logs for details.", None, None
        
    return True, final_url, promo_id, cs_id
