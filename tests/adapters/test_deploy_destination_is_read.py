"""Every file a deploy writes is a file the reads of the same resolver find, on every platform.

The layout lives in one place, the path resolver strategies: the reads and a deploy's destinations
are both built from their ``app_dirs()`` and ``user_dir()`` (user decision 2026-11-17, "One layout
for both"). This pins the pairing for all three layouts, with and without a profile, for every
layer a deploy writes, so a layout change that reaches only one side fails on any OS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_DEPLOY_LAYERS = (Layer.APP, Layer.HOST, Layer.USER)


def _roots(tmp_path: Path) -> dict[str, str]:
    """Every layer root under *tmp_path*, named the way each platform's resolver reads it.

    The APPDATA directory is left to the caller: whether it exists decides the Windows user layer.
    """
    return {
        "LIB_LAYERED_CONFIG_ETC": str(tmp_path / "etc"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "HOME": str(tmp_path / "home"),
        "LIB_LAYERED_CONFIG_MAC_APP_ROOT": str(tmp_path / "mac-app"),
        "LIB_LAYERED_CONFIG_MAC_HOME_ROOT": str(tmp_path / "mac-home"),
        "LIB_LAYERED_CONFIG_PROGRAMDATA": str(tmp_path / "programdata"),
        "APPDATA": str(tmp_path / "appdata"),
        "LIB_LAYERED_CONFIG_LOCALAPPDATA": str(tmp_path / "localappdata"),
    }


def _resolver(tmp_path: Path, *, platform: str, profile: str | None, env: dict[str, str]) -> DefaultPathResolver:
    return DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        profile=profile,
        cwd=tmp_path,
        env=env,
        platform=platform,
        hostname="box",
    )


def _read_list(resolver: DefaultPathResolver, layer: Layer) -> Iterable[Path]:
    reads = {Layer.APP: resolver.app, Layer.HOST: resolver.host, Layer.USER: resolver.user}
    return reads[layer]()


def _plant(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a = 1\n", encoding="utf-8")


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
@pytest.mark.parametrize("profile", [None, "staging"])
@pytest.mark.parametrize("layer", _DEPLOY_LAYERS, ids=[layer.value for layer in _DEPLOY_LAYERS])
def test_a_deployed_file_is_one_the_reads_find(
    tmp_path: Path, platform: str, profile: str | None, layer: Layer
) -> None:
    (tmp_path / "appdata").mkdir()
    resolver = _resolver(tmp_path, platform=platform, profile=profile, env=_roots(tmp_path))
    destination = resolver.destination_for(layer)
    assert destination.is_relative_to(tmp_path)
    assert list(_read_list(resolver, layer)) == []

    _plant(destination)

    assert list(_read_list(resolver, layer)) == [destination]


@os_agnostic
@pytest.mark.parametrize("profile", [None, "staging"])
def test_a_windows_user_file_deployed_without_appdata_is_read_back(tmp_path: Path, profile: str | None) -> None:
    # With the APPDATA directory missing, a deploy writes under LOCALAPPDATA; the read must look there.
    resolver = _resolver(tmp_path, platform="win32", profile=profile, env=_roots(tmp_path))
    destination = resolver.destination_for(Layer.USER)
    assert destination.is_relative_to(tmp_path / "localappdata")

    _plant(destination)

    assert list(resolver.user()) == [destination]
