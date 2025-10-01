from __future__ import annotations

import sys
from pathlib import Path

import click

try:  # allow running as package module or stand-alone script
    from ._utils import cmd_exists, ensure_conda, ensure_nix, get_project_metadata, run
except ImportError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import cmd_exists, ensure_conda, ensure_nix, get_project_metadata, run


@click.command(help="Build wheel/sdist, optionally attempt conda/brew/nix builds if tools present")
@click.option("--conda/--no-conda", default=True, help="Attempt conda build if conda present")
@click.option("--brew/--no-brew", default=True, help="Attempt Homebrew build if brew present (macOS)")
@click.option("--nix/--no-nix", default=True, help="Attempt Nix build if nix present")
def main(conda: bool, brew: bool, nix: bool) -> None:
    click.echo("[1/4] Building wheel/sdist via python -m build")
    build_result = run(["python", "-m", "build"], check=False, capture=False)
    build_msg = click.style("success", fg="green") if build_result.code == 0 else click.style("failed", fg="red")
    click.echo(f"[build] {build_msg}")
    if build_result.code != 0:
        raise SystemExit(build_result.code)

    project = get_project_metadata()

    click.echo("[2/4] Attempting conda-build")
    conda_msg: str
    if conda:
        if ensure_conda():
            conda_cmd = ". $HOME/miniforge3/etc/profile.d/conda.sh >/dev/null 2>&1 || true; conda clean --all --yes >/dev/null 2>&1 || true; CONDA_USE_LOCAL=1 conda build packaging/conda/recipe"
            conda_result = run(["bash", "-lc", conda_cmd], check=False, capture=False)
            conda_msg = click.style("success", fg="green") if conda_result.code == 0 else click.style("failed", fg="red")
        else:
            conda_msg = click.style("skipped", fg="yellow")
    else:
        conda_msg = click.style("skipped", fg="yellow")
    click.echo(f"[conda] {conda_msg}")

    click.echo("[3/4] Attempting Homebrew build/install from local formula")
    brew_msg: str
    if brew and cmd_exists("brew"):
        brew_result = run(["bash", "-lc", f"brew install --build-from-source {project.brew_formula_path}"], check=False, capture=False)
        brew_msg = click.style("success", fg="green") if brew_result.code == 0 else click.style("failed", fg="red")
    else:
        brew_msg = click.style("skipped", fg="yellow")
    click.echo(f"[brew] {brew_msg}")

    click.echo("[4/4] Attempting Nix flake build")
    nix_msg: str
    if nix:
        if ensure_nix():
            nix_cmd = ". $HOME/.nix-profile/etc/profile.d/nix.sh >/dev/null 2>&1 || true; nix build --extra-experimental-features 'nix-command flakes' ./packaging/nix#default -L"
            nix_result = run(["bash", "-lc", nix_cmd], check=False, capture=False)
            nix_msg = click.style("success", fg="green") if nix_result.code == 0 else click.style("failed", fg="red")
        else:
            nix_msg = click.style("skipped", fg="yellow")
    else:
        nix_msg = click.style("skipped", fg="yellow")
    click.echo(f"[nix] {nix_msg}")


if __name__ == "__main__":
    main()
