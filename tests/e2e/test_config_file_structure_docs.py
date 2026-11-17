"""The annotated configuration file in ``docs/config-file-structure.md`` loads, and its access example is true.

The page presents its first TOML block as a complete file a reader can copy, and its "Complete Python
Access Example" comments each ``config.get(...)`` with the value it returns. A second ``[database]``
header once made that file invalid TOML, and the comments showed TOML's ``false``/``true`` where Python
prints ``False``/``True``. These tests load the block through ``read_config`` and compare each comment,
read as a Python literal, with what the call returns.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from lib_layered_config import Config, read_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

_PAGE = Path(__file__).resolve().parents[2] / "docs" / "config-file-structure.md"
_TOML_BLOCK = re.compile(r"^```toml\n(.*?)^```", re.MULTILINE | re.DOTALL)
_ACCESS_EXAMPLE = re.compile(r"^### Complete Python Access Example\n.*?^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)
_COMMENTED_GET = re.compile(r"^\w+ = (?P<call>config\.get\(.*\)(?:\[0\])?)\s+# (?P<shown>.+)$")


@dataclass(frozen=True, slots=True)
class _Claim:
    """One commented line of the access example: the call and the value its comment shows."""

    call: str
    shown: str


def _complete_example() -> str:
    return _TOML_BLOCK.findall(_PAGE.read_text(encoding="utf-8"))[0]


def _claims() -> list[_Claim]:
    match = _ACCESS_EXAMPLE.search(_PAGE.read_text(encoding="utf-8"))
    assert match is not None
    found = (_COMMENTED_GET.match(line.strip()) for line in match.group(1).splitlines())
    return [_Claim(call=hit.group("call"), shown=hit.group("shown")) for hit in found if hit is not None]


def _run(call: str, config: Config) -> object:
    """Evaluate ``config.get("key")``, ``config.get("key", default=N)`` or ``config.get("key")[0]``."""
    expression = ast.parse(call, mode="eval").body
    index: int | None = None
    if isinstance(expression, ast.Subscript):
        index = ast.literal_eval(expression.slice)
        expression = expression.value
    assert isinstance(expression, ast.Call)
    key = ast.literal_eval(expression.args[0])
    defaults = [ast.literal_eval(keyword.value) for keyword in expression.keywords if keyword.arg == "default"]
    value = config.get(key, defaults[0] if defaults else None)
    return value if index is None else value[index]


def _matches(shown: object, value: object) -> bool:
    """Compare a shown literal with the value; a list ending in ``...`` shows only its first items."""
    if isinstance(shown, list) and isinstance(value, list):
        shown_items = list(cast("list[object]", shown))
        items = list(cast("list[object]", value))
        if shown_items and shown_items[-1] is Ellipsis:
            head = shown_items[:-1]
            return items[: len(head)] == head
    return shown == value


@pytest.fixture
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    sandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="MyApp", slug="myapp")
    sandbox.apply_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    defaults = tmp_path / "config.toml"
    defaults.write_text(_complete_example(), encoding="utf-8")
    return read_config(vendor="Acme", app="MyApp", slug="myapp", default_file=defaults)


@os_agnostic
def test_the_complete_example_loads_as_one_file(loaded: Config) -> None:
    assert loaded.get("database.host") == "localhost"
    assert loaded.get("database.replicas") == ["replica1.db.local", "replica2.db.local", "replica3.db.local"]


@os_agnostic
def test_each_commented_value_in_the_access_example_is_what_python_returns(loaded: Config) -> None:
    claims = _claims()
    assert len(claims) >= 10

    wrong: list[str] = []
    for claim in claims:
        value = _run(claim.call, loaded)
        try:
            shown = ast.literal_eval(claim.shown)
        except ValueError:
            wrong.append(f"{claim.call}: comment {claim.shown!r} is not a Python value; it returns {value!r}")
            continue
        if not _matches(shown, value):
            wrong.append(f"{claim.call}: comment {claim.shown!r}, returns {value!r}")
    assert wrong == []
