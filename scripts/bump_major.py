from __future__ import annotations

import click
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bump import main as bump_main  # noqa: E402


@click.command(help="Bump major version")
def main() -> None:  # pragma: no cover
    bump_main.main(standalone_mode=False, args=["--part", "major"])  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
