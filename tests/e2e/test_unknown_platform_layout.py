"""An unknown ``sys.platform`` reads the layout deploy writes there: the Linux one.

Deploy wrote the Linux layout on a platform with no layout of its own (FreeBSD, Solaris, Cygwin),
while the reader used none, so a deployed file was never read back. User decision 2026-11-16
(P-C): both use the Linux layout.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.deploy import deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path

_UNKNOWN = ["freebsd14", "openbsd7", "sunos5", "cygwin"]


# POSIX only: a platform with no layout of its own is a POSIX one, and the library's other
# sys.platform branches (the .env owner check) would take their POSIX arm on a Windows runner.
@posix_only
@pytest.mark.parametrize("platform", _UNKNOWN)
@pytest.mark.parametrize("target", ["app", "host", "user"])
def test_a_deployed_file_is_read_back_on_an_unknown_platform(
    platform: str, target: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo", platform="linux")
    sandbox.apply_env(monkeypatch)
    source = tmp_path / "source.toml"
    source.write_text("answer = 42\n", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", platform)

    results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=[target], set_permissions=False)
    config = read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(tmp_path))

    assert config.get("answer") == 42
    origin = config.origin("answer")
    assert origin is not None
    assert origin["path"] == str(results[0].destination)
