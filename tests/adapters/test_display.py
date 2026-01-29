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
    # Use nested dict so section becomes a header (flat dicts are inline tables)
    config = Config({"app_name": "myapp", "section": {"nested": {"key": "val"}}}, {})
    display_config(config, output_format=OutputFormat.HUMAN)
    output = capsys.readouterr().out

    assert "[app_name]" not in output
    assert 'app_name = "myapp"' in output
    assert "[section]" in output


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
    """Deeply nested dicts with further nesting render as dotted TOML sub-sections."""
    # Flat dicts are inline tables; nested dicts become section headers
    config = Config({"top": {"mid": {"deep": {"deeper": "value"}}}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # [top] and [top.mid] become section headers; deep is an inline table
    assert "[top]" in output
    assert "[top.mid]" in output
    assert 'deep = { deeper = "value" }' in output


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
    assert "enabled = False" in output


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
    """List values should be rendered as JSON arrays."""
    config = Config({"section": {"items": ["a", "b", "c"]}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert '["a","b","c"]' in output


def test_display_human_renders_empty_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty list values should render correctly."""
    config = Config({"section": {"items": []}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "items = []" in output


# ======================== Empty section handling ========================


def test_display_human_skips_empty_dict_sections(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty dict values should not create section headers."""
    config = Config({"lib_log_rich": {"console_styles": {}, "service": "myapp"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "[lib_log_rich]" in output
    assert "service" in output
    assert "[lib_log_rich.console_styles]" not in output


def test_display_human_skips_nested_empty_dicts(capsys: pytest.CaptureFixture[str]) -> None:
    """Deeply nested empty dicts should not create section headers."""
    config = Config({"top": {"mid": {"empty": {}}, "value": "exists"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "[top]" in output
    assert "value" in output
    assert "[top.mid]" not in output
    assert "[top.mid.empty]" not in output


def test_display_human_prints_leaf_values_before_subsections(capsys: pytest.CaptureFixture[str]) -> None:
    """Leaf values must appear under their section header, before any subsections."""
    # payload_limits has nested dict, so it becomes a subsection
    config = Config(
        {"lib_log_rich": {"payload_limits": {"nested": {"deep": "val"}}, "rate_limit": [], "service": "myapp"}}, {}
    )

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # rate_limit and service should appear under [lib_log_rich], before payload_limits subsection
    lib_log_rich_pos = output.find("[lib_log_rich]")
    payload_limits_pos = output.find("[lib_log_rich.payload_limits]")
    rate_limit_pos = output.find("rate_limit")
    service_pos = output.find("service")

    # rate_limit and service should come BEFORE the payload_limits subsection
    assert lib_log_rich_pos < rate_limit_pos < payload_limits_pos
    assert lib_log_rich_pos < service_pos < payload_limits_pos


def test_display_human_renders_flat_dict_as_inline_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Flat dicts (no nested dicts) should render as inline tables, not sections."""
    # config_options is a flat dict - all values are primitives (non-sensitive keys)
    config = Config({"lib_log_rich": {"config_options": {"level": "INFO", "format": "json"}, "service": "myapp"}}, {})

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    # config_options should appear as inline table, NOT as section header
    assert "[lib_log_rich.config_options]" not in output
    assert 'config_options = { level = "INFO", format = "json" }' in output
    assert "[lib_log_rich]" in output
    assert "service" in output


def test_display_human_renders_empty_dict_with_provenance(
    capsys: pytest.CaptureFixture[str],
    source_info_factory: Callable[..., SourceInfo],
) -> None:
    """Empty dicts should show provenance comment when metadata exists."""
    metadata: dict[str, SourceInfo] = {
        "lib_log_rich.console_styles": source_info_factory(
            "lib_log_rich.console_styles", "app", "/etc/myapp/config.toml"
        ),
    }
    config = Config({"lib_log_rich": {"console_styles": {}, "service": "myapp"}}, metadata)

    display_config(config, output_format=OutputFormat.HUMAN)

    output = capsys.readouterr().out
    assert "# layer:app profile:none (/etc/myapp/config.toml)" in output
    assert "console_styles = {}" in output
