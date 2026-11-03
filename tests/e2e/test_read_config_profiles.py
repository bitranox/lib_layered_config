"""``read_config(profile=...)`` reads the app, host and user layers from ``profile/<name>/``.

The path resolvers are unit-tested per platform; this pins the whole read: with a profile every
file layer comes from its ``profile/<name>/`` directory, and the files outside it are not read.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_PROFILE = "staging"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    created.apply_env(monkeypatch)
    host = socket.gethostname()
    profile_dir = f"profile/{_PROFILE}"
    created.write("app", "config.toml", content='[source]\napp = "plain"\n')
    created.write("app", f"{profile_dir}/config.toml", content='[source]\napp = "profile"\n')
    created.write("host", f"{host}.toml", content='[source]\nhost = "plain"\n')
    created.write("app", f"{profile_dir}/hosts/{host}.toml", content='[source]\nhost = "profile"\n')
    created.write("user", "config.toml", content='[source]\nuser = "plain"\n')
    created.write("user", f"{profile_dir}/config.toml", content='[source]\nuser = "profile"\n')
    return created


def _source(sandbox: LayeredSandbox, profile: str | None) -> object:
    config = read_config(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        profile=profile,
        start_dir=str(sandbox.start_dir),
        dotenv_path=str(sandbox.start_dir / "absent.env"),
    )
    return config.get("source")


@os_agnostic
def test_a_profile_reads_every_file_layer_from_its_profile_directory(sandbox: LayeredSandbox) -> None:
    assert _source(sandbox, _PROFILE) == {"app": "profile", "host": "profile", "user": "profile"}


@os_agnostic
def test_without_a_profile_the_files_outside_profile_directories_are_read(sandbox: LayeredSandbox) -> None:
    assert _source(sandbox, None) == {"app": "plain", "host": "plain", "user": "plain"}
