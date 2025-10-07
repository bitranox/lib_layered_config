"""Execute notebook-based documentation to ensure tutorial parity."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

from tests.support.os_markers import IS_MAC, os_agnostic

pytestmark = pytest.mark.slow

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "Quickstart.ipynb"
"""Path to the Quickstart tutorial notebook."""


def _load_notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _is_code_cell(cell: dict[str, object]) -> bool:
    return cell.get("cell_type") == "code"


def _clean_source(cell: dict[str, object]) -> str:
    lines = "".join(cell.get("source", [])).splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            kept.append("")
            continue
        if stripped.startswith("!") or stripped.startswith("%"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _dedent_block(source: str) -> str:
    if not source:
        return ""
    block = textwrap.dedent(source)
    lines = block.splitlines()
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    if 0 not in indents:
        return block
    positives = [indent for indent in indents if indent > 0]
    trim = min(positives, default=0)
    if trim == 0:
        return block
    adjusted: list[str] = []
    for line in lines:
        if line.strip() and len(line) - len(line.lstrip(" ")) >= trim:
            adjusted.append(line[trim:])
            continue
        adjusted.append(line)
    return "\n".join(adjusted)


def iter_executable_cells() -> list[str]:
    notebook = _load_notebook()
    cells = notebook.get("cells", [])
    executable: list[str] = []
    for cell in cells:
        if not _is_code_cell(cell):
            continue
        cleaned = _clean_source(cell)
        if not cleaned:
            continue
        executable.append(_dedent_block(cleaned))
    return executable


@os_agnostic
@pytest.mark.skipif(IS_MAC, reason="Notebook writes system paths on macOS")
def test_quickstart_notebook_executes_cells(tmp_path: Path) -> None:
    namespace: dict[str, object] = {}
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        for source in iter_executable_cells():
            exec(compile(source, NOTEBOOK_PATH.name, "exec"), namespace, namespace)
    finally:
        os.chdir(original_cwd)
