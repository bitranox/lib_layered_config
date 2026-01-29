"""Invoke the project CLI via uvx from the local development directory."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from ._utils import get_dependencies, get_project_metadata, run

PROJECT = get_project_metadata()

__all__ = ["run_cli"]


def _find_local_dependencies() -> list[str]:
    """Find sibling directories that match project dependencies.

    Scans the parent directory for subdirectories that match dependency names
    and contain a pyproject.toml file (indicating a valid Python project).

    Returns:
        List of absolute paths to local dependency directories.
    """
    project_root = Path.cwd().resolve()
    parent_dir = project_root.parent
    dependencies = get_dependencies()

    local_deps: list[str] = []
    for dep_name in dependencies:
        # Check both underscore and hyphen variants
        variants = [dep_name, dep_name.replace("_", "-")]
        for variant in variants:
            sibling = parent_dir / variant
            if sibling.is_dir() and (sibling / "pyproject.toml").exists():
                local_deps.append(str(sibling))
                break
    return local_deps


def run_cli(args: Sequence[str] | None = None) -> int:
    """Invoke the project CLI via uvx using the local development version.

    Uses --refresh to ensure uvx refreshes all cached data. Also discovers
    sibling directories that match project dependencies and includes them
    with --with flags to pick up local development changes.

    This approach is project-independent: it reads dependencies from
    pyproject.toml and finds matching sibling directories automatically.
    """
    forwarded = list(args) if args else ["--help"]

    # Build command with local dependency paths
    command = ["uvx", "--from", ".", "--refresh"]

    # Add local sibling dependencies
    for local_dep in _find_local_dependencies():
        command.extend(["--with", local_dep])

    command.extend([PROJECT.name, *forwarded])

    result = run(command, capture=False, check=False)
    return result.code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli(sys.argv[1:]))
