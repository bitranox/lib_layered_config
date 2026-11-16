"""An identifier refusal names the refused value with its control characters escaped.

User decision 2026-11-16 (R2-F4): a refused vendor, app, slug or hostname was printed raw, so a trailing
newline was invisible and an ESC sequence reached the terminal. A control character is now written as
``\\uXXXX``; an ordinary refused value prints exactly as before.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.domain.identifiers import validate_hostname, validate_identifier, validate_vendor_app
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable

_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")

_VALIDATORS: dict[str, Callable[[str], str]] = {
    "identifier": lambda value: validate_identifier(value, "slug"),
    "vendor_app": lambda value: validate_vendor_app(value, "app"),
    "hostname": validate_hostname,
}

# Each reaches a different refusal: a bad character, non-ASCII, a bad first character, a trailing space.
_VALUES = ["demo\n", "de\x1b[31mmo", "d\u00e9mo\x85", ".x\t", "-x\x7f", "x\x01 "]


def _refusal(validator: str, value: str) -> str:
    with pytest.raises(ValidationError) as caught:
        _VALIDATORS[validator](value)
    return str(caught.value)


@os_agnostic
@pytest.mark.parametrize("validator", sorted(_VALIDATORS))
@pytest.mark.parametrize("value", _VALUES)
def test_a_refusal_writes_each_control_character_as_an_escape(validator: str, value: str) -> None:
    message = _refusal(validator, value)

    assert _CONTROL.search(message) is None
    escaped = _CONTROL.sub(lambda match: f"\\u{ord(match.group()):04x}", value)
    assert message.endswith(f": {escaped}")


@os_agnostic
@pytest.mark.parametrize(
    ("validator", "value", "message"),
    [
        ("identifier", "my/app", "slug contains invalid characters: my/app"),
        ("vendor_app", "a\\b", "app contains invalid characters: a\\b"),
        ("hostname", "-host", "hostname must start with an alphanumeric character: -host"),
    ],
)
def test_an_ordinary_refused_value_prints_as_before(validator: str, value: str, message: str) -> None:
    assert _refusal(validator, value) == message
