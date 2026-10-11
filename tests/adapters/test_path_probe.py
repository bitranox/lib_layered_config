"""probe_path classifies a path the same way on every Python, and nothing else asks pathlib.

Before Python 3.14, ``Path.is_file()``/``is_dir()``/``exists()`` raise ``PermissionError`` when a
directory on the path cannot be entered; from 3.14 they return ``False``. ``probe_path`` reads the
``stat`` error itself, and the read path uses only it.
"""

from __future__ import annotations

import ast
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError
from lib_layered_config.adapters._path_probe import PathKind, checked_kind, probe_path
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Iterator

# Root bypasses directory permissions, so no wall can be built while running as root.
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
needs_wall = pytest.mark.skipif(_RUNS_AS_ROOT, reason="root bypasses directory permissions")

_SRC = Path(__file__).resolve().parents[2] / "src" / "lib_layered_config"


@pytest.fixture
def walled_file(tmp_path: Path) -> Iterator[Path]:
    wall = tmp_path / "wall"
    wall.mkdir()
    (wall / "config.toml").write_text("", encoding="utf-8")
    wall.chmod(0)
    yield wall / "config.toml"
    wall.chmod(stat.S_IRWXU)


@os_agnostic
def test_probe_classifies_missing_file_and_directory(tmp_path: Path) -> None:
    (tmp_path / "f.toml").write_text("", encoding="utf-8")

    assert probe_path(tmp_path / "absent.toml").kind is PathKind.MISSING
    assert probe_path(tmp_path / "f.toml").kind is PathKind.FILE
    assert probe_path(tmp_path).kind is PathKind.DIRECTORY


@os_agnostic
def test_probe_reads_a_path_below_a_file_as_missing(tmp_path: Path) -> None:
    (tmp_path / "f.toml").write_text("", encoding="utf-8")

    assert probe_path(tmp_path / "f.toml" / "config.toml").kind is PathKind.MISSING


@posix_only
def test_probe_reads_a_symlink_loop_as_missing(tmp_path: Path) -> None:
    (tmp_path / "a").symlink_to(tmp_path / "b")
    (tmp_path / "b").symlink_to(tmp_path / "a")

    assert probe_path(tmp_path / "a").kind is PathKind.MISSING


@posix_only
@needs_wall
def test_probe_reports_a_path_inside_an_unenterable_directory_as_cannot_check(walled_file: Path) -> None:
    probe = probe_path(walled_file)

    assert probe.kind is PathKind.CANNOT_CHECK
    assert isinstance(probe.error, PermissionError)


@posix_only
@needs_wall
def test_checked_kind_refuses_a_path_it_cannot_check_naming_it(walled_file: Path) -> None:
    with pytest.raises(InvalidFormatError, match="cannot be read") as caught:
        checked_kind(walled_file)

    assert str(walled_file) in str(caught.value)
    assert not isinstance(caught.value, LayerLoadError)  # read_config wraps it; the adapter does not


@os_agnostic
def test_checked_kind_passes_every_answer_it_can_give_through(tmp_path: Path) -> None:
    assert checked_kind(tmp_path / "absent.toml") is PathKind.MISSING
    assert checked_kind(tmp_path) is PathKind.DIRECTORY


# --- nothing in the read path asks pathlib again -----------------------------------------------

_PATHLIB_PROBES = frozenset({"is_file", "is_dir", "exists"})
# examples/ only WRITES (deploy, generate): a wall there fails at the write on every Python.
_EXEMPT = ("adapters/_path_probe.py", "examples/")


@os_agnostic
def test_the_read_path_never_asks_pathlib_whether_a_path_exists() -> None:
    scanned: list[str] = []
    offenders: list[str] = []
    for source in sorted(_SRC.rglob("*.py")):
        relative = source.relative_to(_SRC).as_posix()
        if relative.startswith(_EXEMPT):
            continue
        scanned.append(relative)
        tree = ast.parse(source.read_text(encoding="utf-8"))
        offenders.extend(
            f"{relative}:{node.lineno} .{node.func.attr}()"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _PATHLIB_PROBES
        )

    assert len(scanned) > 20, f"scanned only {len(scanned)} modules under {_SRC}"
    assert offenders == []
