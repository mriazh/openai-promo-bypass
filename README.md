# OpenAI Promo Bypass

An educational tool to observe and analyze regional checkout flow variations using a localized proxy.

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

**💡 Pro Tip:** We highly recommend running a safe test first using the `--dry-run` flag (see examples below). This ensures your setup is correct without making any actual network requests.

Export your OpenAI session JSON from `chatgpt.com/api/auth/session` to a file, then:

```bash
python openai_promo_bypass.py \
  --session-file session.json \
  --proxy http://user:pass@jp-host:3128
```

Prints the generated checkout URL to stdout.

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

### Dry-run examples (Windows Beginner Friendly)

The `--dry-run` flag lets you validate your configuration safely **without making any network requests**. Your proxy credentials and tokens will be heavily sanitized in the output to prevent leaks.
- `--country` must be exactly 2 letters.
- `--currency` must be exactly 3 letters.

#### PowerShell Example
*Note: The `@' ... '@` heredoc syntax is specific to PowerShell and will not work in Command Prompt (CMD).*

```powershell
@'
{"accessToken":"header.payload.signature"}
'@ | python .\openai_promo_bypass.py --session-file - --proxy http://user:pass@127.0.0.1:8080 --dry-run
```

#### Command Prompt (CMD) Example
In CMD, you can create a temporary `test.json` file, run the validation, and then delete it.

```cmd
echo {"accessToken":"header.payload.signature"} > test.json
python openai_promo_bypass.py --session-file test.json --proxy http://user:pass@127.0.0.1:8080 --dry-run
del test.json
```

**Expected Safe Output:**
```text
--- DRY RUN ---
Proxy    : http://***@127.0.0.1:8080
Token    : <VALID_TOKEN_HIDDEN>
Country  : ID
Currency : IDR
All inputs validated successfully. No network requests were made.
```

## How it works (The Simple Version)

1. **Reads your Session:** The script safely reads your session file to find your access token, checking to make sure it hasn't expired.
2. **Checks Promos:** It uses the Japanese proxy you provided to check if your account is eligible for the free trial promo.
3. **Generates a Checkout Link:** It communicates with the API to generate a regional checkout link based on your chosen country/currency.
4. **Resolves the URL:** It follows the generated link to discover the final localized payment page.

> **Note:** Billing country and currency default to Indonesia (`ID`/`IDR`). Use `--country` and `--currency` to override.

## Disclaimer

This tool is for educational purposes only. It may violate service terms, billing rules, or regional eligibility requirements. Use at your own risk. The author is not responsible for account suspensions, billing issues, or other consequences resulting from its use.
