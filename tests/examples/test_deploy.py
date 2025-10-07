"""Example deployment helper tests covering cross-platform targets.

Ensures ``lib_layered_config.examples.deploy_config`` adheres to the filesystem
layouts documented in the system design and honours force/skip semantics.
"""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest
from textwrap import dedent

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.examples import deploy_config
from lib_layered_config.examples import deploy as deploy_module
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, windows_only

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    """Provide a layered sandbox wired with platform-specific environment variables."""

    instance = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    instance.apply_env(monkeypatch)
    return instance


@pytest.fixture()
def source_config(tmp_path: Path) -> Path:
    """Create a reusable source configuration used across deployment scenarios."""

    config_file = tmp_path / "source.toml"
    config_file.write_text(
        dedent("""
[service]
endpoint = 'https://api.example.com'
"""),
        encoding="utf-8",
    )
    return config_file


@os_agnostic
def test_deploy_config_creates_app_and_user(
    sandbox: LayeredSandbox,
    monkeypatch: pytest.MonkeyPatch,
    source_config: Path,
) -> None:
    """Deploying to app and user targets should create both files with payload intact."""

    monkeypatch.setattr("socket.gethostname", lambda: "deploy-host")

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app", "user"],
        slug=SLUG,
    )

    app_path = sandbox.roots["app"] / "config.toml"
    user_path = sandbox.roots["user"] / "config.toml"

    expected_paths = {app_path, user_path}
    app_text = app_path.read_text(encoding="utf-8")
    user_text = user_path.read_text(encoding="utf-8")
    assert (set(deployed), "endpoint" in app_text, "endpoint" in user_text) == (expected_paths, True, True)


@os_agnostic
def test_deploy_config_host_target(
    sandbox: LayeredSandbox,
    monkeypatch: pytest.MonkeyPatch,
    source_config: Path,
) -> None:
    """Host deployments should place host-specific artefacts in the hosts directory."""

    monkeypatch.setattr("socket.gethostname", lambda: "host-one")

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["host"],
        slug=SLUG,
    )

    host_path = sandbox.roots["host"] / "host-one.toml"
    assert (deployed, host_path.exists()) == ([host_path], True)


@os_agnostic
def test_deploy_config_skips_existing(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Existing targets should be preserved when force is False."""

    existing = sandbox.roots["app"] / "config.toml"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text(
        dedent("""
[existing]
value=1
"""),
        encoding="utf-8",
    )

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
    )

    expected_text = dedent("""
[existing]
value=1
""")
    assert (deployed, existing.read_text(encoding="utf-8")) == ([], expected_text)


@os_agnostic
def test_deploy_config_force_overwrites(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Force mode should overwrite an existing file with the new payload."""

    existing = sandbox.roots["app"] / "config.toml"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text(
        dedent("""
[existing]
value=1
"""),
        encoding="utf-8",
    )

    deployed = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        force=True,
    )

    content = existing.read_text(encoding="utf-8")
    assert (deployed, "https://api.example.com" in content) == ([existing], True)


@os_agnostic
def test_deploy_config_invalid_target(source_config: Path) -> None:
    """Invalid targets should surface a ValueError to callers."""

    with pytest.raises(ValueError):
        deploy_config(source_config, vendor=VENDOR, app=APP, targets=["invalid"])


@os_agnostic
def test_deploy_config_missing_source(tmp_path: Path) -> None:
    """Missing source files should raise FileNotFoundError before any writes occur."""

    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        deploy_config(missing, vendor=VENDOR, app=APP, targets=["app"])


@windows_only
@windows_only
def test_deploy_config_windows_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows deployments should create ProgramData/AppData files with host suffixes."""

    from lib_layered_config.examples import deploy as deploy_module

    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="win32",
    )
    sandbox.apply_env(monkeypatch)

    source = tmp_path / "config.toml"
    source.write_text(
        dedent("""
