"""An example path whose directory cannot be made is refused before anything is written, as deploy refuses it.

An example path below a regular file stats as "not there" (ENOTDIR), so it passed the up-front check:
generation wrote the examples it reached first and then failed with ``FileExistsError`` at the
``mkdir`` for the blocked directory (``NotADirectoryError`` when the destination itself was a file).
Each test here lists the destination tree afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import GenerateDestinationError, generate_examples
from lib_layered_config.generate import generated_before_failure
from tests.support.os_markers import os_agnostic, unmapped_drive_root, windows_only

if TYPE_CHECKING:
    from pathlib import Path

IN_THE_WAY = "not a directory\n"
BLOCKED = " cannot be created: {ancestor} is not a directory"


def _refusal(destination: Path | str, *, force: bool, platform: str = "posix") -> list[str]:
    """Generate into *destination*, require the refusal with nothing written, and return its lines."""
    with pytest.raises(GenerateDestinationError) as caught:
        generate_examples(destination, slug="demo", vendor="Acme", app="Demo", force=force, platform=platform)
    assert generated_before_failure(caught.value) == []
    return str(caught.value).splitlines()


def _tree(root: Path) -> list[str]:
    """Every path below *root*, relative and with forward slashes."""
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


@os_agnostic
@pytest.mark.parametrize("force", [False, True], ids=["kept-mode", "force"])
def test_a_file_where_the_user_example_directory_belongs_is_refused_before_the_first_example(
    tmp_path: Path, *, force: bool
) -> None:
    destination = tmp_path / "dest"
    blocker = destination / "home" / "demo"
    blocker.parent.mkdir(parents=True)
    blocker.write_text(IN_THE_WAY, encoding="utf-8")

    lines = _refusal(destination, force=force)

    assert lines == [
        f"{blocker / 'config.toml'}{BLOCKED.format(ancestor=blocker)}",
        f"{blocker / 'config.d' / '10-override.toml'}{BLOCKED.format(ancestor=blocker)}",
    ]
    assert _tree(destination) == ["home", "home/demo"]
    assert blocker.read_text(encoding="utf-8") == IN_THE_WAY


@os_agnostic
def test_a_file_where_the_dot_d_directory_belongs_is_refused_before_the_first_example(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    blocker = destination / "home" / "demo" / "config.d"
    blocker.parent.mkdir(parents=True)
    blocker.write_text(IN_THE_WAY, encoding="utf-8")

    lines = _refusal(destination, force=False)

    assert lines == [f"{blocker / '10-override.toml'}{BLOCKED.format(ancestor=blocker)}"]
    assert _tree(destination) == ["home", "home/demo", "home/demo/config.d"]


@os_agnostic
def test_a_destination_that_is_a_file_is_refused_for_every_example(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    destination.write_text(IN_THE_WAY, encoding="utf-8")

    lines = _refusal(destination, force=False)

    assert len(lines) == 5, lines  # four layer examples and .env.example
    assert all(line.startswith(str(destination)) for line in lines)
    assert all(line.endswith(BLOCKED.format(ancestor=destination)) for line in lines)
    assert destination.read_text(encoding="utf-8") == IN_THE_WAY


@os_agnostic
def test_an_existing_example_below_a_directory_is_still_kept(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    first = generate_examples(destination, slug="demo", vendor="Acme", app="Demo", platform="posix")

    again = generate_examples(destination, slug="demo", vendor="Acme", app="Demo", platform="posix")

    assert len(first) == 5
    assert again == []


@windows_only
def test_a_destination_on_a_drive_that_is_not_there_is_refused_for_every_example() -> None:
    destination = f"{unmapped_drive_root()}nowhere"

    lines = _refusal(destination, force=False, platform="windows")

    assert len(lines) == 5, lines
    assert all(line.startswith(destination) for line in lines)
    assert all(line.endswith(" cannot be created: no directory above it exists") for line in lines)
