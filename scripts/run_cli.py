from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Sequence

try:
    from ._utils import get_project_metadata
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import get_project_metadata

PROJECT = get_project_metadata()
PACKAGE = PROJECT.import_package

__all__ = ["run_cli"]


def _prepare_paths() -> None:
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"
    for entry in (src_path, project_root):
        candidate = str(entry)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def run_cli(args: Sequence[str] | None = None, *, use_dotenv: bool | None = None) -> int:
    """Invoke the package CLI, forwarding ``args``."""

    _prepare_paths()
    config_module = import_module(f"{PACKAGE}.config")
    env_toggle = os.getenv(config_module.DOTENV_ENV_VAR) if use_dotenv is None else None
    if config_module.should_use_dotenv(explicit=use_dotenv, env_value=env_toggle):
        config_module.enable_dotenv()

    import_module(f"{PACKAGE}.__main__")
    cli_main = import_module(f"{PACKAGE}.cli").main

    forwarded = list(args) if args else ["--help"]
    if use_dotenv is True and "--use-dotenv" not in forwarded:
        forwarded.insert(0, "--use-dotenv")
    elif use_dotenv is False and "--no-use-dotenv" not in forwarded:
        forwarded.insert(0, "--no-use-dotenv")
    return int(cli_main(forwarded))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli(sys.argv[1:]))
