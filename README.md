# OpenAI Promo Bypass

Bypass OpenAI geo promo restrictions via JP proxy — get a $0 checkout URL.

## Important Safety Note

This repository handles OpenAI/ChatGPT session data. A session JSON or access token can let someone act as your account, so treat it like a password.

- Do not commit, upload, or share `session.json`.
- Use a throwaway local copy only, then delete it when finished.
- If you ever shared or committed a session file, sign out of ChatGPT on all devices and rotate/revoke affected sessions before continuing.
- Do not publish proxy credentials in issues, screenshots, logs, or examples.

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

| Flag | Required | Default | Description |
|---|---|---|---|
| `--session-file` | yes | — | Path to file containing `chatgpt.com/api/auth/session` JSON. Use `-` to read from stdin. |
| `--proxy` | yes | — | Japanese HTTP/HTTPS proxy URL |
| `--country` | no | `ID` | Billing country code (must be exactly 2 letters) |
| `--currency` | no | `IDR` | Billing currency code (must be exactly 3 letters) |
| `--verbose` | no | off | Print diagnostic info to stderr |
| `--json` | no | off | Output result as a JSON object (includes `url`, `promo_id`, `checkout_session_id`) |
| `--dry-run` | no | off | Validate inputs and display safe configuration without making network requests |

### JSON output example

```bash
python openai_promo_bypass.py --session-file session.json --proxy ... --json
```

```json
{"url": "https://checkout.stripe.com/...", "promo_id": "...", "checkout_session_id": "..."}
```

### Dry-run example

Validate your configuration safely without making network requests. Tokens and proxy passwords will be heavily sanitized in the output.

```bash
python openai_promo_bypass.py --session-file session.json --proxy http://user:pass@127.0.0.1:8080 --dry-run
```

## How it works

1. Extracts and validates the access token from the session JSON (checks for missing keys and token expiry)
2. Queries OpenAI's account check endpoint through the JP proxy (with automatic retries) to discover eligible promo campaigns
3. Creates a checkout session with `chatgptplusplan`, the configured billing country/currency, and the JP free-trial promo
4. Follows redirects to resolve the final Stripe checkout URL

> **Note:** Billing country and currency default to Indonesia (`ID`/`IDR`). Use `--country` and `--currency` to override.

## Disclaimer

This tool is for educational purposes only. It may violate service terms, billing rules, or regional eligibility requirements. Use at your own risk. The author is not responsible for account suspensions, billing issues, or other consequences resulting from its use.
