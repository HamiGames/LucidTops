"""LucidTops UsersOnly standalone console GUI.

Connect / Disconnect / Install against the Frontend *.onion via TorBrowser.
All operational values come from pull_information + secrets at time of operation.
"""

from __future__ import annotations

import importlib.util
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


# Visual palette — LucidTops UsersOnly
BG = "#0D0D0D"
TEXT = "#FFFFFF"
ACCENT_GREEN = "#00FF08"
ACCENT_BLUE = "#00E1FF"
HOVER_PINK = "#F702D7"


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_useronly_{module_name}"
    if registry in sys.modules:
        return sys.modules[registry]
    spec = importlib.util.spec_from_file_location(registry, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[registry] = module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_install = _load_local("install")
_launch = _load_local("LaunchUser")
_secrets = _load_local("user_secrets")


def _neon_button(
    parent: tk.Misc,
    *,
    text: str,
    command: Callable[[], None],
    accent: str,
) -> tk.Button:
    """Flat accent button with vivid pink hover."""
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=accent,
        fg=BG,
        activebackground=HOVER_PINK,
        activeforeground=TEXT,
        disabledforeground=BG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=14,
        pady=10,
        cursor="hand2",
        font=("Segoe UI", 16, "bold"),
    )

    def on_enter(_: tk.Event[Any]) -> None:
        button.configure(bg=HOVER_PINK, fg=TEXT)

    def on_leave(_: tk.Event[Any]) -> None:
        button.configure(bg=accent, fg=BG)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    return button


class UsersOnlyApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LucidTops Remote Desktop")
        self.minsize(520, 340)
        self.configure(bg=BG)
        try:
            self.option_add("*Background", BG)
            self.option_add("*Foreground", TEXT)
        except tk.TclError:
            pass
        self._build()
        self.after(100, self.refresh_status)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG, padx=20, pady=20)
        outer.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        brand = tk.Label(
            outer,
            text="LucidTops Remote Desktop",
            font=("Segoe UI", 35, "bold"),
            bg=BG,
            fg=ACCENT_GREEN,
        )
        brand.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            outer,
            text="Welcome to Lucidtops remote desktop application",
            font=("Segoe UI", 16),
            bg=BG,
            fg=ACCENT_BLUE,
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 14))

        self.status_var = tk.StringVar(value="Pulling console hardware status…")
        status = tk.Label(
            outer,
            textvariable=self.status_var,
            wraplength=480,
            justify="left",
            font=("Segoe UI", 12),
            bg=BG,
            fg=TEXT,
        )
        status.grid(row=2, column=0, sticky="ew", pady=(0, 16))

        detail = tk.Frame(outer, bg=BG)
        detail.grid(row=3, column=0, sticky="ew")
        detail.columnconfigure(1, weight=1)

        self.ip_var = tk.StringVar(value="—")
        self.mac_var = tk.StringVar(value="—")
        self.onion_var = tk.StringVar(value="—")
        self.role_var = tk.StringVar(value="—")
        self.conn_var = tk.StringVar(value="disconnected")

        rows = (
            ("Hardware IP", self.ip_var),
            ("Hardware MAC", self.mac_var),
            ("Frontend Address", self.onion_var),
            ("Role", self.role_var),
            ("Connection", self.conn_var),
        )
        self._value_labels: dict[str, tk.Label] = {}
        for index, (label, variable) in enumerate(rows):
            tk.Label(
                detail,
                text=f"{label}:",
                font=("Segoe UI", 12),
                bg=BG,
                fg=ACCENT_BLUE,
            ).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=3)
            value_label = tk.Label(
                detail,
                textvariable=variable,
                font=("Segoe UI", 12),
                bg=BG,
                fg=TEXT,
            )
            value_label.grid(row=index, column=1, sticky="w", pady=3)
            self._value_labels[label] = value_label

        accent_bar = tk.Frame(outer, bg=ACCENT_GREEN, height=2)
        accent_bar.grid(row=4, column=0, sticky="ew", pady=(18, 0))

        actions = tk.Frame(outer, bg=BG)
        actions.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        for col in range(3):
            actions.columnconfigure(col, weight=1)

        _neon_button(
            actions, text="Install", command=self.on_install, accent=ACCENT_BLUE
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        _neon_button(
            actions, text="Connect", command=self.on_connect, accent=ACCENT_GREEN
        ).grid(row=0, column=1, sticky="ew", padx=6)
        _neon_button(
            actions, text="Disconnect", command=self.on_disconnect, accent=ACCENT_BLUE
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def refresh_status(self) -> None:
        try:
            _secrets.ensure_user_secrets_from_pull()
            status = _launch.connection_status()
            self.ip_var.set(status.get("hardware_ip") or "—")
            self.mac_var.set(status.get("hardware_mac") or "—")
            onion_ok = bool(status.get("frontend_onion_configured"))
            onion_value = _secrets.get_user_secret("FRONTEND_ONION") if onion_ok else ""
            self.onion_var.set(onion_value or "not configured")
            role = status.get("user_role") or "—"
            active = status.get("node_id") or status.get("user_id") or ""
            self.role_var.set(f"{role}" + (f" ({active})" if active else ""))
            connected = bool(status.get("connected"))
            self.conn_var.set("connected" if connected else "disconnected")
            conn_label = self._value_labels.get("Connection")
            if conn_label is not None:
                conn_label.configure(fg=ACCENT_GREEN if connected else TEXT)
            self.status_var.set("Ready.")
        except Exception as exc:  # noqa: BLE001 — surface any pull/secrets failure in UI
            self.status_var.set(f"Status error: {exc}")

    def on_install(self) -> None:
        self.status_var.set("Installing Tor / writing secrets / firewall allowlist…")
        self.update_idletasks()
        try:
            report = _install.install_user_environment()
            self.status_var.set(
                f"Installed at {report.get('installed_at')} — "
                f"Tor={report.get('tor', {}).get('status')} "
                f"firewall={report.get('firewall', {}).get('status')}"
            )
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Install failed: {exc}")
            messagebox.showerror("Install failed", str(exc))

    def on_connect(self) -> None:
        self.status_var.set("Starting Tor and opening Tor Browser…")
        self.update_idletasks()
        try:
            report = _launch.launch_user_session()
            self.status_var.set(
                f"Connected — role={report.get('role') or 'n/a'} url={report.get('url')}"
            )
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Connect failed: {exc}")
            messagebox.showerror("Connect failed", str(exc))

    def on_disconnect(self) -> None:
        self.status_var.set("Disconnecting Tor Browser…")
        self.update_idletasks()
        try:
            report = _launch.disconnect_user_session()
            self.status_var.set(f"Disconnected at {report.get('disconnected_at')}")
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Disconnect failed: {exc}")
            messagebox.showerror("Disconnect failed", str(exc))


def run_gui() -> int:
    app = UsersOnlyApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
