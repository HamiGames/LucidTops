"""LucidTops UsersOnly selector.

Tkinter only. Colors match frontend/webpage/assets/lucid-theme.css.
The window chooses User or NodeUser. It does not show routes, onions, or secrets.
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

BG = "#0a0c0f"
PANEL = "#12161c"
BG_2 = "#1a212b"
TEXT = "#e8eef2"
MUTED = "#9aa8b5"
ACCENT = "#3dceb4"
ACCENT_2 = "#6fd3ff"
DANGER = "#ff6b7a"
OK = "#5dde9a"
WARN = "#f0c35a"
DISPLAY_FONT = ("Trebuchet MS", 28, "bold")
BODY_FONT = ("Segoe UI", 12)


def _load_local(module_name: str) -> Any:
    path = _DIR / f"{module_name}.py"
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
_launch_user = _load_local("LaunchUser")
_launch_node = _load_local("LaunchNodeUser")
_secrets = _load_local("user_secrets")


def _button(
    parent: tk.Misc,
    *,
    text: str,
    command: Callable[[], None],
    accent: str,
) -> tk.Button:
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=accent,
        fg=BG,
        activebackground=ACCENT_2,
        activeforeground=BG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=12,
        pady=8,
        cursor="hand2",
        font=("Segoe UI", 12, "bold"),
    )

    def on_enter(_: tk.Event[Any]) -> None:
        if str(button.cget("state")) == "disabled":
            return
        button.configure(bg=ACCENT_2)

    def on_leave(_: tk.Event[Any]) -> None:
        if str(button.cget("state")) == "disabled":
            return
        button.configure(bg=accent)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    return button


class UsersOnlyApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LucidTops")
        self.minsize(560, 460)
        self.configure(bg=BG)
        self._node_connect: tk.Button | None = None
        self._node_register: tk.Button | None = None
        self._build()
        self.after(100, self.refresh_status)

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG, padx=24, pady=24)
        outer.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        tk.Label(
            outer,
            text="LucidTops",
            font=DISPLAY_FONT,
            bg=BG,
            fg=ACCENT,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            outer,
            text="Install, then connect or register as a User or a NodeUser.",
            font=BODY_FONT,
            bg=BG,
            fg=ACCENT_2,
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        form = tk.Frame(outer, bg=PANEL, padx=16, pady=16)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.linked_var = tk.StringVar()
        fields = (
            ("Email", self.email_var, False),
            ("Password", self.password_var, True),
            ("Linked UserID", self.linked_var, False),
        )
        for index, (label, variable, secret) in enumerate(fields):
            tk.Label(
                form, text=label, bg=PANEL, fg=MUTED, font=BODY_FONT
            ).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=4)
            tk.Entry(
                form,
                textvariable=variable,
                show="*" if secret else "",
                bg=BG_2,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                font=BODY_FONT,
            ).grid(row=index, column=1, sticky="ew", pady=4)

        self.status_var = tk.StringVar(value="Not installed.")
        self.status_label = tk.Label(
            outer,
            textvariable=self.status_var,
            wraplength=500,
            justify="left",
            font=BODY_FONT,
            bg=BG,
            fg=WARN,
        )
        self.status_label.grid(row=3, column=0, sticky="ew", pady=(16, 8))

        actions = tk.Frame(outer, bg=BG)
        actions.grid(row=4, column=0, sticky="ew")
        for col in range(3):
            actions.columnconfigure(col, weight=1)
        _button(actions, text="Install", command=self.on_install, accent=ACCENT_2).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        _button(
            actions, text="Connect as User", command=self.on_connect_user, accent=ACCENT
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=4)
        _button(
            actions, text="Register as User", command=self.on_register_user, accent=ACCENT
        ).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        _button(
            actions, text="Disconnect", command=self.on_disconnect, accent=DANGER
        ).grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=4)
        self._node_connect = _button(
            actions,
            text="Connect as NodeUser",
            command=self.on_connect_node,
            accent=ACCENT_2,
        )
        self._node_connect.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=4)
        self._node_register = _button(
            actions,
            text="Register as NodeUser",
            command=self.on_register_node,
            accent=ACCENT_2,
        )
        self._node_register.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=4)

    def _credentials(self) -> tuple[str, str]:
        return self.email_var.get().strip(), self.password_var.get()

    def _run(self, pending: str, action: Callable[[], dict[str, Any]], done: str) -> None:
        self.status_var.set(pending)
        self.update_idletasks()
        try:
            action()
        except Exception as exc:  # noqa: BLE001 — show the failure in the window
            self.status_var.set(f"Failed. {exc}")
            messagebox.showerror("LucidTops", str(exc))
            return
        self.status_var.set(done)
        self.refresh_status()

    def refresh_status(self) -> None:
        installed = False
        connected = False
        branch = ""
        try:
            installed = bool(_install.install_is_complete())
        except Exception:  # noqa: BLE001 — status stays user-facing
            installed = False
        if installed:
            try:
                status = _launch_user.connection_status()
                connected = bool(status.get("connected"))
                session = status.get("session") if isinstance(status.get("session"), dict) else {}
                branch = str(session.get("branch") or "")
            except Exception:  # noqa: BLE001
                connected = False
        if connected and branch == "nodeuser":
            text = "Connected as NodeUser."
            color = OK
        elif connected:
            text = "Connected as User."
            color = OK
        elif installed:
            text = "Ready. Disconnected."
            color = TEXT
        else:
            text = "Not installed."
            color = WARN
        self.status_var.set(text)
        self.status_label.configure(fg=color)
        allowed = False
        if installed:
            try:
                allowed = bool(_secrets.node_branch_allowed())
            except Exception:  # noqa: BLE001
                allowed = False
        state = "normal" if allowed else "disabled"
        if self._node_connect is not None:
            self._node_connect.configure(state=state)
        if self._node_register is not None:
            self._node_register.configure(state=state)

    def on_install(self) -> None:
        def _install_now() -> dict[str, Any]:
            return _install.install_user_environment()

        self._run("Installing.", _install_now, "Install finished.")

    def on_connect_user(self) -> None:
        email, password = self._credentials()

        def _connect() -> dict[str, Any]:
            return _launch_user.connect_user(email=email, password=password)

        self._run("Connecting as User.", _connect, "Connected as User.")

    def on_register_user(self) -> None:
        email, password = self._credentials()

        def _register() -> dict[str, Any]:
            return _launch_user.register_user(email=email, password=password)

        self._run("Registering as User.", _register, "Registered as User.")

    def on_connect_node(self) -> None:
        email, password = self._credentials()

        def _connect() -> dict[str, Any]:
            return _launch_node.connect_nodeuser(email=email, password=password)

        self._run("Connecting as NodeUser.", _connect, "Connected as NodeUser.")

    def on_register_node(self) -> None:
        email, password = self._credentials()
        linked = self.linked_var.get().strip()

        def _register() -> dict[str, Any]:
            return _launch_node.register_nodeuser(
                email=email, password=password, linked_user_id=linked
            )

        self._run("Registering as NodeUser.", _register, "Registered as NodeUser.")

    def on_disconnect(self) -> None:
        def _disconnect() -> dict[str, Any]:
            return _launch_user.disconnect_user_session()

        self._run("Disconnecting.", _disconnect, "Disconnected.")


def run_gui() -> int:
    app = UsersOnlyApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
