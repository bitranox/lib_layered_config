"""Edge case tests to achieve maximum coverage.

These tests target specific branches and error paths that are not exercised
by the main test suite. Each test is laser-focused on a single edge case.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support.os_markers import os_agnostic


# =============================================================================
# CLI Helpers: describe_distribution fallback paths
# =============================================================================


@os_agnostic
def test_describe_distribution_uses_info_lines_when_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When info_lines is callable, describe_distribution yields its output."""
    from lib_layered_config.cli import common as common_module

    fake_metadata = SimpleNamespace(
        name="test",
        title="Test",
        version="1.0.0",
        homepage="https://test.com",
        author="Test Author",
        author_email="test@test.com",
        shell_command="test",
        info_lines=lambda: ["Line 1", "Line 2"],
    )
    monkeypatch.setattr(common_module, "package_metadata", fake_metadata)

    lines = list(common_module.describe_distribution())

    assert lines == ["Line 1", "Line 2"]


@os_agnostic
def test_fallback_info_lines_uses_metadata_fields_when_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When metadata_fields is callable, _fallback_info_lines uses its output."""
    from lib_layered_config.cli import common as common_module

    fake_metadata = SimpleNamespace(
        name="test",
        title="Test Package",
        version="2.0.0",
        homepage="https://example.com",
        author="Author",
        author_email="author@example.com",
        shell_command="testcmd",
        metadata_fields=lambda: (
            ("custom", "value"),
            ("another", "field"),
        ),
    )
    monkeypatch.setattr(common_module, "package_metadata", fake_metadata)

    lines = common_module._fallback_info_lines()

    assert any("custom" in line for line in lines)


# =============================================================================
# Path Resolver: strategy and context property access
# =============================================================================


@os_agnostic
def test_path_resolver_strategy_property_returns_strategy(tmp_path: Path) -> None:
    """The strategy property should expose the current platform strategy."""
    from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="linux",
    )

    assert resolver.strategy is not None
    assert "Linux" in type(resolver.strategy).__name__


@os_agnostic
def test_path_resolver_context_property_returns_context(tmp_path: Path) -> None:
    """The context property should expose the platform context."""
    from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="darwin",
    )

    assert resolver.context is not None
    assert resolver.context.slug == "demo"


@os_agnostic
def test_path_resolver_unknown_platform_returns_none_strategy() -> None:
    """An unknown platform should result in no strategy selected."""
    from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="freebsd",
    )

    assert resolver.strategy is None


# =============================================================================
# Linux Strategy: fallback host path (line 66)
# =============================================================================


@os_agnostic
def test_linux_host_fallback_to_etc_location(tmp_path: Path) -> None:
    """When XDG host file is missing, Linux falls back to /etc location."""
    from tests.support import create_layered_sandbox
    from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver

    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="Demo",
        slug="demo",
        platform="linux",
    )

    # Create only the fallback location file (not XDG location)
    etc_host = sandbox.roots["host"] / "test-host.toml"
    etc_host.parent.mkdir(parents=True, exist_ok=True)
    etc_host.write_text("[service]\nvalue = 1\n", encoding="utf-8")

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        env=sandbox.env,
        platform="linux",
        hostname="test-host",
    )

    host_paths = list(resolver.host())
    assert any("test-host.toml" in path for path in host_paths)


# =============================================================================
# Identifier validation: additional edge cases
# =============================================================================


@os_agnostic
def test_validate_hostname_invalid_pattern_raises() -> None:
    """Hostname with invalid pattern (not starting with alnum) raises ValueError."""
    from lib_layered_config.domain.identifiers import validate_hostname

    # This specifically hits line 131 - the fallback error
    with pytest.raises(ValueError, match="hostname contains invalid characters"):
        validate_hostname("!invalid")


@os_agnostic
def test_validate_vendor_app_invalid_pattern_fallback() -> None:
    """Vendor/app with non-ASCII after passing other checks raises."""
    from lib_layered_config.domain.identifiers import validate_vendor_app

    # This hits line 122 - the fallback error for permissive pattern
    with pytest.raises(ValueError, match="vendor contains invalid characters"):
        validate_vendor_app("test|invalid", "vendor")


@os_agnostic
def test_validate_vendor_app_trailing_space() -> None:
    """Vendor/app ending with space raises ValueError (line 137)."""
    from lib_layered_config.domain.identifiers import validate_vendor_app

    with pytest.raises(ValueError, match="cannot end with a dot or space"):
        validate_vendor_app("Acme Corp ", "vendor")


@os_agnostic
def test_validate_path_segment_with_dots_allowed() -> None:
    """Path segment validation with allow_dots=True skips pattern check."""
    from lib_layered_config.domain.identifiers import validate_path_segment

    # This exercises line 199 - early return when allow_dots is True
    result = validate_path_segment("test.host.name", "hostname", allow_dots=True)
    assert result == "test.host.name"


# =============================================================================
# YAML Loader: NotFoundError when PyYAML unavailable
# =============================================================================


@os_agnostic
def test_require_yaml_module_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_require_yaml_module raises NotFoundError when PyYAML is not installed."""
    from lib_layered_config.adapters.file_loaders import structured
    from lib_layered_config.domain.errors import NotFoundError

    # Force yaml to None to simulate missing dependency
    monkeypatch.setattr(structured, "yaml", None)
    monkeypatch.setattr(
        structured,
        "_load_yaml_module",
        lambda: None,
    )

    with pytest.raises(NotFoundError, match="PyYAML is required"):
        structured._require_yaml_module()
