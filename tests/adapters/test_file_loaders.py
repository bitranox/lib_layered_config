from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError, NotFoundError

from tests.support.os_markers import os_agnostic


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
def test_toml_loader_refuses_unfinished_lists(tmp_path: Path) -> None:
    path = _write(tmp_path / "broken.toml", "not = ['valid'", encoding="utf-8")
    with pytest.raises(InvalidFormatError):
        TOMLFileLoader().load(str(path))


@pytest.mark.skipif(structured_module.yaml is None, reason="PyYAML not available")
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


@pytest.mark.skipif(structured_module.yaml is None, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_cries_out_on_illegal_syntax(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.yaml", "key: : :\n", encoding="utf-8")
    with pytest.raises(InvalidFormatError):
        YAMLFileLoader().load(str(path))


@os_agnostic
def test_yaml_parser_returns_empty_dict_when_document_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_yaml = SimpleNamespace(safe_load=lambda _: None, YAMLError=Exception)
    empty_mapping = structured_module._parse_yaml_bytes(b"", fake_yaml, "memory.yaml")
    assert empty_mapping == {}


@os_agnostic
def test_yaml_parser_wraps_yaml_errors_with_context(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(Exception):
        pass

    def explode(_: bytes) -> None:
        raise Boom("boom")

    fake_yaml = SimpleNamespace(safe_load=explode, YAMLError=Boom)
    with pytest.raises(InvalidFormatError) as exc:
        structured_module._parse_yaml_bytes(b"", fake_yaml, "memory.yaml")
    assert "memory.yaml" in str(exc.value)


def _write(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Write text to *path* and return the path so the call reads like a sentence."""

    path.write_text(text, encoding=encoding)
    return path
