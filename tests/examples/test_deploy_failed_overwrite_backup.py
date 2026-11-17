"""A forced overwrite that fails after its backup leaves nothing unreported behind.

The backup is written first, then the new content. When that second write fails (a full disk, a quota) the
backup was left on disk and named nowhere: not by ``deployed_before_failure``, not by the CLI. A file-size
limit in a child process stands in for the full disk, so the real write paths run. If the destination is
still unchanged the backup is removed; if an in-place rewrite stopped part-way the backup is the only intact
copy, so it stays and is reported.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from tests.support import create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path

_CHILD = """
import json, resource, signal, sys
from pathlib import Path
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
from lib_layered_config import deploy_config, deploy_config_paths, deployed_before_failure
naming = {"vendor": "Acme", "app": "Demo", "slug": "demo", "targets": ["user"]}
# Where the deploy aims, so a test cannot pass on a destination the deploy never touched.
aimed_at = sorted(str(p) for p in deploy_config_paths(Path(sys.argv[1]), **naming))
try:
    deploy_config(Path(sys.argv[1]), **naming, force=True, set_permissions=sys.argv[2] == "on")
    report = {"error": None, "written": []}
except OSError as error:
    report = {
        "error": type(error).__name__,
        "written": [
            [str(r.destination), r.action.value, None if r.backup_path is None else str(r.backup_path)]
            for r in deployed_before_failure(error)
        ],
    }
report["aimed_at"] = aimed_at
print(json.dumps(report))
"""


def _deploy_under_a_size_limit(tmp_path: Path, *, hard_linked: bool) -> tuple[dict[str, object], Path]:
    # The sandbox gives every layer a root under tmp_path for the running OS: macOS keeps the user
    # layer under Library/Application Support, not XDG_CONFIG_HOME, and no host layer may be read.
    sandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")
    destination = sandbox.roots["user"] / "config.toml"
    destination.parent.mkdir(parents=True)
    destination.write_text("old = 1\n", encoding="utf-8")
    if hard_linked:
        # A second name makes a rename change the file, so with permission setting off (a restricted
        # write always renames) the new content is written in place.
        os.link(destination, tmp_path / "other-name.toml")
    source = tmp_path / "source.toml"
    source.write_text("".join(f"key_{index} = {index}\n" for index in range(20000)), encoding="utf-8")
    env = {**os.environ, "HOME": str(tmp_path), **sandbox.env}
    completed = subprocess.run(  # noqa: S603 - argv is sys.executable plus literals and a test path
        [sys.executable, "-c", _CHILD, str(source), "off" if hard_linked else "on"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=tmp_path,
        check=True,
        timeout=60,
    )
    report: dict[str, object] = json.loads(completed.stdout)
    return report, destination


@posix_only
def test_an_overwrite_that_changed_nothing_removes_its_backup(tmp_path: Path) -> None:
    report, destination = _deploy_under_a_size_limit(tmp_path, hard_linked=False)

    assert report == {"error": "OSError", "written": [], "aimed_at": [str(destination.resolve())]}
    assert destination.read_text(encoding="utf-8") == "old = 1\n"
    assert sorted(p.name for p in destination.parent.iterdir()) == ["config.toml"]


@posix_only
def test_an_overwrite_stopped_part_way_keeps_and_reports_its_backup(tmp_path: Path) -> None:
    report, destination = _deploy_under_a_size_limit(tmp_path, hard_linked=True)
    backup = destination.with_name("config.toml.bak")

    assert report == {
        "error": "OSError",
        "written": [[str(destination), "overwritten", str(backup)]],
        "aimed_at": [str(destination.resolve())],
    }
    assert backup.read_text(encoding="utf-8") == "old = 1\n"
