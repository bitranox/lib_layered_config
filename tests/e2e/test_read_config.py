"""Composition root stories that prove precedence, provenance, and defaults."""

from __future__ import annotations

import importlib.util
import json
import logging
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ConfigError, read_config, read_config_json, read_config_raw
from lib_layered_config.core import LayerLoadError
from tests.adapters.test_loader_errors import _chain
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "ConfigKit"
SLUG = "config-kit"

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None


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


@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML not available")
@os_agnostic
def test_read_config_reports_a_yaml_construction_error_as_layer_load_error(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox, caplog: pytest.LogCaptureFixture
) -> None:
    """PyYAML's timestamp constructor raises a bare ``ValueError`` for an out-of-range calendar
    date, never its own ``YAMLError``; ``read_config`` must still refuse it as ``LayerLoadError``
    naming the file, not leak the parser's own ``ValueError`` or its message text."""
    sandbox.apply_env(monkeypatch)
    written = sandbox.write("app", "config.d/01-broken.yaml", content="a: 2020-13-01\n")

    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(LayerLoadError) as captured:
        read_config_raw(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir))

    assert isinstance(captured.value, ConfigError)
    message = str(captured.value)
    assert str(written) in message
    assert "is not valid YAML" in message
    # pytest's own tmp_path can legitimately contain "13" (e.g. "pytest-13"), so check
    # leak-freedom on the message with the path removed, not on the raw message.
    without_path = message.replace(str(written), "")
    assert "month" not in without_path
    assert "13" not in without_path
    for link in _chain(captured.value):
        link_text = str(link).replace(str(written), "")
        assert "month" not in link_text
        assert "13" not in link_text
    # Liveness: the capture sees the event, so an absent leak means the event is clean, not unseen.
    assert any(record.getMessage() == "config_file_invalid" for record in caplog.records)
    assert not any("month" in repr(vars(record)) for record in caplog.records)


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
