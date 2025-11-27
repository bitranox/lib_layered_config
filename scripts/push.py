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

__all__ = ["push"]

_DEFAULT_REMOTE = get_default_remote()


def push(*, remote: str = _DEFAULT_REMOTE, message: str | None = None) -> None:
    """Run checks, commit changes, and push the current branch."""

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
