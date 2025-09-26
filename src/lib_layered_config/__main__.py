"""Module execution entry point delegating to the CLI adapter."""

from __future__ import annotations

import sys

from .cli import main


if __name__ == "__main__":  # pragma: no cover - exercised via python -m
    raise SystemExit(main(sys.argv[1:]))
