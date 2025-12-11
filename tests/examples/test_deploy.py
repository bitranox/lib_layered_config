"""Deploy scenario poems ensuring every branch is illuminated."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import socket

import pytest

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.examples import deploy as deploy_module
from lib_layered_config.examples.deploy import DeployAction, DeployResult, deploy_config
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
    batch: bool = False,
    platform: str | None = None,
) -> list[DeployResult]:
    return deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=targets,
        slug=SLUG,
        force=force,
        batch=batch,
        platform=platform,
    )


def _created_paths(results: list[DeployResult]) -> list[Path]:
    """Extract paths where files were actually created or overwritten."""
    return [r.destination for r in results if r.action in (DeployAction.CREATED, DeployAction.OVERWRITTEN)]


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
    results = _deploy(sandbox, source_config, targets=["app"])

    assert _created_paths(results) == [_path_for(sandbox, "app")]


@os_agnostic
def test_deploy_writes_payload_into_app_destination(sandbox: LayeredSandbox, source_config: Path) -> None:
    destination = _path_for(sandbox, "app")
    _deploy(sandbox, source_config, targets=["app"])

    assert _read(destination).strip().endswith("flag = true")


@os_agnostic
def test_deploy_returns_the_user_destination_path(sandbox: LayeredSandbox, source_config: Path) -> None:
    results = _deploy(sandbox, source_config, targets=["user"])

    assert _created_paths(results) == [_path_for(sandbox, "user")]


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

    results = _deploy(sandbox, source_config, targets=["host"])

    assert _created_paths(results) == [_path_for(sandbox, "host", hostname="host-one")]


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
def test_deploy_batch_keeps_existing_and_creates_ucf(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Batch mode keeps existing files and creates .ucf for review."""
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("""[existing]\nvalue = 1\n""", encoding="utf-8")

    results = _deploy(sandbox, source_config, targets=["app"], batch=True)

    assert len(results) == 1
    assert results[0].action == DeployAction.KEPT
    assert results[0].destination == target
    assert results[0].ucf_path is not None
    assert results[0].ucf_path.exists()
    # Original file unchanged
    assert _read(target) == """[existing]\nvalue = 1\n"""


@os_agnostic
def test_deploy_overwrites_when_force_is_true(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")

    results = _deploy(sandbox, source_config, targets=["app"], force=True)

    assert len(results) == 1
    assert results[0].action == DeployAction.OVERWRITTEN
    assert results[0].destination == target
    assert results[0].backup_path is not None
    assert results[0].backup_path.exists()
    assert results[0].backup_path.read_text(encoding="utf-8") == "old"
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
    resolver = deploy_module._prepare_resolver(vendor=VENDOR, app=APP, slug=SLUG, profile=None, platform="macos")
    assert resolver.platform == "macos"


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

    results = deploy_config(
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
    created_paths = {r.destination.resolve() for r in results if r.action == DeployAction.CREATED}
    assert created_paths == expected_paths
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

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["user"],
        slug=SLUG,
    )

    expected_user = local / VENDOR / APP / "config.toml"
    assert len(results) == 1
    assert results[0].destination == expected_user
    assert results[0].action == DeployAction.CREATED
    assert expected_user.exists()


@os_agnostic
def test_copy_payload_creates_parent_directories(tmp_path: Path) -> None:
    payload = b"echo"
    destination = tmp_path / "nested" / "config.toml"

    deploy_module._copy_payload(destination, payload)

    assert destination.read_bytes() == payload


# ---------------------------------------------------------------------------
# Profile deployment tests
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_with_profile_creates_profile_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    sandbox.apply_env(monkeypatch)

    source = tmp_path / "source.toml"
    _write_payload(source)

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        profile="test",
        platform="linux",
    )

    assert len(results) == 1
    assert "profile/test/config.toml" in results[0].destination.as_posix()


@os_agnostic
def test_deploy_with_profile_host_includes_profile_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    sandbox.apply_env(monkeypatch)
    monkeypatch.setattr("socket.gethostname", lambda: "profile-host")

    source = tmp_path / "source.toml"
    _write_payload(source)

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["host"],
        slug=SLUG,
        profile="staging",
        platform="linux",
    )

    assert len(results) == 1
    assert "profile/staging/hosts/profile-host.toml" in results[0].destination.as_posix()


