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
# Environment Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _plain_cli_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin rich-click to plain, uncoloured output for the whole suite.

    Every CLI-output assertion in this suite reads plain text. rich-click's
    ``force_terminal_default()`` (rich_help_configuration.py) checks
    ``FORCE_COLOR``, then ``PY_COLORS``, then ``GITHUB_ACTIONS`` and forces a
    terminal (ANSI colour codes) when the FIRST of those present in the
    environment is truthy. GitHub Actions sets ``GITHUB_ACTIONS=true``, so a
    CI run colours every rendered error panel and an assertion looking for
    plain text fails there while passing locally.

    Setting ``FORCE_COLOR``/``NO_COLOR`` via ``monkeypatch.setenv`` is NOT
    enough: ``rich_click.rich_click`` computes a module-level constant
    ``FORCE_TERMINAL = force_terminal_default()`` once, at import time
    (``rich_click/rich_click.py``), and ``RichCommand._generate_rich_help_config``
    reads it back through ``RichHelpConfiguration.load_from_globals()``, which
    copies ``FORCE_TERMINAL`` (not a fresh env read) into the per-invocation
    config's ``force_terminal`` field. Since rich-click is already imported by
    the time this fixture runs, an env var set here never reaches that cached
    constant. Patch the constant itself so every command invocation in this
    test session sees a pinned, non-forced terminal regardless of what
    ``GITHUB_ACTIONS``/``FORCE_COLOR`` were at interpreter start-up.

    ``adapters/display/rich.py`` builds its console per call (``_build_console()``),
    so it reads ``FORCE_COLOR``/``NO_COLOR`` fresh at call time and no internal
    Rich attribute needs patching - but the value matters, not just presence:
    ``Console.is_terminal`` (``rich/console.py``) reads ``FORCE_COLOR`` as
    ``environ.get("FORCE_COLOR") is not None: return force_color != ""``, so
    an explicit ``FORCE_COLOR=0`` is itself a non-empty value and FORCES a
    terminal - the opposite of what the name suggests (https://force-color.org/
    documents this: presence forces colour, only an EMPTY value or its total
    absence leaves detection to ``NO_COLOR``/``isatty()``). Remove the var
    instead of setting it to "0", so ambient FORCE_COLOR from the calling
    shell cannot leak into the suite either.
    """
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr("rich_click.rich_click.FORCE_TERMINAL", False)


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
