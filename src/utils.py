import re
import json
import base64
import time
import os
from datetime import datetime

LOG_FILE = os.path.join("logs", "error.log")

def init_logging():
    os.makedirs("logs", exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

def log_error(context_msg, error_str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"[START] {timestamp}\n"
        f"[ERROR] {context_msg}: {error_str}\n"
        f"[END] {timestamp}\n\n"
    )
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to write to error log: {e}")

def sanitize_proxy(url):
    if url:
        return re.sub(r'://[^@]+@', '://***@', url)
    return url

def sanitize_token(token):
    if token:
        return "<VALID_TOKEN_HIDDEN>"
    return "<NO_TOKEN>"

def parse_proxy_string(proxy_str):
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None
    if not (proxy_str.startswith("http") or proxy_str.startswith("socks")):
        proxy_str = f"http://{proxy_str}"
    return proxy_str

def extract_and_validate_session(raw):
    raw = raw.strip()
    if not raw:
        return False, "Session input is empty."
    
    try:
        d = json.loads(raw)
        for k in ("accessToken", "access_token", "token"):
            if d.get(k):
                return True, d[k]
    except Exception:
        pass

    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', raw)
    if m:
        return True, m.group(1)
        
    return False, "Session JSON does not contain an expected token key (accessToken, access_token, or token)."

def check_token_expiry(token):
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
                    return False, f"Token expired at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(exp))}."
        return True, "Token is active."
    except Exception as e:
        log_error("Token parsing", str(e))
        return True, "Unable to parse expiry, proceeding anyway."
