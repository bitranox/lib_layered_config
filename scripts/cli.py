from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import rich_click as click

try:
    from . import build as build_module
    from . import bump as bump_module
    from . import clean as clean_module
    from . import dev as dev_module
    from . import install as install_module
    from . import push as push_module
    from . import release as release_module
    from . import run_cli as run_cli_module
    from . import test as test_module
    from . import version_current as version_module
    from .bump_major import bump_major
    from .bump_minor import bump_minor
    from .bump_patch import bump_patch
except ImportError:  # pragma: no cover - direct execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import build as build_module
    from scripts import bump as bump_module
    from scripts import clean as clean_module
    from scripts import dev as dev_module
    from scripts import install as install_module
    from scripts import push as push_module
    from scripts import release as release_module
    from scripts import run_cli as run_cli_module
    from scripts import test as test_module
    from scripts import version_current as version_module
    from scripts.bump_major import bump_major
    from scripts.bump_minor import bump_minor
    from scripts.bump_patch import bump_patch

__all__ = ["main"]

click.rich_click.GROUP_ARGUMENTS_OPTIONS = True


@click.group(help="Automation toolbox for project workflows.")
def main() -> None:
    """Entry point for the scripts CLI."""


@main.command(name="install", help="Editable install: pip install -e .")
@click.option("--dry-run", is_flag=True, help="Print commands only")
def install_command(dry_run: bool) -> None:
    install_module.install(dry_run=dry_run)


@main.command(name="dev", help="Install with development extras: pip install -e .[dev]")
@click.option("--dry-run", is_flag=True, help="Print commands only")
def dev_command(dry_run: bool) -> None:
    dev_module.install_dev(dry_run=dry_run)


@main.command(name="clean", help="Remove caches and build artefacts")
@click.option("--pattern", "patterns", multiple=True, help="Additional glob patterns to delete")
def clean_command(patterns: tuple[str, ...]) -> None:
    target_patterns = clean_module.DEFAULT_PATTERNS + tuple(patterns)
    clean_module.clean(target_patterns)


@main.command(name="run", help="Run the project CLI and forward extra arguments")
@click.option("--use-dotenv", "use_dotenv", flag_value=True, default=None, help="Enable dotenv loading")
@click.option("--no-use-dotenv", "use_dotenv", flag_value=False, help="Disable dotenv loading")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run_command(use_dotenv: Optional[bool], args: Sequence[str]) -> None:
    raise SystemExit(run_cli_module.run_cli(args, use_dotenv=use_dotenv))


@main.command(name="test", help="Run lint, type-check, tests, and coverage upload")
@click.option("--coverage", type=click.Choice(["on", "auto", "off"]), default="on", show_default=True)
@click.option("--verbose", is_flag=True, help="Print executed commands")
@click.option("--strict-format/--no-strict-format", default=None, help="Control ruff format behaviour")
@click.option("--skip-packaging-sync/--no-skip-packaging-sync", default=None, help="Control packaging sync step")
def test_command(
    coverage: str,
    verbose: bool,
    strict_format: Optional[bool],
    skip_packaging_sync: Optional[bool],
) -> None:
    test_module.run_tests(
        coverage=coverage,
        verbose=verbose,
        strict_format=strict_format,
        skip_packaging_sync=skip_packaging_sync,
    )


@main.command(name="build", help="Build wheel/sdist and optional packaging artefacts")
@click.option("--conda/--no-conda", "allow_conda", default=True, show_default=True)
@click.option("--brew/--no-brew", "allow_brew", default=True, show_default=True)
@click.option("--nix/--no-nix", "allow_nix", default=True, show_default=True)
def build_command(allow_conda: bool, allow_brew: bool, allow_nix: bool) -> None:
    build_module.build_artifacts(
        allow_conda=allow_conda,
        allow_brew=allow_brew,
        allow_nix=allow_nix,
    )


@main.command(name="release", help="Create git tag and optional GitHub release")
@click.option("--remote", default="origin", show_default=True)
@click.option("--retries", default=5, show_default=True, type=int)
@click.option("--retry-wait", default=3.0, show_default=True, type=float)
def release_command(remote: str, retries: int, retry_wait: float) -> None:
    release_module.release(remote=remote, retries=retries, retry_wait=retry_wait)


@main.command(name="push", help="Run checks, commit, and push current branch")
@click.option("--remote", default="origin", show_default=True)
@click.option("--message", "message", type=str, default=None, help="Commit message (overrides prompt)")
def push_command(remote: str, message: Optional[str]) -> None:
    push_module.push(remote=remote, message=message)


@main.command(name="version-current", help="Print current version from pyproject.toml")
@click.option("--pyproject", type=click.Path(path_type=Path), default=Path("pyproject.toml"))
def version_command(pyproject: Path) -> None:
    click.echo(version_module.print_current_version(pyproject))


@main.command(name="bump", help="Bump version and changelog")
@click.option("--version", "version_", type=str, help="Explicit version X.Y.Z")
@click.option("--part", type=click.Choice(["major", "minor", "patch"]), default=None)
@click.option("--pyproject", type=click.Path(path_type=Path), default=Path("pyproject.toml"))
@click.option("--changelog", type=click.Path(path_type=Path), default=Path("CHANGELOG.md"))
def bump_command(
    version_: Optional[str],
    part: Optional[str],
    pyproject: Path,
    changelog: Path,
) -> None:
    bump_module.bump(version=version_, part=part, pyproject=pyproject, changelog=changelog)


@main.command(name="bump-major", help="Convenience wrapper to bump major version")
def bump_major_command() -> None:
    bump_major()


@main.command(name="bump-minor", help="Convenience wrapper to bump minor version")
def bump_minor_command() -> None:
    bump_minor()


@main.command(name="bump-patch", help="Convenience wrapper to bump patch version")
def bump_patch_command() -> None:
    bump_patch()


if __name__ == "__main__":  # pragma: no cover
    main()
