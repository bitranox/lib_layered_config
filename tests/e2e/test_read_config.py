from __future__ import annotations

import sys
from pathlib import Path

from lib_layered_config import read_config, read_config_raw

VENDOR = "Acme"
APP = "ConfigKit"
SLUG = "config-kit"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _platform_paths(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str], Path]:
    overrides: dict[str, str] = {}
    if sys.platform.startswith("win"):
        program_data = tmp_path / "ProgramData"
        overrides["LIB_LAYERED_CONFIG_PROGRAMDATA"] = str(program_data)
        appdata = tmp_path / "AppData" / "Roaming"
        local = tmp_path / "AppData" / "Local"
        overrides["LIB_LAYERED_CONFIG_APPDATA"] = str(appdata)
        overrides["LIB_LAYERED_CONFIG_LOCALAPPDATA"] = str(local)
        app_dir = program_data / VENDOR / APP
        host_dir = app_dir / "hosts"
        user_dir = appdata / VENDOR / APP
        start_dir = user_dir
    elif sys.platform == "darwin":
        app_support = tmp_path / "Library" / "Application Support"
        home_support = tmp_path / "HomeLibrary" / "Application Support"
        overrides["LIB_LAYERED_CONFIG_MAC_APP_ROOT"] = str(app_support)
        overrides["LIB_LAYERED_CONFIG_MAC_HOME_ROOT"] = str(home_support)
        app_dir = app_support / VENDOR / APP
        host_dir = app_dir / "hosts"
        user_dir = home_support / VENDOR / APP
        start_dir = user_dir
    else:
        etc_root = tmp_path / "etc"
        overrides["LIB_LAYERED_CONFIG_ETC"] = str(etc_root)
        xdg_root = tmp_path / "xdg"
        overrides["XDG_CONFIG_HOME"] = str(xdg_root)
        app_dir = etc_root / SLUG
        host_dir = app_dir / "hosts"
        user_dir = xdg_root / SLUG
        start_dir = user_dir
    return {"app": app_dir, "host": host_dir, "user": user_dir}, overrides, start_dir


def test_read_config_precedence(tmp_path: Path, monkeypatch) -> None:
    paths, env, start_dir = _platform_paths(tmp_path)

    write(paths["app"] / "config.toml", "[service]\ntimeout = 5\n")
    write(paths["app"] / "config.d" / "01-extra.toml", "[service]\nretries = 1\n")
    write(paths["host"] / "test-host.toml", "[service]\ntimeout = 10\n")

    write(paths["user"] / "config.toml", "[service]\nendpoint = 'https://api'\n")
    write(paths["user"] / ".env", "SERVICE__TIMEOUT=15\n")

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setenv("CONFIG_KIT_SERVICE__TIMEOUT", "20")
    monkeypatch.setenv("CONFIG_KIT_SERVICE__MODE", "debug")

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(start_dir))
    assert config.get("service.timeout") == 20
    assert config.get("service.retries") == 1
    assert config.get("service.endpoint") == "https://api"

    data, meta = read_config_raw(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(start_dir))
    assert meta["service.timeout"]["layer"] == "env"
    assert meta["service.retries"]["layer"] == "app"
