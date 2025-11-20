"""Example generation helper tests recited as tiny poems."""

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


def _write_tree(tmp_path: Path, platform: str, *, force: bool = False) -> tuple[Path, list[Path]]:
    destination = tmp_path / platform
    written = generate_examples(
        destination,
        slug=SLUG,
        vendor=VENDOR,
        app=APP,
        platform=platform,
        force=force,
    )
    return destination, written


@os_agnostic
def test_when_posix_tree_is_written_the_app_config_file_waits(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "posix")
    assert (destination / "xdg" / SLUG / "config.toml").exists()


@os_agnostic
def test_when_posix_tree_is_written_the_return_list_mentions_app_config(tmp_path: Path) -> None:
    destination, written = _write_tree(tmp_path, "posix")
    assert destination / "xdg" / SLUG / "config.toml" in written


@os_agnostic
def test_when_posix_tree_is_written_the_host_template_arrives(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "posix")
    assert (destination / "xdg" / SLUG / "hosts" / "your-hostname.toml").exists()


@os_agnostic
def test_when_posix_tree_is_written_the_user_config_arrives(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "posix")
    assert (destination / "home" / SLUG / "config.toml").exists()


@os_agnostic
def test_when_posix_tree_is_written_the_split_override_waits(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "posix")
    assert (destination / "home" / SLUG / "config.d" / "10-override.toml").exists()


@os_agnostic
def test_when_posix_tree_is_written_the_env_example_resting(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "posix")
    assert (destination / ".env.example").exists()


@os_agnostic
def test_when_force_is_true_the_app_config_is_listed_again(tmp_path: Path) -> None:
    _write_tree(tmp_path, "posix")
    target = tmp_path / "posix" / "xdg" / SLUG / "config.toml"
    target.write_text("old", encoding="utf-8")
    _, refreshed = _write_tree(tmp_path, "posix", force=True)
    assert target in refreshed


@os_agnostic
def test_when_force_is_true_the_app_config_receives_fresh_content(tmp_path: Path) -> None:
    _write_tree(tmp_path, "posix")
    target = tmp_path / "posix" / "xdg" / SLUG / "config.toml"
    target.write_text("old", encoding="utf-8")
    _write_tree(tmp_path, "posix", force=True)
    assert target.read_text(encoding="utf-8") != "old"


@os_agnostic
def test_when_called_twice_without_force_the_second_run_is_quiet(tmp_path: Path) -> None:
    _write_tree(tmp_path, "posix")
    _, repeat = _write_tree(tmp_path, "posix")
    assert repeat == []


@os_agnostic
def test_when_windows_tree_is_written_the_programdata_home_exists(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "windows")
    assert (destination / "ProgramData" / VENDOR / APP / "config.toml").exists()


@os_agnostic
def test_when_windows_tree_is_written_the_roaming_home_exists(tmp_path: Path) -> None:
    destination, _ = _write_tree(tmp_path, "windows")
    assert (destination / "AppData" / "Roaming" / VENDOR / APP / "config.toml").exists()


@os_agnostic
def test_when_app_defaults_body_speaks_it_mentions_defaults() -> None:
    body = _app_defaults_body(SLUG)
    assert "Application-wide defaults" in body


@os_agnostic
def test_when_app_defaults_body_speaks_it_mentions_timeout() -> None:
    body = _app_defaults_body(SLUG)
    assert "timeout = 10" in body


@os_agnostic
def test_when_env_body_sings_it_shouts_uppercase_slug() -> None:
    body = _env_secrets_body(SLUG)
    assert SLUG.replace("-", "_").upper() in body


@os_agnostic
def test_when_env_body_sings_it_mentions_password_token() -> None:
    body = _env_secrets_body(SLUG)
    assert "SERVICE__PASSWORD" in body


@os_agnostic
def test_when_split_override_body_speaks_it_mentions_config_directory() -> None:
    body = _split_override_body()
    assert "config.d" in body
