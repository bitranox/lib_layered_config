from __future__ import annotations

import shutil
from pathlib import Path

import click


DEFAULTS = [
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
]


def _glob_delete(pattern: str) -> None:
    for path in Path(".").glob(pattern):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


@click.command(help="Remove caches, build artifacts, and coverage outputs")
def main() -> None:
    for p in DEFAULTS:
        _glob_delete(p)


if __name__ == "__main__":
    main()
