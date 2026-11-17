"""Explicit dir_mode / file_mode through deploy_config, on a real filesystem."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import pytest

from lib_layered_config.deploy import deploy_config
from lib_layered_config.domain.deploy_mode import DeployMode, DeployModeError, ModeKind
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


class _ExplicitModes(TypedDict, total=False):
    """The explicit modes a parametrized case hands to deploy_config."""

    dir_mode: int | None
    file_mode: int | None


def _deploy(source: Path, *, targets: list[str], dir_mode: int | None = None, file_mode: int | None = None) -> None:
    deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets, dir_mode=dir_mode, file_mode=file_mode)


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
    sandbox: LayeredSandbox, source: Path, kwargs: _ExplicitModes, fragments: list[str]
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


@posix_only
def test_a_deploy_mode_object_is_applied_like_the_int_it_holds(sandbox: LayeredSandbox, source: Path) -> None:
    deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        targets=["user"],
        dir_mode=DeployMode(0o750, ModeKind.DIRECTORY),
        file_mode=DeployMode(0o640, ModeKind.FILE),
    )
    destination = _destination(sandbox, "user")
    assert (destination.parent.stat().st_mode & 0o7777) == 0o750
    assert (destination.stat().st_mode & 0o7777) == 0o640


@os_agnostic
def test_a_deploy_mode_object_beside_an_int_is_accepted(sandbox: LayeredSandbox, source: Path) -> None:
    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        targets=["user"],
        dir_mode=0o700,
        file_mode=DeployMode.from_text("600", ModeKind.FILE),
    )
    assert [result.destination for result in results] == [_destination(sandbox, "user")]


@os_agnostic
def test_a_deploy_mode_of_the_wrong_kind_is_refused_naming_both_kinds(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(DeployModeError) as caught:
        deploy_config(
            source,
            vendor=VENDOR,
            app=APP,
            slug=SLUG,
            targets=["user"],
            dir_mode=DeployMode(0o600, ModeKind.FILE),
            file_mode=DeployMode(0o700, ModeKind.DIRECTORY),
        )
    assert str(caught.value).splitlines() == [
        "dir_mode: got a file mode (0o600); dir_mode takes a directory mode",
        "file_mode: got a directory mode (0o700); file_mode takes a file mode",
    ]
    assert not _destination(sandbox, "user").parent.exists()
