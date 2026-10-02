"""An unquoted ``.env`` value is converted exactly like the same value in the environment.

``PORT=5432`` in a ``.env`` file and ``<PREFIX>___PORT=5432`` in the environment reach the
configuration as the same int, so a value never changes type when it moves between the two. A
quoted value is the literal text, which is the one way to keep ``5432`` or ``true`` a string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


def _load(tmp_path: Path, line: str) -> object:
    path = tmp_path / ".env"
    path.write_text(f"{line}\n", encoding="utf-8")
    return DefaultDotEnvLoader().load(dotenv_path=str(path))


@os_agnostic
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("SERVICE__ENABLED=true", {"service": {"enabled": True}}),
        ("SERVICE__ENABLED=False", {"service": {"enabled": False}}),
        ("SERVICE__PORT=5432", {"service": {"port": 5432}}),
        ("SERVICE__RATIO=3.5", {"service": {"ratio": 3.5}}),
        ("SERVICE__TIMEOUT=null", {"service": {"timeout": None}}),
        ("SERVICE__PORT=5432 # the default", {"service": {"port": 5432}}),
        ("SERVICE__ZIP=007", {"service": {"zip": "007"}}),
        ("SERVICE__NAME=demo", {"service": {"name": "demo"}}),
        ("SERVICE__NAME=", {"service": {"name": ""}}),
    ],
)
def test_an_unquoted_value_is_converted(tmp_path: Path, line: str, expected: object) -> None:
    assert _load(tmp_path, line) == expected


@os_agnostic
@pytest.mark.parametrize("line", ['SERVICE__PORT="5432"', "SERVICE__PORT='5432'"])
def test_a_quoted_value_stays_the_literal_text(tmp_path: Path, line: str) -> None:
    assert _load(tmp_path, line) == {"service": {"port": "5432"}}


@os_agnostic
@pytest.mark.parametrize("spelling", ["null", "none", "None"])
def test_a_sensitive_key_spelled_null_or_none_stays_text(tmp_path: Path, spelling: str) -> None:
    assert _load(tmp_path, f"EMAIL__SMTP_PASSWORD={spelling}") == {"email": {"smtp_password": spelling}}


@os_agnostic
@pytest.mark.parametrize("value", ["true", "5432", "3.5", "null", "007", "none", "[1, 2]", "demo"])
@pytest.mark.parametrize("key", ["SERVICE__VALUE", "EMAIL__SMTP_PASSWORD"])
def test_dotenv_and_environment_read_an_unquoted_value_identically(tmp_path: Path, key: str, value: str) -> None:
    from_dotenv = _load(tmp_path, f"{key}={value}")
    from_environment = DefaultEnvLoader(environ={f"DEMO___{key}": value}).load("DEMO")

    assert from_dotenv == from_environment


@os_agnostic
def test_read_config_gives_a_dotenv_port_the_same_type_as_an_environment_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    sandbox.start_dir.mkdir(parents=True, exist_ok=True)
    dotenv = sandbox.start_dir / ".env"
    dotenv.write_text("DATABASE__PORT=5432\nDATABASE__TLS=true\n", encoding="utf-8")

    config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))

    assert config.get("database.port") == 5432
    assert config.get("database.tls") is True
