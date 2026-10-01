"""An unquoted null/none for a sensitive environment key is reported when it becomes None.

The environment layer reads an unquoted ``null`` or ``none`` as None. For a secret that is
spelled exactly that way, None means no credential at all, and a consumer such as a mail
sender then works without one. Until the next major release keeps such a value as text, the
loader logs one ``env_secret_became_none`` warning naming the key, and never the value.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_EVENT = "env_secret_became_none"


def _warned_keys(caplog: pytest.LogCaptureFixture) -> list[object]:
    return [record.__dict__["context"]["key"] for record in caplog.records if record.message == _EVENT]


@os_agnostic
@pytest.mark.parametrize("spelling", ["null", "none", "NULL", "None"])
def test_a_sensitive_key_spelled_null_or_none_still_becomes_none_and_is_warned(
    spelling: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="lib_layered_config")
    loader = DefaultEnvLoader(environ={"DEMO___EMAIL__SMTP_PASSWORD": spelling})

    payload = loader.load("DEMO")

    assert payload == {"email": {"smtp_password": None}}
    assert _warned_keys(caplog) == ["email.smtp_password"]


@os_agnostic
def test_a_non_sensitive_key_becoming_none_is_not_warned(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="lib_layered_config")
    loader = DefaultEnvLoader(environ={"DEMO___SERVICE__TIMEOUT": "null"})

    assert loader.load("DEMO") == {"service": {"timeout": None}}
    assert _warned_keys(caplog) == []


@os_agnostic
def test_a_sensitive_key_with_a_real_value_is_not_warned(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="lib_layered_config")
    loader = DefaultEnvLoader(environ={"DEMO___API_TOKEN": "abc", "DEMO___DB__PASSWORD": "nullable"})

    assert loader.load("DEMO") == {"api_token": "abc", "db": {"password": "nullable"}}
    assert _warned_keys(caplog) == []


@os_agnostic
def test_read_config_warns_for_a_secret_spelled_null_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv("CONFIG_KIT___EMAIL__SMTP_PASSWORD", "null")
    caplog.set_level(logging.WARNING, logger="lib_layered_config")

    config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))

    assert config.get("email.smtp_password", default="unset") is None
    assert _warned_keys(caplog) == ["email.smtp_password"]
