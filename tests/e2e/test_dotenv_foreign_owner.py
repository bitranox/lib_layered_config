"""A ``.env`` another user owns cannot outrank the user's own configuration file.

The upward ``.env`` search climbs every parent directory up to ``/``, so a ``.env`` planted in a
shared directory (``/tmp/.env``) was loaded by every program started below it, and as the dotenv
layer it outranked the app, host and user files. The search now passes over a file neither the
current user nor root owns.

The effective uid is faked at ``os.geteuid``: an unprivileged test cannot create a file some other
user owns, and the uid is the OS edge the check reads.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import posix_only

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    created.apply_env(monkeypatch)
    created.write("user", "config.toml", content='[service]\nmode = "user"\n')
    created.start_dir.mkdir(parents=True, exist_ok=True)
    (created.start_dir / ".env").write_text("SERVICE__MODE=planted\n", encoding="utf-8")
    return created


def _mode(sandbox: LayeredSandbox) -> object:
    config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))
    return config.get("service.mode")


@posix_only
def test_a_dotenv_another_user_owns_does_not_override_the_user_file(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = (sandbox.start_dir / ".env").stat().st_uid
    if owner == 0:
        pytest.skip("the test files are root-owned, and root-owned files are trusted")
    monkeypatch.setattr(os, "geteuid", lambda: owner + 1)

    assert _mode(sandbox) == "user"


@posix_only
def test_a_dotenv_the_current_user_owns_still_overrides_the_user_file(sandbox: LayeredSandbox) -> None:
    assert _mode(sandbox) == "planted"
