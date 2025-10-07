from __future__ import annotations

import json

from lib_layered_config.domain import config as config_module
from lib_layered_config.domain.config import Config, SourceInfo

from tests.support.os_markers import os_agnostic


def make_config() -> Config:
    data = {"db": {"host": "localhost", "port": 5432}, "feature": True}
    meta = {
        "db.host": SourceInfo(layer="app", path="/etc/app.toml", key="db.host"),
        "db.port": SourceInfo(layer="host", path="/etc/host.toml", key="db.port"),
        "feature": SourceInfo(layer="env", path=None, key="feature"),
    }
    return Config(data, meta)


@os_agnostic
def test_config_admits_feature_flag_truthfully() -> None:
    config = make_config()
    assert config["feature"] is True


@os_agnostic
def test_config_invites_membership_checks_like_story_titles() -> None:
    config = make_config()
    assert "db" in config


@os_agnostic
def test_config_counts_top_level_chapters() -> None:
    config = make_config()
    assert len(config) == 2


@os_agnostic
def test_config_iteration_returns_titles_in_creation_order() -> None:
    config = make_config()
    assert list(iter(config)) == ["db", "feature"]


@os_agnostic
def test_config_follow_path_finds_nested_value() -> None:
    config = make_config()
    assert config.get("db.host") == "localhost"


@os_agnostic
def test_config_follow_path_returns_none_when_branch_missing() -> None:
    config = make_config()
    assert config.get("db.password") is None


@os_agnostic
def test_config_follow_path_honours_default_when_branch_missing() -> None:
    config = make_config()
    assert config.get("db.password", default="secret") == "secret"


@os_agnostic
def test_config_clone_keeps_original_untouched() -> None:
    config = make_config()
    clone = config.as_dict()
    clone["db"]["host"] = "remote"
    assert config["db"]["host"] == "localhost"


@os_agnostic
def test_config_to_json_carries_numeric_values() -> None:
    config = make_config()
    payload = json.loads(config.to_json())
    assert payload["db"]["port"] == 5432


@os_agnostic
def test_config_to_json_respects_indent_request() -> None:
    config = make_config()
    formatted = config.to_json(indent=2)
    assert '\n  "db"' in formatted


@os_agnostic
def test_config_origin_names_layer_when_known() -> None:
    config = make_config()
    origin = config.origin("db.port")
    assert origin is not None and origin["layer"] == "host"


@os_agnostic
def test_config_origin_returns_none_for_unknown_key() -> None:
    config = make_config()
    assert config.origin("missing") is None


@os_agnostic
def test_config_with_overrides_returns_new_value() -> None:
    config = make_config()
    replaced = config.with_overrides({"feature": False})
    assert replaced["feature"] is False


@os_agnostic
def test_config_with_overrides_preserves_original_story() -> None:
    config = make_config()
    config.with_overrides({"feature": False})
    assert config["feature"] is True


@os_agnostic
def test_config_with_overrides_reuses_metadata() -> None:
    config = make_config()
    replaced = config.with_overrides({"feature": False})
    assert replaced.origin("feature") == config.origin("feature")


@os_agnostic
def test_follow_path_returns_default_when_start_is_scalar() -> None:
    assert config_module._follow_path(5, "foo", default="bar") == "bar"


@os_agnostic
def test_clone_map_keeps_tuple_shape_intact() -> None:
    sample = {"letters": ("a", "b")}
    clone = config_module._clone_map(sample)
    assert clone["letters"] == ("a", "b")


@os_agnostic
def test_clone_map_keeps_set_shape_intact() -> None:
    sample = {"flags": {"alpha", "beta"}}
    clone = config_module._clone_map(sample)
    assert clone["flags"] == {"alpha", "beta"}


@os_agnostic
def test_clone_map_keeps_nested_list_shape_intact() -> None:
    sample = {"nested": [{"value": 1}]}
    clone = config_module._clone_map(sample)
    assert clone["nested"][0]["value"] == 1


@os_agnostic
def test_clone_map_returns_new_dictionary_instance() -> None:
    sample = {"letters": ("a", "b")}
    clone = config_module._clone_map(sample)
    assert clone is not sample


@os_agnostic
def test_looks_like_mapping_rejects_non_string_keys() -> None:
    weird_mapping = {1: "value"}
    assert config_module._looks_like_mapping(weird_mapping) is False
