"""A machine hostname that cannot name a host file turns off the host layer, never the whole read.

The host layer reads ``hosts/<hostname>.toml``, and the hostname comes from ``socket.gethostname()``.
A hostname the rules refused used to make every read and every deploy raise ``ValidationError``,
even with no host file anywhere. User decision 2026-11-16 (R1-F2, "Allow _, skip the rest"): ``_``
is allowed, any other refused hostname skips the host layer with a warning, and only a deploy to
the ``host`` target is refused.
"""

from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ValidationError, read_config
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.deploy import deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.layered import LayeredSandbox

_NON_ASCII = "M" + chr(0xDC) + "LLER-PC"
_REFUSED = [_NON_ASCII, "con", "web:01"]
_SKIP_EVENT = "host_layer_skipped_invalid_hostname"


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostname: str) -> LayeredSandbox:
    sandbox = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    # The machine's name is an OS edge the library reads and no caller can pass.
    monkeypatch.setattr(socket, "gethostname", lambda: hostname)
    return sandbox


def _read(sandbox: LayeredSandbox) -> dict[str, object]:
    return read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(sandbox.start_dir)).as_dict()


@os_agnostic
def test_an_underscore_hostname_reads_its_host_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch, "build_agent_01")
    sandbox.write("app", "config.toml", content="a = 1\n")
    sandbox.write("host", "build_agent_01.toml", content="h = 2\n")

    assert _read(sandbox) == {"a": 1, "h": 2}


@os_agnostic
@pytest.mark.parametrize("hostname", _REFUSED)
def test_a_refused_hostname_skips_only_the_host_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, hostname: str
) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch, hostname)
    sandbox.write("app", "config.toml", content="a = 1\n")
    sandbox.write("user", "config.toml", content="u = 3\n")

    with caplog.at_level(logging.WARNING, logger="lib_layered_config"):
        data = _read(sandbox)

    assert data == {"a": 1, "u": 3}
    skipped = [record for record in caplog.records if record.message == _SKIP_EVENT]
    assert [record.levelno for record in skipped] == [logging.WARNING]
    assert skipped[0].__dict__["context"]["hostname"] == hostname


@os_agnostic
@pytest.mark.parametrize("hostname", _REFUSED)
def test_a_refused_hostname_still_deploys_to_the_user_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostname: str
) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch, hostname)
    source = tmp_path / "src" / "config.toml"
    source.parent.mkdir()
    source.write_text("c = 3\n", encoding="utf-8")

    results = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], set_permissions=False)

    assert [result.action.value for result in results] == ["created"]
    assert (sandbox.roots["user"] / "config.toml").read_text(encoding="utf-8") == "c = 3\n"


@os_agnostic
@pytest.mark.parametrize("hostname", _REFUSED)
def test_a_refused_hostname_refuses_a_host_deploy_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostname: str
) -> None:
    sandbox = _sandbox(tmp_path, monkeypatch, hostname)
    source = tmp_path / "src" / "config.toml"
    source.parent.mkdir()
    source.write_text("c = 3\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="hostname"):
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["host", "user"], set_permissions=False)

    assert not (sandbox.roots["user"] / "config.toml").exists()
    assert not sandbox.roots["host"].exists() or not any(sandbox.roots["host"].iterdir())


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_every_platform_reads_no_host_file_for_a_refused_hostname(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    # A file named after the missing name ("None.toml") would be picked up by a layout that built
    # the path anyway; plant one so such a layout shows.
    sandbox = create_layered_sandbox(tmp_path / "root", vendor="Acme", app="Demo", slug="demo", platform=platform)
    monkeypatch.setattr(socket, "gethostname", lambda: "con")
    sandbox.write("host", "None.toml", content="n = 9\n")

    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", env=sandbox.env, platform=platform)

    assert resolver.host_file_name is None
    assert list(resolver.host()) == []
