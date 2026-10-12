"""Redaction reaches a sensitive key inside any container, however the containers nest.

The walk used to recurse only into a dict under a key and a dict directly inside a list, so a
secret one container deeper - a list inside a list, a tuple anywhere, a mapping that is not a
``dict`` - came back in clear. TOML can write the first (``s = [[{password = "x"}]]``), and a
caller building ``Config`` or calling ``redact_mapping`` directly can hand in the others.
"""

from __future__ import annotations

import io
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from lib_layered_config import Config, OutputFormat, display_config, read_config
from lib_layered_config.domain.errors import InvalidFormatError
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, redact_mapping
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_SECRET = "s3cret-value"


@os_agnostic
def test_a_dict_in_a_list_in_a_list_is_redacted() -> None:
    assert redact_mapping({"s": [[{"password": _SECRET, "host": "h"}]]}) == {
        "s": [[{"password": REDACTED_PLACEHOLDER, "host": "h"}]]
    }


@os_agnostic
def test_a_dict_in_a_tuple_is_redacted_and_stays_a_tuple() -> None:
    result = redact_mapping({"s": ({"token": _SECRET},)})

    assert result == {"s": ({"token": REDACTED_PLACEHOLDER},)}
    assert isinstance(result["s"], tuple)


@os_agnostic
def test_a_mapping_that_is_not_a_dict_is_redacted() -> None:
    data: dict[str, Any] = {"db": MappingProxyType({"password": _SECRET})}

    assert redact_mapping(data) == {"db": {"password": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_mixed_nesting_is_redacted_at_every_depth() -> None:
    data: dict[str, Any] = {"a": ([{"b": [({"api_key": _SECRET},)]}],)}

    assert _SECRET not in repr(redact_mapping(data))


@os_agnostic
def test_a_declared_exemption_reaches_through_nested_lists() -> None:
    # A declaration addresses list items without an index, at any list depth.
    result = redact_mapping({"s": [[{"token": "visible", "password": _SECRET}]]}, not_sensitive=["s.token"])

    assert result == {"s": [[{"token": "visible", "password": REDACTED_PLACEHOLDER}]]}


@os_agnostic
def test_list_nesting_the_loader_accepts_still_shows_in_every_redacted_view(tmp_path: Path) -> None:
    # The merge bounds MAPPING nesting at 100 and list nesting not at all, so 120 levels of
    # array load fine; a redacted view must not refuse what reading accepted. JSON, because
    # rtoml (from 0.14.0) refuses TOML nested deeper than 80 levels.
    defaults = tmp_path / "defaults.json"
    defaults.write_text('{"x": ' + "[" * 120 + "1" + "]" * 120 + "}\n", encoding="utf-8")
    config = read_config(
        vendor="Acme",
        app="NestedRedaction",
        slug="nested-redaction-probe",
        default_file=str(defaults),
        start_dir=str(tmp_path),
        dotenv_path=str(tmp_path / "absent.env"),
    )

    assert config.as_dict(redact=True) == config.as_dict()
    assert config.to_json(redact=True) == config.to_json()


@os_agnostic
def test_pathologically_deep_list_nesting_refuses_with_a_readable_error() -> None:
    root: list[object] = []
    node = root
    for _ in range(400):
        child: list[object] = []
        node.append(child)
        node = child

    with pytest.raises(InvalidFormatError):
        redact_mapping({"k": root})


@os_agnostic
def test_a_secret_in_a_nested_toml_array_never_reaches_either_display(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(f's = [[{{password = "{_SECRET}"}}]]\n', encoding="utf-8")
    config = read_config(
        vendor="Acme",
        app="NestedRedaction",
        slug="nested-redaction-probe",
        default_file=str(defaults),
        start_dir=str(tmp_path),
        dotenv_path=str(tmp_path / "absent.env"),
    )
    assert config.get("s") == [[{"password": _SECRET}]], "precondition: the secret was loaded"

    human = io.StringIO()
    display_config(config, console=Console(file=human, width=500, no_color=True))
    display_config(config, output_format=OutputFormat.JSON)

    assert _SECRET not in human.getvalue()
    assert _SECRET not in capsys.readouterr().out
    assert _SECRET not in Config(config.as_dict(), {}).to_json(redact=True)
