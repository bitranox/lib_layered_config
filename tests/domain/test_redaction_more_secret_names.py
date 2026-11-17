"""Redaction hides the short secret names and the password inside a URL.

Keys named ``pwd``, ``pass``, ``privatekey``, ``privkey`` or ``bearer`` used to come back in clear
from every redacted view, and so did ``postgres://alice:hunter2@db/x`` under a key such as ``url``
or ``dsn``, because only key names were looked at. The short names are now stems like ``password``,
and a URL-shaped value has its password replaced wherever it sits, unless its path is declared not
sensitive.
"""

from __future__ import annotations

from typing import Any

import pytest

from lib_layered_config import Config
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, NotSensitiveKeys, is_sensitive, redact_mapping
from tests.support.os_markers import os_agnostic

_MASKED_PASSWORD = f"postgres://alice:{REDACTED_PLACEHOLDER}@db.example:5432/app"


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [
        "pwd",
        "db_pwd",
        "dbPwd",
        "PWD",
        "pass",
        "smtp_pass",
        "smtpPass",
        "smtp-pass",
        "privatekey",
        "privkey",
        "ssh_privkey",
        "bearer",
        "auth_bearer",
        "bearer_tokens",
    ],
)
def test_the_short_secret_names_are_sensitive(key: str) -> None:
    assert is_sensitive(key) is True


@os_agnostic
@pytest.mark.parametrize("key", ["passenger", "bypass", "passport", "compass", "passthrough", "pwdx"])
def test_words_that_only_contain_a_short_name_stay_visible(key: str) -> None:
    assert is_sensitive(key) is False


@os_agnostic
@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("postgres://alice:hunter2@db.example:5432/app", _MASKED_PASSWORD),
        ("redis://:hunter2@cache.example/0", f"redis://:{REDACTED_PLACEHOLDER}@cache.example/0"),
        ("amqp://alice:p@ss@mq.example/vh", f"amqp://alice:{REDACTED_PLACEHOLDER}@mq.example/vh"),
        ("HTTPS://alice:hunter2@example.com", f"HTTPS://alice:{REDACTED_PLACEHOLDER}@example.com"),
    ],
)
def test_the_password_of_a_url_value_is_masked_under_any_key(value: str, shown: str) -> None:
    assert redact_mapping({"db": {"url": value}}) == {"db": {"url": shown}}


@os_agnostic
@pytest.mark.parametrize(
    "value",
    [
        "postgres://alice@db.example/app",
        "https://example.com/path?next=a:b@c",
        "https://example.com/a:b@c",
        "alice:hunter2@db.example",
        "mailto:alice@example.com",
        "not a url at all",
    ],
)
def test_a_value_without_a_url_password_is_left_as_it_is(value: str) -> None:
    assert redact_mapping({"url": value}) == {"url": value}


@os_agnostic
def test_a_url_password_in_a_list_is_masked() -> None:
    redacted = redact_mapping({"mirrors": ["https://a:b@one.example", "https://two.example"]})

    assert redacted == {"mirrors": [f"https://a:{REDACTED_PLACEHOLDER}@one.example", "https://two.example"]}


@os_agnostic
def test_a_url_under_a_path_declared_not_sensitive_stays_visible() -> None:
    data: dict[str, Any] = {"db": {"url": "postgres://alice:hunter2@db.example:5432/app"}}

    assert redact_mapping(data, not_sensitive=["db.url"]) == data


@os_agnostic
def test_every_redacted_view_of_a_config_masks_a_url_password() -> None:
    cfg = Config(
        {"db": {"url": "postgres://alice:hunter2@db.example:5432/app", "pass": "x"}}, {}, NotSensitiveKeys.NONE
    )

    assert cfg.as_dict(redact=True) == {"db": {"url": _MASKED_PASSWORD, "pass": REDACTED_PLACEHOLDER}}
    assert "hunter2" not in cfg.to_json(redact=True)
    assert cfg.get_redacted("db.url") == _MASKED_PASSWORD
    assert cfg.get_redacted("db") == {"url": _MASKED_PASSWORD, "pass": REDACTED_PLACEHOLDER}
    assert cfg.get("db.url") == "postgres://alice:hunter2@db.example:5432/app"
