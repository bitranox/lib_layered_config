from __future__ import annotations

import click
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._utils import run  # noqa: E402


@click.command(help="Editable install with dev extras: pip install -e .[dev]")
@click.option("--dry-run", is_flag=True, help="Print commands only")
def main(dry_run: bool) -> None:
    run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"], dry_run=dry_run)


if __name__ == "__main__":
    main()
