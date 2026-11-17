"""Deploy scenario poems ensuring every branch is illuminated."""

from __future__ import annotations

import contextlib
import functools
import os
import socket
import sys
import threading
import tracemalloc
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import deploy as deploy_module
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.deploy import DeployAction, DeployResult, deploy_config, deploy_config_paths
from lib_layered_config.domain.deploy_permissions import DeployPermissions
from lib_layered_config.domain.errors import DeployDestinationError, ValidationError
from lib_layered_config.domain.identifiers import Layer
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only, windows_only

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Private helpers pinned one by one: deploy_config reaches them only in combination, so a
# failure there would not say which helper broke.
_validate_target = deploy_module._validate_target  # pyright: ignore[reportPrivateUsage] - pins target-name normalisation and its exact refusal text
_destinations_for = deploy_module._destinations_for  # pyright: ignore[reportPrivateUsage] - pins the layer carried by each destination
_prepare_resolver = deploy_module._prepare_resolver  # pyright: ignore[reportPrivateUsage] - pins the resolver built from the platform and profile overrides
_copy_file = deploy_module._copy_file  # pyright: ignore[reportPrivateUsage] - pins the file write primitive on its own
_next_available_path = deploy_module._next_available_path  # pyright: ignore[reportPrivateUsage] - pins the sidecar numbering on its own
_Sidecar = deploy_module._Sidecar  # pyright: ignore[reportPrivateUsage] - the sidecar kind _next_available_path takes
_backup_file = deploy_module._backup_file  # pyright: ignore[reportPrivateUsage] - pins the backup copy on its own
_write_ucf = deploy_module._write_ucf  # pyright: ignore[reportPrivateUsage] - pins the .ucf sidecar write and its modes on its own

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


def _source_holding(tmp_path: Path, payload: bytes) -> Path:
    """A source file holding *payload*, for the write helpers that copy from a path."""
    source = tmp_path / "payload.src"
    source.write_bytes(payload)
    return source


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


