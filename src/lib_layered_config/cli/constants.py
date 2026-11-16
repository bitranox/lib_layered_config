"""Shared CLI constants used across command modules."""

from __future__ import annotations

from typing import Final

from ..domain.identifiers import ExamplePlatform, Layer

__all__ = [
    "CLICK_CONTEXT_SETTINGS",
    "DEFAULT_JSON_INDENT",
    "EXAMPLE_PLATFORM_CHOICES",
    "TARGET_CHOICES",
    "TRACEBACK_SUMMARY",
    "TRACEBACK_VERBOSE",
]


CLICK_CONTEXT_SETTINGS: Final[dict[str, tuple[str, str]]] = {"help_option_names": ("-h", "--help")}
#: Where an error message is cut without ``--traceback``. The library's refusals put one line per
#: problem, each naming its source, then a hint, and deploy's hint alone is about 290 characters:
#: 500 cut a single refused mode with an ordinary home path. 4000 holds every permission setting
#: refused at once (about 2900) and still bounds a runaway message.
TRACEBACK_SUMMARY: Final[int] = 4000
TRACEBACK_VERBOSE: Final[int] = 10_000
#: Deploy target layers, sourced from the Layer enum so the set is defined once.
TARGET_CHOICES: Final[tuple[str, ...]] = (Layer.APP.value, Layer.HOST.value, Layer.USER.value)
#: Example layouts, sourced from the ExamplePlatform enum so the set is defined once.
EXAMPLE_PLATFORM_CHOICES: Final[tuple[str, ...]] = tuple(member.value for member in ExamplePlatform)
DEFAULT_JSON_INDENT: Final[int] = 2
