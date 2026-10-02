"""NodeUser branch.

Registration posts email, password, and console hardware with no TokenID.
Login sends the stored TokenID as the API key.
The route set after that is the NodeUser set, not the User set.
The operations container is already installed. This module does not call
LaunchUser and does not start the Proxy container.
The Node container is attached only when a MasterServer-issued NodeID is stored.
That container is what joins DockerDNS. This process does not.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


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


_user_secrets = _load_local("user_secrets")
_install = _load_local("install")
_access = _load_local("frontend_access")
_routes = _load_local("internal_routes")

get_user_secret = _user_secrets.get_user_secret
require_user_secret = _user_secrets.require_user_secret
ensure_user_secrets_from_pull = _user_secrets.ensure_user_secrets_from_pull


def _require_install() -> None:
    if not _install.install_is_complete():
        raise RuntimeError("Install has not finished on this console")


def _hardware() -> dict[str, str]:
    return {
        "hostname": get_user_secret("HOSTNAME_CONSOLE"),
        "machine_id": get_user_secret("HOST_MACHINE_ID"),
        "primary_mac": get_user_secret("HARDWARE_PRIMARY_MAC"),
        "primary_ip": get_user_secret("HARDWARE_PRIMARY_IP"),
        "primary_iface": get_user_secret("HARDWARE_PRIMARY_IFACE"),
    }


def _hardware_fields(hardware: dict[str, str]) -> dict[str, str]:
    return {
        "HOSTNAME_CONSOLE": hardware.get("hostname", ""),
        "HOST_MACHINE_ID": hardware.get("machine_id", ""),
        "HARDWARE_PRIMARY_MAC": hardware.get("primary_mac", ""),
        "HARDWARE_PRIMARY_IP": hardware.get("primary_ip", ""),
        "HARDWARE_PRIMARY_IFACE": hardware.get("primary_iface", ""),
    }


def _driver_dir() -> Path:
    raw = get_user_secret("DRIVER_DIR")
    if not raw:
        raise RuntimeError("DRIVER_DIR missing — run Install before choosing User or NodeUser")
    return Path(raw)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _require_operations_image() -> None:
    docker = shutil.which("docker") or shutil.which("docker.exe")
    if not docker:
        raise RuntimeError("Docker missing — re-run Install")
    inspect = _run([docker, "image", "inspect", "lucid-operations:v1.0.0"])
    if inspect.returncode != 0:
        raise RuntimeError(
            "operations container image lucid-operations:v1.0.0 is not installed"
        )


def attach_node_container(node_id: str, routes: dict[str, str]) -> dict[str, Any]:
    """Attach the downloadable Node container only for a registered NodeID."""
    if not node_id.strip():
        return {"status": "not_attached", "reason": "NodeID has not been returned by the MasterServer"}
    image = _routes.node_image_name()
    if not image:
        raise RuntimeError("Node image name missing from the internalized NodeUser route set")
    docker = shutil.which("docker") or shutil.which("docker.exe")
    if not docker:
        raise RuntimeError("Docker missing — cannot attach the Node container")
    container_name = "lucid-node-" + "".join(ch for ch in node_id if ch.isalnum())[:12]
    existing = _run([docker, "inspect", container_name])
    if existing.returncode == 0:
        started = _run([docker, "start", container_name])
        if started.returncode != 0:
            raise RuntimeError(f"Node container {container_name} did not start")
        return {"status": "started", "container": container_name, "image": image}
    command = [docker, "run", "-d", "--name", container_name]
    network = routes.get("DOCKER_NETWORK_NAME", "").strip()
    if network:
        command.extend(["--network", network])
    command.append(image)
    created = _run(command)
    if created.returncode != 0:
        raise RuntimeError(
            f"Node container was not created (exit {created.returncode})"
        )
    return {"status": "created", "container": container_name, "image": image}


def _register_body(*, email: str, password: str, linked_user_id: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "action": "register",
        "account_type": "node",
        "Email": email,
        "Password": password,
        **_hardware_fields(_hardware()),
    }
    if linked_user_id.strip():
        body["UserID"] = linked_user_id.strip()
    return body


def _login_body(*, email: str, password: str) -> dict[str, Any]:
    token_id = get_user_secret("TOKEN_ID")
    return {
        "action": "login",
        "account_type": "node",
        "Email": email,
        "Password": password,
        "UserID": get_user_secret("USER_ID"),
        "NodeID": get_user_secret("NODE_ID"),
        "TokenID": token_id,
        "api_key": token_id,
    }


def _post(
    *,
    email: str,
    password: str,
    action: str,
    linked_user_id: str,
    file_name: str,
) -> dict[str, Any]:
    _require_install()
    ensure_user_secrets_from_pull()
    _require_operations_image()
    if not email.strip() or not password:
        raise RuntimeError("Email and password are required")
    routes = _access.routes_for(True)
    command = require_user_secret("USER_TOR_START_COMMAND")
    tor = _access.start_tor_background(command)
    if action == "register":
        path = _access.registration_path(routes, nodeuser=True)
        body = _register_body(
            email=email.strip(),
            password=password,
            linked_user_id=linked_user_id,
        )
    else:
        path = _access.login_path(routes, nodeuser=True)
        body = _login_body(email=email.strip(), password=password)
    submitted = _access.submit_validation(
        routes,
        path=path,
        body=body,
        driver_dir=_driver_dir(),
        file_name=file_name,
    )
    stored = _user_secrets.apply_master_identity(submitted["reply"], nodeuser=True)
    _user_secrets.verify_id_secrets()
    attached = attach_node_container(stored.get("NODE_ID", ""), routes)
    state_path = _access.write_session_state(
        {
            "status": "connected",
            "branch": "nodeuser",
            "tor_pid": tor.get("pid"),
            "launched_at": _access.utc_now(),
        }
    )
    return {
        "status": "registered" if action == "register" else "connected",
        "branch": "nodeuser",
        "post_file": submitted["post_file"],
        "node_id_returned": bool(stored.get("NODE_ID")),
        "token_id_returned": bool(stored.get("TOKEN_ID")),
        "node_container": attached,
        "session_state": state_path.as_posix(),
    }


def register_nodeuser(*, email: str, password: str, linked_user_id: str = "") -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    return _post(
        email=email,
        password=password,
        action="register",
        linked_user_id=linked_user_id or get_user_secret("USER_ID"),
        file_name="registration_nodeuser.post.json",
    )


def connect_nodeuser(*, email: str, password: str) -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    if get_user_secret("NODEUSER").lower() == "false" and get_user_secret("USER_ID"):
        raise RuntimeError("NodeUser route refused — this console identity is a User")
    _user_secrets.verify_id_secrets()
    if not get_user_secret("TOKEN_ID"):
        raise RuntimeError("Login without a TokenID is rejected")
    if not get_user_secret("NODE_ID"):
        raise RuntimeError("Register as a NodeUser before connecting")
    return _post(
        email=email,
        password=password,
        action="login",
        linked_user_id=get_user_secret("USER_ID"),
        file_name="login_nodeuser.post.json",
    )


def disconnect_nodeuser_session() -> dict[str, Any]:
    ensure_user_secrets_from_pull()
    return _access.disconnect_session()
