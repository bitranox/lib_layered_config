"""Example generation helper tests recited as tiny poems."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.generate import generate_examples
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

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


def _generated_text(tmp_path: Path, *parts: str) -> str:
    """Write the POSIX example tree and return the text of one generated file."""
    destination, _ = _write_tree(tmp_path, "posix")
    return destination.joinpath(*parts).read_text(encoding="utf-8")


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
def test_the_user_config_names_vendor_then_app_on_each_platform(tmp_path: Path) -> None:
    posix, _ = _write_tree(tmp_path, "posix")
    windows, _ = _write_tree(tmp_path, "windows")
    expected = f"# User-specific preferences for {VENDOR} {APP}\n"

    assert (posix / "home" / SLUG / "config.toml").read_text(encoding="utf-8").startswith(expected)
    roaming = windows / "AppData" / "Roaming" / VENDOR / APP / "config.toml"
    assert roaming.read_text(encoding="utf-8").startswith(expected)


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
def test_when_app_defaults_body_speaks_it_mentions_defaults(tmp_path: Path) -> None:
    body = _generated_text(tmp_path, "xdg", SLUG, "config.toml")
    assert "Application-wide defaults" in body


@os_agnostic
def test_when_app_defaults_body_speaks_it_mentions_timeout(tmp_path: Path) -> None:
    body = _generated_text(tmp_path, "xdg", SLUG, "config.toml")
    assert "timeout = 10" in body


@os_agnostic
def test_when_env_body_sings_it_shouts_uppercase_slug(tmp_path: Path) -> None:
    body = _generated_text(tmp_path, ".env.example")
    assert SLUG.replace("-", "_").upper() in body


@os_agnostic
def test_when_env_body_sings_it_mentions_password_token(tmp_path: Path) -> None:
    body = _generated_text(tmp_path, ".env.example")
    assert "SERVICE__PASSWORD" in body


@os_agnostic
def test_when_split_override_body_speaks_it_mentions_config_directory(tmp_path: Path) -> None:
    body = _generated_text(tmp_path, "home", SLUG, "config.d", "10-override.toml")
    assert "config.d" in body


@os_agnostic
def test_an_unknown_platform_is_refused_with_validation_error_and_nothing_written(tmp_path: Path) -> None:
    # Every other entry point raises ValidationError for an unknown platform; the generator re-raised
    # the same message as a bare ValueError, which an ``except ConfigError`` does not catch.
    with pytest.raises(ValidationError, match=r"Platform must be one of: .*windows"):
        generate_examples(tmp_path / "dest", slug=SLUG, vendor=VENDOR, app=APP, platform="xml")

    assert not (tmp_path / "dest").exists()
