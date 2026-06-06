# OpenAI Promo Bypass (GUI)

An incredibly easy-to-use desktop application (GUI) to bypass regional restrictions for OpenAI/ChatGPT Promos. Designed to be highly beginner-friendly—no complicated terminal commands required.

## Key Features
- 🖥️ **Visual Interface (GUI):** A simple point-and-click interface.
- 🔒 **Built-in SSH Tunnel:** No need to buy expensive Private Proxies. Just use a free SSH account (from fastssh, vpnjantit, etc.), and the app will automatically create a local SOCKS5 proxy for you.
- 🌐 **Auto-Open Browser:** Once the URL is generated, click one button to open it in your preferred browser (Edge, Firefox, Brave, etc.).
- 🛡️ **Safe & Clean Logs:** Passwords and sensitive session tokens are strictly hidden and scrubbed from error logs.

---

## 📥 Download (Easiest Method)

You do not need to install Python. Simply download the ready-to-use `.exe` file from the **[Releases](https://github.com/username/openai-promo-bypass/releases/latest)** page, extract it, and double-click `OpenAI Promo Bypass.exe` to start.

---

## 🛠️ Installation from Source (For Developers)

1. Make sure **Python** (version 3.9 or higher) is installed on your computer.
2. Download this repository, extract it, and open a terminal (Command Prompt / PowerShell) inside the folder.
3. Install the required dependencies by running this command:
   ```bash
   pip install -r requirements.txt
   ```

---

## How to Use

If you downloaded the release, simply double-click **`OpenAI Promo Bypass.exe`**.
If you are running from source, use the following command:
```bash
python main.py
```

Once the application opens, follow these 3 simple steps:

### 1. "Session" Tab (Required)
This is the "key" to your ChatGPT account.
- Click the **"Open Auth Session Link"** button. Your browser will open.
- *(Important: Ensure you are already **logged in** to ChatGPT in that browser).*
- A long block of text (JSON) will appear. Copy **all** of that text.
- Paste it into the large text box in the application, then click **"Validate Session"**. If the status turns green ("Valid"), proceed to the next tab!

### 2. "Proxy" Tab (Choose One)
Since promos are region-restricted (usually Japan), you need to route your connection through an IP from that country.

**Option A: SSH Tunnel (Highly Recommended, Free & Easy)**
- Create a free Japanese SSH server account on websites like *vpnjantit.com*, *fastssh.com*, etc.
- Enter the **SSH Host** (e.g., *premijp1.vpnjantit.com*).
- Enter your SSH **Username** and **Password**.
- Click **"Connect"**. Wait until the status changes to *✓ Connected* (you will see the Ping & IP info).

**Option B: Private Proxy (If you have a paid Proxy)**
- Enter your Host/IP, Port, Username, and Password for your private proxy.

### 3. "Settings" Tab
- **Preferred Browser:** (Located at the top of the window) Choose which browser you want to use to open the final checkout link (using a different clean browser or incognito mode is highly recommended).
- **Country & Currency:** Leave the defaults (ID & IDR) to display the price in Indonesian Rupiah.
- Click **"Generate Checkout URL"**.
- Done! The Checkout URL will appear on your screen. Click "Open in Browser" to proceed with the payment.

---

## Security Warning

1. **Keep Your Session JSON Secret:** The JSON text from Step 1 gives full access to your ChatGPT account. **Never** share screenshots containing that text with anyone!
2. If your session is accidentally leaked, immediately go to your ChatGPT account settings and click *Sign Out All Devices*.
3. This application is for educational purposes only. Any risks associated with using this tool are entirely the user's responsibility.
