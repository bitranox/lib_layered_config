"""A variable that sets a value and another that sets a key below it give one answer in any order.

``DEMO___DB=flat`` and ``DEMO___DB__PORT=2`` cannot both be honoured. Their order in the environment
or the ``.env`` file is not something a user controls reliably (the shell, systemd or docker decides
it), so the loaders must refuse the clash in both orders, name both variables, and never drop one.
A JSON object value is a table, so keys below it merge into it whichever comes first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_SCALAR = ("DB", "flat-value")
_NESTED = ("DB__PORT", "2")
_ORDERS = pytest.mark.parametrize("scalar_first", [True, False], ids=["scalar-first", "nested-first"])


def _ordered(first: tuple[str, str], second: tuple[str, str], *, keep: bool) -> list[tuple[str, str]]:
    return [first, second] if keep else [second, first]


def _load_env(pairs: list[tuple[str, str]]) -> dict[str, object]:
    return DefaultEnvLoader(environ={f"DEMO___{key}": value for key, value in pairs}).load("DEMO")


def _load_dotenv(tmp_path: Path, pairs: list[tuple[str, str]]) -> object:
    path = tmp_path / "app.env"
    path.write_text("".join(f"{key}={value}\n" for key, value in pairs), encoding="utf-8")
    return DefaultDotEnvLoader().load(dotenv_path=str(path))


@os_agnostic
@_ORDERS
def test_env_refuses_a_value_and_a_key_below_it_in_either_order(scalar_first: bool) -> None:
    with pytest.raises(InvalidFormatError) as caught:
        _load_env(_ordered(_SCALAR, _NESTED, keep=scalar_first))

    message = str(caught.value)
    assert "DEMO___DB " in message
    assert "DEMO___DB__PORT" in message
    assert "flat-value" not in message


@os_agnostic
@_ORDERS
def test_dotenv_refuses_a_value_and_a_key_below_it_in_either_order(tmp_path: Path, scalar_first: bool) -> None:
    with pytest.raises(InvalidFormatError) as caught:
        _load_dotenv(tmp_path, _ordered(_SCALAR, _NESTED, keep=scalar_first))

    message = str(caught.value)
    assert "app.env" in message
    assert "DB (line" in message
    assert "DB__PORT (line" in message
    assert "flat-value" not in message


@os_agnostic
@_ORDERS
def test_env_merges_keys_below_a_json_object_in_either_order(scalar_first: bool) -> None:
    loaded = _load_env(_ordered(("DB", '{"host": "h"}'), _NESTED, keep=scalar_first))

    assert loaded == {"db": {"host": "h", "port": 2}}


@os_agnostic
@_ORDERS
def test_dotenv_merges_keys_below_a_json_object_in_either_order(tmp_path: Path, scalar_first: bool) -> None:
    loaded = _load_dotenv(tmp_path, _ordered(("DB", '{"host": "h"}'), _NESTED, keep=scalar_first))

    assert loaded == {"db": {"host": "h", "port": 2}}


@os_agnostic
@_ORDERS
def test_the_deeper_variable_wins_over_the_same_key_inside_a_json_object(scalar_first: bool) -> None:
    loaded = _load_env(_ordered(("DB", '{"port": 1}'), _NESTED, keep=scalar_first))

    assert loaded == {"db": {"port": 2}}


@os_agnostic
def test_env_names_the_variable_whose_json_object_holds_the_blocking_value() -> None:
    with pytest.raises(InvalidFormatError) as caught:
        _load_env([("DB__PORT__NUMBER", "2"), ("DB", '{"port": 1}')])

    message = str(caught.value)
    assert "DEMO___DB " in message
    assert "DEMO___DB__PORT__NUMBER" in message


@os_agnostic
def test_a_repeated_dotenv_key_still_takes_the_last_value(tmp_path: Path) -> None:
    assert _load_dotenv(tmp_path, [("DB__PORT", "1"), ("DB__PORT", "2")]) == {"db": {"port": 2}}


@os_agnostic
@_ORDERS
def test_read_config_reports_the_environment_clash_as_a_layer_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scalar_first: bool
) -> None:
    for key, value in _ordered(_SCALAR, _NESTED, keep=scalar_first):
        monkeypatch.setenv(f"CLASH_KIT___{key}", value)

    with pytest.raises(LayerLoadError, match="CLASH_KIT___DB__PORT"):
        read_config(
            vendor="Acme",
            app="ClashKit",
            slug="clash-kit",
            start_dir=str(tmp_path),
            dotenv_path=str(tmp_path / "absent.env"),
        )
