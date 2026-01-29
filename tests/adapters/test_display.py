"""Tests for Rich-styled configuration display.

Covers display_config behavior - private helper functions are tested
implicitly through the public API.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from lib_layered_config import Config, OutputFormat, display_config
from lib_layered_config.domain.config import SourceInfo


@pytest.fixture
def config_factory() -> Callable[[dict[str, Any]], Config]:
    """Create real Config instances from test data dicts."""

    def _factory(data: dict[str, Any]) -> Config:
        return Config(data, {})

    return _factory


@pytest.fixture
def source_info_factory() -> Callable[[str, str, str | None], SourceInfo]:
    """Create SourceInfo dicts for provenance-tracking tests."""

    def _factory(key: str, layer: str, path: str | None = None) -> SourceInfo:
        return {"layer": layer, "path": path, "key": key}

    return _factory


# ======================== display_config — header ========================


def test_display_human_shows_header_comment(capsys: pytest.CaptureFixture[str]) -> None:
    """Human output must start with explanatory header about TOML formatting."""
    config = Config({"key": "value"}, {})
    display_config(config, output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    # Header appears first (may be wrapped by console)
    assert "# Note: Nested dictionaries are displayed as" in output
    assert "[section.subsection]" in output
    # Header comes before any config content
    header_pos = output.find("# Note:")
    value_pos = output.find('key = "value"')
    assert header_pos < value_pos


def test_display_json_does_not_show_header(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON output must not include the human-readable header."""
    config = Config({"key": "value"}, {})
    display_config(config, output_format=OutputFormat.JSON)
    output = capsys.readouterr().out

    assert "# Note:" not in output
    assert output.strip().startswith("{")


# ======================== display_config — error paths ========================


def test_display_config_raises_for_nonexistent_section(
    config_factory: Callable[[dict[str, Any]], Config],
) -> None:
    """Requesting a section that doesn't exist must raise ValueError."""
    config = config_factory({"existing_section": {"key": "value"}})
    with pytest.raises(ValueError, match="not found"):
        display_config(config, output_format=OutputFormat.HUMAN, section="nonexistent")


def test_display_config_raises_for_nonexistent_section_json(
    config_factory: Callable[[dict[str, Any]], Config],
) -> None:
    """Requesting a nonexistent section in JSON format must also raise ValueError."""
    config = config_factory({"existing_section": {"key": "value"}})
    with pytest.raises(ValueError, match="not found"):
        display_config(config, output_format=OutputFormat.JSON, section="nonexistent")


# ======================== display_config — scalar rendering ========================


