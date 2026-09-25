"""RunRdp — start the Rdp container at time of operation.

Flow:
1. createRDP.pull_information / build_and_write_rdp_secrets (hardware → rdp.secrets)
2. load secrets
3. create FastAPI app (RdpRoutes)
4. uvicorn bind host/port from secrets

RULES:
- No hardcoded values, all values are created at time of operation.
- No placeholder values, all values are created at time of operation.
- No sensitive data, all data is stored in the secrets file.
- NO pull from GIT repository, all values are created at time of operation.
- DO NOT EDIT THE COMMENTS, THEY ARE FOR DOCUMENTATION ONLY.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load_local(module_name: str, filename: str | None = None) -> Any:
    file_name = filename or f"{module_name}.py"
    path = _DIR / file_name
    registry = f"lucid_rdp_{module_name.replace('-', '_')}"
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


def bootstrap_secrets(*, overwrite: bool = False) -> dict[str, Any]:
    create_rdp = _load_local("createRDP", "createRDP.py")
    return create_rdp.build_and_write_rdp_secrets(overwrite_keys=overwrite)


def run_server(*, overwrite_secrets: bool = False) -> None:
    report = bootstrap_secrets(overwrite=overwrite_secrets)
    rdp_secrets = _load_local("rdp_secrets")
    rdp_secrets.load_rdp_secrets(reload=True)
    require_rdp_secret = rdp_secrets.require_rdp_secret
    require_rdp_secret_int = rdp_secrets.require_rdp_secret_int

    dns = _load_local("DockerDns")
    dns.assert_dns_configured()

    rdp_main = _load_local("RdpMain")
    start_report = rdp_main.start_rdp_container()

    routes = _load_local("RdpRoutes")
    app = routes.create_rdp_app()

    host = require_rdp_secret("RDP_BIND_HOST")
    port = require_rdp_secret_int("RDP_PORT")

    import uvicorn

    print(
        json.dumps(
            {
                "status": "starting",
                "secrets": report,
                "start": start_report,
                "bind_host": host,
                "port": port,
            },
            indent=2,
        )
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LucidTops Rdp runner")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run", "pull", "secrets"),
        help="run=bootstrap+uvicorn; pull/secrets=write rdp.secrets only",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing non-hardware keys in rdp.secrets",
    )
    args = parser.parse_args(list(argv if argv is not None else sys.argv[1:]))

    if args.command in {"pull", "secrets"}:
        report = bootstrap_secrets(overwrite=args.overwrite)
        print(json.dumps(report, indent=2))
        return 0

    run_server(overwrite_secrets=args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
