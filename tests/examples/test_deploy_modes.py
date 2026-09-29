"""Explicit dir_mode / file_mode through deploy_config, on a real filesystem."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config.domain.deploy_mode import DeployModeError
from lib_layered_config.examples.deploy import deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    # Nothing here may depend on the directory the suite was started from.
    monkeypatch.chdir(tmp_path)
    return home


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text("[service]\nflag = true\n", encoding="utf-8")
    return path


def _destination(sandbox: LayeredSandbox, target: str) -> Path:
    return sandbox.roots[target] / "config.toml"


def _deploy(source: Path, *, targets: list[str], **kwargs: Any) -> None:
    deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets, **kwargs)


@os_agnostic
@pytest.mark.parametrize(
    ("kwargs", "fragments"),
    [
        ({"dir_mode": -1}, ["dir_mode: mode -1 is outside 0..0o7777"]),
        (
            {"file_mode": 444},
            ["file_mode: unsafe file mode 0o674", "group write (0o020)", "an execute bit on a file (0o10)"],
        ),
        ({"dir_mode": 0o777}, ["dir_mode: unsafe directory mode 0o777", "group write (0o020)", "world write (0o002)"]),
        ({"dir_mode": 0o770}, ["dir_mode: unsafe directory mode 0o770: group write (0o020)"]),
        ({"file_mode": True}, ["file_mode: a mode must be an int, got bool"]),
    ],
)
def test_a_refused_mode_stops_the_deploy_before_anything_is_written(
    sandbox: LayeredSandbox, source: Path, kwargs: dict[str, object], fragments: list[str]
) -> None:
    with pytest.raises(DeployModeError) as caught:
        _deploy(source, targets=["user"], **kwargs)
    for fragment in fragments:
        assert fragment in str(caught.value)
    destination = _destination(sandbox, "user")
    assert not destination.exists()
    assert not destination.parent.exists()


@os_agnostic
def test_a_huge_dir_mode_is_refused_with_a_bounded_message_not_a_bare_value_error(
    sandbox: LayeredSandbox, source: Path
) -> None:
    """A 5000-digit dir_mode trips CPython's int-to-str conversion limit inside DeployMode's own
    f-strings; deploy_config must still surface a DeployModeError of bounded length."""
    huge = 10**5000
    with pytest.raises(DeployModeError) as caught:
        _deploy(source, targets=["user"], dir_mode=huge)
    message = str(caught.value)
    assert len(message) < 200
    assert message.startswith("dir_mode: mode ")
    assert "outside 0.." in message
    destination = _destination(sandbox, "user")
    assert not destination.exists()
    assert not destination.parent.exists()


@os_agnostic
def test_two_refused_modes_are_reported_together(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(DeployModeError) as caught:
        _deploy(source, targets=["user"], dir_mode=-1, file_mode=0o777)
    lines = str(caught.value).splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("dir_mode: mode -1 is outside 0..0o7777")
    assert lines[1].startswith("file_mode: unsafe file mode 0o777")


@posix_only
def test_both_explicit_modes_are_applied(sandbox: LayeredSandbox, source: Path) -> None:
    _deploy(source, targets=["user"], dir_mode=0o750, file_mode=0o640)
    destination = _destination(sandbox, "user")
    assert (destination.parent.stat().st_mode & 0o7777) == 0o750
    assert (destination.stat().st_mode & 0o7777) == 0o640


@posix_only
def test_only_a_dir_mode_leaves_the_file_at_its_layer_mode(sandbox: LayeredSandbox, source: Path) -> None:
    _deploy(source, targets=["app"], dir_mode=0o750)
    destination = _destination(sandbox, "app")
    assert (destination.parent.stat().st_mode & 0o7777) == 0o750
    assert (destination.stat().st_mode & 0o7777) == 0o644


@posix_only
def test_only_a_file_mode_leaves_the_directory_at_its_layer_mode(sandbox: LayeredSandbox, source: Path) -> None:
    _deploy(source, targets=["user"], file_mode=0o640)
    destination = _destination(sandbox, "user")
    assert (destination.parent.stat().st_mode & 0o7777) == 0o700
    assert (destination.stat().st_mode & 0o7777) == 0o640


@posix_only
def test_dot_d_files_get_the_same_modes(sandbox: LayeredSandbox, source: Path) -> None:
    dot_d = source.with_suffix(".d")
    dot_d.mkdir()
    (dot_d / "10-extra.toml").write_text("[extra]\nx = 1\n", encoding="utf-8")
    _deploy(source, targets=["user"], dir_mode=0o750, file_mode=0o640)
    deployed = _destination(sandbox, "user").with_suffix(".d") / "10-extra.toml"
    assert (deployed.parent.stat().st_mode & 0o7777) == 0o750
    assert (deployed.stat().st_mode & 0o7777) == 0o640
