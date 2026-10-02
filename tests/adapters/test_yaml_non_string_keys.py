"""A YAML key that is not a string refuses the file.

YAML reads ``1:`` as an int key and ``true:`` as a bool key, while every consumer of a loaded
mapping treats its keys as strings: a mapping holding such a key would merge as ONE opaque value,
none of its keys reachable by dotted lookup. The loader refuses the file instead, naming the file,
where each such key sits and the key itself, and never a value.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

_SECRET_VALUE = "s3cr3t-value-never-logged"


def _refusal(tmp_path: Path, text: str) -> tuple[str, str]:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))
    return str(path), str(caught.value)


@os_agnostic
def test_an_int_key_and_a_bool_key_refuse_the_file_naming_both(tmp_path: Path) -> None:
    path, message = _refusal(tmp_path, f"1: {_SECRET_VALUE}\nfalse: b\nname: c\n")

    assert path in message
    assert "1 (int)" in message
    assert "False (bool)" in message


@os_agnostic
def test_a_nested_key_and_a_key_inside_a_list_name_where_they_sit(tmp_path: Path) -> None:
    _, message = _refusal(tmp_path, "db:\n  5: x\nitems:\n  - name: a\n  - 7: y\n")

    assert "db: 5 (int)" in message
    assert "items.1: 7 (int)" in message


@os_agnostic
def test_the_refusal_never_carries_a_value(tmp_path: Path) -> None:
    _, message = _refusal(tmp_path, f"1: {_SECRET_VALUE}\nouter:\n  2: {_SECRET_VALUE}\n")

    assert _SECRET_VALUE not in message


@os_agnostic
def test_a_file_with_only_string_keys_loads(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("'1': quoted\nservice:\n  timeout: 5\nlist:\n  - a: 1\n", encoding="utf-8")

    assert YAMLFileLoader().load(str(path)) == {"1": "quoted", "service": {"timeout": 5}, "list": [{"a": 1}]}


@os_agnostic
def test_read_config_refuses_a_non_string_key_in_an_app_dot_d_yaml_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.d/10-service.yaml", content="service:\n  3: three\n  timeout: 5\n")

    with pytest.raises(LayerLoadError, match=r"service: 3 \(int\)"):
        read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))
