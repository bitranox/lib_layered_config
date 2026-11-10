"""The Python deploy functions read a platform name the way the CLI's ``--platform`` does.

``macos``, ``mac`` and ``Darwin`` name the macOS layout and ``win`` the Windows one; a name no layout
answers to is refused with the CLI's own message instead of deploying the Linux layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import pytest

from lib_layered_config import ValidationError, deploy_config, deploy_config_paths, read_deploy_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


class _Identity(TypedDict):
    """The vendor/app/slug every deploy function here is called with."""

    vendor: str
    app: str
    slug: str


_IDENTITY: _Identity = {"vendor": "Acme", "app": "Kit", "slug": "kit"}
_TARGETS = ["app", "user"]


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="Kit", slug="kit")
    created.apply_env(monkeypatch)
    # The sandbox sets only this OS's roots; a Windows layout needs an absolute ProgramData here.
    monkeypatch.setenv("LIB_LAYERED_CONFIG_PROGRAMDATA", str(tmp_path / "ProgramData"))
    return created


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text("[service]\nport = 1\n", encoding="utf-8")
    return path


def _paths(source: Path, platform: str) -> frozenset[Path]:
    return deploy_config_paths(source, targets=_TARGETS, platform=platform, **_IDENTITY)


@os_agnostic
@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("macos", "darwin"), ("mac", "darwin"), ("Darwin", "darwin"), ("win", "win32"), ("posix", "linux")],
)
def test_a_platform_alias_deploys_the_layout_it_names(
    sandbox: LayeredSandbox, source: Path, alias: str, canonical: str
) -> None:
    assert _paths(source, "darwin") != _paths(source, "linux")
    assert _paths(source, alias) == _paths(source, canonical)


@os_agnostic
def test_an_unknown_platform_is_refused_by_every_deploy_function(sandbox: LayeredSandbox, source: Path) -> None:
    refusals = [
        lambda: deploy_config_paths(source, targets=_TARGETS, platform="beos", **_IDENTITY),
        lambda: read_deploy_config(source, skip=(), platform="beos", **_IDENTITY),
        lambda: deploy_config(source, targets=_TARGETS, platform="beos", **_IDENTITY),
    ]
    for refuse in refusals:
        with pytest.raises(ValidationError, match=r"Platform must be one of: .*darwin"):
            refuse()


@os_agnostic
def test_a_refused_platform_writes_nothing(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(ValidationError):
        deploy_config(source, targets=_TARGETS, platform="beos", **_IDENTITY)

    assert not [path for path in _paths(source, "linux") if path.exists()]
