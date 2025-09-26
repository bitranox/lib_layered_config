from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from lib_layered_config.examples import deploy_config


@pytest.fixture
def source_config(tmp_path: Path) -> Path:
    config_file = tmp_path / "source.toml"
    config_file.write_text("[service]\nendpoint = 'https://api.example.com'\n", encoding="utf-8")
    return config_file


def test_deploy_config_creates_app_and_user(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(tmp_path / "etc"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr("socket.gethostname", lambda: "deploy-host")

    deployed = deploy_config(
        source_config,
        vendor="Acme",
        app="Demo",
        targets=["app", "user"],
        slug="demo",
    )

    app_path = Path(os.environ["LIB_LAYERED_CONFIG_ETC"]) / "demo" / "config.toml"
    user_path = Path(os.environ["XDG_CONFIG_HOME"]) / "demo" / "config.toml"

    assert app_path in deployed
    assert user_path in deployed
    assert "endpoint" in app_path.read_text(encoding="utf-8")
    assert "endpoint" in user_path.read_text(encoding="utf-8")


def test_deploy_config_host_target(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(tmp_path / "etc"))
    monkeypatch.setattr("socket.gethostname", lambda: "host-one")

    deployed = deploy_config(
        source_config,
        vendor="Acme",
        app="Demo",
        targets=["host"],
        slug="demo",
    )

    host_path = Path(os.environ["LIB_LAYERED_CONFIG_ETC"]) / "demo" / "hosts" / "host-one.toml"
    assert deployed == [host_path]
    assert host_path.exists()


def test_deploy_config_skips_existing(tmp_path: Path, monkeypatch, source_config: Path) -> None:
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(tmp_path / "etc"))
    existing = Path(os.environ["LIB_LAYERED_CONFIG_ETC"]) / "demo" / "config.toml"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("[existing]\nvalue=1\n", encoding="utf-8")

    deployed = deploy_config(
        source_config,
        vendor="Acme",
        app="Demo",
        targets=["app"],
        slug="demo",
    )

    assert deployed == []
    assert existing.read_text(encoding="utf-8") == "[existing]\nvalue=1\n"


def test_deploy_config_invalid_target(source_config: Path) -> None:
    with pytest.raises(ValueError):
        deploy_config(source_config, vendor="Acme", app="Demo", targets=["invalid"])


def test_deploy_config_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        deploy_config(missing, vendor="Acme", app="Demo", targets=["app"])
