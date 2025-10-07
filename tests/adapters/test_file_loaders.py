from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormat, NotFound

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_toml_loader_reads_integer(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[db]\nport = 5432\n")
    loader = TOMLFileLoader()
    data = loader.load(str(path))
    assert data["db"]["port"] == 5432


@os_agnostic
def test_toml_loader_raises_not_found_when_missing(tmp_path: Path) -> None:
    loader = TOMLFileLoader()
    missing = tmp_path / "missing.toml"
    with pytest.raises(NotFound):
        loader.load(str(missing))


@os_agnostic
def test_json_loader_raises_invalid_format_on_bad_payload(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{invalid}")
    loader = JSONFileLoader()
    with pytest.raises(InvalidFormat):
        loader.load(str(path))


@os_agnostic
def test_json_loader_parses_boolean(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    json.dump({"feature": True}, path.open("w", encoding="utf-8"))
    loader = JSONFileLoader()
    data = loader.load(str(path))
    assert data["feature"] is True


@os_agnostic
def test_toml_loader_invalid_format(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("not = ['valid'", encoding="utf-8")
    loader = TOMLFileLoader()
    with pytest.raises(InvalidFormat):
        loader.load(str(path))


@pytest.mark.skipif(structured_module.yaml is None, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_returns_empty_mapping_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("# empty file\n")
    loader = YAMLFileLoader()
    data = loader.load(str(path))
    assert data == {}


@os_agnostic
def test_ensure_yaml_available_raises_when_dependency_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(structured_module, "yaml", None)
    with pytest.raises(NotFound):
        structured_module._ensure_yaml_available()


@os_agnostic
def test_ensure_mapping_rejects_scalar_payload() -> None:
    with pytest.raises(InvalidFormat):
        structured_module.BaseFileLoader._ensure_mapping(7, path="demo.toml")


@pytest.mark.skipif(structured_module.yaml is None, reason="PyYAML not available")
@os_agnostic
def test_yaml_loader_reports_invalid_document(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("key: : :\n", encoding="utf-8")
    loader = YAMLFileLoader()
    with pytest.raises(InvalidFormat):
        loader.load(str(path))
