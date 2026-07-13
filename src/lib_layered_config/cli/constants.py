"""Shared CLI constants used across command modules."""

from __future__ import annotations

from typing import Final

from ..domain.identifiers import Layer

CLICK_CONTEXT_SETTINGS: Final[dict[str, tuple[str, str]]] = {"help_option_names": ("-h", "--help")}
TRACEBACK_SUMMARY: Final[int] = 500
TRACEBACK_VERBOSE: Final[int] = 10_000
#: Deploy target layers, sourced from the Layer enum so the set is defined once.
TARGET_CHOICES: Final[tuple[str, ...]] = (Layer.APP.value, Layer.HOST.value, Layer.USER.value)
EXAMPLE_PLATFORM_CHOICES: Final[tuple[str, ...]] = ("posix", "windows")
DEFAULT_JSON_INDENT: Final[int] = 2
