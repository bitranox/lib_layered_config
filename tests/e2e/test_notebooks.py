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
        # The `assert _exit_code == N` after each `!` line gates that shell command in CI's
        # notebook run; the command is dropped above, so its gate has nothing to check here.
        if stripped.startswith("assert _exit_code"):
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
    # The notebook sets LIB_LAYERED_CONFIG_ETC, XDG_CONFIG_HOME and a DEMO_CONFIG_* variable for
    # its reader and never unsets them; put the environment back so they cannot reach whichever
    # test this worker runs next.
    original_environ = dict(os.environ)
    try:
        os.chdir(tmp_path)
        for source in iter_executable_cells():
            # Executes this repo's own trusted Quickstart notebook, not untrusted input.
            exec(compile(source, NOTEBOOK_PATH.name, "exec"), namespace, namespace)  # noqa: S102
    finally:
        os.chdir(original_cwd)
        os.environ.clear()
        os.environ.update(original_environ)
