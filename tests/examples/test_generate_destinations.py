"""generate_examples refuses an example path it would write through, the way deploy does.

User decisions 2026-11-16 (R3-F3): "Same rules as deploy", scoped to "Only paths it would write",
writing through "Deploy's writer, as deploy". With ``force`` every example path that is a symbolic
link or not a regular file is refused before anything is written; without ``force`` only a link
that resolves to nothing (the one case a plain create wrote through) is refused, and what is already
there is kept as before. An example that is written goes through deploy's writer with permission
setting off, so a hard-linked example is rewritten in place, as deploy does.
"""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import GenerateDestinationError, generate_examples
from lib_layered_config.generate import generate_examples_report
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

_LINK_REFUSAL = "is a symbolic link; generate neither writes through nor replaces one"
_NOT_REGULAR_REFUSAL = "is not a regular file; generate writes only regular files"


def _generate(destination: Path, *, force: bool) -> list[Path]:
    return generate_examples(destination, slug="demo", vendor="Acme", app="Demo", force=force, platform="posix")


def _example_paths(tmp_path: Path) -> list[Path]:
    """Every path generation writes, learned from a run in a scratch destination."""
    scratch = tmp_path / "scratch"
    return sorted(path.relative_to(scratch) for path in _generate(scratch, force=False))


def _first_example(tmp_path: Path) -> tuple[Path, Path]:
    """A fresh destination and the first example path in it, with its parent directory made."""
    destination = tmp_path / "dest"
    target = destination / _example_paths(tmp_path)[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    return destination, target


def _make_fifo(path: Path) -> None:
    assert sys.platform != "win32"  # posix_only; tells the checker os.mkfifo exists here
    os.mkfifo(path)


def _files_under(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())


@os_agnostic
def test_force_refuses_a_directory_at_an_example_path_and_writes_nothing(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    target.mkdir()

    with pytest.raises(GenerateDestinationError) as caught:
        _generate(destination, force=True)

    assert str(caught.value) == f"{target} {_NOT_REGULAR_REFUSAL}"
    assert _files_under(destination) == []


@os_agnostic
def test_force_names_every_refused_path_one_line_each(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    first, second = (destination / path for path in _example_paths(tmp_path)[:2])
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    with pytest.raises(GenerateDestinationError) as caught:
        _generate(destination, force=True)

    assert sorted(str(caught.value).splitlines()) == sorted(
        [f"{first} {_NOT_REGULAR_REFUSAL}", f"{second} {_NOT_REGULAR_REFUSAL}"]
    )


@posix_only
def test_force_refuses_a_fifo_instead_of_waiting_on_it(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    _make_fifo(target)

    with pytest.raises(GenerateDestinationError, match=_NOT_REGULAR_REFUSAL):
        _generate(destination, force=True)

    assert stat.S_ISFIFO(target.lstat().st_mode)


@posix_only
def test_force_refuses_a_symlink_and_leaves_the_file_it_points_at(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    target.symlink_to(outside)

    with pytest.raises(GenerateDestinationError) as caught:
        _generate(destination, force=True)

    assert str(caught.value) == f"{target} {_LINK_REFUSAL}"
    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"


@posix_only
@pytest.mark.parametrize("force", [False, True], ids=["kept-mode", "force"])
def test_a_link_to_nothing_is_refused_and_nothing_is_created_at_its_target(tmp_path: Path, *, force: bool) -> None:
    destination, target = _first_example(tmp_path)
    outside = tmp_path / "created-outside.txt"
    target.symlink_to(outside)

    with pytest.raises(GenerateDestinationError) as caught:
        _generate(destination, force=force)

    assert str(caught.value) == f"{target} {_LINK_REFUSAL}"
    assert not outside.exists()


@posix_only
def test_a_link_looping_on_itself_is_refused_without_force(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    target.symlink_to(target)

    with pytest.raises(GenerateDestinationError, match=_LINK_REFUSAL):
        _generate(destination, force=False)


@posix_only
@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_without_force_what_is_already_there_is_kept(tmp_path: Path, kind: str) -> None:
    destination, target = _first_example(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    make = {
        "symlink": lambda: target.symlink_to(outside),
        "fifo": lambda: _make_fifo(target),
        "directory": target.mkdir,
    }
    make[kind]()

    report = generate_examples_report(
        destination, slug="demo", vendor="Acme", app="Demo", force=False, platform="posix"
    )

    assert target in report.kept
    assert target not in report.created
    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"


@os_agnostic
def test_force_rewrites_a_hard_linked_example_in_place_as_deploy_does(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    target.write_text("OLD\n", encoding="utf-8")
    other = tmp_path / "other-name.txt"
    os.link(target, other)

    _generate(destination, force=True)

    assert other.stat().st_ino == target.stat().st_ino
    assert other.read_text(encoding="utf-8") == target.read_text(encoding="utf-8") != "OLD\n"


@os_agnostic
def test_force_replaces_a_plain_example_by_rename_rather_than_rewriting_it(tmp_path: Path) -> None:
    """A rename, so a write that fails half-way leaves the old example whole; it shows as a new inode."""
    destination, target = _first_example(tmp_path)
    target.write_text("OLD\n", encoding="utf-8")
    before = target.stat().st_ino

    _generate(destination, force=True)

    assert target.stat().st_ino != before
    assert target.read_text(encoding="utf-8") != "OLD\n"


@posix_only
def test_force_keeps_the_mode_of_the_example_it_replaces(tmp_path: Path) -> None:
    destination, target = _first_example(tmp_path)
    target.write_text("OLD\n", encoding="utf-8")
    target.chmod(0o640)

    _generate(destination, force=True)

    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert target.read_text(encoding="utf-8") != "OLD\n"


@os_agnostic
def test_force_leaves_no_temporary_file_beside_the_examples(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    _generate(destination, force=False)

    rewritten = _generate(destination, force=True)

    assert _files_under(destination) == sorted(rewritten)


@os_agnostic
def test_examples_keep_this_platform_s_line_endings(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    written = _generate(destination, force=False)
    _generate(destination, force=True)

    for path in written:
        data = path.read_bytes()
        assert data.count(os.linesep.encode()) == data.count(b"\n"), path
