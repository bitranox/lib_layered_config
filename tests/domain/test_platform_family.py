"""Tests for the platform-family and example-platform enums shared by the resolver, deploy and examples."""

from __future__ import annotations

import pytest

from lib_layered_config.domain.identifiers import ExamplePlatform, PlatformFamily, platform_family
from lib_layered_config.domain.source_position import SourcePosition


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("linux", PlatformFamily.LINUX),
        ("linux2", PlatformFamily.LINUX),
        ("darwin", PlatformFamily.MACOS),
        ("win32", PlatformFamily.WINDOWS),
        ("win64", PlatformFamily.WINDOWS),
    ],
)
def test_platform_family_classifies_a_sys_platform_value(platform: str, expected: PlatformFamily) -> None:
    assert platform_family(platform) is expected


@pytest.mark.parametrize("platform", ["freebsd14", "cygwin", "aix", "darwin2", ""])
def test_platform_family_is_none_for_a_platform_with_no_layout(platform: str) -> None:
    """The resolver offers no paths there; each caller decides its own fallback."""
    assert platform_family(platform) is None


def test_the_enum_values_are_the_wire_strings() -> None:
    assert [member.value for member in PlatformFamily] == ["linux", "macos", "windows"]
    assert [member.value for member in ExamplePlatform] == ["posix", "windows"]
    assert ExamplePlatform("windows") is ExamplePlatform.WINDOWS


def test_a_source_position_is_a_line_column_pair_that_still_unpacks() -> None:
    position = SourcePosition(line=3, column=7)

    line, column = position

    assert (line, column) == (3, 7)
    assert position == (3, 7)
    assert position.line == 3
    assert position.column == 7
