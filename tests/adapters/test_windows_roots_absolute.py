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


def _user_only_windows_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    """Clear every Windows root, then set only the APPDATA override, as a user-only deploy needs."""
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    appdata = tmp_path / "appdata"
    _clear_windows_roots(monkeypatch, work)
    monkeypatch.setenv("LIB_LAYERED_CONFIG_APPDATA", str(appdata))
    return source, work, appdata


@posix_only
def test_a_user_only_windows_deploy_needs_no_programdata_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, work, appdata = _user_only_windows_env(monkeypatch, tmp_path)

    results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], platform="win32")

    assert [result.destination for result in results] == [appdata / "Acme" / "Demo" / "config.toml"]
    assert list(work.iterdir()) == []


@posix_only
def test_the_cli_deploys_a_user_only_windows_target_without_programdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, work, appdata = _user_only_windows_env(monkeypatch, tmp_path)
    argv = ["deploy", "--source", str(source), "--vendor", "Acme", "--app", "Demo", "--slug", "demo"]

    code = main([*argv, "--target", "user", "--platform", "windows", "--batch"], restore_traceback=False)

    assert code == 0
    assert (appdata / "Acme" / "Demo" / "config.toml").read_text(encoding="utf-8") == "a = 1\n"
    assert list(work.iterdir()) == []


@posix_only
def test_a_planted_relative_programdata_tree_does_not_decide_the_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, work, appdata = _user_only_windows_env(monkeypatch, tmp_path)
    planted = work / "C:\\ProgramData" / "Acme" / "Demo" / "config.toml"
    planted.parent.mkdir(parents=True)
    planted.write_text('[lib_layered_config.default_permissions]\nuser_file = "0o640"\n', encoding="utf-8")

    deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], platform="win32")

    assert ((appdata / "Acme" / "Demo" / "config.toml").stat().st_mode & 0o777) == 0o600


@os_agnostic
@pytest.mark.parametrize(
    ("value", "shown"),
    [("rel\\dir", "'rel\\dir'"), ("rel\ndir", "'rel\\u000adir'")],
)
def test_a_refused_root_is_named_with_one_backslash_and_its_control_characters_escaped(value: str, shown: str) -> None:
    # User decision 2026-11-16 (R2-F4): the path was printed with repr, which doubled each backslash.
    with pytest.raises(ValidationError) as caught:
        program_data_root({"LIB_LAYERED_CONFIG_PROGRAMDATA": value})

    assert f"root {shown} is not an absolute path" in str(caught.value)