@os_agnostic
def test_deploy_with_profile_user_includes_profile_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    sandbox.apply_env(monkeypatch)

    source = tmp_path / "source.toml"
    _write_payload(source)

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["user"],
        slug=SLUG,
        profile="production",
        platform="linux",
    )

    assert len(results) == 1
    assert "profile/production/config.toml" in results[0].destination.as_posix()


@os_agnostic
def test_prepare_resolver_with_profile_sets_profile(tmp_path: Path) -> None:
    resolver = deploy_module._prepare_resolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        profile="test",
        platform="linux",
    )
    assert resolver.profile == "test"


@os_agnostic
def test_deploy_strategy_profile_segment_returns_path_when_set(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        profile="test",
        env=sandbox.env,
        platform="linux",
        hostname="host",
    )
    strategy = deploy_module.LinuxDeployment(resolver)

    segment = strategy._profile_segment()
    assert segment == Path("profile/test")


@os_agnostic
def test_deploy_strategy_profile_segment_returns_empty_when_none(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        profile=None,
        env=sandbox.env,
        platform="linux",
        hostname="host",
    )
    strategy = deploy_module.LinuxDeployment(resolver)

    segment = strategy._profile_segment()
    assert segment == Path()


@os_agnostic
def test_deploy_mac_with_profile_includes_profile_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    sandbox.apply_env(monkeypatch)

    source = tmp_path / "source.toml"
    _write_payload(source)

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        profile="dev",
        platform="darwin",
    )

    assert len(results) == 1
    assert "profile/dev/config.toml" in results[0].destination.as_posix()


@os_agnostic
def test_deploy_windows_with_profile_includes_profile_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="win32")
    sandbox.apply_env(monkeypatch)

    source = tmp_path / "source.toml"
    _write_payload(source)

    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        profile="prod",
        platform="win32",
    )

    assert len(results) == 1
    assert "profile/prod/config.toml" in results[0].destination.as_posix()


# ---------------------------------------------------------------------------
# Backup and UCF file tests
# ---------------------------------------------------------------------------


@os_agnostic
def test_next_available_path_returns_simple_suffix_when_not_exists(tmp_path: Path) -> None:
    base = tmp_path / "config.toml"
    base.write_text("content", encoding="utf-8")

    result = deploy_module._next_available_path(base, ".bak")

    assert result == tmp_path / "config.toml.bak"


@os_agnostic
def test_next_available_path_returns_numbered_suffix_when_exists(tmp_path: Path) -> None:
    base = tmp_path / "config.toml"
    base.write_text("content", encoding="utf-8")
    bak = tmp_path / "config.toml.bak"
    bak.write_text("old backup", encoding="utf-8")

    result = deploy_module._next_available_path(base, ".bak")

    assert result == tmp_path / "config.toml.bak.1"


@os_agnostic
def test_next_available_path_increments_suffix_number(tmp_path: Path) -> None:
    base = tmp_path / "config.toml"
    base.write_text("content", encoding="utf-8")
    (tmp_path / "config.toml.bak").write_text("bak0", encoding="utf-8")
    (tmp_path / "config.toml.bak.1").write_text("bak1", encoding="utf-8")
    (tmp_path / "config.toml.bak.2").write_text("bak2", encoding="utf-8")

    result = deploy_module._next_available_path(base, ".bak")

    assert result == tmp_path / "config.toml.bak.3"


