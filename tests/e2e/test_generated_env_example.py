"""The generated ``.env.example``, copied to ``.env`` as it tells you to, sets the setting it names.

The template wrote ``DEMO___SERVICE__PASSWORD=changeme``. A ``.env`` key takes no environment prefix, so
the copied file set ``_service.password`` under a table named ``demo`` and left ``service.password``,
the key the generated ``config.toml`` files hold, unset.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.generate import generate_examples
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo-app"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Points every platform's app/host/user roots into tmp_path, so only the copied .env is read.
    create_layered_sandbox(tmp_path / "layers", vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)


@os_agnostic
def test_the_copied_env_example_sets_the_service_password(tmp_path: Path) -> None:
    generate_examples(tmp_path / "examples", vendor=VENDOR, app=APP, slug=SLUG, platform="posix")
    project = tmp_path / "project"
    project.mkdir()
    shutil.copyfile(tmp_path / "examples" / ".env.example", project / ".env")

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(project))

    assert config.as_dict() == {"service": {"password": "changeme"}}


@os_agnostic
def test_the_env_example_names_the_environment_variable_for_the_same_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_examples(tmp_path / "examples", vendor=VENDOR, app=APP, slug=SLUG, platform="posix")
    text = (tmp_path / "examples" / ".env.example").read_text(encoding="utf-8")
    assert "DEMO_APP___SERVICE__PASSWORD" in text

    monkeypatch.setenv("DEMO_APP___SERVICE__PASSWORD", "from-env")
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path)).get("service.password") == "from-env"
