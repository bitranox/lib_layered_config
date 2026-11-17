"""A deploy's backup is never readable more widely than the file it copies, not even for a moment.

``shutil.copy2`` creates its copy with the process umask's mode and copies the source's mode only
afterwards, so a ``.bak`` of an owner-only ``config.toml`` was briefly ``0o644`` (``0o666`` under
umask 0), and whoever opened it then kept the descriptor after the chmod. A Python audit hook sees
every ``os.chmod`` just before it happens, so the mode a file had until then can be read there.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest

    from tests.support import LayeredSandbox


# An audit hook cannot be removed, so one hook is installed for the process and reads this state.
class _Watch:
    def __init__(self) -> None:
        self.directory: Path | None = None
        self.seen: list[tuple[str, int]] = []


_WATCH = _Watch()


def _path_of(value: object) -> Path | None:
    if isinstance(value, Path):
        return value
    return Path(value) if isinstance(value, str) else None


def _record_chmod_targets(event: str, args: tuple[object, ...]) -> None:
    path = _path_of(args[0]) if event == "os.chmod" and args else None
    if path is None or _WATCH.directory is None or path.parent != _WATCH.directory:
        return
    _WATCH.seen.append((path.name, stat.S_IMODE(os.lstat(path).st_mode)))


sys.addaudithook(_record_chmod_targets)


@contextmanager
def _watching(directory: Path) -> Generator[list[tuple[str, int]], None, None]:
    """Record every chmod in *directory* with the mode the file had until then, under umask 0."""
    _WATCH.directory, _WATCH.seen = directory, []
    previous = os.umask(0)
    try:
        yield _WATCH.seen
    finally:
        os.umask(previous)
        _WATCH.directory, _WATCH.seen = None, []


@posix_only
def test_a_backup_is_never_wider_than_the_file_it_copies(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    destination = sandbox.write("user", "config.toml", content="secret = 1\n")
    destination.chmod(0o600)
    source = tmp_path / "source.toml"
    source.write_text("secret = 2\n", encoding="utf-8")

    with _watching(destination.parent) as seen:
        results = deploy_config(
            source, vendor="Acme", app="Demo", slug="demo", targets=["user"], force=True, set_permissions=False
        )
        backups = [(name, mode) for name, mode in seen if ".bak" in name]

    assert [r.action for r in results] == [DeployAction.OVERWRITTEN]
    assert backups, "no chmod of the backup was observed, so the check saw nothing"
    assert [(name, oct(mode)) for name, mode in backups if mode & ~0o600] == []
    assert stat.S_IMODE(destination.with_name("config.toml.bak").stat().st_mode) == 0o600


@os_agnostic
def test_a_backup_keeps_the_replaced_file_s_times(
    sandbox: LayeredSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The backup is copied with copystat, not copymode: it keeps the old file's times (and on Linux
    # and macOS its POSIX ACL), so a backup reads as the version it holds, not as the moment of the deploy.
    sandbox.apply_env(monkeypatch)
    destination = sandbox.write("user", "config.toml", content="old = 1\n")
    os.utime(destination, (1_000_000_000, 1_000_000_000))
    source = tmp_path / "source.toml"
    source.write_text("old = 2\n", encoding="utf-8")

    deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], force=True)

    assert destination.with_name("config.toml.bak").stat().st_mtime == 1_000_000_000
