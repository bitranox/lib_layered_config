"""The wheel ships exactly the package's files, the PEP 561 marker included.

``[tool.hatch.build.targets.wheel] packages`` decides what goes in; an ``include`` beside it is
ignored for files under the package, so a packaging edit can look harmless and still drop or add
a file. These tests compare the built wheel with the package directory itself.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from hatchling.builders.wheel import WheelBuilder

from tests.support.os_markers import os_agnostic

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "src" / "lib_layered_config"
_DIST_INFO_SUFFIX = ".dist-info"


def _package_files() -> set[str]:
    """Every file under the package as a wheel names it, without bytecode caches."""
    return {
        path.relative_to(_PACKAGE.parent).as_posix()
        for path in _PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def _wheel_package_members(tmp_path: Path) -> set[str]:
    wheel = next(iter(WheelBuilder(str(_ROOT)).build(directory=str(tmp_path), versions=["standard"])))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    return {name for name in names if not name.split("/", 1)[0].endswith(_DIST_INFO_SUFFIX)}


@os_agnostic
def test_the_wheel_holds_exactly_the_package_files(tmp_path: Path) -> None:
    expected = _package_files()

    assert len(expected) > 1, "found no package files to compare against"
    assert _wheel_package_members(tmp_path) == expected


@os_agnostic
def test_the_wheel_carries_the_type_marker(tmp_path: Path) -> None:
    assert "lib_layered_config/py.typed" in _wheel_package_members(tmp_path)
