import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QTextEdit, QLineEdit, QComboBox, 
    QTabWidget, QFormLayout, QFileDialog, QMessageBox, QGroupBox,
    QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QFont, QColor, QDesktopServices
import subprocess

from src.utils import extract_and_validate_session, parse_proxy_string, check_token_expiry, sanitize_proxy
from src.core import generate_checkout
from src.ssh_tunnel import SSHTunnelThread

# Background Thread for Checkout
class CheckoutThread(QThread):
    result_ready = Signal(bool, str, str, str) # success, url/error, promo, cs_id
    log_msg = Signal(str)
    log_err = Signal(str)   # separate signal for error-level messages → shown in red

    def __init__(self, token, proxy, country, currency):
        super().__init__()
        self.token = token
        self.proxy = proxy
        self.country = country
        self.currency = currency

    def run(self):
        def logger(msg):
            # Route attempt-fail messages to the error signal
            if "failed →" in msg or "Attempt" in msg:
                self.log_err.emit(msg)
            else:
                self.log_msg.emit(msg)
        try:
            success, url, promo, cs_id = generate_checkout(
                self.token, self.proxy, self.country, self.currency,
                logger_callback=logger
            )
            self.result_ready.emit(success, url, promo or "", cs_id or "")
        except Exception as e:
            self.log_err.emit(f"Critical checkout error: {e}")
            self.result_ready.emit(False, str(e), "", "")

