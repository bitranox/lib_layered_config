"""A configuration path behind a permission wall reads the same on every Python.

Before Python 3.14, ``Path.is_file()`` raises ``PermissionError`` when a directory on the path
cannot be entered; from 3.14 it returns ``False``. Left to pathlib, the same configuration crashed
on one interpreter and was silently dropped on the other. The ``.env`` upward search treats a
directory it cannot enter as holding no ``.env``; a layer's own location, or a file the caller
named, refuses with ``LayerLoadError`` naming the path.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config import LayerLoadError, read_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# Root bypasses directory permissions, so no wall can be built while running as root.
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
needs_wall = pytest.mark.skipif(_RUNS_AS_ROOT, reason="root bypasses directory permissions")

_VENDOR, _APP, _SLUG = "Acme", "ConfigKit", "config-kit"


@contextmanager
def walled(target: Path, mode: int = 0) -> Iterator[Path]:
    """Hold *target* at *mode* (no access by default), restoring it so tmp cleanup works."""
    target.chmod(mode)
    try:
        yield target
    finally:
        target.chmod(stat.S_IRWXU)


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=_VENDOR, app=_APP, slug=_SLUG)
    created.apply_env(monkeypatch)
    created.write("app", "config.toml", content='[service]\nname = "app"\n')
    return created


def _read(
    *, start_dir: str | None = None, default_file: str | None = None, dotenv_path: str | None = None
) -> dict[str, Any]:
    config = read_config(
        vendor=_VENDOR,
        app=_APP,
        slug=_SLUG,
        start_dir=start_dir,
        default_file=default_file,
        dotenv_path=dotenv_path,
    )
    return config.as_dict()


def _carries(exc: BaseException, kind: type[BaseException]) -> bool:
    """Whether the operating system's own error is reachable from *exc* through its chain.

    A caller tells "permission denied" from "malformed file" by finding the ``OSError`` there
    (lsdsk maps a ``PermissionError`` in the chain to exit 13), so a refusal that drops it reads as
    a broken file. Both links are followed: ``raise ... from`` sets ``__cause__``.
    """
    seen: list[BaseException] = []
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if any(current is known for known in seen):
            continue
        seen.append(current)
        pending.extend(link for link in (current.__cause__, current.__context__) if link is not None)
    return any(isinstance(item, kind) for item in seen)


# --- the .env search skips what it cannot enter ------------------------------------------------


@posix_only
@needs_wall
def test_read_config_run_from_an_unenterable_cwd_finds_no_env_and_loads(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "unenterable-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    with walled(cwd):
        data = _read()

    assert data == {"service": {"name": "app"}}


@posix_only
def test_read_config_run_from_a_deleted_cwd_finds_no_env_and_loads(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The OS cannot name a removed working directory (getcwd fails with ENOENT), the same way macOS
    # cannot name one the user cannot enter: the search then has nowhere to start.
    cwd = tmp_path / "deleted-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    cwd.rmdir()

    assert _read() == {"service": {"name": "app"}}


@posix_only
@needs_wall
def test_read_config_with_an_unenterable_start_dir_finds_no_env_and_loads(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    start = tmp_path / "unenterable-start"
    start.mkdir()

    with walled(start):
        data = _read(start_dir=str(start))

    assert data == {"service": {"name": "app"}}


# --- a layer location or a named file refuses --------------------------------------------------


@posix_only
@needs_wall
def test_an_unenterable_app_layer_directory_refuses_naming_the_path(sandbox: LayeredSandbox) -> None:
    app_root = sandbox.roots["app"]

    with walled(app_root), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir))

    assert str(app_root) in str(caught.value)
    assert _carries(caught.value, PermissionError)


@posix_only
@needs_wall
def test_a_default_file_behind_a_wall_refuses_naming_the_path(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    wall = tmp_path / "defaults-wall"
    wall.mkdir()
    (wall / "defaults.toml").write_text('[service]\nname = "default"\n', encoding="utf-8")

    with walled(wall), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir), default_file=str(wall / "defaults.toml"))

    assert str(wall / "defaults.toml") in str(caught.value)
    assert _carries(caught.value, PermissionError)


@posix_only
@needs_wall
def test_a_dotenv_path_behind_a_wall_refuses_naming_the_path(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    wall = tmp_path / "dotenv-wall"
    wall.mkdir()
    (wall / ".env").write_text("SERVICE__NAME=dotenv\n", encoding="utf-8")

    with walled(wall), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir), dotenv_path=str(wall / ".env"))

    assert str(wall / ".env") in str(caught.value)
    assert _carries(caught.value, PermissionError)


@posix_only
@needs_wall
def test_an_unreadable_config_file_refuses_naming_the_path(sandbox: LayeredSandbox) -> None:
    config = sandbox.roots["app"] / "config.toml"

    with walled(config), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir))

    assert str(config) in str(caught.value)
    assert _carries(caught.value, PermissionError)


@posix_only
@needs_wall
@pytest.mark.parametrize("mode", [0, stat.S_IRUSR], ids=["no-access", "list-only"])
def test_a_dot_d_directory_it_cannot_read_refuses_naming_the_path(sandbox: LayeredSandbox, mode: int) -> None:
    sandbox.write("app", "config.d/10-extra.toml", content='[service]\nextra = "d"\n')
    dot_d = sandbox.roots["app"] / "config.d"

    with walled(dot_d, mode), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir))

    assert str(dot_d) in str(caught.value)
    assert _carries(caught.value, PermissionError)


# --- the platform .env location is a layer location, probed only when the search runs ----------


@posix_only
@needs_wall
def test_an_unenterable_user_layer_directory_refuses_as_layer_load_error(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    user_root = sandbox.roots["user"]
    user_root.mkdir(parents=True, exist_ok=True)

    with walled(user_root), pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(tmp_path))

    assert str(user_root) in str(caught.value)
    assert _carries(caught.value, PermissionError)


@posix_only
@needs_wall
def test_an_explicit_dotenv_path_never_probes_the_platform_env(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    wall = tmp_path / "platform-env-wall"
    wall.mkdir()
    sandbox.roots["user"].mkdir(parents=True, exist_ok=True)
    (sandbox.roots["user"] / ".env").symlink_to(wall / ".env")
    explicit = tmp_path / "explicit.env"
    explicit.write_text("SERVICE__NAME=explicit\n", encoding="utf-8")

    with walled(wall):
        data = _read(start_dir=str(tmp_path), dotenv_path=str(explicit))

    assert data == {"service": {"name": "explicit"}}


# --- a path the operating system cannot even take ----------------------------------------------


@os_agnostic
def test_a_start_dir_with_a_nul_byte_is_skipped_by_the_search(sandbox: LayeredSandbox) -> None:
    # Anchored in the sandbox: a relative start_dir walks up through the test runner's cwd, whose
    # own .env would then be read into the result.
    start_dir = str(sandbox.start_dir / "unusable\x00dir")

    assert _read(start_dir=start_dir) == {"service": {"name": "app"}}


@os_agnostic
def test_a_default_file_with_a_nul_byte_refuses(sandbox: LayeredSandbox) -> None:
    with pytest.raises(LayerLoadError, match="cannot be read") as caught:
        _read(start_dir=str(sandbox.start_dir), default_file="defaults\x00.toml")

    assert _carries(caught.value, ValueError)
