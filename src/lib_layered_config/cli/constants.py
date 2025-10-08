"""Shared CLI constants used across command modules."""

from __future__ import annotations

from typing import Final

CLICK_CONTEXT_SETTINGS: Final[dict[str, tuple[str, str]]] = {"help_option_names": ("-h", "--help")}
TRACEBACK_SUMMARY: Final[int] = 500
TRACEBACK_VERBOSE: Final[int] = 10_000
TARGET_CHOICES: Final[tuple[str, ...]] = ("app", "host", "user")
EXAMPLE_PLATFORM_CHOICES: Final[tuple[str, ...]] = ("posix", "windows")
DEFAULT_JSON_INDENT: Final[int] = 2
