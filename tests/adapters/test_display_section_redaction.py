"""The section view masks exactly what the full view masks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from lib_layered_config import REDACTED_PLACEHOLDER, Config, OutputFormat, display_config
from lib_layered_config.domain.config import SourceInfo
from lib_layered_config.domain.redaction import NotSensitiveKeys
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    import pytest

_DATA = {"credentials": {"user": "alice"}, "performance": {"max_token_bytes": 4096}}
_KEYS = ("credentials.user", "performance.max_token_bytes")


def _config(not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE) -> Config:
    meta = {key: SourceInfo(layer="app", path="/etc/demo/config.toml", key=key) for key in _KEYS}
    return Config(_DATA, meta, not_sensitive)


def _section_json(capsys: pytest.CaptureFixture[str], config: Config, section: str) -> object:
    display_config(config, output_format=OutputFormat.JSON, section=section)
    return orjson.loads(capsys.readouterr().out)


@os_agnostic
def test_a_key_below_a_masked_section_is_masked_in_the_json_section_view(capsys: pytest.CaptureFixture[str]) -> None:
    assert _section_json(capsys, _config(), "credentials.user") == {"credentials.user": REDACTED_PLACEHOLDER}


@os_agnostic
def test_a_key_below_a_masked_section_is_masked_in_the_human_section_view(capsys: pytest.CaptureFixture[str]) -> None:
    display_config(_config(), output_format=OutputFormat.HUMAN, section="credentials.user")

    out = capsys.readouterr().out
    assert REDACTED_PLACEHOLDER in out
    assert "alice" not in out


@os_agnostic
def test_the_section_view_applies_the_configs_declaration(capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(NotSensitiveKeys.of(["performance.max_token_bytes"]))

    assert _section_json(capsys, config, "performance") == {"performance": {"max_token_bytes": 4096}}
    assert _section_json(capsys, config, "performance.max_token_bytes") == {"performance.max_token_bytes": 4096}


@os_agnostic
def test_an_undeclared_sensitive_key_is_masked_in_the_section_view(capsys: pytest.CaptureFixture[str]) -> None:
    assert _section_json(capsys, _config(), "performance") == {"performance": {"max_token_bytes": REDACTED_PLACEHOLDER}}
