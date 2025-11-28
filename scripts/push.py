from __future__ import annotations

import os
import sys
from pathlib import Path

import rich_click as click

from ._utils import (
    get_default_remote,
    get_project_metadata,
    git_branch,
    read_version_from_pyproject,
    run,
    sync_metadata_module,
)
from . import dependencies as dependencies_module

__all__ = ["push"]

_DEFAULT_REMOTE = get_default_remote()


def _get_installed_version(package_name: str) -> str | None:
    """Get the installed version of a package, or None if not installed."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
    except Exception:
        return None


def _check_and_update_pip() -> None:
    """Check if pip is at the latest version and update if needed."""
    click.echo("[pip] Checking pip version...")

    installed = _get_installed_version("pip")
    if installed is None:
        click.echo("[pip] Could not determine installed pip version", err=True)
        return

    # Fetch latest pip version from PyPI
    latest = dependencies_module._fetch_latest_version("pip")  # pyright: ignore[reportPrivateUsage]
    if latest is None:
        click.echo("[pip] Could not fetch latest pip version from PyPI", err=True)
        return

    status = dependencies_module._compare_versions(installed, latest)  # pyright: ignore[reportPrivateUsage]

    if status == "up-to-date":
        click.echo(f"[pip] pip {installed} is up-to-date")
        return

    click.echo(f"[pip] pip {installed} is outdated (latest: {latest})")

    # Check if running in CI or non-interactive mode
    if os.getenv("CI") or not sys.stdin.isatty():
        click.echo("[pip] Updating pip...")
        _do_pip_upgrade()
        return

    # Prompt user for update
    try:
        response = click.prompt(
            "Do you want to update pip now?",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="y",
            show_choices=True,
        )
    except (click.Abort, EOFError):
        click.echo("\n[pip] Update skipped")
        return

    if response.lower() == "y":
        _do_pip_upgrade()
    else:
        click.echo("[pip] Update skipped")


def _do_pip_upgrade() -> None:
    """Execute pip upgrade command."""
    upgrade_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    if sys.platform.startswith("linux"):
        upgrade_cmd.insert(4, "--break-system-packages")

    result = run(upgrade_cmd, check=False, capture=True)

    if result.code == 0:
        new_version = _get_installed_version("pip")
        click.echo(f"[pip] Successfully updated to pip {new_version}")
    else:
        # Check for SHA256 verification errors in CI (known issue)
        combined = f"{result.out}\n{result.err}".lower()
        if "sha256" in combined and "hash" in combined:
            click.echo("[pip] Update failed due to hash verification (common in CI); continuing...")
        else:
            click.echo(f"[pip] Update failed (exit code {result.code})", err=True)
            if result.err:
                click.echo(result.err, err=True)


def _check_dependencies_and_prompt_update() -> None:
    """Check dependencies and prompt user to update if outdated."""
    click.echo("\n[dependencies] Checking for outdated dependencies...")

    try:
        deps = dependencies_module.check_dependencies()
    except Exception as exc:
        click.echo(f"[dependencies] Failed to check dependencies: {exc}", err=True)
        return

    outdated = [d for d in deps if d.status == "outdated"]

    if not outdated:
        click.echo("[dependencies] All dependencies are up-to-date!")
        return

    # Display outdated dependencies
    click.echo(f"\n[dependencies] Found {len(outdated)} outdated dependencies:\n")

    # Calculate column widths for alignment
    name_width = max(len(d.name) for d in outdated)
    current_width = max(len(d.current_min) for d in outdated)

    for dep in sorted(outdated, key=lambda d: d.name.lower()):
        click.echo(f"  {dep.name:<{name_width}}  {dep.current_min:<{current_width}}  -->  {dep.latest}")

    click.echo("")

    # Check if running in CI or non-interactive mode
    if os.getenv("CI") or not sys.stdin.isatty():
        click.echo("[dependencies] Run 'make dependencies-update' to update dependencies")
        return

    # Prompt user for update
    try:
        response = click.prompt(
            "Do you want to update these dependencies now?",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="n",
            show_choices=True,
        )
    except (click.Abort, EOFError):
        click.echo("\n[dependencies] Update skipped")
        return

    if response.lower() == "y":
        click.echo("\n[dependencies] Updating dependencies...")
        updated = dependencies_module.update_dependencies(deps, dry_run=False)
        if updated > 0:
            click.echo(f"[dependencies] Successfully updated {updated} dependencies")
            click.echo("[dependencies] Run 'make test' again to verify changes")
        else:
            click.echo("[dependencies] No dependencies were updated")
    else:
        click.echo("[dependencies] Update skipped. Run 'make dependencies-update' later to update.")


def _check_installed_dependencies() -> None:
    """Check if dependencies are installed at the versions specified in pyproject.toml."""
    click.echo("\n[dependencies] Checking installed packages against pyproject.toml requirements...")

    try:
        deps = dependencies_module.check_dependencies()
    except Exception as exc:
        click.echo(f"[dependencies] Failed to check dependencies: {exc}", err=True)
        return

    missing: list[tuple[str, str]] = []  # (name, required_version)
    outdated_installed: list[tuple[str, str, str, str]] = []  # (name, installed, required, latest)

    for dep in deps:
        if not dep.current_min:
            continue

        installed = _get_installed_version(dep.name)

        if installed is None:
            missing.append((dep.name, dep.current_min))
        else:
            # Compare installed version with required minimum
            installed_status = dependencies_module._compare_versions(installed, dep.current_min)  # pyright: ignore[reportPrivateUsage]
            if installed_status == "outdated":
                # Installed version is older than required
                outdated_installed.append((dep.name, installed, dep.current_min, dep.latest))

    if not missing and not outdated_installed:
        click.echo("[dependencies] All required packages are installed at correct versions!")
        return

    # Display missing packages
    if missing:
        click.echo(f"\n[dependencies] {len(missing)} packages are NOT installed:\n")
        name_width = max(len(name) for name, _ in missing)
        for name, required in sorted(missing):
            click.echo(f"  [X] {name:<{name_width}}  (requires >={required})")

    # Display outdated installed packages
    if outdated_installed:
        click.echo(f"\n[dependencies] {len(outdated_installed)} installed packages are below required version:\n")
        name_width = max(len(name) for name, _, _, _ in outdated_installed)
        installed_width = max(len(installed) for _, installed, _, _ in outdated_installed)
        for name, installed, required, latest in sorted(outdated_installed):
            click.echo(
                f"  [!] {name:<{name_width}}  {installed:<{installed_width}}  (requires >={required}, latest: {latest})"
            )

    total_issues = len(missing) + len(outdated_installed)
    click.echo("")

    # Check if running in CI or non-interactive mode
    if os.getenv("CI") or not sys.stdin.isatty():
        click.echo(f"[dependencies] {total_issues} package(s) need updating. Run 'pip install -e .[dev]' to fix.")
        return

    # Prompt user to install/update
    try:
        response = click.prompt(
            "Do you want to install/update these packages now?",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="y",
            show_choices=True,
        )
    except (click.Abort, EOFError):
        click.echo("\n[dependencies] Install skipped")
        return

    if response.lower() == "y":
        click.echo("\n[dependencies] Installing/updating packages...")
        install_cmd = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
        if sys.platform.startswith("linux"):
            install_cmd.insert(4, "--break-system-packages")
        result = run(install_cmd, check=False, capture=False)
        if result.code == 0:
            click.echo("[dependencies] Packages installed successfully!")
        else:
            click.echo(f"[dependencies] Package installation failed (exit code {result.code})", err=True)
    else:
        click.echo("[dependencies] Install skipped. Run 'pip install -e .[dev]' to update packages.")


def push(*, remote: str = _DEFAULT_REMOTE, message: str | None = None) -> None:
    """Run checks, commit changes, and push the current branch."""

    # Step 0: Ensure pip is up-to-date
    _check_and_update_pip()

    # Step 1: Check pyproject.toml dependencies against PyPI
    _check_dependencies_and_prompt_update()

    # Step 2: Check installed packages meet requirements
    _check_installed_dependencies()

    metadata = get_project_metadata()
    sync_metadata_module(metadata)
    version = read_version_from_pyproject(Path("pyproject.toml")) or "unknown"
    click.echo("[push] project diagnostics: " + ", ".join(metadata.diagnostic_lines()))
    click.echo(f"[push] version={version}")
    branch = git_branch()
    click.echo(f"[push] branch={branch} remote={remote}")

    click.echo("[push] Running local checks (python -m scripts.test)")
    run(["python", "-m", "scripts.test"], capture=False)

    click.echo("[push] Committing and pushing (single attempt)")
    run(["git", "add", "-A"], capture=False)  # stage all
    staged = run(["bash", "-lc", "! git diff --cached --quiet"], check=False)
    commit_message = _resolve_commit_message(message)
    if staged.code != 0:
        click.echo("[push] No staged changes detected; creating empty commit")
    run(["git", "commit", "--allow-empty", "-m", commit_message], capture=False)  # type: ignore[list-item]
    click.echo(f"[push] Commit message: {commit_message}")
    run(["git", "push", "-u", remote, branch], capture=False)  # type: ignore[list-item]


def _resolve_commit_message(message: str | None) -> str:
    default_message = os.environ.get("COMMIT_MESSAGE", "chore: update").strip() or "chore: update"
    if message is not None:
        return message.strip() or default_message

    env_message = os.environ.get("COMMIT_MESSAGE")
    if env_message is not None:
        final = env_message.strip() or default_message
        click.echo(f"[push] Using commit message from COMMIT_MESSAGE: {final}")
        return final

    if sys.stdin.isatty():
        return click.prompt("[push] Commit message", default=default_message)

    try:
        with open("/dev/tty", "r+", encoding="utf-8", errors="ignore") as tty:
            tty.write(f"[push] Commit message [{default_message}]: ")
            tty.flush()
            response = tty.readline()
    except OSError:
        click.echo("[push] Non-interactive input; using default commit message")
        return default_message
    except KeyboardInterrupt:
        raise SystemExit("[push] Commit aborted by user")

    response = response.strip()
    return response or default_message


if __name__ == "__main__":  # pragma: no cover
    from .cli import main as cli_main

    cli_main(["push", *sys.argv[1:]])
