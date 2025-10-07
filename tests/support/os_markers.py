"""Declarative pytest markers that sing about operating system expectations."""

from __future__ import annotations

import os
import sys
from typing import Callable, TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., object])


IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_POSIX = os.name == "posix"

__all__ = [
    "IS_WINDOWS",
    "IS_MAC",
    "IS_POSIX",
    "os_agnostic",
    "posix_only",
    "mac_only",
    "windows_only",
]


def os_agnostic(test: F) -> F:
    """Mark *test* as portable poetry that runs everywhere."""

    return pytest.mark.os_agnostic(test)


def posix_only(test: F) -> F:
    """Mark *test* as a POSIX-only stanza and skip elsewhere."""

    decorated = pytest.mark.skipif(not IS_POSIX, reason="POSIX-only behaviour")(test)
    return pytest.mark.posix_only(decorated)


def mac_only(test: F) -> F:
    """Mark *test* as a macOS ballad and skip on foreign platforms."""

    decorated = pytest.mark.skipif(not IS_MAC, reason="macOS-only behaviour")(test)
    return pytest.mark.mac_only(decorated)


def windows_only(test: F) -> F:
    """Mark *test* as a Windows hymn and skip when not on Windows."""

    decorated = pytest.mark.skipif(not IS_WINDOWS, reason="Windows-only behaviour")(test)
    return pytest.mark.windows_only(decorated)
