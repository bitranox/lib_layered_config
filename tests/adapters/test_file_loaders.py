from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormat, NotFound


def test_toml_loader(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[db]\nport = 5432\n")
    loader = TOMLFileLoader()
    data = loader.load(str(path))
    assert data["db"]["port"] == 5432


def test_toml_loader_missing_file(tmp_path: Path) -> None:
    loader = TOMLFileLoader()
    missing = tmp_path / "missing.toml"
    with pytest.raises(NotFound):
        loader.load(str(missing))


def test_json_loader_invalid(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{invalid}")
    loader = JSONFileLoader()
    with pytest.raises(InvalidFormat):
        loader.load(str(path))


def test_json_loader_valid(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    json.dump({"feature": True}, path.open("w", encoding="utf-8"))
    loader = JSONFileLoader()
    data = loader.load(str(path))
    assert data["feature"] is True


@pytest.mark.skipif(structured_module.yaml is None, reason="PyYAML not available")
def test_yaml_loader_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("# empty file\n")
    loader = YAMLFileLoader()
    data = loader.load(str(path))
    assert data == {}
