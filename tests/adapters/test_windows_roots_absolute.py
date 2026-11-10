"""A Windows layer root must be an absolute path, whatever supplied it.

``C:\\ProgramData`` is absolute on Windows and RELATIVE everywhere else, so a deploy for Windows
run from Linux or macOS without an override wrote ``./C:\\ProgramData/<Vendor>/<App>/config.toml``
into the current directory and reported success. A relative ``ProgramData`` from the environment
did the same on any OS, and the resolver read from that cwd-relative place too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from lib_cli_exit_tools import get_system_exit_code

from lib_layered_config.adapters.path_resolvers._windows import appdata_root, localappdata_root, program_data_root
from lib_layered_config.cli import main
from lib_layered_config.deploy import deploy_config
from lib_layered_config.domain.errors import ValidationError
from tests.support.os_markers import os_agnostic, posix_only

_Root = Callable[[Mapping[str, str]], Path]

_WINDOWS_ROOT_VARIABLES = (
    "LIB_LAYERED_CONFIG_PROGRAMDATA",
    "LIB_LAYERED_CONFIG_APPDATA",
    "LIB_LAYERED_CONFIG_LOCALAPPDATA",
    "ProgramData",
    "PROGRAMDATA",
    "APPDATA",
    "LOCALAPPDATA",
)


@os_agnostic
@pytest.mark.parametrize(
    ("root", "env"),
    [
        (program_data_root, {"ProgramData": "rel/pd"}),
        (program_data_root, {"LIB_LAYERED_CONFIG_PROGRAMDATA": "rel/pd"}),
        (appdata_root, {"APPDATA": "rel/roaming"}),
        (appdata_root, {"LIB_LAYERED_CONFIG_APPDATA": "rel/roaming"}),
        (localappdata_root, {"LOCALAPPDATA": "rel/local"}),
        (localappdata_root, {"LIB_LAYERED_CONFIG_LOCALAPPDATA": ""}),
    ],
)
def test_a_relative_root_from_the_environment_is_refused(root: _Root, env: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="is not an absolute path"):
        root(env)


@posix_only
def test_the_builtin_programdata_fallback_is_refused_off_windows() -> None:
    with pytest.raises(ValidationError, match="LIB_LAYERED_CONFIG_PROGRAMDATA"):
        program_data_root({})


@os_agnostic
def test_an_absolute_or_unc_root_is_kept(tmp_path: Path) -> None:
    assert program_data_root({"ProgramData": str(tmp_path)}) == tmp_path
    assert program_data_root({"LIB_LAYERED_CONFIG_PROGRAMDATA": "//server/share"}) == Path("//server/share")


def _clear_windows_roots(monkeypatch: pytest.MonkeyPatch, cwd: Path) -> None:
    for name in _WINDOWS_ROOT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(cwd)


@posix_only
def test_a_windows_deploy_off_windows_writes_nothing_into_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    _clear_windows_roots(monkeypatch, work)

    with pytest.raises(ValidationError, match="not an absolute path"):
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["app"], platform="win32")

    assert list(work.iterdir()) == []


@posix_only
def test_the_cli_refuses_a_windows_deploy_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    _clear_windows_roots(monkeypatch, work)
    argv = ["deploy", "--source", str(source), "--vendor", "Acme", "--app", "Demo", "--slug", "demo"]

    code = main([*argv, "--target", "app", "--platform", "windows"], restore_traceback=False)

    assert code == get_system_exit_code(ValueError())
    assert "not an absolute path" in capsys.readouterr().err
    assert list(work.iterdir()) == []
