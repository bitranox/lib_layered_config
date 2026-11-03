"""The generate-examples documentation names the files the command really writes.

The CLI and Python references list, copy and check the generated files in several examples. They
once described an ``etc/`` tree that is never written, so the documented CI recipe always failed.
Each example's paths are read from the docs and compared with what ``generate_examples`` writes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib_layered_config import generate_examples
from tests.support.os_markers import os_agnostic

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _generate(tmp_path: Path, platform: str) -> list[Path]:
    return generate_examples(tmp_path, slug="myapp", vendor="Acme", app="MyApp", platform=platform)


def _section(document: str, heading: str) -> str:
    text = (_DOCS / document).read_text(encoding="utf-8")
    start = text.index(f"### `{heading}`")
    return text[start : text.index("\n---\n", start)]


def _example(section: str, number: int) -> list[tuple[str, str]]:
    """Return the (language, body) code blocks of example *number* in *section*."""
    start = section.index(f"**Example {number}:")
    end = section.find(f"**Example {number + 1}:", start)
    return [(match.group(1), match.group(2)) for match in _FENCE.finditer(section[start : end if end != -1 else None])]


@pytest.fixture(params=["posix", "windows"])
def written(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[str, list[str]]:
    platform = str(request.param)
    paths = _generate(tmp_path, platform)
    return platform, [path.relative_to(tmp_path).as_posix() for path in paths]


def _posix(tmp_path: Path) -> list[str]:
    return [path.relative_to(tmp_path).as_posix() for path in _generate(tmp_path, "posix")]


@os_agnostic
def test_cli_example_one_prints_the_json_the_command_prints(tmp_path: Path) -> None:
    (_, body) = next(
        block for block in _example(_section("cli-reference.md", "generate-examples"), 1) if block[0] == "json"
    )
    documented = [path.split("configuration-examples/", 1)[1] for path in json.loads(body)]

    assert documented == _posix(tmp_path)


@os_agnostic
def test_cli_example_four_lists_every_written_file(tmp_path: Path) -> None:
    blocks = _example(_section("cli-reference.md", "generate-examples"), 4)
    listing = next(body for _, body in blocks if body.startswith("./"))
    documented = [line.split("#", 1)[0].strip() for line in listing.splitlines() if line.startswith("./")]

    assert documented == sorted(f"./{path}" for path in _posix(tmp_path))


@os_agnostic
@pytest.mark.parametrize(("number", "pattern"), [(5, r"/tmp/myapp-examples/(\S+)"), (6, r'^\s+"([^"]+)"$')])
def test_cli_examples_five_and_six_name_only_written_files(tmp_path: Path, number: int, pattern: str) -> None:
    script = "\n".join(body for _, body in _example(_section("cli-reference.md", "generate-examples"), number))
    named = re.findall(pattern, script, flags=re.MULTILINE)

    assert len(named) >= 3
    assert set(named) <= set(_posix(tmp_path))


@os_agnostic
def test_python_examples_list_what_each_platform_writes(written: tuple[str, list[str]]) -> None:
    platform, paths = written
    section = _section("python-api.md", "generate_examples")
    block = next(body for number in (1, 2) for _, body in _example(section, number) if f'platform="{platform}"' in body)
    documented = [
        re.sub(r"\s+\(.*\)$", "", line.split("- ", 1)[1]) for line in block.splitlines() if line.startswith("#   - ")
    ]

    assert documented == paths


@os_agnostic
def test_python_example_three_edits_the_user_file(tmp_path: Path) -> None:
    (_, body) = _example(_section("python-api.md", "generate_examples"), 3)[0]
    edited = re.findall(r'user_examples / "([^"]+)"', body)

    assert edited == ["home/myapp/config.toml"]
    assert edited[0] in _posix(tmp_path)
