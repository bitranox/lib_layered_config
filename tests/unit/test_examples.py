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
