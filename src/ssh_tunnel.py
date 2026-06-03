"""
SSH Tunnel via SOCKS5 — Pure Python implementation.

Uses paramiko for SSH authentication (supports password & key).
Implements a minimal SOCKS5 server locally that proxies all connections
through the SSH channel (equivalent to ssh -D).

Usage:
    tunnel = SSHTunnelThread("ssh.example.com", 22, "user", "pass")
    tunnel.connected.connect(lambda url: print(f"Proxy: {url}"))
    tunnel.start()
    ...
    tunnel.stop(); tunnel.wait()
"""

import socket
import select
import struct
import threading

import paramiko
import logging

# Suppress noisy paramiko network exception logs on exit
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

from PySide6.QtCore import QThread, Signal


class SSHTunnelThread(QThread):
    """QThread that establishes an SSH connection and exposes a local SOCKS5 proxy."""

    connected    = Signal(str, int, str)  # proxy_url, ping_ms (-1 = unknown), public_ip
    disconnected = Signal()
    error        = Signal(str)
    log_msg      = Signal(str)

    def __init__(self, host: str, ssh_port: int, username: str,
                 password: str = "", key_path: str = "", local_port: int = 1080):
        super().__init__()
        self.host       = host
        self.ssh_port   = ssh_port
        self.username   = username
        self.password   = password
        self.key_path   = key_path
        self.local_port = local_port

        self._running = False
        self._ssh: paramiko.SSHClient | None = None
        self._server: socket.socket | None = None

    # ------------------------------------------------------------------ #

    def run(self):
        try:
            self.log_msg.emit(f"[SSH] Connecting to {self.username}@{self.host}:{self.ssh_port} …")
            self._ssh = paramiko.SSHClient()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = dict(
                hostname=self.host,
                port=self.ssh_port,
                username=self.username,
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
            )
            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
            else:
                connect_kwargs["password"] = self.password

            self._ssh.connect(**connect_kwargs)
            transport = self._ssh.get_transport()
            self.log_msg.emit("[SSH] Authenticated. Starting local SOCKS5 proxy …")

            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind(("127.0.0.1", self.local_port))
            self._server.listen(50)
            self._running = True

            proxy_url = f"socks5://127.0.0.1:{self.local_port}"
            self.log_msg.emit(f"[SSH] SOCKS5 proxy ready → {proxy_url}")
            
            # Measure ping via SSH channel (TCP connect time to google.com:80)
            ping_ms = -1
            try:
                import time as _time
                t0 = _time.monotonic()
                ch = transport.open_channel("direct-tcpip", ("google.com", 80), ("127.0.0.1", 0))
                ping_ms = int((_time.monotonic() - t0) * 1000)
                ch.close()
                self.log_msg.emit(f"[SSH] Ping via tunnel: {ping_ms}ms")
            except Exception:
                pass
            
            # Fetch public IP via SSH channel
            public_ip = "Unknown IP"
            try:
                ch_ip = transport.open_channel("direct-tcpip", ("api.ipify.org", 80), ("127.0.0.1", 0))
                ch_ip.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
                resp = b""
                while True:
                    data = ch_ip.recv(1024)
                    if not data:
                        break
                    resp += data
                ch_ip.close()
                resp_str = resp.decode(errors="ignore")
                if "\r\n\r\n" in resp_str:
                    public_ip = resp_str.split("\r\n\r\n")[1].strip()
                self.log_msg.emit(f"[SSH] Public IP: {public_ip}")
            except Exception:
                pass
            
            self.connected.emit(proxy_url, ping_ms, public_ip)

            self._server.settimeout(1.0)
            while self._running:
                try:
                    client_sock, _ = self._server.accept()
                    t = threading.Thread(
                        target=_handle_socks5,
                        args=(client_sock, transport),
                        daemon=True,
                    )
                    t.start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        except Exception as exc:
            self.error.emit(f"SSH tunnel error: {exc}")
        finally:
            self._cleanup()
            self.disconnected.emit()

    def stop(self):
        """Stop the tunnel gracefully."""
        self._running = False
        self._cleanup()

    def _cleanup(self):
        for attr in ("_server", "_ssh"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)


# ------------------------------------------------------------------ #
#  SOCKS5 handler (runs in a daemon thread per connection)
# ------------------------------------------------------------------ #

def _handle_socks5(client_sock: socket.socket, transport: paramiko.Transport):
    channel = None
    try:
        # ── Greeting ──────────────────────────────────────────────
        header = _recv_exact(client_sock, 2)
        if not header or header[0] != 0x05:
            return
        nmethods = header[1]
        _recv_exact(client_sock, nmethods)          # discard methods
        client_sock.sendall(b"\x05\x00")            # no-auth

        # ── Request ───────────────────────────────────────────────
        req = _recv_exact(client_sock, 4)
        if not req or req[0] != 0x05 or req[1] != 0x01:   # only CONNECT
            client_sock.sendall(b"\x05\x07\x00\x01" + b"\x00" * 6)
            return

        atyp = req[3]
        if atyp == 0x01:        # IPv4
            raw = _recv_exact(client_sock, 4)
            addr = socket.inet_ntoa(raw)
        elif atyp == 0x03:      # Domain
            length = _recv_exact(client_sock, 1)[0]
            addr = _recv_exact(client_sock, length).decode()
        elif atyp == 0x04:      # IPv6
            addr = socket.inet_ntop(socket.AF_INET6, _recv_exact(client_sock, 16))
        else:
            client_sock.sendall(b"\x05\x08\x00\x01" + b"\x00" * 6)
            return

        port_bytes = _recv_exact(client_sock, 2)
        port = struct.unpack(">H", port_bytes)[0]

        # ── Open SSH channel ──────────────────────────────────────
        try:
            channel = transport.open_channel(
                "direct-tcpip", (addr, port), ("127.0.0.1", 0)
            )
        except Exception:
            client_sock.sendall(b"\x05\x05\x00\x01" + b"\x00" * 6)
            return

        # ── Success reply ─────────────────────────────────────────
        client_sock.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")

        # ── Bidirectional relay ───────────────────────────────────
        while True:
            r, _, _ = select.select([client_sock, channel], [], [], 60)
            if not r:
                break
            if client_sock in r:
                data = client_sock.recv(65536)
                if not data:
                    break
                channel.sendall(data)
            if channel in r:
                data = channel.recv(65536)
                if not data:
                    break
                client_sock.sendall(data)

    except Exception:
        pass
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
        try:
            if channel:
                channel.close()
        except Exception:
            pass


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Receive exactly *n* bytes. Returns None on connection close."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf
