"""An explicit .env path may name a stream, not only a regular file.

A shell process substitution (``--env-file <(printf 'KEY=value')``) hands the program a FIFO such as
``/dev/fd/63``. Such a path used to load nothing, silently, as if it did not exist. It is now read,
with the same size cap a regular file has, so an endless source (a device such as ``/dev/zero``) is
refused at the cap instead of being read forever. A path that does not exist still loads nothing.
"""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from lib_layered_config import cli, read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.core import LayerLoadError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

VENDOR = "Acme"
APP = "Probe"
SLUG = "fifo-probe"
_PAYLOAD = b"SSH__KEY=/opt/keys/id\n"


@pytest.fixture()
def fifo(tmp_path: Path) -> Iterator[Path]:
    """A FIFO with a writer thread that delivers ``_PAYLOAD`` once a reader opens it."""
    path = tmp_path / "env.fifo"
    os.mkfifo(path)
    writer = threading.Thread(target=path.write_bytes, args=(_PAYLOAD,), daemon=True)
    writer.start()
    yield path
    if writer.is_alive():
        # Nobody opened the FIFO: open it ourselves so the writer is released, then fail loudly.
        path.read_bytes()
        writer.join(timeout=5)
        pytest.fail("the code under test never opened the FIFO")
    writer.join(timeout=5)


@posix_only
def test_the_loader_reads_a_fifo_named_as_the_dotenv_path(fifo: Path) -> None:
    loader = DefaultDotEnvLoader()

    data = loader.load(dotenv_path=str(fifo))

    assert data == {"ssh": {"key": "/opt/keys/id"}}
    assert loader.last_loaded_path == str(fifo)


@posix_only
def test_read_config_reads_a_fifo_and_names_it_as_the_origin(
    tmp_path: Path, fifo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path=str(fifo))

    assert config.get("ssh.key") == "/opt/keys/id"
    origin = config.origin("ssh.key")
    assert origin is not None
    assert origin["path"] == str(fifo)


@posix_only
def test_the_read_command_takes_a_fifo_as_env_file(tmp_path: Path, fifo: Path) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    args = ["read", "--vendor", VENDOR, "--app", APP, "--slug", SLUG, "--format", "json", "--no-provenance"]

    result = CliRunner().invoke(cli.cli, [*args, "--env-file", str(fifo)], env=sandbox.env)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ssh": {"key": "/opt/keys/id"}}


@posix_only
def test_an_endless_device_is_refused_at_the_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    with pytest.raises(LayerLoadError, match="exceeding the 10485760-byte limit"):
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path="/dev/zero")


@os_agnostic
def test_a_missing_dotenv_path_still_loads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)

    config = read_config(
        vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), dotenv_path=str(tmp_path / "absent.env")
    )

    assert config.as_dict() == {}
