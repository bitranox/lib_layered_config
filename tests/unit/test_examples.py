from __future__ import annotations

from pathlib import Path

from lib_layered_config.examples.generate import generate_examples


def test_generate_examples_idempotent(tmp_path: Path) -> None:
    written_first = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    assert written_first
    # second call without force should not overwrite
    written_second = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    assert written_second == []


def test_generate_examples_force_overwrites(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit")
    target = paths[0]
    original = target.read_text(encoding="utf-8")
    target.write_text("override", encoding="utf-8")
    generate_examples(tmp_path, slug="config-kit", vendor="Acme", app="ConfigKit", force=True)
    assert target.read_text(encoding="utf-8") == original


def test_generate_examples_paths_posix(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="demo-config", vendor="Acme", app="ConfigKit", platform="posix")
    relative = {p.relative_to(tmp_path).as_posix() for p in paths}
    expected = {
        "etc/demo-config/config.toml",
        "etc/demo-config/hosts/your-hostname.toml",
        "xdg/demo-config/config.toml",
        "xdg/demo-config/config.d/10-override.toml",
        ".env.example",
    }
    assert len(paths) == len(expected)
    assert relative == expected


def test_generate_examples_paths_windows(tmp_path: Path) -> None:
    paths = generate_examples(tmp_path, slug="demo-config", vendor="Acme", app="ConfigKit", platform="windows")
    relative = {p.relative_to(tmp_path).as_posix() for p in paths}
    expected = {
        "AppData/Roaming/Acme/ConfigKit/config.d/10-override.toml",
        "AppData/Roaming/Acme/ConfigKit/config.toml",
        "ProgramData/Acme/ConfigKit/config.toml",
        "ProgramData/Acme/ConfigKit/hosts/your-hostname.toml",
        ".env.example",
    }
    assert len(paths) == len(expected)
    assert relative == expected


def test_deploy_config_reexported() -> None:
    from lib_layered_config import deploy_config
    from lib_layered_config.examples import deploy_config as helper

    assert deploy_config is helper
