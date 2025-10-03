from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import rich_click as click

try:
    from ._utils import git_branch, run, sync_packaging
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import git_branch, run, sync_packaging

__all__ = ["push"]


def push(*, remote: str = "origin", message: Optional[str] = None) -> None:
    """Run checks, sync packaging, commit changes, and push the current branch."""

    click.echo("[push] Sync packaging with pyproject before checks")
    sync_packaging()

    click.echo("[push] Running local checks (scripts/test.py)")
    run(["python", "scripts/test.py"])  # type: ignore[list-item]

    click.echo("[push] Sync packaging with pyproject before commit")
    sync_packaging()

    click.echo("[push] Committing and pushing (single attempt)")
    run(["git", "add", "-A"])  # stage all
    staged = run(["bash", "-lc", "! git diff --cached --quiet"], check=False)
    commit_message = _resolve_commit_message(message)
    if staged.code != 0:
        click.echo("[push] No staged changes detected; creating empty commit")
    run(["git", "commit", "--allow-empty", "-m", commit_message])  # type: ignore[list-item]
    branch = git_branch()
    run(["git", "push", "-u", remote, branch])  # type: ignore[list-item]


def _resolve_commit_message(message: Optional[str]) -> str:
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
    from scripts.cli import main as cli_main

    cli_main(["push", *sys.argv[1:]])
