from __future__ import annotations

import click
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._utils import run  # noqa: E402


@click.command(help="Bump version in pyproject.toml and CHANGELOG.md")
@click.option("--version", "version_", type=str, help="Explicit version X.Y.Z")
@click.option("--part", type=click.Choice(["major", "minor", "patch"]), default=None)
@click.option("--pyproject", type=click.Path(path_type=Path), default=Path("pyproject.toml"))
@click.option("--changelog", type=click.Path(path_type=Path), default=Path("CHANGELOG.md"))
def main(version_: str | None, part: str | None, pyproject: Path, changelog: Path) -> None:
    args = [sys.executable, "scripts/bump_version.py"]
    if version_:
        args += ["--version", version_]
    else:
        args += ["--part", part or "patch"]
    args += ["--pyproject", str(pyproject), "--changelog", str(changelog)]
    run(args)


if __name__ == "__main__":
    main()
