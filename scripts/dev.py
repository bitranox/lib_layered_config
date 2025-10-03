from __future__ import annotations

import sys
from pathlib import Path

try:
    from ._utils import run
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import run

__all__ = ["install_dev"]


def install_dev(*, dry_run: bool = False) -> None:
    """Install the project with development extras."""

    run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"], dry_run=dry_run)


if __name__ == "__main__":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.cli import main as cli_main

    cli_main(["dev", *sys.argv[1:]])