@os_agnostic
def test_backup_file_creates_bak_copy(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("original content", encoding="utf-8")

    backup_path = deploy_module._backup_file(target)

    assert backup_path == tmp_path / "config.toml.bak"
    assert backup_path.read_text(encoding="utf-8") == "original content"
    assert target.read_text(encoding="utf-8") == "original content"


@os_agnostic
def test_backup_file_uses_numbered_suffix_when_bak_exists(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("current content", encoding="utf-8")
    existing_bak = tmp_path / "config.toml.bak"
    existing_bak.write_text("old backup", encoding="utf-8")

    backup_path = deploy_module._backup_file(target)

    assert backup_path == tmp_path / "config.toml.bak.1"
    assert backup_path.read_text(encoding="utf-8") == "current content"


@os_agnostic
def test_write_ucf_creates_ucf_file(tmp_path: Path) -> None:
    destination = tmp_path / "config.toml"
    destination.write_text("existing content", encoding="utf-8")
    payload = b"new content"

    ucf_path = deploy_module._write_ucf(destination, payload)

    assert ucf_path == tmp_path / "config.toml.ucf"
    assert ucf_path.read_bytes() == payload


@os_agnostic
def test_write_ucf_uses_numbered_suffix_when_ucf_exists(tmp_path: Path) -> None:
    destination = tmp_path / "config.toml"
    destination.write_text("existing content", encoding="utf-8")
    existing_ucf = tmp_path / "config.toml.ucf"
    existing_ucf.write_text("old ucf", encoding="utf-8")
    payload = b"new content"

    ucf_path = deploy_module._write_ucf(destination, payload)

    assert ucf_path == tmp_path / "config.toml.ucf.1"
    assert ucf_path.read_bytes() == payload


@os_agnostic
def test_deploy_with_conflict_resolver_calls_callback(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    calls: list[Path] = []

    def resolver(destination: Path) -> DeployAction:
        calls.append(destination)
        return DeployAction.SKIPPED

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        conflict_resolver=resolver,
    )

    assert len(calls) == 1
    assert calls[0] == target
    assert results[0].action == DeployAction.SKIPPED


@os_agnostic
def test_deploy_with_conflict_resolver_overwrite_creates_backup(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original", encoding="utf-8")

    def resolver(_: Path) -> DeployAction:
        return DeployAction.OVERWRITTEN

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        conflict_resolver=resolver,
    )

    assert results[0].action == DeployAction.OVERWRITTEN
    assert results[0].backup_path is not None
    assert results[0].backup_path.exists()
    assert results[0].backup_path.read_text(encoding="utf-8") == "original"
    assert "flag = true" in target.read_text(encoding="utf-8")


@os_agnostic
def test_deploy_with_conflict_resolver_kept_creates_ucf(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing content", encoding="utf-8")

    def resolver(_: Path) -> DeployAction:
        return DeployAction.KEPT

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        conflict_resolver=resolver,
    )

    assert results[0].action == DeployAction.KEPT
    assert results[0].ucf_path is not None
    assert results[0].ucf_path.exists()
    assert "flag = true" in results[0].ucf_path.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "existing content"


@os_agnostic
def test_deploy_batch_mode_creates_ucf_for_different_content(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Batch mode keeps existing and writes new config as .ucf for review."""
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        batch=True,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.KEPT
    assert results[0].ucf_path is not None
    assert results[0].ucf_path.exists()
    assert target.read_text(encoding="utf-8") == "existing"


@os_agnostic
def test_deploy_force_mode_ignores_batch(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        force=True,
        batch=True,  # Should be ignored when force=True
    )

    assert results[0].action == DeployAction.OVERWRITTEN
    assert results[0].backup_path is not None


@os_agnostic
def test_deploy_without_conflict_resolver_defaults_to_skip(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    # No force, no batch, no conflict_resolver - defaults to skip
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.SKIPPED


@os_agnostic
def test_deploy_multiple_overwrites_create_multiple_backups(
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("v1", encoding="utf-8")

    source1 = tmp_path / "source1.toml"
    source2 = tmp_path / "source2.toml"
    source1.write_text("[v2]", encoding="utf-8")
    source2.write_text("[v3]", encoding="utf-8")

    # First deploy with force
    results1 = deploy_config(
        source1,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        force=True,
    )

    # Second deploy with force
    results2 = deploy_config(
        source2,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        force=True,
    )

    assert results1[0].backup_path.name == "config.toml.bak"
    assert results2[0].backup_path.name == "config.toml.bak.1"
    assert results1[0].backup_path.read_text(encoding="utf-8") == "v1"
    assert results2[0].backup_path.read_text(encoding="utf-8") == "[v2]"
    assert target.read_text(encoding="utf-8") == "[v3]"
