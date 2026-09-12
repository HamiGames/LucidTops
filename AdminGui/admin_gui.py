"""LucidTops AdminGui standalone console GUI.

Authenticate / Connect / Disconnect against the Frontend AdminHome *.onion via TorBrowser.
Optional Linux CLI when co-located with MasterServer.
All operational values come from pull_information + secrets at time of operation.
No installer (AdminGui restrictions).
"""

from __future__ import annotations

import importlib.util
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext
from typing import Any, Callable

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


# Visual palette — LucidTops UsersOnly / AdminGui (same color pallet as user_gui.py)
BG = "#0D0D0D"
TEXT = "#FFFFFF"
ACCENT_GREEN = "#00FF08"
ACCENT_BLUE = "#00E1FF"
HOVER_PINK = "#F702D7"


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_admingui_{module_name}"
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


_launch = _load_local("LaunchAdmin")
_secrets = _load_local("admin_secrets")
_download_auth = _load_local("download_auth")
_admin_cli = _load_local("admin_cli")


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


class AdminGuiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LucidTops AdminGui")
        self.minsize(560, 480)
        self.configure(bg=BG)
        try:
            self.option_add("*Background", BG)
            self.option_add("*Foreground", TEXT)
        except tk.TclError:
            pass
        self._cli_session = _admin_cli.AdminCliSession()
        self._build()
        self.after(100, self.refresh_status)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG, padx=20, pady=20)
        outer.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(8, weight=1)

        brand = tk.Label(
            outer,
            text="LucidTops AdminGui",
            font=("Segoe UI", 35, "bold"),
            bg=BG,
            fg=ACCENT_GREEN,
        )
        brand.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            outer,
            text="AdminID console — connect to Frontend AdminHome via Tor",
            font=("Segoe UI", 16),
            bg=BG,
            fg=ACCENT_BLUE,
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 14))

        self.status_var = tk.StringVar(value="Pulling console hardware status…")
        status = tk.Label(
            outer,
            textvariable=self.status_var,
            wraplength=520,
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
        self.admin_var = tk.StringVar(value="—")
        self.auth_var = tk.StringVar(value="unverified")
        self.conn_var = tk.StringVar(value="disconnected")
        self.cli_var = tk.StringVar(value="—")

        rows = (
            ("Hardware IP", self.ip_var),
            ("Hardware MAC", self.mac_var),
            ("Frontend Address", self.onion_var),
            ("AdminID", self.admin_var),
            ("Download Auth", self.auth_var),
            ("Connection", self.conn_var),
            ("MasterServer CLI", self.cli_var),
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

        auth_row = tk.Frame(outer, bg=BG)
        auth_row.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        auth_row.columnconfigure(1, weight=1)
        tk.Label(
            auth_row,
            text="Auth code:",
            font=("Segoe UI", 12),
            bg=BG,
            fg=ACCENT_BLUE,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.code_entry = tk.Entry(
            auth_row,
            font=("Segoe UI", 14),
            bg="#1A1A1A",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
        )
        self.code_entry.grid(row=0, column=1, sticky="ew")

        accent_bar = tk.Frame(outer, bg=ACCENT_GREEN, height=2)
        accent_bar.grid(row=5, column=0, sticky="ew", pady=(18, 0))

        actions = tk.Frame(outer, bg=BG)
        actions.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        for col in range(4):
            actions.columnconfigure(col, weight=1)

        _neon_button(
            actions, text="Send Code", command=self.on_send_code, accent=ACCENT_BLUE
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        _neon_button(
            actions, text="Authenticate", command=self.on_authenticate, accent=ACCENT_BLUE
        ).grid(row=0, column=1, sticky="ew", padx=6)
        _neon_button(
            actions, text="Connect", command=self.on_connect, accent=ACCENT_GREEN
        ).grid(row=0, column=2, sticky="ew", padx=6)
        _neon_button(
            actions, text="Disconnect", command=self.on_disconnect, accent=ACCENT_BLUE
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        cli_frame = tk.Frame(outer, bg=BG)
        cli_frame.grid(row=7, column=0, sticky="ew", pady=(16, 0))
        cli_frame.columnconfigure(0, weight=1)
        tk.Label(
            cli_frame,
            text="Linux CLI (co-located MasterServer only)",
            font=("Segoe UI", 12),
            bg=BG,
            fg=ACCENT_BLUE,
        ).grid(row=0, column=0, sticky="w")
        self.cli_entry = tk.Entry(
            cli_frame,
            font=("Segoe UI", 12),
            bg="#1A1A1A",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
        )
        self.cli_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.cli_entry.bind("<Return>", lambda _e: self.on_cli_run())
        _neon_button(
            cli_frame, text="Run CLI", command=self.on_cli_run, accent=ACCENT_GREEN
        ).grid(row=1, column=1, sticky="e", padx=(8, 0))

        self.cli_out = scrolledtext.ScrolledText(
            outer,
            height=8,
            font=("Consolas", 11),
            bg="#1A1A1A",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
        )
        self.cli_out.grid(row=8, column=0, sticky="nsew", pady=(10, 0))
        self.cli_out.configure(state="disabled")

    def _append_cli(self, text: str) -> None:
        self.cli_out.configure(state="normal")
        self.cli_out.insert("end", text)
        if not text.endswith("\n"):
            self.cli_out.insert("end", "\n")
        self.cli_out.see("end")
        self.cli_out.configure(state="disabled")

    def refresh_status(self) -> None:
        try:
            _secrets.ensure_admin_secrets_from_pull()
            status = _launch.connection_status()
            self.ip_var.set(status.get("hardware_ip") or "—")
            self.mac_var.set(status.get("hardware_mac") or "—")
            onion_ok = bool(status.get("frontend_onion_configured"))
            onion_value = (
                _secrets.get_admin_secret("FRONTEND_ONION") if onion_ok else ""
            )
            self.onion_var.set(onion_value or "not configured")
            admin_id = status.get("admin_id") or ""
            self.admin_var.set(admin_id or "—")
            verified = bool(status.get("download_auth_verified"))
            self.auth_var.set("verified" if verified else "unverified")
            auth_label = self._value_labels.get("Download Auth")
            if auth_label is not None:
                auth_label.configure(fg=ACCENT_GREEN if verified else TEXT)
            connected = bool(status.get("connected"))
            self.conn_var.set("connected" if connected else "disconnected")
            conn_label = self._value_labels.get("Connection")
            if conn_label is not None:
                conn_label.configure(fg=ACCENT_GREEN if connected else TEXT)
            cli_info = _admin_cli.cli_availability()
            if cli_info.get("available"):
                self.cli_var.set(f"available ({cli_info.get('shell')})")
            else:
                self.cli_var.set(cli_info.get("reason") or "unavailable")
            self.status_var.set("Ready.")
        except Exception as exc:  # noqa: BLE001 — surface any pull/secrets failure in UI
            self.status_var.set(f"Status error: {exc}")

    def on_send_code(self) -> None:
        self.status_var.set("Issuing and emailing download auth code…")
        self.update_idletasks()
        try:
            report = _download_auth.issue_download_auth_code()
            dest = (report.get("email") or {}).get("destination") or "secrets destination"
            self.status_var.set(
                f"Code emailed to {dest} — expires {report.get('expires_at')}"
            )
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Send code failed: {exc}")
            messagebox.showerror("Send code failed", str(exc))

    def on_authenticate(self) -> None:
        code = self.code_entry.get().strip()
        self.status_var.set("Verifying download auth code…")
        self.update_idletasks()
        try:
            report = _download_auth.verify_download_auth_code(code)
            self.status_var.set(f"Authenticated at {report.get('verified_at')}")
            self.code_entry.delete(0, "end")
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Authenticate failed: {exc}")
            messagebox.showerror("Authenticate failed", str(exc))

    def on_connect(self) -> None:
        self.status_var.set("Validating AdminID and opening Tor Browser to AdminHome…")
        self.update_idletasks()
        try:
            report = _launch.launch_admin_session()
            self.status_var.set(
                f"Connected — admin={report.get('admin_id') or 'n/a'} url={report.get('url')}"
            )
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Connect failed: {exc}")
            messagebox.showerror("Connect failed", str(exc))

    def on_disconnect(self) -> None:
        self.status_var.set("Disconnecting Tor Browser…")
        self.update_idletasks()
        try:
            report = _launch.disconnect_admin_session()
            self.status_var.set(f"Disconnected at {report.get('disconnected_at')}")
            self.refresh_status()
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Disconnect failed: {exc}")
            messagebox.showerror("Disconnect failed", str(exc))

    def on_cli_run(self) -> None:
        command = self.cli_entry.get().strip()
        if not command:
            return
        self.status_var.set("Running Linux CLI command…")
        self.update_idletasks()
        try:
            report = self._cli_session.run_command(command)
            self._append_cli(f"$ {command}")
            if report.get("stdout"):
                self._append_cli(str(report["stdout"]).rstrip())
            if report.get("stderr"):
                self._append_cli(str(report["stderr"]).rstrip())
            self._append_cli(f"[exit {report.get('exit')}]")
            self.cli_entry.delete(0, "end")
            self.status_var.set(f"CLI exit={report.get('exit')}")
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"CLI failed: {exc}")
            messagebox.showerror("CLI failed", str(exc))


def run_gui() -> int:
    app = AdminGuiApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
