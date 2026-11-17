"""On Windows, deploying over a file keeps who may read it.

Deploy writes a new file and renames it over the old one, and backs the old one up with a copy. On
Windows a new file gets the access list (DACL) its directory passes down, so a ``config.toml``
restricted with ``icacls /inheritance:r`` (as docs/cli-reference.md advises) came back readable by
everyone the directory lets in, and so did its ``.bak``. User decision 2026-11-16 (R4-F2, "Carry
the file's ACL over"): the replaced file's DACL goes onto the new file, the backup and the ``.ucf``
sidecar. A file whose DACL is inherited keeps inheriting.

The access lists are compared as ``icacls`` prints them, on the same machine, so the account
names' language does not matter.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters._file_write import write_file
from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import windows_only

if TYPE_CHECKING:
    from lib_layered_config.deploy import ConflictResolver
    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


def _tool(name: str) -> str:
    # From System32, never PATH: the windows-latest runner puts Git Bash's coreutils first on PATH,
    # so a PATH lookup of "whoami" found /usr/bin/whoami, which refuses "/user".
    found = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / f"{name}.exe"
    assert found.is_file(), f"{found} not found"
    return str(found)


def _run(*argv: str) -> str:
    result = subprocess.run(  # noqa: S603 - a resolved system tool and fixed arguments, no shell
        list(argv), capture_output=True, encoding="oem", errors="replace", check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _aces(path: Path) -> list[str]:
    """The access entries ``icacls`` lists for *path*, without the path itself."""
    lines = _run(_tool("icacls"), str(path)).splitlines()
    entries = [lines[0][len(str(path)) :].strip()]
    for line in lines[1:]:
        if not line.strip():
            break
        entries.append(line.strip())
    return entries


def _own_sid() -> str:
    return _run(_tool("whoami"), "/user", "/fo", "csv", "/nh").strip().split(",")[-1].strip('"')


def _restrict_to_owner(path: Path) -> list[str]:
    _run(_tool("icacls"), str(path), "/inheritance:r", "/grant:r", f"*{_own_sid()}:(F)")
    aces = _aces(path)
    assert not any("(I)" in ace for ace in aces), aces
    return aces


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path / "root", vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    return created


def _deploy(
    tmp_path: Path,
    content: str,
    *,
    set_permissions: bool | None = None,
    force: bool = False,
    conflict_resolver: ConflictResolver | None = None,
) -> list[DeployAction]:
    source = tmp_path / "src" / "config.toml"
    source.parent.mkdir(exist_ok=True)
    source.write_text(content, encoding="utf-8")
    results = deploy_config(
        source,
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        targets=["user"],
        set_permissions=set_permissions,
        force=force,
        conflict_resolver=conflict_resolver,
    )
    return [result.action for result in results]


@windows_only
@pytest.mark.parametrize("set_permissions", [True, False], ids=["permissions", "no-permissions"])
def test_a_forced_deploy_keeps_the_files_own_acl_on_the_file_and_its_backup(
    sandbox: LayeredSandbox, tmp_path: Path, set_permissions: bool
) -> None:
    assert _deploy(tmp_path, "a = 1\n", set_permissions=set_permissions) == [DeployAction.CREATED]
    target = sandbox.roots["user"] / "config.toml"
    restricted = _restrict_to_owner(target)

    actions = _deploy(tmp_path, "a = 2\n", set_permissions=set_permissions, force=True)

    assert actions == [DeployAction.OVERWRITTEN]
    assert target.read_text(encoding="utf-8") == "a = 2\n"
    assert _aces(target) == restricted
    assert _aces(target.with_name("config.toml.bak")) == restricted


@windows_only
def test_a_kept_file_gives_its_ucf_sidecar_its_own_acl(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    assert _deploy(tmp_path, "a = 1\n") == [DeployAction.CREATED]
    target = sandbox.roots["user"] / "config.toml"
    restricted = _restrict_to_owner(target)

    actions = _deploy(tmp_path, "a = 2\n", conflict_resolver=lambda _path: DeployAction.KEPT)

    assert actions == [DeployAction.KEPT]
    assert _aces(target.with_name("config.toml.ucf")) == restricted


@windows_only
def test_an_inherited_acl_stays_inherited(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    # A new file inherits only what its directory passes down. On the windows-latest runner the temp
    # directories pass nothing, so a new file got the process's default ACL, with no (I) entry, and
    # the test had nothing to keep. One inheritable entry on the user root gives it the case it tests.
    root = sandbox.roots["user"]
    root.mkdir(parents=True, exist_ok=True)
    _run(_tool("icacls"), str(root), "/grant", f"*{_own_sid()}:(OI)(CI)(F)")
    assert _deploy(tmp_path, "a = 1\n") == [DeployAction.CREATED]
    target = root / "config.toml"
    inherited = _aces(target)
    assert any("(I)" in ace for ace in inherited), inherited

    assert _deploy(tmp_path, "a = 2\n", force=True) == [DeployAction.OVERWRITTEN]

    assert _aces(target) == inherited


# An audit hook cannot be removed, so one hook is installed for the process and reads this state.
# The hook fires when the write opens its source, which is after the temp file exists and before
# a byte of content goes into it: the access list the temp has then is the one the content meets.
class _Watch:
    def __init__(self) -> None:
        self.source: Path | None = None
        self.seen: list[list[list[str]]] = []
        self.busy = False


_WATCH = _Watch()


def _path_of(value: object) -> Path | None:
    if isinstance(value, Path):
        return value
    return Path(value) if isinstance(value, str) else None


def _record_temp_acls(event: str, args: tuple[object, ...]) -> None:
    source = _WATCH.source
    if event != "open" or source is None or _WATCH.busy or not args or _path_of(args[0]) != source:
        return
    _WATCH.busy = True  # icacls runs a subprocess, which raises audit events of its own
    try:
        temps = sorted(p for p in source.parent.iterdir() if p.name.endswith(".tmp"))
        _WATCH.seen.append([_aces(temp) for temp in temps])
    finally:
        _WATCH.busy = False


sys.addaudithook(_record_temp_acls)


@windows_only
def test_the_temp_file_has_the_destination_acl_before_any_content_is_written(tmp_path: Path) -> None:
    # The content is the secret: a temp that took its directory's access list would expose it to
    # everyone the directory lets in for as long as the write takes.
    destination = tmp_path / "config.toml"
    destination.write_text("secret = 1\n", encoding="utf-8")
    restricted = _restrict_to_owner(destination)
    source = tmp_path / "source.toml"
    source.write_text("secret = 2\n", encoding="utf-8")
    _WATCH.source, _WATCH.seen = source, []
    try:
        write_file(destination, source, restrict=False, chunk_bytes=4096)
    finally:
        seen, _WATCH.source, _WATCH.seen = _WATCH.seen, None, []

    assert seen == [[restricted]]
    assert destination.read_text(encoding="utf-8") == "secret = 2\n"
