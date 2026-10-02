"""An unquoted null/none for a sensitive key stays text in the environment layer.

The environment layer reads an unquoted ``null`` or ``none`` as None. For a secret spelled exactly
that way, None would mean no credential at all, and a consumer such as a mail sender would then
work without one. A sensitive key (one ``redact=True`` masks) therefore keeps the text, and the
login fails loudly instead. Every other key still reads ``null``/``none`` as None.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
@pytest.mark.parametrize("spelling", ["null", "none", "NULL", "None"])
def test_a_sensitive_key_spelled_null_or_none_stays_text(spelling: str) -> None:
    loader = DefaultEnvLoader(environ={"DEMO___EMAIL__SMTP_PASSWORD": spelling})

    assert loader.load("DEMO") == {"email": {"smtp_password": spelling}}


@os_agnostic
def test_a_non_sensitive_key_spelled_null_becomes_none() -> None:
    loader = DefaultEnvLoader(environ={"DEMO___SERVICE__TIMEOUT": "null"})

    assert loader.load("DEMO") == {"service": {"timeout": None}}


@os_agnostic
def test_only_the_leaf_segment_decides_whether_a_key_is_sensitive() -> None:
    # A sensitive parent such as ``credentials`` holds no secret itself; its ``timeout`` is not one.
    loader = DefaultEnvLoader(environ={"DEMO___CREDENTIALS__TIMEOUT": "none"})

    assert loader.load("DEMO") == {"credentials": {"timeout": None}}


@os_agnostic
def test_a_sensitive_key_keeps_the_other_conversions() -> None:
    loader = DefaultEnvLoader(environ={"DEMO___API_TOKEN": "abc", "DEMO___DB__PASSWORD": "4711"})

    assert loader.load("DEMO") == {"api_token": "abc", "db": {"password": 4711}}


@os_agnostic
def test_read_config_keeps_a_secret_spelled_null_in_the_environment_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv("CONFIG_KIT___EMAIL__SMTP_PASSWORD", "null")

    config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))

    assert config.get("email.smtp_password") == "null"
