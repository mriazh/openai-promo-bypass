# OpenAI Promo Analysis (GUI)

An educational PySide6 GUI application to observe and analyze regional checkout flow variations using a localized proxy.

## Important Safety Note

This repository handles OpenAI/ChatGPT session data. A session JSON or access token can let someone act as your account, so treat it like a password.

- Do not commit, upload, or share `session.json`.
- Use a throwaway local copy only, then delete it when finished.
- If you ever shared or committed a session file, sign out of ChatGPT on all devices and rotate/revoke affected sessions before continuing.
- Do not publish proxy credentials in issues, screenshots, logs, or examples.

## Install

Install the required dependencies via `pip`:

```bash
pip install -r requirements.txt
```

## Usage

Start the GUI application:

```bash
python main.py
```

### GUI Workflow

1. **Welcome Screen:** Click "Start Process" to begin.
2. **Session Tab:** Paste your session JSON data into the text box (or load from file) and click "Validate Session". The application will extract and verify your token securely.
3. **Proxy Tab:** Select a proxy from the dropdown (loaded from `src/proxies.txt` by default) or enter one manually. Click "Test Selected Proxy" to ping Google and Baidu through the proxy.
4. **Settings Tab:** Enter the desired 2-letter Country code and 3-letter Currency code. Click "Generate Checkout URL".
5. **Result Screen:** The final generated Stripe checkout URL will be displayed. You can easily copy it to your clipboard.

## How it works (The Simple Version)

1. **Reads your Session:** The script safely reads your session to find your access token, checking to make sure it hasn't expired.
2. **Checks Promos:** It uses the Japanese proxy you provided to check if your account is eligible for the free trial promo.
3. **Generates a Checkout Link:** It communicates with the API to generate a regional checkout link based on your chosen country/currency.
4. **Resolves the URL:** It follows the generated link to discover the final localized payment page.

> **Note:** Billing country and currency default to Indonesia (`ID`/`IDR`). You can change this in the Settings tab.

## Troubleshooting & Logs

All runtime errors and network issues are safely logged to `logs/error.log` with timestamps. Passwords and tokens are scrubbed from these logs. If the proxy test fails or the URL generation fails, please check the log file or the GUI log panel for details.

## Disclaimer

This tool is for educational purposes only. It may violate service terms, billing rules, or regional eligibility requirements. Use at your own risk. The author is not responsible for account suspensions, billing issues, or other consequences resulting from its use.
