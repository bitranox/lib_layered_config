from __future__ import annotations

import sys
from pathlib import Path

import click

try:  # allow running as package module or stand-alone script
    from ._utils import cmd_exists, get_project_metadata, run
except ImportError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import cmd_exists, get_project_metadata, run


@click.command(help="Build wheel/sdist, optionally attempt conda/brew/nix builds if tools present")
@click.option("--conda/--no-conda", default=True, help="Attempt conda build if conda present")
@click.option("--brew/--no-brew", default=True, help="Attempt Homebrew build if brew present (macOS)")
@click.option("--nix/--no-nix", default=True, help="Attempt Nix build if nix present")
def main(conda: bool, brew: bool, nix: bool) -> None:
    click.echo("[1/4] Building wheel/sdist via python -m build")
    run(["python", "-m", "build"])  # requires build in dev deps

    project = get_project_metadata()

    click.echo("[2/4] Attempting conda-build")
    if conda and cmd_exists("conda"):
        run(["bash", "-lc", "CONDA_USE_LOCAL=1 conda build packaging/conda/recipe"], check=False)
    else:
        click.echo("[conda] skipping: conda not available or disabled")

    click.echo("[3/4] Attempting Homebrew build/install from local formula")
    if brew and cmd_exists("brew"):
        run(["bash", "-lc", f"brew install --build-from-source {project.brew_formula_path}"], check=False)
    else:
        click.echo("[brew] skipping: Homebrew not available or disabled")

    click.echo("[4/4] Attempting Nix flake build")
    if nix and cmd_exists("nix"):
        run(["bash", "-lc", "nix build packaging/nix#default -L"], check=False)
    else:
        click.echo("[nix] skipping: nix not available or disabled")


if __name__ == "__main__":
    main()
