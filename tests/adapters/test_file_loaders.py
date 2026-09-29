from __future__ import annotations

import importlib.util
import json
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError, NotFoundError
from tests.adapters.test_loader_errors import _chain
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

# Check installation with find_spec, not `structured_module.yaml`. That module global is
# populated lazily on first use (_load_yaml_module), so at test-collection time it is
# still None even when PyYAML is installed - a plain `yaml is None` skipif silently skips
# these tests forever.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None


@os_agnostic
def test_toml_loader_recites_the_port_number(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[db]\nport = 5432\n")
    port = TOMLFileLoader().load(str(path))["db"]["port"]
    assert port == 5432


@os_agnostic
def test_toml_loader_laments_when_the_file_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(NotFoundError):
        TOMLFileLoader().load(str(missing))


@os_agnostic
def test_json_loader_rejects_broken_braces(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.json", "{invalid}")
    with pytest.raises(InvalidFormatError):
        JSONFileLoader().load(str(path))


@os_agnostic
def test_json_loader_affirms_boolean_truth(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    json.dump({"feature": True}, path.open("w", encoding="utf-8"))
    feature_flag = JSONFileLoader().load(str(path))["feature"]
    assert feature_flag is True


@os_agnostic
def test_loader_rejects_file_over_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structured_module, "MAX_CONFIG_FILE_BYTES", 10)
    path = _write(tmp_path / "big.toml", "key = 'aaaaaaaaaaaaaaaaaaaaaaaa'\n")
    with pytest.raises(InvalidFormatError):
        TOMLFileLoader().load(str(path))


@os_agnostic
def test_toml_loader_refuses_unfinished_lists(tmp_path: Path) -> None:
    path = _write(tmp_path / "broken.toml", "not = ['valid'", encoding="utf-8")
    with pytest.raises(InvalidFormatError):
        TOMLFileLoader().load(str(path))


@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_whispers_only_silence_for_empty_files(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.yaml", "# empty file\n")
    yaml_payload = YAMLFileLoader().load(str(path))
    assert yaml_payload == {}


@os_agnostic
def test_yaml_guard_explains_when_dependency_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structured_module, "_load_yaml_module", lambda: None)
    monkeypatch.setattr(structured_module, "yaml", None)
    with pytest.raises(NotFoundError):
        structured_module._ensure_yaml_available()


@os_agnostic
def test_loader_mapping_guard_rejects_naked_scalars() -> None:
    with pytest.raises(InvalidFormatError):
        structured_module.BaseFileLoader._ensure_mapping(7, path="demo.toml")


@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_cries_out_on_illegal_syntax(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.yaml", "key: : :\n", encoding="utf-8")
    with pytest.raises(InvalidFormatError):
        YAMLFileLoader().load(str(path))


@os_agnostic
def test_yaml_parser_returns_empty_dict_when_document_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_yaml = SimpleNamespace(safe_load=lambda _: None, YAMLError=Exception)
    empty_mapping = structured_module._parse_yaml_text("", fake_yaml, "memory.yaml")
    assert empty_mapping == {}


@os_agnostic
def test_yaml_parser_wraps_yaml_errors_with_context(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoomError(Exception):
        pass

    def explode(_: bytes) -> None:
        raise BoomError("boom")

    fake_yaml = SimpleNamespace(safe_load=explode, YAMLError=BoomError)
    with pytest.raises(InvalidFormatError) as exc:
        structured_module._parse_yaml_text("", fake_yaml, "memory.yaml")
    assert "memory.yaml" in str(exc.value)


@os_agnostic
def test_yaml_parser_wraps_a_bare_value_error_as_invalid_format() -> None:
    """A construction error (e.g. an out-of-range calendar date) raises plain ``ValueError``,
    not the module's ``YAMLError``; it must still surface as ``InvalidFormatError`` naming the
    file, never the parser's own message."""

    class YAMLError(Exception):
        pass

    def explode(_: bytes) -> None:
        raise ValueError("month must be in 1..12, not 13")

    fake_yaml = SimpleNamespace(safe_load=explode, YAMLError=YAMLError)
    with pytest.raises(InvalidFormatError) as exc:
        structured_module._parse_yaml_text("a: 2020-13-01", fake_yaml, "memory.yaml")
    message = str(exc.value)
    assert message == "memory.yaml is not valid YAML"
    assert "13" not in message
    assert "month" not in message
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


@os_agnostic
def test_yaml_parser_wraps_a_recursion_error_as_invalid_format() -> None:
    class YAMLError(Exception):
        pass

    def explode(_: bytes) -> None:
        raise RecursionError("maximum recursion depth exceeded")

    fake_yaml = SimpleNamespace(safe_load=explode, YAMLError=YAMLError)
    with pytest.raises(InvalidFormatError) as exc:
        structured_module._parse_yaml_text("[[[[[[", fake_yaml, "memory.yaml")
    assert str(exc.value) == "memory.yaml is not valid YAML"


@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_refuses_an_out_of_range_calendar_date_without_leaking_the_construction_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """PyYAML's own timestamp constructor raises a bare ``ValueError`` (never ``YAMLError``) for
    ``2020-13-01``; the loader must still refuse it as ``InvalidFormatError`` naming the file."""
    path = _write(tmp_path / "config.yaml", "a: 2020-13-01\n")
    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(InvalidFormatError) as exc:
        YAMLFileLoader().load(str(path))
    message = str(exc.value)
    assert str(path) in message
    # pytest's own tmp_path can legitimately contain "13" (e.g. "pytest-13"), so check
    # leak-freedom on the message with the path removed, not on the raw message.
    without_path = message.replace(str(path), "")
    assert "month" not in without_path
    assert "13" not in without_path
    for link in _chain(exc.value):
        link_text = str(link).replace(str(path), "")
        assert "month" not in link_text
        assert "13" not in link_text
    # Liveness: the capture sees the event, so an absent leak means the event is clean, not unseen.
    assert any(record.getMessage() == "config_file_invalid" for record in caplog.records)
    assert not any("month" in repr(vars(record)) for record in caplog.records)


def _write(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Write text to *path* and return the path so the call reads like a sentence."""

    path.write_text(text, encoding=encoding)
    return path
