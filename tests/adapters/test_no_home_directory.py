"""A process with no home directory still reads every layer but the user layer.

``Path.home()`` raises RuntimeError when HOME is unset and the uid has no passwd entry (a container
running an arbitrary uid), or on Windows when USERPROFILE, HOMEDRIVE and HOMEPATH are all unset. That
used to take down the whole read, app, host and env layers included, and on Windows even with APPDATA
set, because its default was computed eagerly. ``Path.home`` is the operating system's user database,
an edge this suite cannot inject, so it is patched here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import NoReturn

import pytest

import lib_layered_config
from lib_layered_config import ConfigError, HomeDirectoryUnknownError, read_config
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.deploy import deploy_config
from tests.support.os_markers import os_agnostic


def _no_home(cls: type[Path]) -> NoReturn:
    raise RuntimeError("Could not determine home directory.")


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty current directory and a process for which ``Path.home()`` cannot answer."""
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    for name in ("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", "LIB_LAYERED_CONFIG_APPDATA", "LIB_LAYERED_CONFIG_LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(_no_home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def _plant(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _app_roots(tmp_path: Path) -> dict[str, str]:
    """App roots for every platform, each holding ``k = "app"`` in its own layout."""
    _plant(tmp_path / "etc" / "xdg" / "demo" / "config.toml", 'k = "app"\n')
    _plant(tmp_path / "pd" / "Acme" / "Demo" / "config.toml", 'k = "app"\n')
    return {
        "LIB_LAYERED_CONFIG_ETC": str(tmp_path / "etc"),
        "LIB_LAYERED_CONFIG_MAC_APP_ROOT": str(tmp_path / "pd"),
        "LIB_LAYERED_CONFIG_PROGRAMDATA": str(tmp_path / "pd"),
    }


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_with_no_home_the_resolver_skips_only_the_user_layer(work: Path, tmp_path: Path, platform: str) -> None:
    resolver = DefaultPathResolver(
        vendor="Acme", app="Demo", slug="demo", env=_app_roots(tmp_path), platform=platform, cwd=work
    )
    assert list(resolver.user()) == []
    assert list(resolver.dotenv()) == []
    assert len(list(resolver.app())) == 1


@os_agnostic
@pytest.mark.parametrize("variable", ["LIB_LAYERED_CONFIG_APPDATA", "APPDATA"])
def test_a_set_appdata_needs_no_home_on_windows(work: Path, tmp_path: Path, variable: str) -> None:
    # Both: the override returns before the APPDATA branch, so only APPDATA itself shows whether the
    # home-based default is still computed when the variable answers.
    roaming = _plant(tmp_path / "roaming" / "Acme" / "Demo" / "config.toml", 'k = "user"\n')
    env = {**_app_roots(tmp_path), variable: str(tmp_path / "roaming")}
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", env=env, platform="win32", cwd=work)
    assert list(resolver.user()) == [roaming]


@os_agnostic
def test_read_config_with_no_home_loads_the_other_layers_and_warns(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name, value in _app_roots(tmp_path).items():
        monkeypatch.setenv(name, value)

    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"):
        config = read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(work))

    assert config.get("k") == "app"
    skipped = [record for record in caplog.records if record.message == "user_layer_skipped_no_home"]
    assert [record.levelno for record in skipped] == [logging.WARNING]


@os_agnostic
def test_a_user_deploy_with_no_home_is_refused_naming_the_remedy(work: Path, tmp_path: Path) -> None:
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    with pytest.raises(HomeDirectoryUnknownError) as caught:
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], platform="linux")
    # Path.home() reads USERPROFILE on Windows and ignores HOME there, so the remedy names what it reads.
    home_variable = "USERPROFILE" if os.name == "nt" else "HOME"
    assert str(caught.value) == (
        f"cannot determine the home directory for the user layer: set {home_variable} to an absolute path, "
        "or the variable naming the user-layer root "
        "(XDG_CONFIG_HOME, LIB_LAYERED_CONFIG_MAC_HOME_ROOT, LIB_LAYERED_CONFIG_APPDATA)"
    )
    assert list(work.iterdir()) == []


@os_agnostic
def test_the_no_home_error_is_a_config_error_and_still_a_runtime_error() -> None:
    # Every error the library defines derives from ConfigError; RuntimeError, as Path.home() raises,
    # so an existing ``except RuntimeError`` keeps catching it.
    assert issubclass(HomeDirectoryUnknownError, ConfigError)
    assert issubclass(HomeDirectoryUnknownError, RuntimeError)
    assert "HomeDirectoryUnknownError" in lib_layered_config.__all__
