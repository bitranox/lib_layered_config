"""read_config(not_sensitive=...) declares keys that are not secrets although their name looks it."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import orjson
import pytest

from lib_layered_config import REDACTED_PLACEHOLDER, Config, read_config, read_config_json
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_CONFIG = """
[performance]
max_token_bytes = 4096

[db]
password = "s3cret"
"""
_DECLARED = ["performance.max_token_bytes"]


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    created.apply_env(monkeypatch)
    created.write("app", "config.toml", content=_CONFIG)
    return created


def _read(sandbox: LayeredSandbox, not_sensitive: list[str] | None = None) -> Config:
    return read_config(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        start_dir=str(sandbox.start_dir),
        dotenv_path=str(sandbox.start_dir / "absent.env"),
        not_sensitive=not_sensitive,
    )


@os_agnostic
def test_to_json_shows_a_declared_key_while_a_secret_stays_masked(sandbox: LayeredSandbox) -> None:
    shown = orjson.loads(_read(sandbox, _DECLARED).to_json(redact=True))

    assert shown == {"performance": {"max_token_bytes": 4096}, "db": {"password": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_without_a_declaration_the_key_stays_masked(sandbox: LayeredSandbox) -> None:
    assert _read(sandbox).as_dict(redact=True)["performance"]["max_token_bytes"] == REDACTED_PLACEHOLDER


@os_agnostic
def test_read_config_json_applies_the_declaration(sandbox: LayeredSandbox) -> None:
    payload = orjson.loads(
        read_config_json(
            vendor="Acme",
            app="ConfigKit",
            slug="config-kit",
            start_dir=str(sandbox.start_dir),
            dotenv_path=str(sandbox.start_dir / "absent.env"),
            redact=True,
            not_sensitive=_DECLARED,
        )
    )

    assert payload["config"] == {"performance": {"max_token_bytes": 4096}, "db": {"password": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_the_environment_reads_a_declared_null_as_none(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONFIG_KIT___PERFORMANCE__MAX_TOKEN_BYTES", "null")

    assert _read(sandbox, _DECLARED).get("performance.max_token_bytes", default="absent") is None


@os_agnostic
def test_with_overrides_keeps_the_declaration(sandbox: LayeredSandbox) -> None:
    config = _read(sandbox, _DECLARED).with_overrides({"performance": {"max_token_bytes": 1}})

    assert config.as_dict(redact=True)["performance"]["max_token_bytes"] == 1


@os_agnostic
def test_a_declaration_does_not_change_equality(sandbox: LayeredSandbox) -> None:
    assert _read(sandbox, _DECLARED) == _read(sandbox)


@os_agnostic
def test_an_empty_configuration_keeps_the_declaration_for_later_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    empty.apply_env(monkeypatch)

    config = _read(empty, _DECLARED).with_overrides({"performance": {"max_token_bytes": 1}})

    assert config.as_dict(redact=True) == {"performance": {"max_token_bytes": 1}}


@os_agnostic
def test_a_bare_string_declaration_is_refused() -> None:
    # Refused by read_config's first statement, before any path is resolved or file read.
    with pytest.raises(TypeError, match="not a single str"):
        read_config(
            vendor="Acme",
            app="ConfigKit",
            slug="config-kit",
            not_sensitive=cast("list[str]", "performance.max_token_bytes"),
        )
