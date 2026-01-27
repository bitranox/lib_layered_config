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


# ---------------------------------------------------------------------------
# Redaction tests
# ---------------------------------------------------------------------------


def _make_sensitive_config() -> Config:
    data = {
        "db": {"host": "localhost", "password": "s3cret"},
        "api_token": "tok123",
        "debug": True,
    }
    meta = {
        "db.host": SourceInfo(layer="app", path="/etc/app.toml", key="db.host"),
        "db.password": SourceInfo(layer="app", path="/etc/app.toml", key="db.password"),
        "api_token": SourceInfo(layer="env", path=None, key="api_token"),
        "debug": SourceInfo(layer="env", path=None, key="debug"),
    }
    return Config(data, meta)


@os_agnostic
def test_config_to_json_redact_masks_sensitive_keys() -> None:
    config = _make_sensitive_config()
    payload = json.loads(config.to_json(redact=True))
    assert payload["db"]["password"] == "***REDACTED***"
    assert payload["api_token"] == "***REDACTED***"
    assert payload["db"]["host"] == "localhost"
    assert payload["debug"] is True


@os_agnostic
def test_config_to_json_redact_with_indent() -> None:
    config = _make_sensitive_config()
    formatted = config.to_json(indent=2, redact=True)
    assert "***REDACTED***" in formatted
    assert "\n" in formatted


@os_agnostic
def test_config_as_dict_redact_masks_sensitive_keys() -> None:
    config = _make_sensitive_config()
    result = config.as_dict(redact=True)
    assert result["db"]["password"] == "***REDACTED***"
    assert result["api_token"] == "***REDACTED***"
    assert result["db"]["host"] == "localhost"


@os_agnostic
def test_config_as_dict_redact_does_not_mutate_original() -> None:
    config = _make_sensitive_config()
    _ = config.as_dict(redact=True)
    assert config.get("db.password") == "s3cret"
    assert config.get("api_token") == "tok123"


@os_agnostic
def test_config_to_json_compact_produces_valid_json() -> None:
    config = make_config()
    result = config.to_json()
    parsed = json.loads(result)
    assert parsed["feature"] is True
    assert parsed["db"]["host"] == "localhost"


# ---------------------------------------------------------------------------
# Deep merge tests for with_overrides()
# ---------------------------------------------------------------------------


@os_agnostic
def test_with_overrides_deep_merge_preserves_sibling_keys() -> None:
    cfg = Config({"db": {"host": "localhost", "port": 5432}}, {})
    result = cfg.with_overrides({"db": {"host": "newhost"}})
    assert result["db"] == {"host": "newhost", "port": 5432}


@os_agnostic
def test_with_overrides_deep_merge_multiple_nesting_levels() -> None:
    cfg = Config({"a": {"b": {"c": 1, "d": 2}, "e": 3}}, {})
    result = cfg.with_overrides({"a": {"b": {"c": 99}}})
    assert result["a"]["b"] == {"c": 99, "d": 2}
    assert result["a"]["e"] == 3


@os_agnostic
def test_with_overrides_deep_merge_adds_new_nested_key() -> None:
    cfg = Config({"db": {"host": "localhost"}}, {})
    result = cfg.with_overrides({"db": {"port": 5432}})
    assert result["db"] == {"host": "localhost", "port": 5432}


@os_agnostic
def test_with_overrides_deep_merge_adds_new_top_level_key() -> None:
    cfg = Config({"db": {"host": "localhost"}}, {})
    result = cfg.with_overrides({"cache": {"ttl": 60}})
    assert result["cache"] == {"ttl": 60}
    assert result["db"]["host"] == "localhost"


@os_agnostic
def test_with_overrides_scalar_replaces_dict() -> None:
    cfg = Config({"db": {"host": "localhost", "port": 5432}}, {})
    result = cfg.with_overrides({"db": "sqlite:///db.sqlite"})
    assert result["db"] == "sqlite:///db.sqlite"


@os_agnostic
def test_with_overrides_dict_replaces_scalar() -> None:
    cfg = Config({"db": "sqlite:///db.sqlite"}, {})
    result = cfg.with_overrides({"db": {"host": "localhost"}})
    assert result["db"] == {"host": "localhost"}


@os_agnostic
def test_with_overrides_list_replaced_not_merged() -> None:
    cfg = Config({"tags": ["a", "b"]}, {})
    result = cfg.with_overrides({"tags": ["c"]})
    assert result["tags"] == ["c"]


@os_agnostic
def test_with_overrides_does_not_mutate_original_nested() -> None:
    cfg = Config({"db": {"host": "localhost", "port": 5432}}, {})
    cfg.with_overrides({"db": {"host": "newhost"}})
    assert cfg["db"]["host"] == "localhost"
    assert cfg["db"]["port"] == 5432


@os_agnostic
def test_with_overrides_empty_overrides_returns_equivalent_config() -> None:
    cfg = Config({"db": {"host": "localhost"}}, {})
    result = cfg.with_overrides({})
    assert result["db"]["host"] == "localhost"


# ---------------------------------------------------------------------------
# Unit tests for _deep_merge() helper
# ---------------------------------------------------------------------------


@os_agnostic
def test_deep_merge_disjoint_keys() -> None:
    result = config_module._deep_merge({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


@os_agnostic
def test_deep_merge_overlapping_nested_dicts() -> None:
    base = {"x": {"y": 1, "z": 2}}
    overrides = {"x": {"y": 10, "w": 3}}
    result = config_module._deep_merge(base, overrides)
    assert result == {"x": {"y": 10, "z": 2, "w": 3}}


@os_agnostic
def test_deep_merge_override_scalar_over_nested() -> None:
    result = config_module._deep_merge({"k": {"a": 1}}, {"k": "flat"})
    assert result == {"k": "flat"}


@os_agnostic
def test_deep_merge_override_nested_over_scalar() -> None:
    result = config_module._deep_merge({"k": "flat"}, {"k": {"a": 1}})
    assert result == {"k": {"a": 1}}


@os_agnostic
def test_deep_merge_empty_base() -> None:
    result = config_module._deep_merge({}, {"a": {"b": 1}})
    assert result == {"a": {"b": 1}}


@os_agnostic
def test_deep_merge_empty_overrides() -> None:
    result = config_module._deep_merge({"a": {"b": 1}}, {})
    assert result == {"a": {"b": 1}}
