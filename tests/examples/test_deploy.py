from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

from lib_layered_config.examples import deploy_config

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture
def source_config(tmp_path: Path) -> Path:
    config_file = tmp_path / "source.toml"
    config_file.write_text("[service]\nendpoint = 'https://api.example.com'\n", encoding="utf-8")
    return config_file


def _prepare_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    if sys.platform.startswith("win"):
        program_data = tmp_path / "ProgramData"
        appdata = tmp_path / "AppData" / "Roaming"
        local = tmp_path / "AppData" / "Local"
        monkeypatch.setenv("LIB_LAYERED_CONFIG_PROGRAMDATA", str(program_data))
        monkeypatch.setenv("LIB_LAYERED_CONFIG_APPDATA", str(appdata))
        monkeypatch.setenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", str(local))
        return {
            "app": program_data / VENDOR / APP,
            "user": appdata / VENDOR / APP,
            "host": program_data / VENDOR / APP / "hosts",
        }
    if sys.platform == "darwin":
        app_support = tmp_path / "Library" / "Application Support"
        home_support = tmp_path / "HomeLibrary" / "Application Support"
        monkeypatch.setenv("LIB_LAYERED_CONFIG_MAC_APP_ROOT", str(app_support))
        monkeypatch.setenv("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", str(home_support))
        return {
            "app": app_support / VENDOR / APP,
            "user": home_support / VENDOR / APP,
            "host": app_support / VENDOR / APP / "hosts",
        }
    etc_root = tmp_path / "etc"
    xdg_root = tmp_path / "xdg"
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(etc_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))
    return {
        "app": etc_root / SLUG,
        "user": xdg_root / SLUG,
        "host": (etc_root / SLUG / "hosts"),
    }


def test_deploy_config_creates_app_and_user(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    roots = _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr("socket.gethostname", lambda: "deploy-host")

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app", "user"],
        slug=SLUG,
    )

    app_path = roots["app"] / "config.toml"
    user_path = roots["user"] / "config.toml"

    assert app_path in deployed
    assert user_path in deployed
    assert "endpoint" in app_path.read_text(encoding="utf-8")
    assert "endpoint" in user_path.read_text(encoding="utf-8")


def test_deploy_config_host_target(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    roots = _prepare_env(tmp_path, monkeypatch)
    monkeypatch.setattr("socket.gethostname", lambda: "host-one")

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["host"],
        slug=SLUG,
    )

    host_path = roots["host"] / "host-one.toml"
    assert deployed == [host_path]
    assert host_path.exists()


def test_deploy_config_skips_existing(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    roots = _prepare_env(tmp_path, monkeypatch)
    existing = roots["app"] / "config.toml"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("[existing]\nvalue=1\n", encoding="utf-8")

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
    )

    assert deployed == []
    assert existing.read_text(encoding="utf-8") == "[existing]\nvalue=1\n"


def test_deploy_config_invalid_target(source_config: Path) -> None:
    with pytest.raises(ValueError):
        deploy_config(source_config, vendor=VENDOR, app=APP, targets=["invalid"])


def test_deploy_config_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        deploy_config(missing, vendor=VENDOR, app=APP, targets=["app"])
