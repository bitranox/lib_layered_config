"""Every directory a deploy creates gets the layer's directory mode, not the umask's.

``mkdir(parents=True)`` creates the missing directories above the file's own folder with the
process umask's mode, and only that folder was then set to the layer's mode. A first profile deploy
into the user layer under umask 0002 so left ``demo/`` and ``profile/`` at ``0o775``. A directory
that already existed keeps its mode, except the file's own folder, which is set as before (user
decision 2026-11-18, "Created dirs only").
"""

from __future__ import annotations

import os
import shutil
import stat
from contextlib import contextmanager
from typing import TYPE_CHECKING

from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

    from tests.support import LayeredSandbox


@contextmanager
def _umask(mask: int) -> Generator[None, None, None]:
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source.toml"
    source.write_text("[a]\nb = 1\n", encoding="utf-8")
    return source


def _modes_below(top: Path, file: Path) -> dict[str, str]:
    """The mode of every directory from *top* down to *file*'s own folder, by path relative to *top*.

    Keyed below *top* (``"."`` for *top* itself) because the layer root is named after the slug on Linux
    (``demo``) and after the app on macOS (``Demo``).
    """
    found: dict[str, str] = {}
    directory = file.parent
    while True:
        found[directory.relative_to(top).as_posix()] = oct(stat.S_IMODE(directory.stat().st_mode))
        if directory == top:
            return found
        directory = directory.parent


@posix_only
def test_a_profile_deploy_gives_every_directory_it_creates_the_user_mode(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    source = _source(tmp_path)
    user_root = sandbox.roots["user"]
    assert not user_root.exists(), "the sandbox must leave the user layer for the deploy to create"

    with _umask(0o002):
        results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], profile="staging")

    assert [r.action for r in results] == [DeployAction.CREATED]
    destination = results[0].destination
    assert _modes_below(user_root, destination) == {
        ".": "0o700",
        "profile": "0o700",
        "profile/staging": "0o700",
    }


@posix_only
def test_a_host_deploy_gives_the_directories_it_creates_the_app_mode_under_a_tight_umask(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    source = _source(tmp_path)
    app_root = sandbox.roots["app"]
    # The sandbox makes the app root up front; an empty one is removed so the deploy creates it.
    shutil.rmtree(app_root)

    with _umask(0o077):
        results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["host"])

    destination = results[0].destination
    assert destination.parent.name == "hosts"
    assert _modes_below(app_root, destination) == {".": "0o755", "hosts": "0o755"}


@posix_only
def test_a_deploy_leaves_an_existing_parent_directory_s_mode_alone(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    source = _source(tmp_path)
    profile_dir = sandbox.roots["user"] / "profile"
    profile_dir.mkdir(parents=True)
    profile_dir.chmod(0o750)
    sandbox.roots["user"].chmod(0o751)

    with _umask(0o002):
        results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], profile="staging")

    assert _modes_below(sandbox.roots["user"], results[0].destination) == {
        ".": "0o751",
        "profile": "0o750",
        "profile/staging": "0o700",
    }


@posix_only
def test_a_deploy_without_permissions_leaves_the_created_directories_at_the_umask(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    source = _source(tmp_path)

    with _umask(0o002):
        results = deploy_config(
            source,
            vendor="Acme",
            app="Demo",
            slug="demo",
            targets=["user"],
            profile="staging",
            set_permissions=False,
        )

    assert set(_modes_below(sandbox.roots["user"], results[0].destination).values()) == {"0o775"}
