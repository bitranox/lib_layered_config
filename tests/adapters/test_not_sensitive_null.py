"""A declared not-sensitive key reads an unquoted null/none as None, like any other key."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.domain.redaction import NotSensitiveKeys
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_DECLARED = NotSensitiveKeys.of(["performance.max_token_bytes"])


@os_agnostic
def test_the_environment_reads_a_declared_keys_null_as_none() -> None:
    loader = DefaultEnvLoader(environ={"DEMO___PERFORMANCE__MAX_TOKEN_BYTES": "null"}, not_sensitive=_DECLARED)

    assert loader.load("DEMO") == {"performance": {"max_token_bytes": None}}


@os_agnostic
def test_the_environment_keeps_an_undeclared_secrets_null_as_text() -> None:
    environ = {"DEMO___PERFORMANCE__MAX_TOKEN_BYTES": "null", "DEMO___DB__PASSWORD": "null"}
    loader = DefaultEnvLoader(environ=environ, not_sensitive=NotSensitiveKeys.of(["db.host"]))

    assert loader.load("DEMO") == {"performance": {"max_token_bytes": "null"}, "db": {"password": "null"}}


@os_agnostic
def test_a_declared_key_matches_whatever_case_the_variable_uses() -> None:
    loader = DefaultEnvLoader(environ={"DEMO___Performance__Max_Token_Bytes": "NULL"}, not_sensitive=_DECLARED)

    assert loader.load("DEMO") == {"performance": {"max_token_bytes": None}}


@os_agnostic
def test_dotenv_reads_a_declared_keys_none_as_none_and_keeps_a_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PERFORMANCE__MAX_TOKEN_BYTES=none\nDB__PASSWORD=none\n", encoding="utf-8")
    loader = DefaultDotEnvLoader(not_sensitive=_DECLARED)

    data = loader.load(dotenv_path=str(env_file))

    assert data == {"performance": {"max_token_bytes": None}, "db": {"password": "none"}}


@os_agnostic
def test_dotenv_discovery_from_a_start_dir_honours_the_declaration(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PERFORMANCE__MAX_TOKEN_BYTES=null\nDB__PASSWORD=null\n", encoding="utf-8")
    loader = DefaultDotEnvLoader(not_sensitive=_DECLARED)

    data = loader.load(start_dir=str(tmp_path))

    assert loader.last_loaded_path == str(tmp_path / ".env")
    assert data == {"performance": {"max_token_bytes": None}, "db": {"password": "null"}}
