"""Shared CLI constants used across command modules."""

from __future__ import annotations

from typing import Final

from ..application.ports import OutputFormat
from ..domain.identifiers import DEPLOY_LAYERS, ExamplePlatform

__all__ = [
    "CLICK_CONTEXT_SETTINGS",
    "DEFAULT_JSON_INDENT",
    "EXAMPLE_PLATFORM_CHOICES",
    "OUTPUT_FORMAT_CHOICES",
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
#: Deploy target layers, sourced from DEPLOY_LAYERS so the set is defined once.
TARGET_CHOICES: Final[tuple[str, ...]] = tuple(layer.value for layer in DEPLOY_LAYERS)
#: Example layouts, sourced from the ExamplePlatform enum so the set is defined once.
EXAMPLE_PLATFORM_CHOICES: Final[tuple[str, ...]] = tuple(member.value for member in ExamplePlatform)
#: The read command's --format choices, sourced from the OutputFormat enum so the set is defined once.
OUTPUT_FORMAT_CHOICES: Final[tuple[str, ...]] = tuple(member.value for member in OutputFormat)
DEFAULT_JSON_INDENT: Final[int] = 2
