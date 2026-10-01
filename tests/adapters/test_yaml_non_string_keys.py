"""A YAML key that is not a string is reported, never silently passed on as one.

YAML reads ``1:`` as an int key and ``true:`` as a bool key, while every consumer of a loaded
mapping treats its keys as strings. Until the next major release refuses such keys, the loader
keeps loading the file and logs one ``config_key_not_string`` warning per key, naming the file,
where the key sits and the key itself, and never the value.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

_EVENT = "config_key_not_string"
_SECRET_VALUE = "s3cr3t-value-never-logged"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    """Return the structured context of every non-string-key warning captured."""
    return [record.__dict__["context"] for record in caplog.records if record.message == _EVENT]


def _load(tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture) -> tuple[str, object]:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="lib_layered_config")
    return str(path), YAMLFileLoader().load(str(path))


@os_agnostic
def test_an_int_key_and_a_bool_key_each_log_one_warning_and_the_file_still_loads(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path, loaded = _load(tmp_path, f"1: {_SECRET_VALUE}\nfalse: b\nname: c\n", caplog)

    assert loaded == {1: _SECRET_VALUE, False: "b", "name": "c"}
    found = sorted((ctx["key"], ctx["parent"], ctx["path"]) for ctx in _warnings(caplog))
    assert found == [("1", "", path), ("False", "", path)]


@os_agnostic
def test_a_nested_key_and_a_key_inside_a_list_name_where_they_sit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, _ = _load(tmp_path, "db:\n  5: x\nitems:\n  - name: a\n  - 7: y\n", caplog)

    found = sorted((ctx["key"], ctx["parent"]) for ctx in _warnings(caplog))
    assert found == [("5", "db"), ("7", "items.1")]


@os_agnostic
def test_the_warning_never_carries_the_value(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _, _ = _load(tmp_path, f"1: {_SECRET_VALUE}\nouter:\n  2: {_SECRET_VALUE}\n", caplog)

    assert len(_warnings(caplog)) == 2
    assert all(_SECRET_VALUE not in repr(vars(record)) for record in caplog.records)


@os_agnostic
def test_a_file_with_only_string_keys_logs_no_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _, loaded = _load(tmp_path, "'1': quoted\nservice:\n  timeout: 5\nlist:\n  - a: 1\n", caplog)

    assert loaded == {"1": "quoted", "service": {"timeout": 5}, "list": [{"a": 1}]}
    assert _warnings(caplog) == []


@os_agnostic
def test_read_config_warns_for_a_non_string_key_in_an_app_dot_d_yaml_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.d/10-service.yaml", content="service:\n  3: three\n  timeout: 5\n")
    caplog.set_level(logging.WARNING, logger="lib_layered_config")

    config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))

    assert [(ctx["key"], ctx["parent"]) for ctx in _warnings(caplog)] == [("3", "service")]
    # This is the consequence the warning exists for: a mapping holding a non-string key is
    # merged as ONE value, so its string-keyed siblings are not reachable by dotted lookup.
    assert config.get("service") == {3: "three", "timeout": 5}
    assert config.get("service.timeout") is None
