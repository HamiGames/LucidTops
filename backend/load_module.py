"""Load backend modules whose filenames contain hyphens."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parent


def load_backend_module(filename: str) -> ModuleType:
    path = BACKEND_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Backend module not found: {path}")
    module_name = filename.replace("-", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
