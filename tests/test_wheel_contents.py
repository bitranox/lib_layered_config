"""The wheel ships exactly the package's tracked files, the PEP 561 marker included.

``[tool.hatch.build.targets.wheel] packages`` decides what goes in; an ``include`` beside it is
ignored for files under the package, so a packaging edit can look harmless and still drop or add
a file. These tests build the wheel from the files git tracks, as CI builds it from a clean clone,
and compare it with the tracked files under the package: an untracked or gitignored file left in
``src/`` by local work neither passes nor fails them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from tests.support.os_markers import os_agnostic

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_PREFIX = "src/lib_layered_config/"
_DIST_INFO_SUFFIX = ".dist-info"


def _tracked_files() -> list[str]:
    """Every file git tracks in the checkout, as a POSIX path relative to the project root.

    The child gets no ``GIT_*`` variable: a hook or a linked worktree exports ``GIT_DIR``, which would
    point ``ls-files`` at another repository.
    """
    git = shutil.which("git")
    if git is None or not (_ROOT / ".git").exists():
        pytest.skip("needs a git checkout (an unpacked sdist has none)")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    # The tests redirect HOME, so the user's global safe.directory is not read; a checkout another user owns
    # (an elevated clone on Windows, a shared mount) would make git refuse with exit 128.
    listed = subprocess.run(  # noqa: S603 - argv is the resolved git binary and constants, no shell
        [git, "-c", f"safe.directory={_ROOT.as_posix()}", "-C", str(_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return [path for path in listed.split("\0") if path]


def _tracked_package_files() -> set[str]:
    """The tracked files under the package, named as the wheel names them."""
    return {path.removeprefix("src/") for path in _tracked_files() if path.startswith(_PACKAGE_PREFIX)}


def _wheel_package_members(tmp_path: Path) -> set[str]:
    """Build the wheel from a copy of the tracked files and return its members outside ``.dist-info``."""
    tree = tmp_path / "tracked"
    for relative in _tracked_files():
        source = _ROOT / relative
        if not source.is_file():  # tracked but deleted in the working tree: not part of a build
            continue
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    wheel = next(iter(WheelBuilder(str(tree)).build(directory=str(tmp_path / "dist"), versions=["standard"])))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    return {name for name in names if not name.split("/", 1)[0].endswith(_DIST_INFO_SUFFIX)}


@os_agnostic
def test_the_wheel_holds_exactly_the_tracked_package_files(tmp_path: Path) -> None:
    expected = _tracked_package_files()

    assert len(expected) > 1, "found no tracked package files to compare against"
    assert _wheel_package_members(tmp_path) == expected


@os_agnostic
def test_the_wheel_carries_the_type_marker(tmp_path: Path) -> None:
    assert "lib_layered_config/py.typed" in _wheel_package_members(tmp_path)
