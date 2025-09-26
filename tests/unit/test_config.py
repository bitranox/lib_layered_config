from __future__ import annotations

import json

from lib_layered_config.domain.config import Config, SourceInfo


def make_config() -> Config:
    data = {"db": {"host": "localhost", "port": 5432}, "feature": True}
    meta = {
        "db.host": SourceInfo(layer="app", path="/etc/app.toml", key="db.host"),
        "db.port": SourceInfo(layer="host", path="/etc/host.toml", key="db.port"),
        "feature": SourceInfo(layer="env", path=None, key="feature"),
    }
    return Config(data, meta)


def test_mapping_interface() -> None:
    config = make_config()
    assert config["feature"] is True
    assert "db" in config
    assert len(config) == 2


def test_get_dot_path() -> None:
    config = make_config()
    assert config.get("db.host") == "localhost"
    assert config.get("db.password") is None
    assert config.get("db.password", default="secret") == "secret"


def test_as_dict_returns_deep_copy() -> None:
    config = make_config()
    dictionary = config.as_dict()
    dictionary["db"]["host"] = "remote"
    assert config["db"]["host"] == "localhost"


def test_to_json() -> None:
    config = make_config()
    payload = json.loads(config.to_json())
    assert payload["db"]["port"] == 5432


def test_origin_metadata() -> None:
    config = make_config()
    origin = config.origin("db.port")
    assert origin is not None and origin["layer"] == "host"
    assert config.origin("missing") is None


def test_with_overrides_creates_new_config() -> None:
    config = make_config()
    new_config = config.with_overrides({"feature": False})
    assert new_config["feature"] is False
    assert config["feature"] is True
    assert new_config.origin("feature") == config.origin("feature")
