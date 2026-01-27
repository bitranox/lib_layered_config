"""Tests for the domain redaction module."""

from __future__ import annotations

import pytest

from lib_layered_config.domain.redaction import (
    REDACTED_PLACEHOLDER,
    is_sensitive,
    redact_mapping,
)

from tests.support.os_markers import os_agnostic


# ---------------------------------------------------------------------------
# is_sensitive: true positives
# ---------------------------------------------------------------------------


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [
        "password",
        "passwords",
        "smtp_password",
        "password_hash",
        "secret",
        "secrets",
        "client_secret",
        "secret_value",
        "token",
        "tokens",
        "api_token",
        "token_expiry",
        "credential",
        "credentials",
        "user_credential",
        "api_key",
        "api_keys",
        "secret_key",
        "secret_keys",
        "private_key",
        "private_keys",
        "DATABASE_PASSWORD",
        "API_TOKEN",
        "Secret_Key",
    ],
)
def test_is_sensitive_detects_known_patterns(key: str) -> None:
    assert is_sensitive(key) is True


# ---------------------------------------------------------------------------
# is_sensitive: true negatives
# ---------------------------------------------------------------------------


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [
        "monkey",
        "keyboard",
        "tokenizer",
        "donkey",
        "keynote",
        "hostname",
        "username",
        "database_host",
        "port",
        "debug",
        "log_level",
        "secretary",
    ],
)
def test_is_sensitive_ignores_non_sensitive_keys(key: str) -> None:
    assert is_sensitive(key) is False


# ---------------------------------------------------------------------------
# redact_mapping: flat sensitive values
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_masks_flat_sensitive_values() -> None:
    data = {"password": "s3cret", "host": "localhost", "api_token": "tok123"}
    result = redact_mapping(data)
    assert result["password"] == REDACTED_PLACEHOLDER
    assert result["api_token"] == REDACTED_PLACEHOLDER
    assert result["host"] == "localhost"


# ---------------------------------------------------------------------------
# redact_mapping: nested dicts with sensitive keys
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_masks_nested_sensitive_values() -> None:
    data = {"db": {"host": "localhost", "password": "s3cret"}, "debug": True}
    result = redact_mapping(data)
    assert result["db"]["password"] == REDACTED_PLACEHOLDER
    assert result["db"]["host"] == "localhost"
    assert result["debug"] is True


# ---------------------------------------------------------------------------
# redact_mapping: lists of dicts with sensitive keys
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_masks_sensitive_values_in_list_of_dicts() -> None:
    data = {
        "services": [
            {"name": "api", "secret": "abc"},
            {"name": "web", "token": "xyz"},
        ]
    }
    result = redact_mapping(data)
    assert result["services"][0]["secret"] == REDACTED_PLACEHOLDER
    assert result["services"][1]["token"] == REDACTED_PLACEHOLDER
    assert result["services"][0]["name"] == "api"
    assert result["services"][1]["name"] == "web"


# ---------------------------------------------------------------------------
# redact_mapping: sensitive key with list value (full redaction)
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_replaces_sensitive_list_value_entirely() -> None:
    data = {"passwords": ["pw1", "pw2", "pw3"]}
    result = redact_mapping(data)
    assert result["passwords"] == REDACTED_PLACEHOLDER


# ---------------------------------------------------------------------------
# redact_mapping: non-mutating
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_does_not_mutate_input() -> None:
    data = {"password": "s3cret", "host": "localhost"}
    original_password = data["password"]
    _ = redact_mapping(data)
    assert data["password"] == original_password


@os_agnostic
def test_redact_mapping_does_not_mutate_nested_input() -> None:
    data = {"db": {"password": "s3cret"}}
    _ = redact_mapping(data)
    assert data["db"]["password"] == "s3cret"


# ---------------------------------------------------------------------------
# redact_mapping: empty dict
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_handles_empty_dict() -> None:
    assert redact_mapping({}) == {}


# ---------------------------------------------------------------------------
# redact_mapping: non-sensitive values pass through
# ---------------------------------------------------------------------------


@os_agnostic
def test_redact_mapping_preserves_non_sensitive_values() -> None:
    data = {"host": "localhost", "port": 5432, "debug": True, "tags": ["a", "b"]}
    result = redact_mapping(data)
    assert result == data
