"""Example deployment helper tests covering cross-platform targets.

Ensures ``lib_layered_config.examples.deploy_config`` adheres to the filesystem
layouts documented in the system design and honours force/skip semantics.
"""

from __future__ import annotations

from pathlib import Path
import socket

import pytest
from textwrap import dedent

from lib_layered_config.examples import deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox

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

    assert app_path in deployed
    assert user_path in deployed
    assert "endpoint" in app_path.read_text(encoding="utf-8")
    assert "endpoint" in user_path.read_text(encoding="utf-8")


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
    assert deployed == [host_path]
    assert host_path.exists()


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

    assert deployed == []
    assert existing.read_text(encoding="utf-8") == dedent("""
[existing]
value=1
""")


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

    assert deployed == [existing]
    content = existing.read_text(encoding="utf-8")
    assert "https://api.example.com" in content


def test_deploy_config_invalid_target(source_config: Path) -> None:
    """Invalid targets should surface a ValueError to callers."""

    with pytest.raises(ValueError):
        deploy_config(source_config, vendor=VENDOR, app=APP, targets=["invalid"])


def test_deploy_config_missing_source(tmp_path: Path) -> None:
    """Missing source files should raise FileNotFoundError before any writes occur."""

    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        deploy_config(missing, vendor=VENDOR, app=APP, targets=["app"])


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
