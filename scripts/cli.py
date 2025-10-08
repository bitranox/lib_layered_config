from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

import rich_click as click

try:
    from . import build as build_module
    from . import bump as bump_module
    from . import clean as clean_module
    from . import dev as dev_module
    from . import help as help_module
    from . import install as install_module
    from . import menu as menu_module
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
    from scripts import help as help_module
    from scripts import install as install_module
    from scripts import menu as menu_module
    from scripts import push as push_module
    from scripts import release as release_module
    from scripts import run_cli as run_cli_module
    from scripts import test as test_module
    from scripts import version_current as version_module
    from scripts.bump_major import bump_major
    from scripts.bump_minor import bump_minor
    from scripts.bump_patch import bump_patch

__all__ = ["main"]

_COVERAGE_MODES = {"on", "auto", "off"}
_BUMP_PARTS = {"major", "minor", "patch"}


def _env_value(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    token = value.strip()
    return token or None


def _resolve_choice(
    *,
    option: Optional[str],
    env_name: str,
    allowed: set[str],
    default: str,
) -> str:
    if option:
        return option
    env_value = _env_value(env_name)
    if env_value is None:
        return default
    token = env_value.lower()
    if token not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise click.ClickException(f"{env_name} must be one of: {allowed_values}")
    return token


def _resolve_remote_value(remote: Optional[str]) -> str:
    return remote or _env_value("REMOTE") or "origin"


click.rich_click.GROUP_ARGUMENTS_OPTIONS = True


@click.group(help="Automation toolbox for project workflows.")
def main() -> None:
    """Entry point for the scripts CLI."""


@main.command(name="help", help="Show automation target summary")
def help_command() -> None:
    help_module.print_help()


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
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run_command(args: Sequence[str]) -> None:
    raise SystemExit(run_cli_module.run_cli(args))


@main.command(name="test", help="Run lint, type-check, tests, and coverage upload")
@click.option("--coverage", type=click.Choice(sorted(_COVERAGE_MODES)), default=None, show_default=False)
@click.option("--verbose", is_flag=True, help="Print executed commands")
@click.option("--strict-format/--no-strict-format", default=None, help="Control ruff format behaviour")
def test_command(coverage: Optional[str], verbose: bool, strict_format: Optional[bool]) -> None:
    resolved_coverage = _resolve_choice(
        option=coverage,
        env_name="COVERAGE",
        allowed=_COVERAGE_MODES,
        default="on",
    )
    test_module.run_tests(
        coverage=resolved_coverage,
        verbose=verbose,
        strict_format=strict_format,
    )


@main.command(name="build", help="Build wheel/sdist artifacts")
def build_command() -> None:
    build_module.build_artifacts()


@main.command(name="release", help="Create git tag and optional GitHub release")
@click.option("--remote", default=None, show_default=False)
def release_command(remote: Optional[str]) -> None:
    resolved_remote = _resolve_remote_value(remote)
    release_module.release(remote=resolved_remote)


@main.command(name="push", help="Run checks, commit, and push current branch")
@click.option("--remote", default=None, show_default=False)
@click.option("--message", "message", type=str, default=None, help="Commit message (overrides prompt)")
def push_command(remote: Optional[str], message: Optional[str]) -> None:
    resolved_remote = _resolve_remote_value(remote)
    commit_message = message if message is not None else _env_value("COMMIT_MESSAGE")
    push_module.push(remote=resolved_remote, message=commit_message)


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
    resolved_version = version_ or _env_value("VERSION")
    resolved_part = _resolve_choice(
        option=part,
        env_name="PART",
        allowed=_BUMP_PARTS,
        default="patch",
    )
    bump_module.bump(version=resolved_version, part=resolved_part, pyproject=pyproject, changelog=changelog)


@main.command(name="bump-major", help="Convenience wrapper to bump major version")
def bump_major_command() -> None:
    bump_major()


@main.command(name="bump-minor", help="Convenience wrapper to bump minor version")
def bump_minor_command() -> None:
    bump_minor()


@main.command(name="bump-patch", help="Convenience wrapper to bump patch version")
def bump_patch_command() -> None:
    bump_patch()


@main.command(name="menu", help="Launch interactive TUI menu")
def menu_command() -> None:
    menu_module.run_menu()


if __name__ == "__main__":  # pragma: no cover
    main()