class MainWindow(QMainWindow):
    def __init__(self, is_dark_mode=False):
        super().__init__()
        self.setWindowTitle("OpenAI Promo Bypass - GUI")
        self.setMinimumSize(800, 600)
        
        # State
        self.session_token = None
        self._ssh_tunnel: SSHTunnelThread | None = None
        self._ssh_proxy_url: str | None = None
        
        # Theme handling
        self.is_dark_mode = is_dark_mode
        self.color_working = QColor("#55FF55" if is_dark_mode else "green")
        self.color_failed = QColor("#FF6666" if is_dark_mode else "red")
        


        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        self.setup_welcome_screen()
        self.setup_main_form()
        self.setup_result_screen()
        
        # Start at welcome
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        # Gracefully shutdown SSH tunnel if active
        if self._ssh_tunnel and self._ssh_tunnel.isRunning():
            self._ssh_tunnel.stop()
            self._ssh_tunnel.wait(3000)
            self._ssh_tunnel = None

        if hasattr(self, "checkout_thread") and self.checkout_thread.isRunning():
            self.checkout_thread.wait(1000)

        event.accept()

    # --- Setup Screens ---

    def setup_welcome_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("OpenAI Promo Bypass")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        
        desc = QLabel("Safely generate promotional checkout URLs.")
        desc.setFont(QFont("Arial", 12))
        desc.setAlignment(Qt.AlignCenter)
        
        btn_start = QPushButton("Start Process")
        btn_start.setFixedSize(200, 50)
        btn_start.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(30)
        layout.addWidget(btn_start, alignment=Qt.AlignCenter)
        self.stack.addWidget(page)

    def setup_main_form(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # --- Global Browser Selector (visible from all tabs) ---
        browser_bar = QHBoxLayout()
        lbl_browser = QLabel("Preferred Browser:")
        self.combo_browser = QComboBox()
        self.combo_browser.addItems([
            "Default System Browser",
            "Google Chrome",
            "Microsoft Edge",
            "Mozilla Firefox",
            "Brave"
        ])
        self.combo_browser.setFixedWidth(200)
        browser_bar.addWidget(lbl_browser)
        browser_bar.addWidget(self.combo_browser)
        browser_bar.addStretch()
        layout.addLayout(browser_bar)
        # --------------------------------------------------------
        
        self.tabs = QTabWidget()
        
        # Tab 1: Session
        tab_session = QWidget()
        ts_layout = QVBoxLayout(tab_session)
        
        self.text_session = QTextEdit()
        self.text_session.setPlaceholderText("Paste your session JSON here...")
        
        ts_btn_layout = QHBoxLayout()
        btn_load_session = QPushButton("Load from File")
        btn_load_session.clicked.connect(self.load_session_file)
        btn_clear_session = QPushButton("Clear")
        btn_clear_session.clicked.connect(self.clear_session)
        btn_validate_session = QPushButton("Validate Session")
        btn_validate_session.clicked.connect(self.validate_session)
        
        ts_btn_layout.addWidget(btn_load_session)
        ts_btn_layout.addWidget(btn_clear_session)
        ts_btn_layout.addWidget(btn_validate_session)
        
        btn_open_link = QPushButton("Open Auth Session Link")
        btn_open_link.clicked.connect(self.open_auth_link)
        
        lbl_helper = QLabel("Make sure you are logged in to ChatGPT before opening this link.\nThen copy the JSON response and paste it here, or save it as a file and use 'Load from File'.")
        lbl_helper.setStyleSheet("color: gray;")
        
        self.lbl_session_status = QLabel("Status: Waiting for input...")
        
        ts_layout.addWidget(QLabel("Step 1: Session Input"))
        ts_layout.addWidget(lbl_helper)
        ts_layout.addWidget(btn_open_link)
        ts_layout.addWidget(self.text_session)
        ts_layout.addLayout(ts_btn_layout)
        ts_layout.addWidget(self.lbl_session_status)
        
        # Tab 2: Proxy
        tab_proxy = QWidget()
        tp_layout = QVBoxLayout(tab_proxy)
        tp_layout.setAlignment(Qt.AlignTop)
        
        # --- Manual Private Proxy GroupBox ---
        self.manual_group = QGroupBox("Private Proxy")
        manual_layout = QFormLayout()
        self.inp_host = QLineEdit()
        self.inp_host.setPlaceholderText("e.g. proxy.example.com or 1.2.3.4")
        self.inp_port = QLineEdit()
        self.inp_port.setPlaceholderText("e.g. 8080")
        self.inp_user = QLineEdit()
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.Password)
        manual_layout.addRow("Host/IP:", self.inp_host)
        manual_layout.addRow("Port:", self.inp_port)
        manual_layout.addRow("Username:", self.inp_user)
        manual_layout.addRow("Password:", self.inp_pass)
        self.manual_group.setLayout(manual_layout)
        tp_layout.addWidget(self.manual_group)
        
        lbl_or = QLabel("─────────────── OR ───────────────")
        lbl_or.setAlignment(Qt.AlignCenter)
        lbl_or.setStyleSheet("color: gray;")
        tp_layout.addWidget(lbl_or)
        
        # --- SSH Tunnel GroupBox ---
        ssh_group = QGroupBox("SSH Tunnel (SOCKS5)")
        ssh_layout = QFormLayout()
        self.inp_ssh_host = QLineEdit()
        self.inp_ssh_host.setPlaceholderText("e.g. free.sshserver.net")
        self.inp_ssh_port = QLineEdit("22")
        self.inp_ssh_user = QLineEdit()
        self.inp_ssh_pass = QLineEdit()
        self.inp_ssh_pass.setEchoMode(QLineEdit.Password)
        self.inp_ssh_local_port = QLineEdit("1080")
        # Keep a list for easy read-only toggling
        self._ssh_fields = [
            self.inp_ssh_host, self.inp_ssh_port,
            self.inp_ssh_user, self.inp_ssh_pass, self.inp_ssh_local_port
        ]
        ssh_layout.addRow("SSH Host:", self.inp_ssh_host)
        ssh_layout.addRow("SSH Port:", self.inp_ssh_port)
        ssh_layout.addRow("Username:", self.inp_ssh_user)
        ssh_layout.addRow("Password:", self.inp_ssh_pass)
        ssh_layout.addRow("Local SOCKS5 Port:", self.inp_ssh_local_port)
        
        ssh_btn_row = QHBoxLayout()
        self.btn_ssh_connect = QPushButton("Connect")
        self.btn_ssh_connect.clicked.connect(self.toggle_ssh_tunnel)
        self.btn_ssh_clear = QPushButton("Clear All")
        self.btn_ssh_clear.clicked.connect(self.clear_all_proxy_fields)
        self.lbl_ssh_status = QLabel("Disconnected")
        self.lbl_ssh_status.setStyleSheet("color: gray;")
        ssh_btn_row.addWidget(self.btn_ssh_connect)
        ssh_btn_row.addWidget(self.btn_ssh_clear)
        ssh_btn_row.addWidget(self.lbl_ssh_status, 1)
        
        ssh_layout.addRow(ssh_btn_row)
        ssh_group.setLayout(ssh_layout)
        tp_layout.addWidget(ssh_group)

            
        # Tab 3: Settings
        tab_settings = QWidget()
        tset_layout = QVBoxLayout(tab_settings)
        
        form_settings = QFormLayout()
        self.inp_country = QLineEdit("ID")
        self.inp_currency = QLineEdit("IDR")
        
        form_settings.addRow("Country Code (2 chars):", self.inp_country)
        form_settings.addRow("Currency Code (3 chars):", self.inp_currency)
        
        btn_generate = QPushButton("Generate Checkout URL")
        btn_generate.setFixedSize(200, 50)
        btn_generate.clicked.connect(self.start_checkout)
        
        tset_layout.addLayout(form_settings)
        tset_layout.addSpacing(20)
        tset_layout.addWidget(btn_generate, alignment=Qt.AlignCenter)
        tset_layout.addStretch()
        
        self.tabs.addTab(tab_session, "1. Session")
        self.tabs.addTab(tab_proxy, "2. Proxy")
        self.tabs.addTab(tab_settings, "3. Settings")
        
        layout.addWidget(self.tabs)
        self.stack.addWidget(page)

    def setup_result_screen(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        title = QLabel("Process Result")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        
        self.lbl_result_status = QLabel("Generating...")
        
        self.inp_result_url = QLineEdit()
        self.inp_result_url.setReadOnly(True)
        
        btn_copy = QPushButton("Copy to Clipboard")
        btn_copy.clicked.connect(self.copy_result)
        
        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        
        # Styling the log panel for dark/light mode
        if self.is_dark_mode:
            self.log_panel.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: monospace;")
        else:
            self.log_panel.setStyleSheet("background-color: #f0f0f0; color: #000000; font-family: monospace;")
        
        btn_back = QPushButton("New Process / Back")
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        
        layout.addWidget(title)
        layout.addWidget(self.lbl_result_status)
        layout.addWidget(QLabel("Checkout URL:"))
        
        url_layout = QHBoxLayout()
        url_layout.addWidget(self.inp_result_url)
        url_layout.addWidget(btn_copy)
        
        btn_open_result = QPushButton("Open in Browser")
        btn_open_result.clicked.connect(lambda: self.open_url_custom_browser(self.inp_result_url.text()))
        url_layout.addWidget(btn_open_result)
        
        layout.addLayout(url_layout)
        
        layout.addWidget(QLabel("Process Logs:"))
        layout.addWidget(self.log_panel)
        layout.addWidget(btn_back)
        
        self.stack.addWidget(page)

    # --- Logic Methods ---

    def log_gui(self, msg):
        self.log_panel.append(msg)

    def log_gui_error(self, msg):
        """Append a red-colored error line to the log panel."""
        self.log_panel.append(f'<span style="color:#FF6666;">{msg}</span>')

    def open_url_custom_browser(self, url):
        if not url or "http" not in url:
            return
            
        browser_name = self.combo_browser.currentText()
        if browser_name == "Default System Browser":
            QDesktopServices.openUrl(QUrl(url))
            return
            
        paths = {
            "Google Chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
            "Microsoft Edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
            "Mozilla Firefox": [r"C:\Program Files\Mozilla Firefox\firefox.exe", r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
            "Brave": [r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"]
        }
        
        if browser_name in paths:
            for p in paths[browser_name]:
                if os.path.exists(p):
                    subprocess.Popen([p, url])
                    return
        
        # Fallback if path not found
        QDesktopServices.openUrl(QUrl(url))

    def open_auth_link(self):
        self.open_url_custom_browser("https://chatgpt.com/api/auth/session")

    def load_session_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Session JSON", "", "JSON Files (*.json);;All Files (*)")
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    self.text_session.setReadOnly(False)
                    self.text_session.setText(f.read())
                self.validate_session()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read file:\n{e}")

    def validate_session(self):
        raw = self.text_session.toPlainText()
        valid, result = extract_and_validate_session(raw)
        
        if valid:
            self.session_token = result
            self.text_session.setReadOnly(True)
            exp_ok, exp_msg = check_token_expiry(self.session_token)
            if not exp_ok:
                self.lbl_session_status.setText(f"Status: Valid Token (Warning: {exp_msg})")
                self.lbl_session_status.setStyleSheet("color: orange;")
            else:
                self.lbl_session_status.setText("Status: ✓ Valid Token")
                self.lbl_session_status.setStyleSheet(f"color: {self.color_working.name()};")
            return True
        else:
            self.session_token = None
            self.text_session.setReadOnly(False)
            self.lbl_session_status.setText(f"Status: ✗ Invalid ({result})")
            self.lbl_session_status.setStyleSheet(f"color: {self.color_failed.name()};")
            return False

    def clear_session(self):
        self.text_session.clear()
        self.session_token = None
        self.text_session.setReadOnly(False)
        self.lbl_session_status.setText("Status: Waiting for input...")
        self.lbl_session_status.setStyleSheet("color: gray;")




    def _get_manual_proxy_str(self):
        host = self.inp_host.text().strip()
        if host:
            port = self.inp_port.text().strip()
            user = self.inp_user.text().strip()
            pwd  = self.inp_pass.text().strip()
            p_str = f"{host}:{port}" if port else host
            if user or pwd:
                p_str = f"{user}:{pwd}@{p_str}"
            return p_str
        return None

    def get_current_proxy(self):
        # Priority 1: active SSH tunnel (if connected)
        if self._ssh_proxy_url:
            return self._ssh_proxy_url
        
        # Priority 2: manual private proxy
        p_str = self._get_manual_proxy_str()
        if p_str:
            return parse_proxy_string(p_str)
        return None

    def toggle_ssh_tunnel(self):
        if self._ssh_tunnel and self._ssh_tunnel.isRunning():
            # Disconnect
            self._ssh_tunnel.stop()
            self._ssh_tunnel.wait(3000)
            self._ssh_tunnel = None
            self._ssh_proxy_url = None
            self.btn_ssh_connect.setText("Connect")
            self.lbl_ssh_status.setText("Disconnected")
            self.lbl_ssh_status.setStyleSheet("color: gray;")
            self._set_ssh_readonly(False)
            return

        host = self.inp_ssh_host.text().strip()
        user = self.inp_ssh_user.text().strip()
        pwd  = self.inp_ssh_pass.text().strip()
        if not host or not user:
            QMessageBox.critical(self, "SSH Error", "SSH Host and Username are required.")
            return

        try:
            ssh_port   = int(self.inp_ssh_port.text().strip() or "22")
            local_port = int(self.inp_ssh_local_port.text().strip() or "1080")
        except ValueError:
            QMessageBox.critical(self, "SSH Error", "SSH Port and Local Port must be numbers.")
            return

        self.btn_ssh_connect.setText("Connecting…")
        self.btn_ssh_connect.setEnabled(False)
        self.lbl_ssh_status.setText("Connecting…")
        self.lbl_ssh_status.setStyleSheet("color: orange;")
        self._set_ssh_readonly(True)

        self._ssh_tunnel = SSHTunnelThread(host, ssh_port, user, pwd, local_port=local_port)
        self._ssh_tunnel.connected.connect(self.on_ssh_connected)
        self._ssh_tunnel.disconnected.connect(self.on_ssh_disconnected)
        self._ssh_tunnel.error.connect(self.on_ssh_error)
        self._ssh_tunnel.log_msg.connect(self.log_gui)
        self._ssh_tunnel.start()

    def _set_ssh_readonly(self, readonly: bool):
        for field in self._ssh_fields:
            field.setReadOnly(readonly)
        self.manual_group.setEnabled(not readonly)

    def clear_all_proxy_fields(self):
        """Disconnect if active, then clear all Proxy and SSH fields."""
        if self._ssh_tunnel and self._ssh_tunnel.isRunning():
            self._ssh_tunnel.stop()
            self._ssh_tunnel.wait(3000)
            self._ssh_tunnel = None
            self._ssh_proxy_url = None
            
        # Clear SSH fields
        for field in self._ssh_fields:
            field.setReadOnly(False)
            field.clear()
        
        # Clear Private Proxy fields
        self.inp_host.clear()
        self.inp_port.clear()
        self.inp_user.clear()
        self.inp_pass.clear()
        self.inp_ssh_port.setText("22")
        self.inp_ssh_local_port.setText("1080")
        self.btn_ssh_connect.setText("Connect")
        self.btn_ssh_connect.setEnabled(True)
        self.lbl_ssh_status.setText("Disconnected")
        self.lbl_ssh_status.setStyleSheet("color: gray;")

    def on_ssh_connected(self, proxy_url: str, ping_ms: int, public_ip: str):
        self._ssh_proxy_url = proxy_url
        self.btn_ssh_connect.setText("Disconnect")
        self.btn_ssh_connect.setEnabled(True)
        ping_str = f"  |  Ping: {ping_ms}ms" if ping_ms >= 0 else ""
        ip_str = f"  |  IP: {public_ip}" if public_ip and public_ip != "Unknown IP" else ""
        self.lbl_ssh_status.setText(f"✓ Connected{ping_str}{ip_str}")
        self.lbl_ssh_status.setStyleSheet(f"color: {self.color_working.name()}; font-weight: bold;")
        self.log_gui(f"[SSH] Tunnel active → {proxy_url}{ping_str}{ip_str}")

    def on_ssh_disconnected(self):
        self._ssh_proxy_url = None
        self.btn_ssh_connect.setText("Connect")
        self.btn_ssh_connect.setEnabled(True)
        self.lbl_ssh_status.setText("Disconnected")
        self.lbl_ssh_status.setStyleSheet("color: gray;")
        self._set_ssh_readonly(False)

    def on_ssh_error(self, msg: str):
        self._ssh_proxy_url = None
        self.btn_ssh_connect.setText("Connect")
        self.btn_ssh_connect.setEnabled(True)
        self.lbl_ssh_status.setText("✗ Error")
        self.lbl_ssh_status.setStyleSheet(f"color: {self.color_failed.name()};")
        self._set_ssh_readonly(False)
        QMessageBox.critical(self, "SSH Tunnel Error", msg)

    def start_checkout(self):
        # Validate inputs
        if not self.validate_session():
            QMessageBox.critical(self, "Error", "Invalid session. Please validate session first.")
            self.tabs.setCurrentIndex(0)
            return

        # Proxy check & collision handling
        ssh_active = self._ssh_proxy_url is not None
        manual_active = self._get_manual_proxy_str() is not None

        if ssh_active and manual_active:
            msg = QMessageBox(self)
            msg.setWindowTitle("Multiple Proxies Configured")
            msg.setText("Both Private Proxy and SSH Tunnel are configured.\nWhich one do you want to use?")
            btn_ssh = msg.addButton("Use SSH Tunnel", QMessageBox.AcceptRole)
            btn_proxy = msg.addButton("Use Private Proxy", QMessageBox.RejectRole)
            msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec()
            
            if msg.clickedButton() == btn_ssh:
                proxy = self._ssh_proxy_url
            elif msg.clickedButton() == btn_proxy:
                proxy = parse_proxy_string(self._get_manual_proxy_str())
            else:
                return
        else:
            proxy = self.get_current_proxy()

        if not proxy:
            QMessageBox.critical(self, "Error", "No proxy provided.")
            self.tabs.setCurrentIndex(1)
            return

        country = self.inp_country.text().strip()
        currency = self.inp_currency.text().strip()

        if len(country) != 2:
            QMessageBox.critical(self, "Error", "Country code must be exactly 2 letters.")
            return
        if len(currency) != 3:
            QMessageBox.critical(self, "Error", "Currency code must be exactly 3 letters.")
            return

        # Prepare Result UI
        self.inp_result_url.clear()
        self.log_panel.clear()
        self.lbl_result_status.setText("Processing Checkout...")
        self.lbl_result_status.setStyleSheet("color: blue;")
        self.stack.setCurrentIndex(2) # Go to result screen
        
        self.log_gui(f"Starting process for Country: {country}, Currency: {currency}")
        self.log_gui(f"Proxy: {sanitize_proxy(proxy)}")

        # Start Thread
        self.checkout_thread = CheckoutThread(self.session_token, proxy, country, currency)
        self.checkout_thread.result_ready.connect(self.on_checkout_complete)
        self.checkout_thread.log_msg.connect(self.log_gui)
        self.checkout_thread.log_err.connect(self.log_gui_error)
        self.checkout_thread.start()

    def on_checkout_complete(self, success, url_or_err, promo, cs_id):
        if success:
            self.lbl_result_status.setText("✓ Success!")
            self.lbl_result_status.setStyleSheet(f"color: {self.color_working.name()}; font-weight: bold;")
            self.inp_result_url.setText(url_or_err)
            self.log_gui(f"\n--- SUCCESS ---\nPromo ID: {promo}\nSession ID: {cs_id}")
        else:
            self.lbl_result_status.setText("✗ Failed")
            self.lbl_result_status.setStyleSheet(f"color: {self.color_failed.name()}; font-weight: bold;")
            self.inp_result_url.setText("Error generating checkout URL.")
            self.log_gui(f"\n--- ERROR ---\n{url_or_err}")

    def copy_result(self):
        url = self.inp_result_url.text()
        if url and "Error" not in url:
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            QMessageBox.information(self, "Copied", "URL copied to clipboard!")
