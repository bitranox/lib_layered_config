"""Let ``python -m lib_layered_config`` feel as gentle as ``cli.main``."""

from __future__ import annotations

from collections.abc import Sequence

from .cli import main


def run_module(arguments: Sequence[str] | None = None) -> int:
    """Forward *arguments* to :func:`lib_layered_config.cli.main` and return the exit code."""
    return main(arguments, restore_traceback=True)


if __name__ == "__main__":
    import sys

    raise SystemExit(run_module(sys.argv[1:]))
