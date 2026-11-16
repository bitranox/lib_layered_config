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

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.deploy import DeployAction, deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import windows_only

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config.deploy import ConflictResolver
    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


def _tool(name: str) -> str:
    found = shutil.which(name)
    assert found is not None, f"{name} not found on PATH"
    return found


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
    assert _deploy(tmp_path, "a = 1\n") == [DeployAction.CREATED]
    target = sandbox.roots["user"] / "config.toml"
    inherited = _aces(target)
    assert any("(I)" in ace for ace in inherited), inherited

    assert _deploy(tmp_path, "a = 2\n", force=True) == [DeployAction.OVERWRITTEN]

    assert _aces(target) == inherited