def test_display_human_renders_scalars_as_key_value(capsys: pytest.CaptureFixture[str]) -> None:
    """Top-level scalars must render as 'key = value', not as [key] section headers."""
    # Include a nested dict to verify section handling
    config = Config({"app_name": "myapp", "section": {"nested": {"key": "val"}}}, {})
    display_config(config, output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    assert "[app_name]" not in output
    assert 'app_name = "myapp"' in output
    # rtoml skips intermediate sections with no direct keys, goes straight to deepest
    assert "[section.nested]" in output


def test_display_human_renders_scalar_provenance(
    capsys: pytest.CaptureFixture[str],
    source_info_factory: Callable[..., SourceInfo],
) -> None:
    """Top-level scalars must show source provenance comment when metadata exists."""
    metadata: dict[str, SourceInfo] = {
        "codecov_token": source_info_factory("codecov_token", "dotenv", "/app/.env"),
    }
    config = Config({"codecov_token": "***REDACTED***"}, metadata)
    display_config(config, output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    assert "# layer:dotenv profile:none (/app/.env)" in output
    assert 'codecov_token = "***REDACTED***"' in output
    assert "[codecov_token]" not in output


def test_display_human_renders_profile_in_provenance(
    capsys: pytest.CaptureFixture[str],
    source_info_factory: Callable[..., SourceInfo],
) -> None:
    """Profile name must appear in source provenance comment."""
    # Use a leaf value directly under section to get provenance shown
    metadata: dict[str, SourceInfo] = {
        "section.key": source_info_factory("section.key", "user", "/home/user/.config/app/config.toml"),
    }
    # Include nested dict so section becomes a header (not inline), but also has a leaf
    config = Config({"section": {"key": "value", "nested": {"deep": "val"}}}, metadata)

    display_config(config, output_format=OutputFormat.HUMAN, profile="production")

    output = capsys.readouterr().out
    assert "# layer:user profile:production" in output


def test_display_human_deeply_nested_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Deeply nested dicts render as dotted TOML sections (rtoml standard format)."""
    config = Config({"top": {"mid": {"deep": {"deeper": "value"}}}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # rtoml skips intermediate empty sections, goes directly to deepest section with keys
    assert "[top.mid.deep]" in output
    assert 'deeper = "value"' in output


# ======================== Falsey value handling ========================


def test_display_config_displays_section_with_zero_value(capsys: pytest.CaptureFixture[str]) -> None:
    """Section with integer zero value must display (not raise as 'not found')."""
    config = Config({"section": {"count": 0}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="section")

    output = capsys.readouterr().out
    assert "count = 0" in output


def test_display_config_displays_section_with_false_value(capsys: pytest.CaptureFixture[str]) -> None:
    """Section with boolean False value must display (not raise as 'not found')."""
    config = Config({"section": {"enabled": False}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="section")

    output = capsys.readouterr().out
    # TOML uses lowercase 'false', not Python's 'False'
    assert "enabled = false" in output


def test_display_config_json_displays_section_with_falsey_values(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON format with falsey values must display (not raise as 'not found')."""
    config = Config({"section": {"count": 0, "enabled": False, "items": []}}, {})

    display_config(config, output_format=OutputFormat.JSON, section="section")

    output = capsys.readouterr().out
    assert '"count": 0' in output
    assert '"enabled": false' in output
    assert '"items": []' in output


# ======================== JSON output ========================


def test_display_json_full_config(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON format must output valid JSON with all sections."""
    config = Config({"section": {"key": "value"}, "another": {"num": 42}}, {})

    display_config(config, output_format=OutputFormat.JSON)

    output = capsys.readouterr().out
    assert '"section"' in output
    assert '"key": "value"' in output
    assert '"another"' in output
    assert '"num": 42' in output


def test_display_json_single_section(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON format with section filter must output only that section."""
    config = Config({"section": {"key": "value"}, "other": {"data": "ignored"}}, {})

    display_config(config, output_format=OutputFormat.JSON, section="section")

    output = capsys.readouterr().out
    assert '"section"' in output
    assert '"key": "value"' in output
    assert "other" not in output


# ======================== Redaction ========================


def test_display_human_redacts_sensitive_values(capsys: pytest.CaptureFixture[str]) -> None:
    """Sensitive values should be redacted in human output."""
    config = Config({"email": {"password": "secret123", "host": "smtp.example.com"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "secret123" not in output
    assert "***REDACTED***" in output
    assert "smtp.example.com" in output


def test_display_json_redacts_sensitive_values(capsys: pytest.CaptureFixture[str]) -> None:
    """Sensitive values should be redacted in JSON output."""
    config = Config({"email": {"password": "secret123", "host": "smtp.example.com"}}, {})

    display_config(config, output_format=OutputFormat.JSON)

    output = capsys.readouterr().out
    assert "secret123" not in output
    assert "***REDACTED***" in output
    assert "smtp.example.com" in output


# ======================== List values ========================


def test_display_human_renders_list_values(capsys: pytest.CaptureFixture[str]) -> None:
    """List values should be rendered as TOML arrays."""
    config = Config({"section": {"items": ["a", "b", "c"]}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # rtoml uses spaces after commas in arrays (standard TOML formatting)
    assert '["a", "b", "c"]' in output


def test_display_human_renders_empty_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty list values should render correctly."""
    config = Config({"section": {"items": []}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "items = []" in output


# ======================== Empty section handling ========================


def test_display_human_renders_empty_dict_as_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty dicts are rendered as empty sections by rtoml (valid TOML)."""
    config = Config({"lib_log_rich": {"console_styles": {}, "service": "myapp"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "[lib_log_rich]" in output
    assert "service" in output
    # rtoml renders empty dicts as empty section headers (valid TOML)
    assert "[lib_log_rich.console_styles]" in output


def test_display_human_renders_nested_empty_dicts(capsys: pytest.CaptureFixture[str]) -> None:
    """Nested empty dicts are rendered as empty sections by rtoml."""
    config = Config({"top": {"mid": {"empty": {}}, "value": "exists"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "[top]" in output
    assert "value" in output
    # rtoml renders empty dicts as section headers
    assert "[top.mid.empty]" in output


def test_display_human_prints_leaf_values_under_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Leaf values must appear under their section header."""
    # payload_limits has nested dict, so it becomes a subsection
    config = Config(
        {"lib_log_rich": {"payload_limits": {"nested": {"deep": "val"}}, "rate_limit": [], "service": "myapp"}}, {}
    )

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # lib_log_rich should appear as a section with its direct children
    lib_log_rich_pos = output.find("[lib_log_rich]")
    rate_limit_pos = output.find("rate_limit")
    service_pos = output.find("service")

    # rate_limit and service should come after [lib_log_rich] header
    assert lib_log_rich_pos < rate_limit_pos
    assert lib_log_rich_pos < service_pos


def test_display_human_renders_nested_dict_as_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Nested dicts render as separate section headers (standard TOML format)."""
    # config_options is a nested dict - rtoml always uses section headers for dicts
    config = Config({"lib_log_rich": {"config_options": {"level": "INFO", "format": "json"}, "service": "myapp"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # rtoml uses section headers for all nested dicts (standard TOML format)
    assert "[lib_log_rich.config_options]" in output
    assert 'level = "INFO"' in output
    assert 'format = "json"' in output
    assert "[lib_log_rich]" in output
    assert "service" in output


def test_display_human_renders_empty_dict_value(
    capsys: pytest.CaptureFixture[str],
    source_info_factory: Callable[..., SourceInfo],
) -> None:
    """Empty dicts render as empty section headers (valid TOML)."""
    metadata: dict[str, SourceInfo] = {
        "lib_log_rich.console_styles": source_info_factory(
            "lib_log_rich.console_styles", "app", "/etc/myapp/config.toml"
        ),
    }
    config = Config({"lib_log_rich": {"console_styles": {}, "service": "myapp"}}, metadata)

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # rtoml renders empty dicts as empty section headers
    assert "[lib_log_rich.console_styles]" in output


# ======================== Scalar section filtering ========================


def test_display_human_single_scalar_section(capsys: pytest.CaptureFixture[str]) -> None:
    """Requesting a scalar value by section name should display it directly."""
    config = Config({"top_level_string": "hello", "section": {"key": "value"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="top_level_string")

    output = capsys.readouterr().out
    assert 'top_level_string = "hello"' in output
    assert "[top_level_string]" not in output


def test_display_human_scalar_section_with_provenance(
    capsys: pytest.CaptureFixture[str],
    source_info_factory: Callable[..., SourceInfo],
) -> None:
    """Scalar section with provenance should show source comment."""
    metadata: dict[str, SourceInfo] = {
        "app_name": source_info_factory("app_name", "defaults", "/app/defaults.toml"),
    }
    config = Config({"app_name": "myapp", "other": {"key": "val"}}, metadata)

    display_config(config, output_format=OutputFormat.HUMAN, section="app_name")

    output = capsys.readouterr().out
    assert "# layer:defaults profile:none (/app/defaults.toml)" in output
    assert 'app_name = "myapp"' in output


def test_display_human_scalar_section_integer(capsys: pytest.CaptureFixture[str]) -> None:
    """Integer scalar section should display correctly."""
    config = Config({"port": 8080, "section": {"key": "value"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="port")

    output = capsys.readouterr().out
    assert "port = 8080" in output


def test_display_human_scalar_section_boolean(capsys: pytest.CaptureFixture[str]) -> None:
    """Boolean scalar section should display correctly with TOML format."""
    config = Config({"debug": True, "section": {"key": "value"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="debug")

    output = capsys.readouterr().out
    assert "debug = true" in output


def test_display_human_scalar_section_list(capsys: pytest.CaptureFixture[str]) -> None:
    """List scalar section should display correctly."""
    config = Config({"hosts": ["a", "b"], "section": {"key": "value"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="hosts")

    output = capsys.readouterr().out
    assert 'hosts = ["a","b"]' in output


def test_display_human_scalar_section_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    """Redacted scalar section should display with dim red styling."""
    config = Config({"api_token": "secret123", "section": {"key": "value"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN, section="api_token")

    output = capsys.readouterr().out
    assert "***REDACTED***" in output
    assert "secret123" not in output
