"""A deploy source behind a permission wall raises the same error on every Python.

Before Python 3.14, ``Path.is_file()``/``is_dir()`` raise ``PermissionError`` when a directory on
the path cannot be entered; from 3.14 they return ``False``. Deploy asked pathlib about its source
and the source's ``.d`` files, so a walled source was "not found" on 3.14 and a crash before it,
and a ``.d`` directory that can be listed but not entered lost its files on 3.14 without a word.
Deploy now asks the path probe, which raises the ``stat`` error itself, so both cases raise
``PermissionError`` on every Python and nothing is written.

On Windows the user layer goes to ``%APPDATA%`` and falls back to ``%LOCALAPPDATA%`` only when
``%APPDATA%`` is missing. One that cannot be checked raises too, rather than being read as missing.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.examples.deploy import deploy_config
from tests.support.os_markers import posix_only, windows_only
from tests.support.windows_acl import stat_wall

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from tests.support import LayeredSandbox

# Root bypasses directory permissions, so no wall can be built while running as root.
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
needs_wall = pytest.mark.skipif(_RUNS_AS_ROOT, reason="root bypasses directory permissions")


@pytest.fixture
def walled_source(tmp_path: Path) -> Iterator[Path]:
    wall = tmp_path / "wall"
    wall.mkdir()
    source = wall / "config.toml"
    source.write_text("[service]\nport = 1\n", encoding="utf-8")
    wall.chmod(0)
    yield source
    wall.chmod(stat.S_IRWXU)


@pytest.fixture
def source_with_unenterable_dot_d(tmp_path: Path) -> Iterator[Path]:
    source_dir = tmp_path / "src"
    dot_d = source_dir / "config.d"
    dot_d.mkdir(parents=True)
    source = source_dir / "config.toml"
    source.write_text("[service]\nport = 1\n", encoding="utf-8")
    (dot_d / "10-db.toml").write_text("[db]\nhost = 'h'\n", encoding="utf-8")
    # Readable but not searchable: the names can be listed, the entries cannot be checked.
    dot_d.chmod(stat.S_IRUSR)
    yield source
    dot_d.chmod(stat.S_IRWXU)


def _deploy(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, source: Path, *, set_permissions: bool | None = None
) -> None:
    sandbox.apply_env(monkeypatch)
    deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], set_permissions=set_permissions)


@posix_only
@needs_wall
def test_a_walled_source_raises_permission_error_and_writes_nothing(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, walled_source: Path
) -> None:
    with pytest.raises(PermissionError):
        _deploy(sandbox, monkeypatch, walled_source)

    assert not (sandbox.roots["user"] / "config.toml").exists()


@posix_only
@needs_wall
def test_a_dot_d_directory_that_cannot_be_entered_raises_instead_of_dropping_its_files(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, source_with_unenterable_dot_d: Path
) -> None:
    # set_permissions=False skips deploy's own read of the configuration, which would otherwise
    # refuse the walled .d file first; the .d collection is then the only thing that can notice.
    with pytest.raises(PermissionError):
        _deploy(sandbox, monkeypatch, source_with_unenterable_dot_d, set_permissions=False)

    assert not (sandbox.roots["user"] / "config.toml").exists()


@posix_only
def test_a_missing_source_still_raises_file_not_found(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError, match="Configuration source not found"):
        _deploy(sandbox, monkeypatch, tmp_path / "absent.toml")


@windows_only
def test_a_windows_appdata_that_cannot_be_checked_raises_instead_of_falling_back_to_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    roaming = tmp_path / "AppData" / "Roaming"
    local = tmp_path / "AppData" / "Local"
    roaming.mkdir(parents=True)
    local.mkdir()
    source = tmp_path / "config.toml"
    source.write_text("[service]\nport = 1\n", encoding="utf-8")
    # The override skips the check entirely, so only the plain APPDATA reaches the probe.
    monkeypatch.delenv("LIB_LAYERED_CONFIG_APPDATA", raising=False)
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LIB_LAYERED_CONFIG_LOCALAPPDATA", str(local))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    with stat_wall(roaming):
        # The wall must hold, or a pass would only mean the fallback was never offered.
        with pytest.raises(PermissionError):
            roaming.stat()
        with pytest.raises(PermissionError):
            # set_permissions=False skips deploy's own read of the configuration, which would
            # refuse the walled user layer first as a LayerLoadError.
            deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], set_permissions=False)

    assert list(local.iterdir()) == []
