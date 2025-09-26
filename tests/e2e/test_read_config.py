"""End-to-end tests for the composition root ``read_config`` helpers.

The test case asserts the precedence order and provenance metadata described in
``docs/systemdesign/module_reference.md#module-lib_layered_config/core.py`` using
the shared layered sandbox helper.
"""

from __future__ import annotations

import pytest
from textwrap import dedent

from lib_layered_config import read_config, read_config_raw
from tests.support import LayeredSandbox, create_layered_sandbox

VENDOR = "Acme"
APP = "ConfigKit"
SLUG = "config-kit"


@pytest.fixture()
def sandbox(tmp_path) -> LayeredSandbox:
    """Provide a sandbox configured for the active platform to mirror precedence rules."""

    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


def test_read_config_precedence(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """`read_config` should respect documented precedence and provenance ordering."""

    sandbox.apply_env(monkeypatch)

    sandbox.write(
        "app",
        "config.toml",
        content=dedent("""
[service]
timeout = 5
"""),
    )
    sandbox.write(
        "app",
        "config.d/01-extra.toml",
        content=dedent("""
[service]
retries = 1
"""),
    )
    sandbox.write(
        "host",
        "test-host.toml",
        content=dedent("""
[service]
timeout = 10
"""),
    )
    sandbox.write(
        "user",
        "config.toml",
        content=dedent("""
[service]
endpoint = 'https://api'
"""),
    )
    sandbox.write(
        "user",
        ".env",
        content=dedent("""
SERVICE__TIMEOUT=15
"""),
    )

    monkeypatch.setenv("CONFIG_KIT_SERVICE__TIMEOUT", "20")
    monkeypatch.setenv("CONFIG_KIT_SERVICE__MODE", "debug")

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    assert config.get("service.timeout") == 20
    assert config.get("service.retries") == 1
    assert config.get("service.endpoint") == "https://api"

    data, meta = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    assert meta["service.timeout"]["layer"] == "env"
    assert meta["service.retries"]["layer"] == "app"
