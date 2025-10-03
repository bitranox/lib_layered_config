from __future__ import annotations

import time
from pathlib import Path
import re
import sys

import click

__all__ = ["release"]

try:
    from ._utils import (
        bootstrap_dev,
        gh_available,
        gh_release_create,
        gh_release_edit,
        gh_release_exists,
        git_branch,
        git_create_annotated_tag,
        git_delete_tag,
        git_push,
        git_tag_exists,
        read_version_from_pyproject,
        run,
        sync_packaging,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import (
        bootstrap_dev,
        gh_available,
        gh_release_create,
        gh_release_edit,
        gh_release_exists,
        git_branch,
        git_create_annotated_tag,
        git_delete_tag,
        git_push,
        git_tag_exists,
        read_version_from_pyproject,
        run,
        sync_packaging,
    )


def release(*, remote: str = "origin", retries: int = 5, retry_wait: float = 3.0) -> None:
    version = read_version_from_pyproject(Path("pyproject.toml"))
    if not version or not _looks_like_semver(version):
        raise SystemExit("[release] Could not read version X.Y.Z from pyproject.toml")
    click.echo(f"[release] Target version {version}")

    # Verify clean working tree
    _ensure_clean()

    # Ensure dev tools for build/test flows (optional)
    bootstrap_dev()

    click.echo("[release] Sync packaging with pyproject before checks")
    sync_packaging()

    # Run local checks
    run(["python", "scripts/test.py"])  # type: ignore[list-item]

    # Remove stray 'v' tag (local and remote)
    git_delete_tag("v", remote=remote)

    # Push branch
    branch = git_branch()
    click.echo(f"[release] Pushing branch {branch} to {remote}")
    git_push(remote, branch)

    # Tag and push
    tag = f"v{version}"
    if git_tag_exists(tag):
        click.echo(f"[release] Tag {tag} already exists locally")
    else:
        git_create_annotated_tag(tag, f"Release {tag}")
    click.echo(f"[release] Pushing tag {tag}")
    git_push(remote, tag)

    # Create or edit GitHub release
    if gh_available():
        if gh_release_exists(tag):
            gh_release_edit(tag, tag, f"Release {tag}")
        else:
            click.echo(f"[release] Creating GitHub release {tag}")
            gh_release_create(tag, tag, f"Release {tag}")
    else:
        click.echo("[release] gh CLI not found; skipping GitHub release creation")

    # Retry packaging sync
    for i in range(1, int(retries) + 1):
        click.echo(f"[release] Sync packaging attempt {i}")
        sync_packaging()
        if not _packaging_has_placeholders():
            break
        time.sleep(float(retry_wait))

    # Commit packaging changes, if any
    if run(["bash", "-lc", "! git diff --quiet packaging"], check=False).code == 0:
        run(["git", "add", "packaging"])  # type: ignore[list-item]
        run(["git", "commit", "-m", f"chore(packaging): sync for {tag}"])
        git_push(remote, branch)
    else:
        click.echo("[release] No packaging changes to commit")

    click.echo(f"[release] Done: {tag} tagged and pushed.")


def _ensure_clean() -> None:
    if run(["bash", "-lc", "! git diff --quiet || ! git diff --cached --quiet"], check=False).code == 0:
        raise SystemExit("[release] Working tree not clean. Commit or stash changes first.")


def _packaging_has_placeholders() -> bool:
    return run(["bash", "-lc", "grep -R '<fill-me>' -n packaging >/dev/null"], check=False).code == 0


def _looks_like_semver(v: str) -> bool:
    return bool(re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", v))


if __name__ == "__main__":  # pragma: no cover
    from scripts.cli import main as cli_main

    cli_main(["release", *sys.argv[1:]])
