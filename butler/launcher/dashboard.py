"""Start (if needed) and open the read-only debug console from the launcher.

The console is independent of the Butler stack: it only reads logs and
databases, so it is useful before Start, after Stop, and while running. It is
therefore owned by the launcher window rather than the Supervisor, and a
console someone already started by hand is reused instead of duplicated.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from typing import Callable, Optional

from .config import REPO_ROOT, get_active_setting, get_setting, venv_python, venv_setup_hint

LogFn = Callable[[str, str], None]

# The launcher always probes and opens the console over loopback; what other
# machines can reach is decided by the bind address in settings.env.
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8787
DASHBOARD_URL = f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"
STARTUP_TIMEOUT_SECONDS = 15.0
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_ALL_INTERFACES = "0.0.0.0"


def _bind_host() -> str:
    return get_setting("BUTLER_DEBUG_DASHBOARD_HOST", DASHBOARD_HOST).strip() or DASHBOARD_HOST


def _local_host(bind_host: str) -> str:
    """Address this machine uses to reach a console bound to ``bind_host``."""
    if bind_host in _LOOPBACK_HOSTS or bind_host == _ALL_INTERFACES:
        return DASHBOARD_HOST
    return bind_host


def _primary_lan_ip() -> str | None:
    # Connecting a UDP socket sends nothing; it only asks the OS which local
    # address the default route would use.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith(("127.", "0.")) else address


def network_urls(bind_host: str | None = None) -> list[str]:
    """URLs other machines can use, best first: the vanity link, then the LAN address."""
    bind_host = _bind_host() if bind_host is None else bind_host
    if bind_host in _LOOPBACK_HOSTS:
        return []
    urls: list[str] = []
    link = get_active_setting("BUTLER_DEBUG_DASHBOARD_LINK")
    if link:
        urls.append(link)
    address = _primary_lan_ip() if bind_host == _ALL_INTERFACES else bind_host
    if address:
        urls.append(f"http://{address}:{DASHBOARD_PORT}")
    return urls


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class DashboardProcess:
    """The debug console child process this launcher started, if any."""

    def __init__(self, log: LogFn) -> None:
        self._log = log
        self._popen: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def ensure_running(self) -> str:
        """Return the console URL once it accepts connections.

        Raises ``RuntimeError`` with an operator-readable reason otherwise.
        """
        bind_host = _bind_host()
        local_host = _local_host(bind_host)
        url = f"http://{local_host}:{DASHBOARD_PORT}"
        with self._lock:
            if _port_open(local_host, DASHBOARD_PORT):
                self._log_network_urls(bind_host)
                return url
            if self._popen is None or self._popen.poll() is not None:
                self._popen = self._spawn(bind_host)
            popen = self._popen
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if popen.poll() is not None:
                raise RuntimeError(
                    f"debug console exited with code {popen.returncode}; see the Logs tab"
                )
            if _port_open(local_host, DASHBOARD_PORT):
                self._log_network_urls(bind_host)
                return url
            time.sleep(0.2)
        raise RuntimeError(
            f"debug console did not open {url} within {int(STARTUP_TIMEOUT_SECONDS)}s"
        )

    def start_if_shared(self) -> bool:
        """Start the console in the background when it is bound beyond loopback.

        Other devices can't press the launcher's button, so a network-shared
        console has to be up as soon as the launcher is. Returns whether a
        start was attempted.
        """
        if _bind_host() in _LOOPBACK_HOSTS:
            return False

        def worker() -> None:
            try:
                self.ensure_running()
            except RuntimeError as exc:
                self._log("dashboard", f"network start failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _log_network_urls(self, bind_host: str) -> None:
        for network_url in network_urls(bind_host):
            self._log("dashboard", f"on your network: {network_url}")

    def _spawn(self, bind_host: str) -> subprocess.Popen:
        python = venv_python("main")
        args = [
            str(python), "-m", "butler.debug_dashboard",
            "--host", bind_host, "--port", str(DASHBOARD_PORT),
        ]
        if bind_host not in _LOOPBACK_HOSTS:
            # The server refuses a network bind without this acknowledgement;
            # choosing a non-loopback host in settings.env is that choice.
            args.append("--allow-remote")
        self._log("dashboard", f"starting debug console: {' '.join(args)}")
        env = dict(os.environ)
        env["BUTLER_PROCESS_NAME"] = "dashboard"
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            popen = subprocess.Popen(
                args,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            hint = venv_setup_hint("main")
            raise RuntimeError(
                f"cannot start the debug console: {python} not found"
                + (f"; {hint}" if hint else "")
            ) from exc
        threading.Thread(target=self._pump, args=(popen,), daemon=True).start()
        return popen

    def _pump(self, popen: subprocess.Popen) -> None:
        assert popen.stdout is not None
        for line in popen.stdout:
            self._log("dashboard", line.rstrip("\n"))

    def stop(self) -> None:
        """Stop the console only if this launcher started it."""
        with self._lock:
            popen, self._popen = self._popen, None
        if popen is None or popen.poll() is not None:
            return
        popen.terminate()
        try:
            popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            popen.kill()
