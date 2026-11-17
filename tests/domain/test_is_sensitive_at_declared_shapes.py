"""``is_sensitive_at`` takes ``not_sensitive`` in the shape the other four functions take.

``read_config``, ``read_config_json``, ``read_config_raw`` and ``redact_mapping`` take a plain list of
dotted paths; ``is_sensitive_at`` took only a built ``NotSensitiveKeys``, so the obvious call
``is_sensitive_at(path, not_sensitive=["db.password"])`` raised ``AttributeError: 'list' object has no
attribute 'covers'`` (user decision 2026-11-17, s12 R5-F5: "Accept both shapes").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import NotSensitiveKeys, is_sensitive_at, redact_mapping
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable


@os_agnostic
@pytest.mark.parametrize(
    "declared",
    [["db.password"], ("db.password",), {"db.password"}, NotSensitiveKeys.of(["db.password"])],
    ids=["list", "tuple", "set", "built"],
)
def test_a_declared_path_is_not_sensitive_in_every_shape(declared: Iterable[str] | NotSensitiveKeys) -> None:
    assert is_sensitive_at(("db", "password"), not_sensitive=declared) is False
    assert is_sensitive_at(("db", "token"), not_sensitive=declared) is True


@os_agnostic
def test_a_generator_of_paths_is_read_once_and_works() -> None:
    declared = (path for path in ["db.password"])

    assert is_sensitive_at(("db", "password"), not_sensitive=declared) is False


@os_agnostic
def test_none_declares_nothing_like_on_the_other_functions() -> None:
    assert is_sensitive_at(("db", "password"), not_sensitive=None) is True
    assert redact_mapping({"db": {"password": "x"}}, not_sensitive=None) == {"db": {"password": "***REDACTED***"}}


@os_agnostic
def test_a_single_str_is_refused_with_the_message_the_other_functions_give() -> None:
    with pytest.raises(TypeError) as from_redact:
        redact_mapping({}, not_sensitive="db.password")
    with pytest.raises(TypeError) as from_is_sensitive_at:
        is_sensitive_at(("db", "password"), not_sensitive="db.password")

    assert str(from_is_sensitive_at.value) == str(from_redact.value)
