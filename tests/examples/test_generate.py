"""Example generation helper tests that sing one behaviour each."""

from __future__ import annotations

from pathlib import Path

from lib_layered_config.examples import generate_examples
from lib_layered_config.examples.generate import (
    _app_defaults_body,
    _env_secrets_body,
    _split_override_body,
)
from tests.support.os_markers import os_agnostic

SLUG = "demo"
VENDOR = "Acme"
APP = "Demo"


@os_agnostic
def test_generate_examples_writes_posix_structure(tmp_path: Path) -> None:
    destination = tmp_path / "posix"
    written = generate_examples(destination, slug=SLUG, vendor=VENDOR, app=APP, platform="posix")
    expected = {
        destination / "etc" / SLUG / "config.toml",
        destination / "etc" / SLUG / "hosts" / "your-hostname.toml",
        destination / "xdg" / SLUG / "config.toml",
        destination / "xdg" / SLUG / "config.d" / "10-override.toml",
        destination / ".env.example",
    }
    assert set(written) == expected
    for path in expected:
        assert path.exists()


@os_agnostic
def test_generate_examples_force_rewrites_existing(tmp_path: Path) -> None:
    destination = tmp_path / "posix"
    generate_examples(destination, slug=SLUG, vendor=VENDOR, app=APP, platform="posix")
    target = destination / "etc" / SLUG / "config.toml"
    target.write_text("overwrite", encoding="utf-8")
    refreshed = generate_examples(destination, slug=SLUG, vendor=VENDOR, app=APP, platform="posix", force=True)
    assert target in refreshed
    assert "overwrite" not in target.read_text(encoding="utf-8")


@os_agnostic
def test_generate_examples_skips_when_unchanged(tmp_path: Path) -> None:
    destination = tmp_path / "posix"
    generate_examples(destination, slug=SLUG, vendor=VENDOR, app=APP, platform="posix")
    repeat = generate_examples(destination, slug=SLUG, vendor=VENDOR, app=APP, platform="posix")
    assert repeat == []


@os_agnostic
def test_app_defaults_body_recites_story() -> None:
    body = _app_defaults_body(SLUG)
    assert "Application-wide defaults" in body
    assert "timeout = 10" in body


@os_agnostic
def test_env_secrets_body_uses_uppercase_slug() -> None:
    body = _env_secrets_body(SLUG)
    assert "SERVICE__PASSWORD" in body
    assert SLUG.upper().replace("-", "_") in body


@os_agnostic
def test_split_override_body_mentions_config_directory() -> None:
    body = _split_override_body()
    assert "config.d" in body
