from __future__ import annotations

from pathlib import Path

from lib_layered_config.examples.generate import generate_examples

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_generate_examples_first_pass_creates_files(tmp_path: Path) -> None:
    written = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    assert bool(written) is True


@os_agnostic
def test_generate_examples_second_pass_without_force_writes_nothing(tmp_path: Path) -> None:
    generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    repeat = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    assert repeat == []


@os_agnostic
def test_generate_examples_force_overwrites_existing_payload(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    target = paths[0]
    original = target.read_text(encoding="utf-8")
    target.write_text("override", encoding="utf-8")
    generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit", force=True)
    assert target.read_text(encoding="utf-8") == original


@os_agnostic
def test_generate_examples_emits_posix_layout(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="demo-config", vendor="Acme", app="ConfigKit", platform="posix")
    relative = {p.relative_to(tmp_path).as_posix() for p in paths}
    expected = {
        "xdg/demo-config/config.toml",
        "xdg/demo-config/hosts/your-hostname.toml",
        "home/demo-config/config.toml",
        "home/demo-config/config.d/10-override.toml",
        ".env.example",
    }
    assert relative == expected


@os_agnostic
def test_generate_examples_emits_windows_layout(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="demo-config", vendor="Acme", app="ConfigKit", platform="windows")
    relative = {p.relative_to(tmp_path).as_posix() for p in paths}
    expected = {
        "AppData/Roaming/Acme/ConfigKit/config.d/10-override.toml",
        "AppData/Roaming/Acme/ConfigKit/config.toml",
        "ProgramData/Acme/ConfigKit/config.toml",
        "ProgramData/Acme/ConfigKit/hosts/your-hostname.toml",
        ".env.example",
    }
    assert relative == expected


@os_agnostic
def test_deploy_config_is_reexported_from_public_namespace() -> None:
    from lib_layered_config import deploy_config
    from lib_layered_config.examples import deploy_config as helper

    assert deploy_config is helper
