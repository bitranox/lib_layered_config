"""The sdist ships the package, its tests and docs, and nothing private from the checkout.

hatchling builds the sdist from the working tree and honours only the root ``.gitignore``, so a
file kept out of git through ``.git/info/exclude`` or a nested ``.gitignore`` (handover notes,
review ledgers, ``.remember/`` session archives) went into a locally built sdist. The allowlist in
``[tool.hatch.build.targets.sdist]`` closes that; these tests fail when it is missing or too wide.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
from hatchling.builders.sdist import SdistBuilder

from tests.support.os_markers import os_agnostic

_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED_DIRS = {"src", "tests", "docs", "notebooks"}
_ALLOWED_FILES = {
    "pyproject.toml",
    "conftest.py",  # the root fixtures, which the src doctests need too
    "PKG-INFO",
    ".gitignore",  # hatchling always adds it, so a rebuild from the sdist excludes the same files
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
}


def _sdist_members(tmp_path: Path) -> list[str]:
    archive = next(iter(SdistBuilder(str(_ROOT)).build(directory=str(tmp_path), versions=["standard"])))
    with tarfile.open(archive) as sdist:
        names = [member.name for member in sdist.getmembers() if member.isfile()]
    return [name.split("/", 1)[1] for name in names]


@os_agnostic
def test_every_sdist_member_sits_under_the_allowlist(tmp_path: Path) -> None:
    members = _sdist_members(tmp_path)

    outside = [name for name in members if name not in _ALLOWED_FILES and name.split("/", 1)[0] not in _ALLOWED_DIRS]

    assert members, "the sdist holds no files"
    assert outside == []


@os_agnostic
def test_the_sdist_carries_what_its_test_suite_needs(tmp_path: Path) -> None:
    members = set(_sdist_members(tmp_path))

    needed = {"conftest.py", "tests/conftest.py", "tests/support/__init__.py", "src/lib_layered_config/py.typed"}
    assert needed <= members


@os_agnostic
def test_no_file_git_hides_without_the_root_gitignore_sits_under_an_allowlisted_dir() -> None:
    """Ask git what hatchling sees: untracked files the ROOT .gitignore alone does not exclude.

    ``--exclude-standard`` would also read ``.git/info/exclude`` and nested ``.gitignore`` files and
    so hide exactly the files that still ship.
    """
    git = shutil.which("git")
    if git is None or not (_ROOT / ".git").exists():
        pytest.skip("needs a git checkout (an unpacked sdist has none)")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    # The tests redirect HOME, so the user's global safe.directory is not read; a checkout another user owns
    # (an elevated clone on Windows, a shared mount) would make git refuse with exit 128.
    command = [
        git,
        "-c",
        f"safe.directory={_ROOT.as_posix()}",
        "-C",
        str(_ROOT),
        "ls-files",
        "--others",
        "-z",
        f"--exclude-from={_ROOT / '.gitignore'}",
        "--",
    ]
    listed = subprocess.run(  # noqa: S603 - argv is the resolved git binary and constants, no shell
        [*command, *sorted(_ALLOWED_DIRS)], capture_output=True, check=True, env=env, encoding="utf-8", errors="replace"
    ).stdout

    assert [path for path in listed.split("\0") if path] == []