@posix_only
def test_deploy_batch_keeps_existing_and_applies_explicit_modes_to_dir_and_ucf(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Batch mode with explicit dir_mode/file_mode: the .ucf and directory get the modes,
    the kept file's own mode is left untouched.
    """
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("""[existing]\nvalue = 1\n""", encoding="utf-8")
    target.chmod(0o644)
    original_mode = target.stat().st_mode & 0o7777

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        batch=True,
        set_permissions=True,
        dir_mode=0o750,
        file_mode=0o640,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.KEPT
    assert results[0].destination == target
    ucf_path = results[0].ucf_path
    assert ucf_path is not None
    assert ucf_path.exists()
    assert (ucf_path.stat().st_mode & 0o7777) == 0o640
    assert (target.parent.stat().st_mode & 0o7777) == 0o750
    assert (target.stat().st_mode & 0o7777) == original_mode


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
    assert _validate_target("APP") is Layer.APP


@os_agnostic
def test_validate_target_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match=r"^Unsupported deployment target:  twilight $"):
        _validate_target(" twilight ")


@os_agnostic
@pytest.mark.parametrize("name", ["defaults", "dotenv", "env"])
def test_validate_target_refuses_a_layer_deploy_does_not_write(name: str) -> None:
    with pytest.raises(ValueError, match=f"^Unsupported deployment target: {name}$"):
        _validate_target(name)


@os_agnostic
@pytest.mark.parametrize("deploy", [deploy_config, deploy_config_paths], ids=["deploy_config", "deploy_config_paths"])
@pytest.mark.parametrize(
    ("targets", "remedy"),
    [
        ("user", "write ['user']"),
        # A target name is matched in any case, so ['User'] is accepted and is the right remedy.
        ("User", "write ['User']"),
        ("", "write a list of app, host and user"),
        ("x", "write a list of app, host and user"),
    ],
    ids=["layer-name", "layer-name-capitalised", "empty", "unknown"],
)
def test_a_single_str_targets_is_refused_naming_the_mistake(
    sandbox: LayeredSandbox, source_config: Path, deploy: Callable[..., object], targets: str, remedy: str
) -> None:
    """A str is itself a sequence of str: "user" was read as the targets u, s, e, r, and "" deployed
    nothing. Both are refused with the type a bad target name raises. The remedy wraps the value in a
    list only when that list would be accepted: [''] or ['x'] would be refused next."""
    with pytest.raises(ValidationError) as caught:
        deploy(source_config, vendor=VENDOR, app=APP, slug=SLUG, targets=targets)
    assert str(caught.value) == f"targets takes a sequence of layer names, not a single str: {remedy}"
    assert not (sandbox.roots["user"] / "config.toml").exists()


@os_agnostic
@pytest.mark.parametrize(
    "names",
    [
        (VENDOR, APP, "s" * 256, None),
        ("v" * 256, APP, SLUG, None),
        (VENDOR, "a" * 256, SLUG, None),
        (VENDOR, APP, SLUG, "p" * 256),
    ],
    ids=["slug", "vendor", "app", "profile"],
)
def test_an_identifier_longer_than_a_file_name_is_refused_before_anything_is_written(
    sandbox: LayeredSandbox, source_config: Path, names: tuple[str, str, str, str | None]
) -> None:
    """NAME_MAX is 255; a longer segment used to fail with OSError ENAMETOOLONG from the copy."""
    vendor, app, slug, profile = names
    with pytest.raises(ValidationError, match="exceeds maximum length of 255: 256 characters"):
        deploy_config(
            source_config,
            vendor=vendor,
            app=app,
            slug=slug,
            profile=profile,
            max_profile_length=0,
            targets=["user", "app"],
        )
    assert list(sandbox.roots["user"].rglob("*.toml")) == []


@os_agnostic
def test_destinations_carry_the_layer_each_target_names(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform="linux")
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform="linux", hostname="penguin"
    )

    destinations = list(_destinations_for(resolver, ["User", "HOST", "app"]))

    assert [destination.layer for destination in destinations] == [Layer.USER, Layer.HOST, Layer.APP]
    assert destinations[1].path.name == "penguin.toml"


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_every_platform_layout_gives_each_deploy_target_a_destination(tmp_path: Path, platform: str) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG, platform=platform)
    resolver = DefaultPathResolver(
        vendor=VENDOR, app=APP, slug=SLUG, env=sandbox.env, platform=platform, hostname="penguin"
    )

    destinations = list(_destinations_for(resolver, ["app", "host", "user"]))

    assert [destination.layer for destination in destinations] == [Layer.APP, Layer.HOST, Layer.USER]
    assert [destination.path.name for destination in destinations] == ["config.toml", "penguin.toml", "config.toml"]


@os_agnostic
def test_prepare_resolver_reads_a_platform_alias_as_its_canonical_name() -> None:
    resolver = _prepare_resolver(vendor=VENDOR, app=APP, slug=SLUG, profile=None, platform="macos")
    assert resolver.platform == "darwin"


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
    # A profile WITH a Roaming folder: a resolver ignoring APPDATA would deploy there and fail this test.
    profile = tmp_path / "profile"
    (profile / "AppData" / "Roaming").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(profile))
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
def test_copy_file_creates_parent_directories(tmp_path: Path) -> None:
    payload = b"echo"
    destination = tmp_path / "nested" / "config.toml"

    _copy_file(destination, _source_holding(tmp_path, payload), modes=None)

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
    resolver = _prepare_resolver(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        profile="test",
        platform="linux",
    )
    assert resolver.profile == "test"


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

    result = _next_available_path(base, _Sidecar.BACKUP)

    assert result == tmp_path / "config.toml.bak"


@os_agnostic
def test_next_available_path_returns_numbered_suffix_when_exists(tmp_path: Path) -> None:
    base = tmp_path / "config.toml"
    base.write_text("content", encoding="utf-8")
    bak = tmp_path / "config.toml.bak"
    bak.write_text("old backup", encoding="utf-8")

    result = _next_available_path(base, _Sidecar.BACKUP)

    assert result == tmp_path / "config.toml.bak.1"


@os_agnostic
def test_next_available_path_increments_suffix_number(tmp_path: Path) -> None:
    base = tmp_path / "config.toml"
    base.write_text("content", encoding="utf-8")
    (tmp_path / "config.toml.bak").write_text("bak0", encoding="utf-8")
    (tmp_path / "config.toml.bak.1").write_text("bak1", encoding="utf-8")
    (tmp_path / "config.toml.bak.2").write_text("bak2", encoding="utf-8")

    result = _next_available_path(base, _Sidecar.BACKUP)

    assert result == tmp_path / "config.toml.bak.3"


@os_agnostic
def test_backup_file_creates_bak_copy(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("original content", encoding="utf-8")

    backup_path = _backup_file(target)

    assert backup_path == tmp_path / "config.toml.bak"
    assert backup_path.read_text(encoding="utf-8") == "original content"
    assert target.read_text(encoding="utf-8") == "original content"


@os_agnostic
def test_backup_file_uses_numbered_suffix_when_bak_exists(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("current content", encoding="utf-8")
    existing_bak = tmp_path / "config.toml.bak"
    existing_bak.write_text("old backup", encoding="utf-8")

    backup_path = _backup_file(target)

    assert backup_path == tmp_path / "config.toml.bak.1"
    assert backup_path.read_text(encoding="utf-8") == "current content"


@os_agnostic
def test_write_ucf_creates_ucf_file(tmp_path: Path) -> None:
    destination = tmp_path / "config.toml"
    destination.write_text("existing content", encoding="utf-8")
    payload = b"new content"

    ucf_path = _write_ucf(destination, _source_holding(tmp_path, payload), modes=None)

    assert ucf_path == tmp_path / "config.toml.ucf"
    assert ucf_path.read_bytes() == payload


@os_agnostic
def test_write_ucf_uses_numbered_suffix_when_ucf_exists(tmp_path: Path) -> None:
    destination = tmp_path / "config.toml"
    destination.write_text("existing content", encoding="utf-8")
    existing_ucf = tmp_path / "config.toml.ucf"
    existing_ucf.write_text("old ucf", encoding="utf-8")
    payload = b"new content"

    ucf_path = _write_ucf(destination, _source_holding(tmp_path, payload), modes=None)

    assert ucf_path == tmp_path / "config.toml.ucf.1"
    assert ucf_path.read_bytes() == payload


@posix_only
def test_write_ucf_applies_user_layer_permissions(tmp_path: Path) -> None:
    """A user-layer .ucf sidecar must be hardened to 0o600, not left at umask default."""
    destination = tmp_path / "config.toml"
    payload = b"secret_token = 'abc'"

    ucf_path = _write_ucf(
        destination, _source_holding(tmp_path, payload), modes=DeployPermissions.defaults().for_layer(Layer.USER)
    )

    assert (ucf_path.stat().st_mode & 0o777) == 0o600


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
        return DeployAction.KEPT

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
    assert results[0].action == DeployAction.KEPT


@os_agnostic
@pytest.mark.parametrize(
    ("flag", "decided", "resolver_answer"),
    [
        pytest.param("force", DeployAction.OVERWRITTEN, DeployAction.KEPT, id="force"),
        pytest.param("batch", DeployAction.KEPT, DeployAction.OVERWRITTEN, id="batch"),
    ],
)
def test_force_or_batch_decides_and_the_resolver_is_never_called(
    sandbox: LayeredSandbox,
    source_config: Path,
    flag: str,
    decided: DeployAction,
    resolver_answer: DeployAction,
) -> None:
    """User decision 2026-11-16 (R5-F6): force, then batch, then the resolver - documented, not refused."""
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")
    calls: list[Path] = []

    def resolver(destination: Path) -> DeployAction:
        calls.append(destination)
        return resolver_answer

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        conflict_resolver=resolver,
        force=flag == "force",
        batch=flag == "batch",
    )

    assert (calls, results[0].action) == ([], decided)


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
def test_deploy_refuses_force_with_batch_before_writing(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")
    fresh = sandbox.roots["user"] / "config.toml"

    with pytest.raises(
        ValidationError, match=r"^force=True overwrites an existing file and batch=True keeps it; pass one$"
    ):
        _deploy(sandbox, source_config, targets=["app", "user"], force=True, batch=True)

    assert target.read_text(encoding="utf-8") == "existing"
    assert sorted(path.name for path in target.parent.iterdir()) == ["config.toml"]
    assert not fresh.exists()


@os_agnostic
def test_deploy_without_a_policy_reports_a_conflict_and_leaves_the_file(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """SKIPPED means byte-identical; a differing file left alone for want of a policy is a CONFLICT."""
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
    )

    assert [result.action for result in results] == [DeployAction.CONFLICT]
    assert target.read_text(encoding="utf-8") == "existing"
    assert sorted(path.name for path in target.parent.iterdir()) == ["config.toml"]


@os_agnostic
@pytest.mark.parametrize(
    "answer",
    [DeployAction.SKIPPED, DeployAction.CREATED, DeployAction.CONFLICT, "overwritten", None],
    ids=["skipped", "created", "conflict", "plain-string", "none"],
)
def test_a_resolver_answer_other_than_overwritten_or_kept_is_refused(
    sandbox: LayeredSandbox,
    source_config: Path,
    answer: object,
) -> None:
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(ValidationError, match=r"OVERWRITTEN or DeployAction\.KEPT"):
        deploy_config(
            source_config,
            vendor=VENDOR,
            app=APP,
            targets=["app"],
            slug=SLUG,
            conflict_resolver=lambda _destination: answer,  # pyright: ignore[reportArgumentType, reportReturnType] - a resolver breaking its contract is the case under test
        )

    assert target.read_text(encoding="utf-8") == "existing"
    assert sorted(path.name for path in target.parent.iterdir()) == ["config.toml"]


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

    first_backup = results1[0].backup_path
    second_backup = results2[0].backup_path
    assert first_backup is not None
    assert second_backup is not None
    assert first_backup.name == "config.toml.bak"
    assert second_backup.name == "config.toml.bak.1"
    assert first_backup.read_text(encoding="utf-8") == "v1"
    assert second_backup.read_text(encoding="utf-8") == "[v2]"
    assert target.read_text(encoding="utf-8") == "[v3]"


# ---------------------------------------------------------------------------
# Permission deployment tests
# ---------------------------------------------------------------------------


@posix_only
def test_deploy_with_permissions_disabled_skips_chmod(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Deploying with set_permissions=False leaves the file at the umask-derived mode.

    Asserting only DeployAction.CREATED cannot detect a chmod: pick a distinctive
    umask first, so a stray apply_mode call (which would land on a fixed 0o644/0o600
    regardless of umask) shows up as a mode mismatch.
    """
    old_umask = os.umask(0o077)
    try:
        results = deploy_config(
            source_config,
            vendor=VENDOR,
            app=APP,
            targets=["app"],
            slug=SLUG,
            set_permissions=False,
        )
    finally:
        os.umask(old_umask)

    assert len(results) == 1
    assert results[0].action == DeployAction.CREATED
    expected_mode = 0o666 & ~0o077 & 0o777
    assert (results[0].destination.stat().st_mode & 0o777) == expected_mode


@posix_only
def test_deploy_app_layer_sets_644_file_permissions(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Deploying to app layer should set 644 file permissions."""
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        set_permissions=True,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.CREATED
    destination = results[0].destination
    assert (destination.stat().st_mode & 0o777) == 0o644


@posix_only
def test_deploy_user_layer_sets_600_file_permissions(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Deploying to user layer should set 600 file permissions."""
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["user"],
        slug=SLUG,
        set_permissions=True,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.CREATED
    destination = results[0].destination
    assert (destination.stat().st_mode & 0o777) == 0o600


@posix_only
def test_deploy_host_layer_sets_644_file_permissions(
    sandbox: LayeredSandbox,
    source_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deploying to host layer should set 644 file permissions."""
    monkeypatch.setattr("socket.gethostname", lambda: "test-host")

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["host"],
        slug=SLUG,
        set_permissions=True,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.CREATED
    destination = results[0].destination
    assert (destination.stat().st_mode & 0o777) == 0o644


@posix_only
def test_deploy_with_custom_file_mode(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Custom file_mode should override layer defaults."""
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        set_permissions=True,
        file_mode=0o640,
    )

    assert len(results) == 1
    destination = results[0].destination
    assert (destination.stat().st_mode & 0o777) == 0o640


@posix_only
def test_deploy_with_custom_dir_mode(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Custom dir_mode should set directory permissions."""
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        set_permissions=True,
        dir_mode=0o750,
    )

    assert len(results) == 1
    destination = results[0].destination
    # Check that parent directory has custom mode
    assert (destination.parent.stat().st_mode & 0o777) == 0o750


@posix_only
def test_deploy_permissions_on_overwrite(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """Permissions should be set when overwriting existing file."""
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old content", encoding="utf-8")
    # Set different permissions first
    target.chmod(0o777)

    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["app"],
        slug=SLUG,
        force=True,
        set_permissions=True,
    )

    assert len(results) == 1
    assert results[0].action == DeployAction.OVERWRITTEN
    # File should have correct permissions after overwrite
    assert (target.stat().st_mode & 0o777) == 0o644


@posix_only
def test_deploy_user_directory_permissions_are_700(
    sandbox: LayeredSandbox,
    source_config: Path,
) -> None:
    """User layer directories should have 700 permissions."""
    results = deploy_config(
        source_config,
        vendor=VENDOR,
        app=APP,
        targets=["user"],
        slug=SLUG,
        set_permissions=True,
    )

    assert len(results) == 1
    destination = results[0].destination
    # Check parent directory has user-private permissions
    assert (destination.parent.stat().st_mode & 0o777) == 0o700


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create *link* pointing at *target*, skipping where this account may not create symlinks.

    Windows allows symlinks only with Developer Mode or the create-symlink privilege; the elevated
    GitHub runner has it, so these tests run there and skip only where the OS really refuses.
    """
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"this account cannot create symlinks: {exc}")


_LINK_REFUSAL = "is a symbolic link; deploy neither writes through nor replaces one"


@os_agnostic
@pytest.mark.parametrize("set_permissions", [True, False], ids=["permissions", "no-permissions"])
@pytest.mark.parametrize("dangling", [False, True], ids=["live-link", "dangling-link"])
def test_deploy_refuses_a_symlinked_destination_and_writes_nothing(
    sandbox: LayeredSandbox, source_config: Path, tmp_path: Path, *, set_permissions: bool, dangling: bool
) -> None:
    victim = tmp_path / "victim.toml"
    if not dangling:
        victim.write_text("victim = true\n", encoding="utf-8")
    destination = _path_for(sandbox, "user")
    _symlink_or_skip(destination, victim)

    with pytest.raises(ValidationError, match="is a symbolic link") as caught:
        deploy_config(
            source_config,
            vendor=VENDOR,
            app=APP,
            targets=["user"],
            slug=SLUG,
            force=True,
            set_permissions=set_permissions,
        )

    assert str(caught.value) == f"{destination} {_LINK_REFUSAL}"
    assert destination.is_symlink()
    assert sorted(p.name for p in destination.parent.iterdir()) == ["config.toml"]
    if dangling:
        assert not victim.exists()
    else:
        assert _read(victim) == "victim = true\n"


@os_agnostic
def test_deploy_refuses_a_symlinked_dot_d_destination_before_writing_the_main_file(
    sandbox: LayeredSandbox, source_config: Path, tmp_path: Path
) -> None:
    (source_config.parent / "source.d").mkdir()
    (source_config.parent / "source.d" / "10-db.toml").write_text("[db]\nport = 1\n", encoding="utf-8")
    destination = _path_for(sandbox, "user")
    linked = destination.parent / "config.d" / "10-db.toml"
    _symlink_or_skip(linked, tmp_path / "elsewhere.toml")

    with pytest.raises(DeployDestinationError) as caught:
        _deploy(sandbox, source_config, targets=["user"])

    assert str(caught.value) == f"{linked} {_LINK_REFUSAL}"
    assert not destination.exists()


@os_agnostic
def test_deploy_names_every_symlinked_destination(sandbox: LayeredSandbox, source_config: Path, tmp_path: Path) -> None:
    app_destination = _path_for(sandbox, "app")
    user_destination = _path_for(sandbox, "user")
    _symlink_or_skip(app_destination, tmp_path / "a.toml")
    _symlink_or_skip(user_destination, tmp_path / "u.toml")

    with pytest.raises(DeployDestinationError) as caught:
        _deploy(sandbox, source_config, targets=["app", "user"])

    assert str(caught.value).splitlines() == [
        f"{app_destination} {_LINK_REFUSAL}",
        f"{user_destination} {_LINK_REFUSAL}",
    ]


@os_agnostic
@pytest.mark.parametrize("sidecar", ["BACKUP", "UCF"])
def test_a_dangling_link_takes_its_sidecar_name(tmp_path: Path, sidecar: str) -> None:
    kind = _Sidecar[sidecar]
    base = tmp_path / "config.toml"
    target = tmp_path / "planted.txt"
    # Both the plain name and the first numbered one hold a dangling link.
    _symlink_or_skip(tmp_path / f"config.toml{kind.value}", target)
    _symlink_or_skip(tmp_path / f"config.toml{kind.value}.1", target)

    assert _next_available_path(base, kind).name == f"config.toml{kind.value}.2"


@os_agnostic
def test_a_backup_never_writes_through_a_dangling_link(tmp_path: Path) -> None:
    existing = tmp_path / "config.toml"
    existing.write_text("old = 1\n", encoding="utf-8")
    target = tmp_path / "planted.txt"
    _symlink_or_skip(tmp_path / "config.toml.bak", target)

    backup = _backup_file(existing)

    assert (backup.name, target.exists()) == ("config.toml.bak.1", False)
    assert _read(backup) == "old = 1\n"


def _peak_python_memory_of_deploying_a_dot_d_file(tmp_path: Path, size: int, *, set_permissions: bool) -> int:
    """Deploy a source whose .d holds one *size*-byte file, then deploy it again unchanged.

    The first deploy copies the file, the second compares it and skips it; the peak Python
    allocation over both is returned. The user root must be fresh: the first deploy has to create.
    """
    root = tmp_path / f"size-{size}"
    (root / "source.d").mkdir(parents=True)
    source = root / "source.toml"
    _write_payload(source)
    asset = root / "source.d" / "asset.bin"
    asset.write_bytes(os.urandom(1024) * (size // 1024))
    deploy = functools.partial(
        deploy_config, source, vendor=VENDOR, app=APP, targets=["user"], slug=SLUG, set_permissions=set_permissions
    )
    tracemalloc.start()
    try:
        first = deploy()
        again = deploy(batch=True)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert [r.action for r in first[0].dot_d_results] == [DeployAction.CREATED]
    assert [r.action for r in again[0].dot_d_results] == [DeployAction.SKIPPED]
    copied = again[0].dot_d_results[0].destination
    assert copied.read_bytes() == asset.read_bytes()
    return peak


@os_agnostic
@pytest.mark.parametrize("set_permissions", [True, False], ids=["permissions", "no-permissions"])
def test_deploy_copies_a_large_dot_d_file_without_holding_it_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, set_permissions: bool
) -> None:
    mib = 1024 * 1024
    # One small deploy first, so imports and caches are warm before the 4 MiB one is measured.
    create_layered_sandbox(tmp_path / "home" / "warm", vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
    _peak_python_memory_of_deploying_a_dot_d_file(tmp_path, 64 * 1024, set_permissions=set_permissions)
    peaks: list[int] = []
    for index, size in enumerate((4 * mib, 16 * mib)):
        # A fresh sandbox per size, so each first deploy creates rather than compares. The sandbox
        # sets the user root each platform reads (XDG_CONFIG_HOME, APPDATA, the macOS home root).
        create_layered_sandbox(tmp_path / "home" / str(index), vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
        peaks.append(_peak_python_memory_of_deploying_a_dot_d_file(tmp_path, size, set_permissions=set_permissions))

    # Held whole, the 16 MiB file alone would put the peak above 16 MiB; streamed, it stays flat.
    assert max(peaks) < 2 * mib, peaks
    assert peaks[1] - peaks[0] < mib, peaks


@os_agnostic
def test_deploy_compares_past_the_first_chunk(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = tmp_path / "source.toml"
    body = "# " + "x" * (300 * 1024) + "\n"
    source.write_text(body + "flag = 1\n", encoding="utf-8")
    destination = _path_for(sandbox, "user")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(body + "flag = 2\n", encoding="utf-8")  # same size, differs at the end

    results = _deploy(sandbox, source, targets=["user"], batch=True)

    assert results[0].action == DeployAction.KEPT


@os_agnostic
def test_deploy_refuses_a_directory_at_the_destination(sandbox: LayeredSandbox, source_config: Path) -> None:
    destination = _path_for(sandbox, "user")
    destination.mkdir(parents=True)

    with pytest.raises(DeployDestinationError) as caught:
        _deploy(sandbox, source_config, targets=["user"], force=True)

    assert str(caught.value) == f"{destination} is not a regular file; deploy writes only regular files"
    assert sorted(p.name for p in destination.parent.iterdir()) == ["config.toml"]


@posix_only
def test_deploy_refuses_a_fifo_at_the_destination_instead_of_blocking(
    sandbox: LayeredSandbox, source_config: Path
) -> None:
    if sys.platform == "win32":  # narrows os.mkfifo for the type checker; posix_only already skips here
        return
    destination = _path_for(sandbox, "user")
    destination.parent.mkdir(parents=True)
    os.mkfifo(destination)
    # If deploy regresses to reading the FIFO, every read blocks until a writer comes and goes; this
    # thread plays that writer once a second, so the test fails instead of hanging. With no reader
    # waiting, its open just fails.
    done = threading.Event()
    unblocker = threading.Thread(target=_unblock_fifo_readers, args=(destination, done), daemon=True)
    unblocker.start()
    try:
        with pytest.raises(DeployDestinationError, match="is not a regular file"):
            _deploy(sandbox, source_config, targets=["user"], batch=True)
    finally:
        done.set()
        unblocker.join()


def _unblock_fifo_readers(fifo: Path, done: threading.Event) -> None:
    """Open and close a FIFO's write end once a second until *done*, giving each waiting reader EOF."""
    while not done.wait(1.0):
        _open_and_close_writer(fifo)


def _open_and_close_writer(fifo: Path) -> None:
    """One writer visit; with no reader waiting the non-blocking open fails and nothing happens."""
    if sys.platform == "win32":  # no FIFOs there; narrows os.O_NONBLOCK for the type checker
        return
    with contextlib.suppress(OSError):
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))


@posix_only
def test_deploy_refuses_an_unreadable_source_before_creating_anything(
    sandbox: LayeredSandbox, source_config: Path
) -> None:
    if sys.platform == "win32" or os.geteuid() == 0:  # narrows os.geteuid; root reads through the wall
        pytest.skip("root reads a file whatever its mode")
    source_config.chmod(0)
    destination = _path_for(sandbox, "user")
    try:
        with pytest.raises(PermissionError):
            deploy_config(source_config, vendor=VENDOR, app=APP, targets=["user"], slug=SLUG, set_permissions=False)
    finally:
        source_config.chmod(0o600)

    assert not destination.parent.exists()


@os_agnostic
def test_a_windows_deploy_finds_programdata_whatever_its_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_config: Path
) -> None:
    # Deploy and read_config share one lookup; before, deploy had its own chain that knew only the
    # exact "ProgramData" and an uppercase os.environ fallback, so a lowercase name was missed.
    monkeypatch.delenv("LIB_LAYERED_CONFIG_PROGRAMDATA", raising=False)
    monkeypatch.setenv("programdata", str(tmp_path / "Data"))

    paths = deploy_config_paths(source_config, vendor=VENDOR, app=APP, targets=["app"], slug=SLUG, platform="win32")

    assert paths == frozenset({(tmp_path / "Data" / VENDOR / APP / "config.toml").resolve()})
