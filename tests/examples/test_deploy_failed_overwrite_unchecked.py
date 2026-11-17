"""A failed forced overwrite that cannot be compared with its backup keeps the backup.

After an overwrite fails part-way, deploy compares the destination with its ``.bak``: equal means
nothing changed and the backup is removed; different means the backup is the only intact copy and
stays. When the comparison itself cannot be made, the only safe answer is "changed": reading it as
"unchanged" would delete the one intact copy (user decision 2026-11-17, s5 R4-F7 B6: "Add the
test"). No test reached that branch before, and a mutant flipping it survived the suite.

A child process runs the real deploy under a file-size limit (the full disk of
``test_deploy_failed_overwrite_backup``), on a hard-linked destination with permission setting off,
so the new content is written in place and stops part-way. An audit hook, which fires inside the
real ``open`` call just before it runs, makes the comparison fail once the in-place write opens the
file:

- ``wall``: the directory loses its search permission, so that open fails (``PermissionError``,
  nothing written) and the destination then cannot be stat'ed: the ``except OSError`` in
  ``deploy._failed_overwrite``;
- ``unreadable``: the write stops at the size limit and the destination's read-back open raises
  ``PermissionError``: the ``except OSError`` in ``deploy._content_matches``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from tests.support import create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path

_CHILD = """
import json, os, resource, signal, sys
from pathlib import Path
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
from lib_layered_config import deploy_config, deployed_before_failure
naming = {"vendor": "Acme", "app": "Demo", "slug": "demo", "targets": ["user"]}
source, how, destination = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
state = {"writing": False, "done": []}

def _names_destination(raw):
    return isinstance(raw, (str, bytes, os.PathLike)) and os.fsdecode(raw) == str(destination)

def hook(event, args):
    if event != "open" or len(args) < 2 or not _names_destination(args[0]) or args[1] is None:
        return
    if "w" in args[1] and not state["writing"]:
        state["writing"] = True
        if how == "wall":
            os.chmod(destination.parent, 0o600)
            state["done"].append("walled")
    elif state["writing"] and how == "unreadable" and "r" in args[1]:
        state["done"].append("refused read")
        raise PermissionError(13, "Permission denied", str(destination))

sys.addaudithook(hook)
try:
    deploy_config(source, **naming, force=True, set_permissions=False)
    report = {"error": None, "written": []}
except OSError as error:
    report = {
        "error": type(error).__name__,
        "written": [
            [str(r.destination), r.action.value, None if r.backup_path is None else str(r.backup_path)]
            for r in deployed_before_failure(error)
        ],
    }
report["hook"] = state["done"]
print(json.dumps(report))
"""


_OLD = "k = 1\n" + "#" * (65536 - 7) + "\n"


def _deploy_and_fail_the_compare(tmp_path: Path, how: str) -> tuple[dict[str, object], Path]:
    sandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")
    destination = sandbox.roots["user"] / "config.toml"
    destination.parent.mkdir(parents=True)
    # Exactly the size limit: the torn destination then has the backup's size, so the comparison gets
    # past its size check to the read the unreadable arm refuses.
    destination.write_text(_OLD, encoding="utf-8")
    # A second name makes a rename change the file, so the new content is written in place.
    os.link(destination, tmp_path / "other-name.toml")
    source = tmp_path / "source.toml"
    source.write_text("".join(f"key_{index} = {index}\n" for index in range(20000)), encoding="utf-8")
    env = {**os.environ, "HOME": str(tmp_path), **sandbox.env}
    try:
        completed = subprocess.run(  # noqa: S603 - argv is sys.executable plus literals and test paths
            [sys.executable, "-c", _CHILD, str(source), how, str(destination)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=tmp_path,
            check=True,
            timeout=60,
        )
    finally:
        destination.parent.chmod(0o700)
    report: dict[str, object] = json.loads(completed.stdout)
    return report, destination


@posix_only
@pytest.mark.parametrize(
    ("how", "error", "hook"),
    [("wall", "PermissionError", ["walled"]), ("unreadable", "OSError", ["refused read"])],
    ids=["stat-fails", "read-fails"],
)
def test_a_failed_overwrite_that_cannot_be_compared_keeps_and_reports_its_backup(
    tmp_path: Path, how: str, error: str, hook: list[str]
) -> None:
    # posix_only skips this test on Windows; the assert narrows sys.platform for pyright, which does not
    # read pytest.skip (a callable object) as ending the path.
    assert sys.platform != "win32"
    if os.geteuid() == 0:
        pytest.skip("root passes every permission wall, so the comparison would not fail")
    report, destination = _deploy_and_fail_the_compare(tmp_path, how)
    backup = destination.with_name("config.toml.bak")

    assert report == {
        "error": error,
        "written": [[str(destination), "overwritten", str(backup)]],
        "hook": hook,
    }
    assert backup.read_text(encoding="utf-8") == _OLD
