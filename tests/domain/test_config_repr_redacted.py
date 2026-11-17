"""The text form of a ``Config`` never shows a secret.

``repr(config)`` was the dataclass default, which printed the whole stored tree, so
``logger.debug("loaded %s", config)``, an f-string or a failing assertion's message wrote every
password and token in clear, past any log scrubber that works by field name. The text form now shows
the redacted view, as ``as_dict(redact=True)`` does, and only a count of the provenance entries.
"""

from __future__ import annotations

import pprint
from typing import Any, cast

import pytest
from rich.pretty import pretty_repr

from lib_layered_config import Config, NotSensitiveKeys
from lib_layered_config.domain.config import SourceInfo
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER
from tests.support.os_markers import os_agnostic

_DATA: dict[str, Any] = {
    "db": {"host": "db.example", "password": "s3cret", "url": "postgres://app:hunter2@db.example/app"},
    "token": "tok-abc",
}
_META = {"db.host": SourceInfo(layer="app", path="/opt/app/config.toml", key="db.host")}


def _texts(config: Config) -> dict[str, str]:
    return {
        "repr": repr(config),
        "str": str(config),
        "f-string": f"{config}",
        "percent": "%s" % config,  # noqa: UP031 - the form logging uses for its arguments
        "pprint": pprint.pformat(config),
        "rich": pretty_repr(config),
    }


@os_agnostic
def test_no_text_form_of_a_config_shows_a_secret() -> None:
    config = Config(_DATA, _META)

    for form, text in _texts(config).items():
        assert "s3cret" not in text, form
        assert "tok-abc" not in text, form
        assert "hunter2" not in text, form
        assert "db.example" in text, form
        assert REDACTED_PLACEHOLDER in text, form


@os_agnostic
def test_the_text_form_shows_the_redacted_data_and_counts_the_provenance() -> None:
    config = Config(_DATA, _META)

    assert repr(config) == f"Config({config.as_dict(redact=True)!r}, provenance for 1 key)"


@os_agnostic
def test_a_path_declared_not_sensitive_is_shown_in_the_text_form() -> None:
    config = Config({"limits": {"max_token_bytes": 4096}}, {}, NotSensitiveKeys.of(["limits.max_token_bytes"]))

    assert "4096" in repr(config)


@os_agnostic
def test_a_config_too_deep_to_redact_still_has_a_text_form_without_its_values() -> None:
    deep: dict[str, Any] = {"leaf": "s3cret"}
    for _ in range(400):
        deep = {"n": deep}

    text = repr(Config({"top": deep}, {}))

    assert "s3cret" not in text
    assert text == "Config(<1 top-level key, too deeply nested to show>, provenance for 0 keys)"


@os_agnostic
def test_a_hand_built_config_with_a_key_that_is_not_text_still_has_a_text_form() -> None:
    config = Config(cast("dict[str, Any]", {1: "s3cret"}), {})

    text = repr(config)

    assert "s3cret" not in text
    assert text == "Config(<1 top-level key, not shown: a key is not a string>, provenance for 0 keys)"


class _UnprintableValue:
    def __repr__(self) -> str:
        raise TypeError("this value cannot be printed")


@os_agnostic
def test_a_value_whose_own_repr_fails_is_not_reported_as_a_key_that_is_not_text() -> None:
    config = Config({"a": _UnprintableValue()}, {})

    with pytest.raises(TypeError, match="this value cannot be printed"):
        repr(config)
