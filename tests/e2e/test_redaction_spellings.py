"""A secret named in camelCase or kebab-case is masked like its snake_case spelling.

JSON and YAML configurations commonly name keys in camelCase and TOML ones in kebab-case, so the
name rule has to recognise ``dbPassword`` and ``client-secret`` as well as ``db_password``; read
through every redacting output, those values must never appear.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import REDACTED_PLACEHOLDER, Config, read_config, read_config_json
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_CONFIG = """
[service]
client-secret = "secret-kebab"
dbPassword = "secret-camel"
accessToken = "secret-token"
api-key = "secret-api"
display-name = "shown"
"""
_SECRETS = ("secret-kebab", "secret-camel", "secret-token", "secret-api")


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    created.apply_env(monkeypatch)
    created.write("app", "config.toml", content=_CONFIG)
    return created


def _absent_dotenv(sandbox: LayeredSandbox) -> str:
    return str(sandbox.start_dir / "absent.env")


def _read(sandbox: LayeredSandbox) -> Config:
    return read_config(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        start_dir=str(sandbox.start_dir),
        dotenv_path=_absent_dotenv(sandbox),
    )


@os_agnostic
def test_to_json_masks_camel_and_kebab_case_secrets(sandbox: LayeredSandbox) -> None:
    shown = json.loads(_read(sandbox).to_json(redact=True))

    assert shown == {
        "service": {
            "client-secret": REDACTED_PLACEHOLDER,
            "dbPassword": REDACTED_PLACEHOLDER,
            "accessToken": REDACTED_PLACEHOLDER,
            "api-key": REDACTED_PLACEHOLDER,
            "display-name": "shown",
        }
    }


@os_agnostic
def test_read_config_json_masks_camel_and_kebab_case_secrets(sandbox: LayeredSandbox) -> None:
    payload = read_config_json(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        start_dir=str(sandbox.start_dir),
        dotenv_path=_absent_dotenv(sandbox),
        redact=True,
    )

    assert not [secret for secret in _SECRETS if secret in payload]
    assert "shown" in payload
