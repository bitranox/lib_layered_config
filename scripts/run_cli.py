from __future__ import annotations

import click
import sys
from importlib import import_module
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
src_path = project_root / 'src'
for entry in (src_path, project_root):
    candidate = str(entry)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
from scripts._utils import get_project_metadata  # noqa: E402

PROJECT = get_project_metadata()
PACKAGE = PROJECT.import_package


@click.command(help=f"Run {PROJECT.name} CLI (passes additional args)")
@click.argument("args", nargs=-1)
def main(args: tuple[str, ...]) -> None:
    import_module(f"{PACKAGE}.__main__")
    cli_main = import_module(f"{PACKAGE}.cli").main

    code = cli_main(list(args) if args else ["--help"])  # returns int
    raise SystemExit(int(code))


if __name__ == "__main__":
    main()
