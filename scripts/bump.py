from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    from ._utils import run
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import run

__all__ = ["bump"]


def bump(
    *, version: Optional[str] = None, part: Optional[str] = None, pyproject: Path = Path("pyproject.toml"), changelog: Path = Path("CHANGELOG.md")
) -> None:
    """Bump the project version and update the changelog."""

    args = [sys.executable, "scripts/bump_version.py"]
    if version:
        args += ["--version", version]
    else:
        args += ["--part", part or "patch"]
    args += ["--pyproject", str(pyproject), "--changelog", str(changelog)]
    run(args)


if __name__ == "__main__":  # pragma: no cover
    from scripts.cli import main as cli_main

    cli_main(["bump", *sys.argv[1:]])
