"""DefaultPathResolver reads its platform with the same aliases deploy_config and the CLI take.

A direct caller of the resolver writing ``platform="macos"`` or ``"Windows"`` used to get the Linux
layout silently, because the resolver compared the raw string and knew only ``darwin`` and ``win*``.
A ``sys.platform`` value with no alias of its own (``freebsd14``) still selects the Linux layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config._platform import (
    _CANONICAL_RESOLVER,  # pyright: ignore[reportPrivateUsage] - the alias table the entry points read
)
from lib_layered_config.adapters.path_resolvers import (
    DefaultPathResolver,
    LinuxStrategy,
    MacOSStrategy,
    PlatformStrategy,
    WindowsStrategy,
)
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

#: Every alias the public entry points take, and the layout it must select. Written out by hand, so
#: the test does not take the table it checks as its own oracle.
_EXPECTED: dict[str, type[PlatformStrategy]] = {
    "linux": LinuxStrategy,
    "posix": LinuxStrategy,
    "darwin": MacOSStrategy,
    "mac": MacOSStrategy,
    "macos": MacOSStrategy,
    "windows": WindowsStrategy,
    "win": WindowsStrategy,
    "win32": WindowsStrategy,
    "wine": WindowsStrategy,
}


def _padded(alias: str) -> str:
    return f"  {alias} "


def _strategy(tmp_path: Path, platform: str) -> PlatformStrategy:
    resolver = DefaultPathResolver(
        vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, env={}, platform=platform, hostname="test-host"
    )
    return resolver.strategy


@os_agnostic
def test_the_expected_table_names_every_alias_the_entry_points_take() -> None:
    assert set(_EXPECTED) == set(_CANONICAL_RESOLVER)


@os_agnostic
@pytest.mark.parametrize("spelling", [str.lower, str.upper, str.title, _padded])
@pytest.mark.parametrize("alias", sorted(_EXPECTED))
def test_every_alias_selects_its_layout_in_any_case_and_spacing(
    tmp_path: Path, alias: str, spelling: Callable[[str], str]
) -> None:
    assert type(_strategy(tmp_path, spelling(alias))) is _EXPECTED[alias]


@os_agnostic
@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("freebsd14", LinuxStrategy),
        ("cygwin", LinuxStrategy),
        ("sunos5", LinuxStrategy),
        ("aix", LinuxStrategy),
        ("emscripten", LinuxStrategy),
        ("win64", WindowsStrategy),
    ],
)
def test_a_sys_platform_value_without_an_alias_keeps_its_layout(
    tmp_path: Path, platform: str, expected: type[PlatformStrategy]
) -> None:
    assert type(_strategy(tmp_path, platform)) is expected
