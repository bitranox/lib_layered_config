from __future__ import annotations

from pathlib import Path

from lib_layered_config import read_config, read_config_raw


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_read_config_precedence(tmp_path, monkeypatch) -> None:
    slug = "config-kit"
    vendor = "Acme"
    app = "ConfigKit"

    etc_root = tmp_path / "etc"
    write(etc_root / slug / "config.toml", "[service]\ntimeout = 5\n")
    write(etc_root / slug / "config.d" / "01-extra.toml", "[service]\nretries = 1\n")
    write(etc_root / slug / "hosts" / "test-host.toml", "[service]\ntimeout = 10\n")

    xdg_root = tmp_path / "xdg"
    write(xdg_root / slug / "config.toml", "[service]\nendpoint = 'https://api'\n")

    env_file = xdg_root / slug / ".env"
    write(env_file, "SERVICE__TIMEOUT=15\n")

    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", str(etc_root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    monkeypatch.setenv("CONFIG_KIT_SERVICE__TIMEOUT", "20")
    monkeypatch.setenv("CONFIG_KIT_SERVICE__MODE", "debug")

    config = read_config(vendor=vendor, app=app, slug=slug, start_dir=str(xdg_root / slug))
    assert config.get("service.timeout") == 20
    assert config.get("service.retries") == 1
    assert config.get("service.endpoint") == "https://api"

    data, meta = read_config_raw(vendor=vendor, app=app, slug=slug, start_dir=str(xdg_root / slug))
    assert meta["service.timeout"]["layer"] == "env"
    assert meta["service.retries"]["layer"] == "app"
