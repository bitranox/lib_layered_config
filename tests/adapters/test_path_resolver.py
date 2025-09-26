from __future__ import annotations

from pathlib import Path

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver


def test_linux_path_resolver(tmp_path: Path, monkeypatch) -> None:
    slug = "config-kit"
    etc_root = tmp_path / "etc"
    app_dir = etc_root / slug
    app_dir.mkdir(parents=True)
    (app_dir / "config.toml").write_text("[app]\nvalue = 1\n", encoding="utf-8")
    conf_d = app_dir / "config.d"
    conf_d.mkdir()
    (conf_d / "10-user.toml").write_text("[feature]\nflag = false\n", encoding="utf-8")
    hosts_dir = app_dir / "hosts"
    hosts_dir.mkdir()
    (hosts_dir / "test-host.toml").write_text("[host]\nvalue = 2\n", encoding="utf-8")

    xdg_root = tmp_path / "xdg"
    user_dir = xdg_root / slug
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text("[user]\nvalue = 3\n", encoding="utf-8")
    (user_dir / "config.d").mkdir()

    env = {
        "LIB_LAYERED_CONFIG_ETC": str(etc_root),
        "XDG_CONFIG_HOME": str(xdg_root),
    }

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug=slug,
        cwd=user_dir,
        env=env,
        platform="linux",
        hostname="test-host",
    )

    app_paths = list(resolver.app())
    assert app_paths[0].endswith("config.toml")
    normalized = [p.replace("\\", "/") for p in app_paths]
    assert any(path.endswith("config.d/10-user.toml") for path in normalized)

    host_paths = list(resolver.host())
    assert host_paths and host_paths[0].endswith("hosts/test-host.toml")

    user_paths = list(resolver.user())
    assert user_paths and user_paths[0].endswith("config.toml")

    dotenv_paths = list(resolver.dotenv())
    assert dotenv_paths == []  # none exist yet


def test_dotenv_extra_path(tmp_path: Path) -> None:
    slug = "config-kit"
    etc_root = tmp_path / "etc"
    etc_root.mkdir()
    env = {
        "LIB_LAYERED_CONFIG_ETC": str(etc_root),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }

    home_env = Path(env["XDG_CONFIG_HOME"]) / slug
    home_env.mkdir(parents=True)
    env_file = home_env / ".env"
    env_file.write_text("KEY=value\n", encoding="utf-8")

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug=slug,
        env=env,
        platform="linux",
    )
    dotenv_paths = list(resolver.dotenv())
    assert str(env_file) in dotenv_paths


def test_windows_path_resolver(tmp_path: Path) -> None:
    program_data = tmp_path / "ProgramData"
    program_data.mkdir()
    app_dir = program_data / "Acme" / "ConfigKit"
    app_dir.mkdir(parents=True)
    (app_dir / "config.toml").write_text("[windows]\nvalue=1\n", encoding="utf-8")

    env = {
        "LIB_LAYERED_CONFIG_PROGRAMDATA": str(program_data),
        "LIB_LAYERED_CONFIG_APPDATA": str(tmp_path / "AppData" / "Roaming"),
        "LIB_LAYERED_CONFIG_LOCALAPPDATA": str(tmp_path / "AppData" / "Local"),
    }

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        env=env,
        platform="win32",
        hostname="HOST",
    )

    app_paths = list(resolver.app())
    assert app_paths and app_paths[0].endswith("config.toml")
