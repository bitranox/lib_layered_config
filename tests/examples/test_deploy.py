"""Deploy scenario poems ensuring every branch is illuminated."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import socket

import pytest

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.examples import deploy as deploy_module
from lib_layered_config.examples.deploy import deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, windows_only

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


def _write_payload(path: Path, stanza: str = "flag = true") -> None:
    path.write_text(
        dedent(f"""
[service]
{stanza}
"""),
        encoding="utf-8",
    )


def _deploy(
    sandbox: LayeredSandbox,
    source_config: Path,
    *,
    targets: list[str],
    force: bool = False,
    platform: str | None = None,
) -> list[Path]:
    return deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=targets,
        slug=SLUG,
        force=force,
        platform=platform,
    )


def _path_for(sandbox: LayeredSandbox, target: str, hostname: str = "host") -> Path:
    if target == "host":
        return sandbox.roots["host"] / f"{hostname}.toml"
    return sandbox.roots[target] / "config.toml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    return home


@pytest.fixture()
def source_config(tmp_path: Path) -> Path:
    source = tmp_path / "source.toml"
    _write_payload(source)
    return source


@os_agnostic
def test_deploy_returns_the_app_destination_path(sandbox: LayeredSandbox, source_config: Path) -> None:
    created = _deploy(sandbox, source_config, targets=["app"])

    assert created == [_path_for(sandbox, "app")]


@os_agnostic
def test_deploy_writes_payload_into_app_destination(sandbox: LayeredSandbox, source_config: Path) -> None:
    destination = _path_for(sandbox, "app")
    _deploy(sandbox, source_config, targets=["app"])

    assert _read(destination).strip().endswith("flag = true")


@os_agnostic
def test_deploy_returns_the_user_destination_path(sandbox: LayeredSandbox, source_config: Path) -> None:
    created = _deploy(sandbox, source_config, targets=["user"])

    assert created == [_path_for(sandbox, "user")]


@os_agnostic
def test_deploy_writes_payload_into_user_destination(sandbox: LayeredSandbox, source_config: Path) -> None:
    destination = _path_for(sandbox, "user")
    _deploy(sandbox, source_config, targets=["user"])

    assert _read(destination).strip().endswith("flag = true")


@os_agnostic
def test_deploy_returns_the_host_destination_path(
    sandbox: LayeredSandbox,
    source_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.gethostname", lambda: "host-one")

    created = _deploy(sandbox, source_config, targets=["host"])

    assert created == [_path_for(sandbox, "host", hostname="host-one")]


@os_agnostic
def test_deploy_writes_payload_into_host_destination(
    sandbox: LayeredSandbox,
    source_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.gethostname", lambda: "host-one")

    destination = _path_for(sandbox, "host", hostname="host-one")
    _deploy(sandbox, source_config, targets=["host"])

    assert _read(destination).strip().endswith("flag = true")


@os_agnostic
def test_deploy_refuses_to_disturb_existing_files_without_force(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("""[existing]\nvalue = 1\n""", encoding="utf-8")

    result = _deploy(sandbox, source_config, targets=["app"])

    assert (result, _read(target)) == ([], """[existing]\nvalue = 1\n""")


@os_agnostic
def test_deploy_overwrites_when_force_is_true(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")

    created = _deploy(sandbox, source_config, targets=["app"], force=True)

    assert created == [target]
    assert "flag = true" in _read(target)


@os_agnostic
def test_deploy_refuses_unknown_targets(source_config: Path) -> None:
    with pytest.raises(ValueError):
        deploy_config(source_config, vendor=VENDOR, app=APP, targets=["mystery"], slug=SLUG)


@os_agnostic
def test_deploy_requires_source_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        deploy_config(missing, vendor=VENDOR, app=APP, targets=["app"], slug=SLUG)


@os_agnostic
def test_ensure_path_raises_when_destination_vanishes() -> None:
    with pytest.raises(ValueError):
        deploy_module._ensure_path(None, "ghost")


@os_agnostic
def test_ensure_path_returns_concrete_path(tmp_path: Path) -> None:
    destination = tmp_path / "target.toml"
    assert deploy_module._ensure_path(destination, "app") is destination


@os_agnostic
def test_validate_target_normalises_known_names() -> None:
    assert deploy_module._validate_target("APP") == "app"


@os_agnostic
def test_validate_target_rejects_unknown_names() -> None:
    with pytest.raises(ValueError):
        deploy_module._validate_target(" twilight ")


@os_agnostic
def test_strategy_for_selects_windows_strategy() -> None:
    resolver = DefaultPathResolver(vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    strategy = deploy_module._strategy_for(resolver)
    assert strategy.__class__.__name__ == "WindowsDeployment"


@os_agnostic
def test_strategy_for_selects_mac_strategy() -> None:
    resolver = DefaultPathResolver(vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    strategy = deploy_module._strategy_for(resolver)
    assert strategy.__class__.__name__ == "MacDeployment"


@os_agnostic
def test_strategy_for_defaults_to_linux_strategy() -> None:
    resolver = DefaultPathResolver(vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    strategy = deploy_module._strategy_for(resolver)
    assert strategy.__class__.__name__ == "LinuxDeployment"


@os_agnostic
def test_deployment_strategy_iterates_known_targets(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )
    strategy = deploy_module.LinuxDeployment(resolver)

    destinations = list(strategy.iter_destinations(["app", "user"]))

    assert destinations[-1].as_posix().endswith("config.toml")


@os_agnostic
def test_deployment_strategy_raises_on_unknown_target(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )
    strategy = deploy_module.LinuxDeployment(resolver)

    with pytest.raises(ValueError):
        list(strategy.iter_destinations(["mystery"]))


@os_agnostic
def test_deployment_strategy_skips_none_destinations(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    class NullStrategy(deploy_module.DeploymentStrategy):
        def destination_for(self, target: str) -> Path | None:  # pragma: no cover - abstract contract
            return None

    strategy = NullStrategy(resolver)

    assert list(strategy.iter_destinations(["app"])) == []


@os_agnostic
def test_platform_family_identifies_windows_strings() -> None:
    assert deploy_module._platform_family("win64") == "windows"


@os_agnostic
def test_platform_family_identifies_mac_strings() -> None:
    assert deploy_module._platform_family("darwin") == "mac"


@os_agnostic
def test_platform_family_falls_back_to_linux_for_other_names() -> None:
    assert deploy_module._platform_family("freebsd") == "linux"


@os_agnostic
def test_destinations_skip_none(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResolver(DefaultPathResolver):
        pass

    resolver = DummyResolver(vendor=VENDOR, app=APP, slug=SLUG)
    monkeypatch.setattr(deploy_module, "_resolve_destination", lambda *_: None)

    assert list(deploy_module._destinations_for(resolver, ["app"])) == []


@os_agnostic
def test_prepare_resolver_uses_platform_override() -> None:
    resolver = deploy_module._prepare_resolver(vendor=VENDOR, app=APP, slug=SLUG, platform="macos")
    assert resolver.platform == "macos"


@os_agnostic
def test_linux_destination_helper_returns_app_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    app_path = deploy_module._linux_destination_for(resolver, "app")
    assert app_path.as_posix().endswith("config.toml")


@os_agnostic
def test_linux_destination_helper_returns_host_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    host_path = deploy_module._linux_destination_for(resolver, "host")
    assert host_path.as_posix().endswith("hosts/penguin.toml")


@os_agnostic
def test_linux_destination_helper_returns_user_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    user_path = deploy_module._linux_destination_for(resolver, "user")
    assert user_path.as_posix().endswith("config.toml")


@os_agnostic
def test_linux_app_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    assert deploy_module._linux_app_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_linux_host_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    assert deploy_module._linux_host_path(resolver).as_posix().endswith("hosts/penguin.toml")


@os_agnostic
def test_linux_user_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    assert deploy_module._linux_user_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_mac_destination_helper_returns_app_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    app_path = deploy_module._mac_destination_for(resolver, "app")
    assert app_path.as_posix().endswith("config.toml")


@os_agnostic
def test_mac_destination_helper_returns_host_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    host_path = deploy_module._mac_destination_for(resolver, "host")
    assert host_path.as_posix().endswith("hosts/mac-host.toml")


@os_agnostic
def test_mac_destination_helper_returns_user_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    user_path = deploy_module._mac_destination_for(resolver, "user")
    assert user_path.as_posix().endswith("config.toml")


@os_agnostic
def test_mac_app_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    assert deploy_module._mac_app_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_mac_host_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    assert deploy_module._mac_host_path(resolver).as_posix().endswith("hosts/mac-host.toml")


@os_agnostic
def test_mac_user_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    assert deploy_module._mac_user_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_mac_app_root_reports_application_support(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    assert deploy_module._mac_app_root(resolver).as_posix().endswith("Application Support/Acme/Demo")


@os_agnostic
def test_mac_home_root_reports_application_support(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="darwin", hostname="mac-host"
    )

    assert deploy_module._mac_home_root(resolver).as_posix().endswith("Application Support")


@os_agnostic
def test_windows_destination_helper_returns_app_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    app_path = deploy_module._windows_destination_for(resolver, "app")
    assert app_path.as_posix().endswith("config.toml")


@os_agnostic
def test_windows_destination_helper_returns_host_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    host_path = deploy_module._windows_destination_for(resolver, "host")
    assert host_path.as_posix().endswith("hosts/WINHOST.toml")


@os_agnostic
def test_windows_destination_helper_returns_user_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    user_path = deploy_module._windows_destination_for(resolver, "user")
    assert user_path.as_posix().endswith("config.toml")


@os_agnostic
def test_windows_app_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_app_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_windows_host_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_host_path(resolver).as_posix().endswith("hosts/WINHOST.toml")


@os_agnostic
def test_windows_user_path_wraps_ensure_path(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_user_path(resolver).as_posix().endswith("config.toml")


@os_agnostic
def test_windows_program_data_reports_programdata(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_program_data(resolver).as_posix().endswith("ProgramData")


@os_agnostic
def test_windows_appdata_reports_roaming(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_appdata(resolver).as_posix().endswith("AppData/Roaming")


@os_agnostic
def test_windows_localappdata_reports_local(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="win32", hostname="WINHOST"
    )

    assert deploy_module._windows_localappdata(resolver).as_posix().endswith("AppData/Local")


@os_agnostic
def test_windows_user_path_falls_back_to_local_when_roaming_missing(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    env = dict(sandbox.env)
    roaming = tmp_path / "Roaming"
    env.pop("LIB_LAYERED_CONFIG_APPDATA", None)
    env["APPDATA"] = str(roaming)
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=env,
        platform="win32",
        hostname="WINHOST",
    )

    user_path = deploy_module._windows_destination_for(resolver, "user")
    assert user_path.as_posix().endswith("AppData/Local/Acme/Demo/config.toml")


@os_agnostic
def test_windows_programdata_override_is_honoured(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    env = dict(sandbox.env)
    env["LIB_LAYERED_CONFIG_PROGRAMDATA"] = str(tmp_path / "ProgramDataOverride")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=env,
        platform="win32",
        hostname="WINHOST",
    )

    app_path = deploy_module._windows_destination_for(resolver, "app")
    assert "ProgramDataOverride" in app_path.as_posix()


@windows_only
def test_deploy_windows_uses_programdata_and_appdata_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = "WIN-POEM"
    program_data = tmp_path / "ProgramData"
    roaming = tmp_path / "AppData" / "Roaming"
    local = tmp_path / "AppData" / "Local"
    for base in (program_data, roaming, local):
        base.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LIB_LAYERED_CONFIG_PROGRAMDATA", str(program_data))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_APPDATA", str(roaming))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(socket, "gethostname", lambda: host)

    source = tmp_path / "windows-source.toml"
    _write_payload(source)

    created = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["app", "host", "user"],
        slug=SLUG,
    )

    expected_paths = {
        (program_data / VENDOR / APP / "config.toml").resolve(),
        (program_data / VENDOR / APP / "hosts" / f"{host}.toml").resolve(),
        (roaming / VENDOR / APP / "config.toml").resolve(),
    }
    assert {path.resolve() for path in created} == expected_paths
    for destination in expected_paths:
        assert destination.exists()


@windows_only
def test_deploy_windows_falls_back_to_localappdata_when_roaming_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = "WIN-FALLBACK"
    program_data = tmp_path / "ProgramData"
    local = tmp_path / "AppData" / "Local"
    for base in (program_data, local):
        base.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LIB_LAYERED_CONFIG_PROGRAMDATA", str(program_data))
    monkeypatch.delenv("LIB_LAYERED_CONFIG_APPDATA", raising=False)
    monkeypatch.setenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "MissingRoaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(socket, "gethostname", lambda: host)

    source = tmp_path / "windows-fallback.toml"
    _write_payload(source)

    created = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["user"],
        slug=SLUG,
    )

    expected_user = local / VENDOR / APP / "config.toml"
    assert created == [expected_user]
    assert expected_user.exists()


@os_agnostic
def test_should_copy_declines_when_paths_match(tmp_path: Path) -> None:
    source = tmp_path / "config.toml"
    source.write_text("text", encoding="utf-8")

    assert deploy_module._should_copy(source, source, force=False) is False


@os_agnostic
def test_should_copy_declines_when_destination_exists_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.toml"
    source.write_text("text", encoding="utf-8")
    destination = tmp_path / "dest.toml"
    destination.write_text("text", encoding="utf-8")

    assert deploy_module._should_copy(source, destination, force=False) is False


@os_agnostic
def test_should_copy_allows_when_force_true(tmp_path: Path) -> None:
    source = tmp_path / "source.toml"
    source.write_text("text", encoding="utf-8")
    destination = tmp_path / "dest.toml"
    destination.write_text("text", encoding="utf-8")

    assert deploy_module._should_copy(source, destination, force=True) is True


@os_agnostic
def test_copy_payload_creates_parent_directories(tmp_path: Path) -> None:
    payload = b"echo"
    destination = tmp_path / "nested" / "config.toml"

    deploy_module._copy_payload(destination, payload)

    assert destination.read_bytes() == payload
