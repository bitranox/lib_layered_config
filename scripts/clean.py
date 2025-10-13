from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PATTERNS: tuple[str, ...] = (
    ".hypothesis",
    ".import_linter_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".pyright",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".eggs",
    "*.egg-info",
    "build",
    "dist",
    "htmlcov",
    ".coverage",
    "coverage.xml",
    "codecov.sh",
    ".cache",
    "result",
)

__all__ = ["clean", "DEFAULT_PATTERNS"]


def clean(patterns: Iterable[str] = DEFAULT_PATTERNS) -> None:
    """Remove cached artefacts and build outputs matching ``patterns``."""

    for pattern in patterns:
        for path in Path.cwd().glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue


if __name__ == "__main__":  # pragma: no cover
    from .cli import main as cli_main

    cli_main(["clean"])
