"""A regular file where a deploy destination's directory belongs is refused before anything is written.

A destination below a regular file stats as "not there" (ENOTDIR), so it used to pass the destination
check: the deploy wrote the files it reached first and then failed with ``FileExistsError`` at the
``mkdir`` for the blocked directory. Each test here lists every destination tree afterwards.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import deploy_config
from lib_layered_config.domain.errors import DeployDestinationError
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, unmapped_drive_root, windows_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
IN_THE_WAY = "not a directory\n"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    """A per-OS layer sandbox under *tmp_path*, its environment applied."""
    home = create_layered_sandbox(tmp_path / "root", vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    return home


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    """A source config.toml with a config.d holding one file."""
    source_dir = tmp_path / "source"
    (source_dir / "config.d").mkdir(parents=True)
    (source_dir / "config.d" / "10-db.toml").write_text("[db]\nport = 1\n", encoding="utf-8")
    config = source_dir / "config.toml"
    config.write_text("[service]\nflag = true\n", encoding="utf-8")
    return config


def _tree(root: Path) -> list[str]:
    """Every path below *root*, relative and with forward slashes, or an empty list when it is absent."""
    if not root.exists():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def _refusal(source: Path, *, targets: list[str]) -> str:
    """Deploy *source* to *targets*, require the destination refusal, and return its message."""
    with pytest.raises(DeployDestinationError) as caught:
        deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets, set_permissions=False)
    return str(caught.value)


@os_agnostic
def test_a_file_where_the_dot_d_directory_belongs_is_refused_before_the_main_file(
    sandbox: LayeredSandbox, source: Path
) -> None:
    user_root = sandbox.roots["user"]
    user_root.mkdir(parents=True)
    blocker = user_root / "config.d"
    blocker.write_text(IN_THE_WAY, encoding="utf-8")

    message = _refusal(source, targets=["user"])

    assert message == f"{blocker / '10-db.toml'} cannot be created: {blocker} is not a directory"
    assert _tree(user_root) == ["config.d"]
    assert blocker.read_text(encoding="utf-8") == IN_THE_WAY


@os_agnostic
def test_a_file_where_a_later_target_s_directory_belongs_is_refused_before_the_first_target(
    sandbox: LayeredSandbox, source: Path
) -> None:
    host_root = sandbox.roots["host"]
    host_root.parent.mkdir(parents=True, exist_ok=True)
    host_root.write_text(IN_THE_WAY, encoding="utf-8")
    before = _tree(host_root.parent)

    message = _refusal(source, targets=["user", "host"])

    lines = message.splitlines()
    assert len(lines) == 2, lines  # the host file and its one .d copy
    assert lines[0].startswith(f"{host_root}{os.sep}")
    assert all(line.endswith(f" cannot be created: {host_root} is not a directory") for line in lines)
    assert _tree(sandbox.roots["user"]) == []
    assert _tree(host_root.parent) == before
    assert host_root.read_text(encoding="utf-8") == IN_THE_WAY


@os_agnostic
def test_a_file_where_the_layer_directory_belongs_is_a_destination_refusal(
    sandbox: LayeredSandbox, source: Path
) -> None:
    user_root = sandbox.roots["user"]
    user_root.write_text(IN_THE_WAY, encoding="utf-8")

    message = _refusal(source, targets=["user"])

    assert message.splitlines() == [
        f"{user_root / 'config.toml'} cannot be created: {user_root} is not a directory",
        f"{user_root / 'config.d' / '10-db.toml'} cannot be created: {user_root} is not a directory",
    ]
    assert user_root.read_text(encoding="utf-8") == IN_THE_WAY


@os_agnostic
def test_a_dangling_link_where_the_layer_directory_belongs_is_a_destination_refusal(
    sandbox: LayeredSandbox, source: Path, tmp_path: Path
) -> None:
    user_root = sandbox.roots["user"]
    user_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        user_root.symlink_to(tmp_path / "nowhere", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"this account cannot create symlinks: {exc}")

    message = _refusal(source, targets=["user"])

    assert message.splitlines()[0] == f"{user_root / 'config.toml'} cannot be created: {user_root} is not a directory"
    assert not (tmp_path / "nowhere").exists()


@windows_only
def test_a_layer_root_on_a_drive_that_is_not_there_is_refused_before_the_first_target(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_roaming = f"{unmapped_drive_root()}nowhere\\Roaming"
    monkeypatch.setenv("LIB_LAYERED_CONFIG_APPDATA", missing_roaming)
    app_root = sandbox.roots["app"]

    message = _refusal(source, targets=["app", "user"])

    lines = message.splitlines()
    assert len(lines) == 2, lines  # the user file and its one .d copy
    assert all(line.startswith(missing_roaming) for line in lines)
    assert all(line.endswith(" cannot be created: no directory above it exists") for line in lines)
    assert _tree(app_root) == []
