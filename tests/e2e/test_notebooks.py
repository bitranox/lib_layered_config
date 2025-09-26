from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "Quickstart.ipynb"
"""Path to the Quickstart tutorial notebook."""


def _iter_code_cells() -> list[str]:
    """Yield dedented source from each executable notebook cell."""
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        filtered_lines: list[str] = []
        for line in "".join(cell.get("source", [])).splitlines():
            stripped = line.lstrip()
            if not stripped:
                filtered_lines.append("")
                continue
            if stripped.startswith("!") or stripped.startswith("%"):
                continue
            filtered_lines.append(line)
        filtered_source = "\n".join(filtered_lines).strip()
        if not filtered_source:
            continue
        dedented = textwrap.dedent(filtered_source)
        lines = dedented.splitlines()
        indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
        positive_indents = [indent for indent in indents if indent > 0]
        min_positive = min(positive_indents) if positive_indents else None
        if min_positive is not None and min_positive <= 2 and 0 in indents:
            trim = min_positive
            adjusted_lines = []
            for line in lines:
                if line.strip():
                    leading = len(line) - len(line.lstrip(" "))
                    if leading >= trim:
                        adjusted_lines.append(line[trim:])
                        continue
                adjusted_lines.append(line)
            dedented = "\n".join(adjusted_lines)
        yield dedented


def test_quickstart_notebook_executes(tmp_path) -> None:
    """Execute every code cell in the Quickstart notebook to guard against regressions."""
    namespace: dict[str, object] = {}
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        for source in _iter_code_cells():
            exec(compile(source, NOTEBOOK_PATH.name, "exec"), namespace, namespace)
    finally:
        os.chdir(original_cwd)
