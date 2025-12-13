"""Tests for dot-d directory expansion utility."""

from __future__ import annotations

from pathlib import Path

from lib_layered_config.adapters.file_loaders._dot_d import (
    _collect_dot_d_files,
    expand_dot_d,
)

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_expand_dot_d_returns_base_only_when_no_dot_d_dir(tmp_path: Path) -> None:
    """When only the base file exists, yield just that file."""
    base = tmp_path / "config.toml"
    base.write_text("[app]\nname = 'test'\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert result == [str(base)]


@os_agnostic
def test_expand_dot_d_returns_empty_when_neither_exists(tmp_path: Path) -> None:
    """When neither base file nor .d directory exists, yield nothing."""
    missing = tmp_path / "missing.toml"

    result = list(expand_dot_d(str(missing)))

    assert result == []


@os_agnostic
def test_expand_dot_d_returns_dot_d_only_when_base_missing(tmp_path: Path) -> None:
    """When only .d directory exists (no base file), yield .d files."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"  # config.toml → config.d (without .toml)
    dot_d.mkdir()
    (dot_d / "10-db.toml").write_text("[db]\nhost = 'localhost'\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert result == [str(dot_d / "10-db.toml")]


@os_agnostic
def test_expand_dot_d_merges_base_and_dot_d_in_order(tmp_path: Path) -> None:
    """Base file comes first, then .d files in lexicographic order."""
    base = tmp_path / "config.toml"
    base.write_text("[app]\nname = 'base'\n", encoding="utf-8")

    dot_d = tmp_path / "config.d"  # config.toml → config.d
    dot_d.mkdir()
    (dot_d / "20-cache.toml").write_text("[cache]\nenabled = true\n", encoding="utf-8")
    (dot_d / "10-db.toml").write_text("[db]\nport = 5432\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert result == [
        str(base),
        str(dot_d / "10-db.toml"),
        str(dot_d / "20-cache.toml"),
    ]


@os_agnostic
def test_expand_dot_d_sorts_lexicographically(tmp_path: Path) -> None:
    """Files are sorted by name, not by insertion order."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    (dot_d / "z-last.toml").write_text("z = 1\n", encoding="utf-8")
    (dot_d / "a-first.toml").write_text("a = 1\n", encoding="utf-8")
    (dot_d / "m-middle.toml").write_text("m = 1\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert [Path(p).name for p in result] == ["a-first.toml", "m-middle.toml", "z-last.toml"]


@os_agnostic
def test_expand_dot_d_filters_unsupported_extensions(tmp_path: Path) -> None:
    """Non-config files in .d directory are ignored."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    (dot_d / "10-valid.toml").write_text("[valid]\nx = 1\n", encoding="utf-8")
    (dot_d / "README.md").write_text("# Ignore me\n", encoding="utf-8")
    (dot_d / "notes.txt").write_text("Ignore me too\n", encoding="utf-8")
    (dot_d / ".hidden.toml").write_text("[hidden]\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert [Path(p).name for p in result] == [".hidden.toml", "10-valid.toml"]


@os_agnostic
def test_expand_dot_d_handles_mixed_formats_in_dot_d(tmp_path: Path) -> None:
    """The .d directory can contain TOML, YAML, and JSON files."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    (dot_d / "10-toml.toml").write_text("[toml]\nx = 1\n", encoding="utf-8")
    (dot_d / "20-yaml.yaml").write_text("yaml:\n  y: 2\n", encoding="utf-8")
    (dot_d / "30-json.json").write_text('{"json": {"z": 3}}\n', encoding="utf-8")
    (dot_d / "40-yml.yml").write_text("yml:\n  w: 4\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert [Path(p).name for p in result] == [
        "10-toml.toml",
        "20-yaml.yaml",
        "30-json.json",
        "40-yml.yml",
    ]


@os_agnostic
def test_expand_dot_d_ignores_subdirectories(tmp_path: Path) -> None:
    """Subdirectories inside .d are not traversed."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    (dot_d / "10-valid.toml").write_text("[valid]\n", encoding="utf-8")
    subdir = dot_d / "nested"
    subdir.mkdir()
    (subdir / "should-ignore.toml").write_text("[nested]\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert [Path(p).name for p in result] == ["10-valid.toml"]


@os_agnostic
def test_expand_dot_d_empty_dot_d_directory(tmp_path: Path) -> None:
    """Empty .d directory yields nothing (but doesn't error)."""
    base = tmp_path / "config.toml"
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    result = list(expand_dot_d(str(base)))

    assert result == []


@os_agnostic
def test_collect_dot_d_files_returns_empty_for_nonexistent_dir(tmp_path: Path) -> None:
    """Helper function returns empty when directory doesn't exist."""
    nonexistent = tmp_path / "nonexistent.d"

    result = list(_collect_dot_d_files(nonexistent))

    assert result == []


@os_agnostic
def test_collect_dot_d_files_sorts_and_filters(tmp_path: Path) -> None:
    """Helper function sorts files and filters by extension."""
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()

    (dot_d / "b.toml").write_text("b = 1\n", encoding="utf-8")
    (dot_d / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    (dot_d / "c.txt").write_text("ignore\n", encoding="utf-8")

    result = list(_collect_dot_d_files(dot_d))

    assert [Path(p).name for p in result] == ["a.yaml", "b.toml"]


@os_agnostic
def test_expand_dot_d_with_yaml_base_file(tmp_path: Path) -> None:
    """Expansion works for YAML base files - same .d directory as TOML."""
    base = tmp_path / "config.yaml"
    base.write_text("app:\n  name: test\n", encoding="utf-8")

    dot_d = tmp_path / "config.d"  # config.yaml → config.d (same as config.toml)
    dot_d.mkdir()
    (dot_d / "10-extra.yaml").write_text("extra:\n  key: value\n", encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert result == [str(base), str(dot_d / "10-extra.yaml")]


@os_agnostic
def test_expand_dot_d_with_json_base_file(tmp_path: Path) -> None:
    """Expansion works for JSON base files - same .d directory as TOML."""
    base = tmp_path / "config.json"
    base.write_text('{"app": {"name": "test"}}\n', encoding="utf-8")

    dot_d = tmp_path / "config.d"  # config.json → config.d (same as config.toml)
    dot_d.mkdir()
    (dot_d / "10-extra.json").write_text('{"extra": true}\n', encoding="utf-8")

    result = list(expand_dot_d(str(base)))

    assert result == [str(base), str(dot_d / "10-extra.json")]


@os_agnostic
def test_expand_dot_d_shared_directory_for_all_formats(tmp_path: Path) -> None:
    """TOML, YAML, and JSON base files all share the same .d directory."""
    # All three formats: config.toml, config.yaml, config.json
    # all use config.d as their companion directory
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()
    (dot_d / "10-shared.toml").write_text("[shared]\nvalue = 1\n", encoding="utf-8")

    for ext in [".toml", ".yaml", ".json"]:
        base = tmp_path / f"config{ext}"
        result = list(expand_dot_d(str(base)))
        assert len(result) == 1
        assert Path(result[0]).name == "10-shared.toml"
