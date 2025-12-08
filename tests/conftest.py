"""Shared test fixtures for lib_layered_config test suite.

Centralizes common fixtures to reduce duplication and make test setup discoverable.
All fixtures here are available to all test modules automatically via pytest.

Fixture Categories:
    - Path fixtures: tmp_path variants for test isolation
    - Sandbox fixtures: LayeredSandbox for multi-layer config testing
    - Loader fixtures: Pre-configured adapters for adapter tests
    - CLI fixtures: CliRunner and related utilities
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from click.testing import CliRunner

from tests.support import LayeredSandbox, create_layered_sandbox

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


# =============================================================================
# Common Test Constants
# =============================================================================

DEFAULT_VENDOR = "Acme"
DEFAULT_APP = "Demo"
DEFAULT_SLUG = "demo"


# =============================================================================
# Sandbox Fixtures
# =============================================================================


@pytest.fixture
def sandbox(tmp_path: Path) -> LayeredSandbox:
    """Create a standard layered sandbox with default vendor/app/slug.

    Returns:
        LayeredSandbox configured for 'Acme/Demo/demo' on current platform.
    """
    return create_layered_sandbox(
        tmp_path,
        vendor=DEFAULT_VENDOR,
        app=DEFAULT_APP,
        slug=DEFAULT_SLUG,
    )


@pytest.fixture
def linux_sandbox(tmp_path: Path) -> LayeredSandbox:
    """Create a sandbox emulating Linux paths."""
    return create_layered_sandbox(
        tmp_path,
        vendor=DEFAULT_VENDOR,
        app=DEFAULT_APP,
        slug=DEFAULT_SLUG,
        platform="linux",
    )


@pytest.fixture
def darwin_sandbox(tmp_path: Path) -> LayeredSandbox:
    """Create a sandbox emulating macOS paths."""
    return create_layered_sandbox(
        tmp_path,
        vendor=DEFAULT_VENDOR,
        app=DEFAULT_APP,
        slug=DEFAULT_SLUG,
        platform="darwin",
    )


@pytest.fixture
def windows_sandbox(tmp_path: Path) -> LayeredSandbox:
    """Create a sandbox emulating Windows paths."""
    return create_layered_sandbox(
        tmp_path,
        vendor=DEFAULT_VENDOR,
        app=DEFAULT_APP,
        slug=DEFAULT_SLUG,
        platform="win32",
    )


@pytest.fixture
def applied_sandbox(
    sandbox: LayeredSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> LayeredSandbox:
    """Create a sandbox with environment variables applied to the process."""
    sandbox.apply_env(monkeypatch)
    return sandbox


# =============================================================================
# CLI Fixtures
# =============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a fresh Click CLI test runner."""
    return CliRunner()


# =============================================================================
# Source File Fixtures
# =============================================================================


@pytest.fixture
def source_toml(tmp_path: Path) -> Path:
    """Create a minimal TOML source file for deployment tests.

    Returns:
        Path to a TOML file containing [service] flag = true
    """
    source = tmp_path / "source.toml"
    source.write_text("[service]\nflag = true\n", encoding="utf-8")
    return source


@pytest.fixture
def defaults_toml(tmp_path: Path) -> Path:
    """Create a defaults file for precedence testing.

    Returns:
        Path to a TOML file with service defaults (timeout=3, mode=defaults).
    """
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(
        '[service]\ntimeout = 3\nmode = "defaults"\n',
        encoding="utf-8",
    )
    return defaults
