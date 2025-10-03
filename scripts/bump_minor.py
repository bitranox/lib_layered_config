from __future__ import annotations

import sys
from pathlib import Path

try:
    from .bump import bump
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.bump import bump

__all__ = ["bump_minor"]


def bump_minor(pyproject: Path = Path("pyproject.toml"), changelog: Path = Path("CHANGELOG.md")) -> None:
    """Convenience wrapper to bump the minor version component."""

    bump(part="minor", pyproject=pyproject, changelog=changelog)


if __name__ == "__main__":  # pragma: no cover
    from scripts.cli import main as cli_main

    cli_main(["bump", "--part", "minor", *sys.argv[1:]])
