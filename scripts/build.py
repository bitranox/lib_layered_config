from __future__ import annotations

import shutil
import sys
from pathlib import Path

import rich_click as click

try:
    from ._utils import ensure_conda, ensure_nix, get_project_metadata, run
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import ensure_conda, ensure_nix, get_project_metadata, run

__all__ = ["build_artifacts"]

PROJECT = get_project_metadata()


def _status(label: str) -> str:
    return click.style(label, fg="green")


def _failure(label: str) -> str:
    return click.style(label, fg="red")


def _skip(label: str) -> str:
    return click.style(label, fg="yellow")


def build_artifacts(*, allow_conda: bool = True, allow_brew: bool = True, allow_nix: bool = True) -> None:
    """Build Python artifacts and optionally attempt conda, brew, and nix builds."""

    click.echo("[1/4] Building wheel/sdist via python -m build")
    build_result = run(["python", "-m", "build"], check=False, capture=False)
    click.echo(f"[build] {_status('success') if build_result.code == 0 else _failure('failed')}")
    if build_result.code != 0:
        raise SystemExit(build_result.code)

    project = PROJECT

    click.echo("[2/4] Attempting conda-build")
    if allow_conda and ensure_conda():
        conda_cmd = ". $HOME/miniforge3/etc/profile.d/conda.sh >/dev/null 2>&1 || true; conda clean --all --yes >/dev/null 2>&1 || true; CONDA_USE_LOCAL=1 conda build packaging/conda/recipe"
        conda_result = run(["bash", "-lc", conda_cmd], check=False, capture=False)
        conda_msg = _status("success") if conda_result.code == 0 else _failure("failed")
    else:
        conda_msg = _skip("skipped")
    click.echo(f"[conda] {conda_msg}")

    click.echo("[3/4] Attempting Homebrew build/install from local formula")
    if allow_brew and shutil.which("brew"):
        brew_result = run(["bash", "-lc", f"brew install --build-from-source {project.brew_formula_path}"], check=False, capture=False)
        brew_msg = _status("success") if brew_result.code == 0 else _failure("failed")
    else:
        brew_msg = _skip("skipped")
    click.echo(f"[brew] {brew_msg}")

    click.echo("[4/4] Attempting Nix flake build")
    if allow_nix and ensure_nix():
        nix_cmd = ". $HOME/.nix-profile/etc/profile.d/nix.sh >/dev/null 2>&1 || true; nix build --extra-experimental-features 'nix-command flakes' ./packaging/nix#default -L"
        nix_result = run(["bash", "-lc", nix_cmd], check=False, capture=False)
        nix_msg = _status("success") if nix_result.code == 0 else _failure("failed")
    else:
        nix_msg = _skip("skipped")
    click.echo(f"[nix] {nix_msg}")


def main() -> None:  # pragma: no cover
    build_artifacts()


if __name__ == "__main__":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.cli import main as cli_main

    cli_main(["build", *sys.argv[1:]])
