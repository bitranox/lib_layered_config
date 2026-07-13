"""Composition root stories that prove precedence, provenance, and defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textwrap import dedent

from lib_layered_config import read_config, read_config_json, read_config_raw
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

VENDOR = "Acme"
APP = "ConfigKit"
SLUG = "config-kit"


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


def arrange_precedence_story(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
):
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [service]
            timeout = 5
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/01-extra.toml",
        content=dedent(
            """
            [service]
            retries = 1
            """
        ),
    )
    sandbox.write(
        "host",
        "test-host.toml",
        content=dedent(
            """
            [service]
            timeout = 10
            """
        ),
    )
    sandbox.write(
        "user",
        "config.toml",
        content=dedent(
            """
            [service]
            endpoint = 'https://api'
            """
        ),
    )
    sandbox.write(
        "user",
        ".env",
        content="SERVICE__TIMEOUT=15\n",
    )
    monkeypatch.setenv("CONFIG_KIT___SERVICE__TIMEOUT", "20")
    monkeypatch.setenv("CONFIG_KIT___SERVICE__MODE", "debug")
    result = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    return result


@os_agnostic
def test_read_config_returns_highest_precedence_value(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    timeout = result.data["service"]["timeout"]  # type: ignore[index]
    assert int(timeout) == 20


@os_agnostic
def test_read_config_preserves_lower_precedence_scalars(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.data["service"]["retries"] == 1  # type: ignore[index]


@os_agnostic
def test_read_config_provenance_records_env_layer(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.provenance["service.timeout"]["layer"] == "env"


@os_agnostic
def test_read_config_provenance_records_app_layer(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.provenance["service.retries"]["layer"] == "app"


@os_agnostic
def test_read_config_json_contains_config_and_provenance(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content="""[feature]\nflag = true\n""",
    )
    payload = read_config_json(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    data = json.loads(payload)
    assert data["config"]["feature"]["flag"] is True
    assert data["provenance"]["feature.flag"]["layer"] == "app"


@os_agnostic
def test_read_config_default_file_serves_as_lowest_precedence(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    default_file = tmp_path / "defaults.toml"
    default_file.write_text(
        dedent(
            """
            [service]
            timeout = 3
            mode = "defaults"
            region = "eu-central"
            """
        ),
        encoding="utf-8",
    )
    sandbox.write(
        "app",
        "config.toml",
        content="""[service]\nmode = \"app\"\n""",
    )
    sandbox.write(
        "user",
        "config.toml",
        content="""[service]\ntimeout = 10\n""",
    )
    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        default_file=default_file,
    )
    assert config.get("service.timeout") == 10
    assert config.get("service.region") == "eu-central"


@os_agnostic
def test_read_config_dotenv_path_overrides_discovery(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    # Write a .env in start_dir that should be ignored
    sandbox.write("user", ".env", content="SERVICE__MODE=discovered\n")
    # Write an explicit dotenv file elsewhere
    explicit_env = tmp_path / "explicit.env"
    explicit_env.write_text("SERVICE__MODE=explicit\n", encoding="utf-8")

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        dotenv_path=explicit_env,
    )
    assert config.get("service.mode") == "explicit"


@os_agnostic
def test_read_config_dotenv_path_provenance_records_explicit_file(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    explicit_env = tmp_path / "custom.env"
    explicit_env.write_text("SERVICE__REGION=us-east\n", encoding="utf-8")

    result = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        dotenv_path=str(explicit_env),
    )
    assert result.data["service"]["region"] == "us-east"  # type: ignore[index]
    assert result.provenance["service.region"]["layer"] == "dotenv"
    assert result.provenance["service.region"]["path"] == str(explicit_env)


@os_agnostic
def test_env_var_overrides_one_array_element_end_to_end(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    """A prefixed env var with a numeric segment overrides one element of a file-defined array."""
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [[dataset]]
            name = "primary"
            dsn = "postgres://old"

            [[dataset]]
            name = "secondary"
            """
        ),
    )
    monkeypatch.setenv("CONFIG_KIT___DATASET__0__DSN", "postgres://new")

    result = read_config_raw(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir))

    dataset = result.data["dataset"]  # type: ignore[index]
    assert isinstance(dataset, list)
    assert dataset[0]["dsn"] == "postgres://new"
    assert dataset[0]["name"] == "primary"
    assert dataset[1]["name"] == "secondary"
    assert result.provenance["dataset.0.dsn"]["layer"] == "env"
