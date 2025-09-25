from __future__ import annotations

import click
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._utils import read_version_from_pyproject  # noqa: E402


@click.command(name="version-current", help="Print version from pyproject.toml")
@click.option("--pyproject", type=click.Path(path_type=Path), default=Path("pyproject.toml"))
def main(pyproject: Path) -> None:
    v = read_version_from_pyproject(pyproject)
    if not v:
        raise SystemExit("version not found")
    click.echo(v)


if __name__ == "__main__":
    main()