[service]
endpoint = "https://api.example.com"
"""),
        encoding="utf-8",
    )

    class _Resolver(deploy_module.DefaultPathResolver):
        def __init__(self, **kwargs):
            super().__init__(platform="win32", hostname="WINHOST", **kwargs)

    monkeypatch.setattr(deploy_module, "DefaultPathResolver", _Resolver)

    deployed = deploy_module.deploy_config(
        source,
        vendor="Acme",
        app="Demo",
        targets=["app", "host", "user"],
        slug="demo",
    )

    relative = sorted(path.relative_to(tmp_path).as_posix() for path in deployed)
    assert relative == [
        "AppData/Roaming/Acme/Demo/config.toml",
        "ProgramData/Acme/Demo/config.toml",
        "ProgramData/Acme/Demo/hosts/WINHOST.toml",
    ]


@windows_only
def test_deploy_config_windows_respects_override_even_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="win32",
    )
    sandbox.apply_env(monkeypatch)

    appdata_root = Path(sandbox.env["LIB_LAYERED_CONFIG_APPDATA"])
    if appdata_root.exists():
        shutil.rmtree(appdata_root)

    source = tmp_path / "payload.toml"
    source.write_text("""[service]\nflag = true\n""", encoding="utf-8")

    class StubResolver(deploy_module.DefaultPathResolver):
        def __init__(self, **kwargs):
            super().__init__(platform="win32", hostname="WINHOST", **kwargs)

    monkeypatch.setattr(deploy_module, "DefaultPathResolver", StubResolver)

    deployed = deploy_module.deploy_config(
        source,
        vendor="Acme",
        app="Demo",
        targets=["user"],
        slug="demo",
    )

    expected = Path(sandbox.env["LIB_LAYERED_CONFIG_APPDATA"]) / "Acme" / "Demo" / "config.toml"
    assert (deployed, expected.exists()) == ([expected], True)


@windows_only
def test_deploy_config_windows_localapp_fallback_when_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="win32",
    )

    app_env = dict(sandbox.env)
    local_appdata = app_env.pop("LIB_LAYERED_CONFIG_LOCALAPPDATA")
    appdata_override = app_env.pop("LIB_LAYERED_CONFIG_APPDATA")
    sandbox.apply_env(monkeypatch)
    monkeypatch.delenv("LIB_LAYERED_CONFIG_APPDATA", raising=False)
    monkeypatch.delenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", appdata_override)
    monkeypatch.setenv("LOCALAPPDATA", local_appdata)

    roaming_path = Path(appdata_override)
    if roaming_path.exists():
        shutil.rmtree(roaming_path)

    source = tmp_path / "payload.toml"
    source.write_text("""[service]\nflag = true\n""", encoding="utf-8")

    class StubResolver(deploy_module.DefaultPathResolver):
        def __init__(self, **kwargs):
            super().__init__(platform="win32", hostname="WINHOST", **kwargs)

    monkeypatch.setattr(deploy_module, "DefaultPathResolver", StubResolver)

    deployed = deploy_module.deploy_config(
        source,
        vendor="Acme",
        app="Demo",
        targets=["user"],
        slug="demo",
    )

    expected = Path(local_appdata) / "Acme" / "Demo" / "config.toml"
    assert (deployed, expected.exists()) == ([expected], True)


@os_agnostic
def test_prepare_resolver_respects_platform_override() -> None:
    resolver = deploy_module._prepare_resolver(vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    assert resolver.platform == "linux"


@os_agnostic
def test_destinations_for_skips_none_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResolver:
        platform = "linux"

    monkeypatch.setattr(deploy_module, "_resolve_destination", lambda *_: None)

    assert list(deploy_module._destinations_for(DummyResolver(), ["app"])) == []


@os_agnostic
def test_should_copy_returns_false_when_paths_match(tmp_path: Path) -> None:
    source = tmp_path / "config.toml"
    source.write_text("data", encoding="utf-8")
    assert deploy_module._should_copy(source, source, False) is False


@os_agnostic
def test_platform_family_classifies_platform_strings() -> None:
    assert deploy_module._platform_family("darwin") == "mac"
    assert deploy_module._platform_family("win32") == "windows"
    assert deploy_module._platform_family("freebsd") == "linux"


@os_agnostic
def test_linux_destination_helpers_return_expected_paths(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=sandbox.env,
        platform="linux",
        hostname="example-host",
    )
    assert deploy_module._linux_destination_for(resolver, "app").as_posix().endswith("config.toml")
    assert deploy_module._linux_destination_for(resolver, "host").as_posix().endswith("hosts/example-host.toml")
    assert deploy_module._linux_destination_for(resolver, "user").as_posix().endswith("config.toml")


@os_agnostic
def test_mac_destination_helpers_return_expected_paths(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=sandbox.env,
        platform="darwin",
        hostname="mac-host",
    )
    app_path = deploy_module._mac_destination_for(resolver, "app")
    host_path = deploy_module._mac_destination_for(resolver, "host")
    user_path = deploy_module._mac_destination_for(resolver, "user")
    assert app_path.as_posix().endswith("config.toml")
    assert host_path.as_posix().endswith("hosts/mac-host.toml")
    assert user_path.as_posix().endswith("config.toml")


@os_agnostic
def test_windows_destination_helpers_return_expected_paths(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=sandbox.env,
        platform="win32",
        hostname="WINHOST",
    )
    app_path = deploy_module._windows_destination_for(resolver, "app")
    host_path = deploy_module._windows_destination_for(resolver, "host")
    user_path = deploy_module._windows_destination_for(resolver, "user")
    assert app_path.as_posix().endswith("config.toml")
    assert host_path.as_posix().endswith("hosts/WINHOST.toml")
    assert user_path.as_posix().endswith("config.toml")


@os_agnostic
def test_windows_user_path_falls_back_to_local_when_roaming_missing(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    env = dict(sandbox.env)
    roaming = tmp_path / "FallbackRoaming"
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
    destination = deploy_module._windows_user_path(resolver)
    expected = Path(sandbox.env["LIB_LAYERED_CONFIG_LOCALAPPDATA"]) / VENDOR / APP / "config.toml"
    assert destination == expected


@os_agnostic
def test_windows_localappdata_helper_respects_override(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        env=sandbox.env,
        platform="win32",
        hostname="WINHOST",
    )
    expected = Path(sandbox.env["LIB_LAYERED_CONFIG_LOCALAPPDATA"])
    assert deploy_module._windows_localappdata(resolver) == expected
