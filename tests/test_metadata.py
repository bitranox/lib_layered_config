"""Metadata tales celebrating the pinned project portrait."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
import runpy
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TARGET_FIELDS = ("name", "title", "version", "homepage", "author", "author_email", "shell_command")


def _load_pyproject() -> dict[str, Any]:
    with PYPROJECT_PATH.open("rb") as stream:
        return tomllib.load(stream)


def _resolve_init_conf_path(pyproject: dict[str, Any]) -> Path:
    project_table = cast(dict[str, Any], pyproject["project"])
    tool_table = cast(dict[str, Any], pyproject.get("tool", {}))
    hatch_table = cast(dict[str, Any], tool_table.get("hatch", {}))
    targets_table = cast(dict[str, Any], cast(dict[str, Any], hatch_table.get("build", {})).get("targets", {}))
    wheel_table = cast(dict[str, Any], targets_table.get("wheel", {}))
    packages = cast(list[Any], wheel_table.get("packages", []))

    for package_entry in packages:
        if isinstance(package_entry, str):
            candidate = PROJECT_ROOT / package_entry / "__init__conf__.py"
            if candidate.is_file():
                return candidate

    fallback = PROJECT_ROOT / "src" / project_table["name"].replace("-", "_") / "__init__conf__.py"
    if fallback.is_file():
        return fallback

    raise AssertionError("Unable to locate __init__conf__.py")


def _load_init_conf_metadata(init_conf_path: Path) -> dict[str, str]:
    fragments: list[str] = []
    for raw_line in init_conf_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        for key in TARGET_FIELDS:
            prefix = f"{key} = "
            if stripped.startswith(prefix):
                fragments.append(stripped)
                break
    if not fragments:
        raise AssertionError("No metadata assignments found in __init__conf__.py")
    metadata_text = "[metadata]\n" + "\n".join(fragments)
    parsed = tomllib.loads(metadata_text)
    metadata_table = cast(dict[str, str], parsed["metadata"])
    return metadata_table


def _load_init_conf_module(init_conf_path: Path) -> dict[str, Any]:
    return runpy.run_path(str(init_conf_path))


@pytest.mark.os_agnostic
def test_when_print_info_runs_it_lists_every_field(capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = _load_pyproject()
    init_conf_path = _resolve_init_conf_path(pyproject)
    init_conf_module = _load_init_conf_module(init_conf_path)

    print_info = init_conf_module["print_info"]
    assert callable(print_info)

    print_info()

    captured = capsys.readouterr().out

    for label in TARGET_FIELDS:
        assert f"{label}" in captured


@pytest.mark.os_agnostic
def test_the_metadata_constants_match_the_project() -> None:
    pyproject = _load_pyproject()
    project_table = cast(dict[str, Any], pyproject["project"])
    init_conf_path = _resolve_init_conf_path(pyproject)
    metadata = _load_init_conf_metadata(init_conf_path)

    urls = cast(dict[str, str], project_table.get("urls", {}))
    authors = cast(list[dict[str, str]], project_table.get("authors", []))
    scripts = cast(dict[str, Any], project_table.get("scripts", {}))

    assert authors, "pyproject.toml must declare at least one author entry"
    assert "Homepage" in urls, "pyproject.toml must define project.urls.Homepage"

    assert metadata["name"] == project_table["name"]
    assert metadata["title"] == project_table["description"]
    assert metadata["version"] == project_table["version"]
    assert metadata["homepage"] == urls["Homepage"]
    assert metadata["author"] == authors[0]["name"]
    assert metadata["author_email"] == authors[0]["email"]
    assert metadata["shell_command"] in scripts
