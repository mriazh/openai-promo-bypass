# OpenAI Promo Bypass

Bypass OpenAI geo promo restrictions via JP proxy — get a $0 checkout URL.

## Install

```bash
pip install -r requirements.txt
```

## Usage

Export your OpenAI session JSON from `chatgpt.com/api/auth/session` to a file, then:

```bash
python openai_promo_bypass.py \
  --session-file session.json \
  --proxy http://user:pass@jp-host:3128
```

Prints the Stripe checkout URL to stdout. Open it in a browser to complete signup at $0.

### Flags

| Flag | Required | Description |
|---|---|---|
| `--session-file` | yes | Path to file containing `chatgpt.com/api/auth/session` JSON |
| `--proxy` | yes | Japanese HTTP/HTTPS proxy URL |

## How it works

1. Extracts the access token from the session JSON
2. Queries OpenAI's account check endpoint through the JP proxy to discover eligible promo campaigns
3. Creates a checkout session with `chatgptplusplan`, IDR billing, and the JP free-trial promo
4. Follows redirects to resolve the final Stripe checkout URL

> **Note:** Billing country (`ID`) and currency (`IDR`) default to Indonesia. Change `billing_details` in the source to use your own country/currency.

## Disclaimer

This tool is for educational purposes only. Use at your own risk. The author is not responsible for any account suspensions, billing issues, or other consequences resulting from its use.
