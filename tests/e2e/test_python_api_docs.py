"""The Python API reference shows calls that work against the installed package.

``docs/python-api.md`` once unpacked ``read_config_raw`` as a tuple, which raises ``TypeError``,
and imported return types from internal module paths. These tests run what a reader copies: the
``read_config_raw`` calls and every ``lib_layered_config`` import in the reference.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

import lib_layered_config
from lib_layered_config.application.merge import MergeResult
from lib_layered_config.deploy import DeployAction, DeployResult
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

_REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "python-api.md"
_CODE_BLOCK = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _blocks(text: str) -> list[str]:
    return [match.group(1) for match in _CODE_BLOCK.finditer(text)]


def _section(heading: str) -> str:
    text = _REFERENCE.read_text(encoding="utf-8")
    start = text.index(f"### `{heading}`")
    return text[start : text.index("\n---\n", start)]


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="MyApp", slug="myapp")
    sandbox.apply_env(monkeypatch)
    # The examples search for .env from the working directory: keep the repository's out.
    monkeypatch.chdir(tmp_path)
    return tmp_path


@os_agnostic
@pytest.mark.parametrize(
    ("name", "expected"),
    [("MergeResult", MergeResult), ("DeployResult", DeployResult), ("DeployAction", DeployAction)],
)
def test_the_package_exports_the_types_its_functions_return(name: str, expected: type) -> None:
    assert getattr(lib_layered_config, name, None) is expected
    assert name in lib_layered_config.__all__


@os_agnostic
def test_every_read_config_raw_call_in_the_reference_runs(isolated: Path) -> None:
    calls = [
        line
        for block in _blocks(_section("read_config_raw"))
        for line in block.splitlines()
        if "read_config_raw(" in line and not line.startswith(("from ", "import "))
    ]
    assert len(calls) >= 3

    for call in calls:
        exec(f"from lib_layered_config import read_config_raw\n{call}", {})  # noqa: S102 - the reference's own lines


@os_agnostic
def test_the_self_contained_read_config_raw_examples_run(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runnable = [
        block for block in _blocks(_section("read_config_raw")) if "jinja2" not in block and "args." not in block
    ]
    assert runnable

    for block in runnable:
        exec(block, {})  # noqa: S102 - the reference's own example

    assert "Missing required key: database.host" in capsys.readouterr().out


@os_agnostic
def test_every_import_from_the_package_in_the_reference_resolves() -> None:
    imports = [
        (node.module, alias.name)
        for block in _blocks(_REFERENCE.read_text(encoding="utf-8"))
        for node in ast.walk(_parse(block))
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.startswith("lib_layered_config")
        for alias in node.names
    ]
    assert len(imports) > 20

    missing = [f"{module}.{name}" for module, name in imports if not hasattr(importlib.import_module(module), name)]
    internal = sorted({f"{module}.{name}" for module, name in imports if module != "lib_layered_config"})
    assert missing == []
    assert internal == []


def _parse(block: str) -> ast.Module:
    try:
        return ast.parse(block)
    except SyntaxError:
        return ast.Module(body=[], type_ignores=[])
