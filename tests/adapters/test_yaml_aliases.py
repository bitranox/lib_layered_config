"""A YAML file whose aliases form a cycle or expand without bound is refused, never walked forever.

PyYAML builds an alias as a shared reference, so ``a: &x [*x]`` parses into a list that contains
itself and a few hundred bytes of nested aliases parse into a graph that expands to millions of
values. Every check the loader runs after parsing walks that graph as a tree, so before the refusal
existed a cycle made ``read_config`` spin forever and a small alias bomb exhausted memory. The hang
cases run the loader in a child process with a timeout, so a regression fails the test instead of
wedging the suite.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader, refuse_yaml_alias_blowup
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None
_needs_yaml = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is not installed on this interpreter")

#: Seconds a child gets to load one file. The fixed loader answers in well under a second; the
#: unfixed one spins forever on a cycle and needs about ten seconds to walk the bomb below.
_CHILD_TIMEOUT = 60

_LOAD_IN_CHILD = """
import sys
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
try:
    YAMLFileLoader().load(sys.argv[1])
except InvalidFormatError as exc:
    print("REFUSED:", exc)
else:
    print("LOADED")
"""


def _alias_bomb(levels: int, width: int = 9) -> str:
    """Return a YAML document whose last anchor expands to about ``width ** levels`` values."""
    lines = [f"a0: &a0 [{', '.join(['x'] * width)}]"]
    lines.extend(f"a{level}: &a{level} [{', '.join([f'*a{level - 1}'] * width)}]" for level in range(1, levels))
    return "\n".join(lines) + "\n"


def _load_in_child(path: Path) -> str:
    """Load *path* in a fresh interpreter and return what it printed; a hang raises TimeoutExpired."""
    completed = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", _LOAD_IN_CHILD, str(path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CHILD_TIMEOUT,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@os_agnostic
@_needs_yaml
@pytest.mark.parametrize(
    "document",
    [
        pytest.param("a: &x [*x]\n", id="list-contains-itself"),
        pytest.param("a: &x {b: *x}\n", id="mapping-contains-itself"),
        pytest.param("a: &x {b: [1, {c: *x}]}\n", id="cycle-through-a-list"),
    ],
)
def test_a_yaml_alias_cycle_is_refused(tmp_path: Path, document: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(document, encoding="utf-8")
    assert _load_in_child(path) == f"REFUSED: {path} aliases a node into itself"


@os_agnostic
@_needs_yaml
def test_a_yaml_alias_bomb_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(_alias_bomb(levels=7), encoding="utf-8")
    assert _load_in_child(path) == f"REFUSED: {path} expands its aliases to more than 1,000,000 values"


@os_agnostic
@_needs_yaml
def test_read_config_refuses_a_yaml_alias_cycle_as_a_layer_error(tmp_path: Path) -> None:
    path = tmp_path / "defaults.yaml"
    path.write_text("a: &x [*x]\n", encoding="utf-8")
    script = (
        "import sys\n"
        "from lib_layered_config import LayerLoadError, read_config\n"
        "try:\n"
        "    read_config(vendor='Acme', app='Demo', slug='demo', default_file=sys.argv[1])\n"
        "except LayerLoadError as exc:\n"
        "    print('LAYER ERROR:', exc)\n"
    )
    completed = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", script, str(path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CHILD_TIMEOUT,
        check=False,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("LAYER ERROR:")
    assert "aliases a node into itself" in completed.stdout


@os_agnostic
@_needs_yaml
def test_a_shared_alias_without_a_cycle_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("base: &b {host: db.example.test, ports: [1, 2]}\nprod: *b\nstage: *b\n", encoding="utf-8")
    loaded = YAMLFileLoader().load(str(path))
    expected = {"host": "db.example.test", "ports": [1, 2]}
    assert loaded == {"base": expected, "prod": expected, "stage": expected}


@os_agnostic
@_needs_yaml
def test_aliases_that_expand_below_the_bound_still_load(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(_alias_bomb(levels=5), encoding="utf-8")
    loaded = YAMLFileLoader().load(str(path))
    assert len(loaded) == 5


@os_agnostic
def test_a_large_document_without_aliases_is_never_refused_for_its_size() -> None:
    """The bound limits what aliases ADD; a plain document of more values than the bound loads."""
    refuse_yaml_alias_blowup({"items": list(range(1_000_001))}, path="big.yaml")


@os_agnostic
def test_the_refusal_names_no_value(tmp_path: Path) -> None:
    secret: list[object] = ["s3cret-value"]
    secret.append(secret)
    with pytest.raises(InvalidFormatError) as caught:
        refuse_yaml_alias_blowup({"password": secret}, path="secret.yaml")
    assert "s3cret" not in str(caught.value)


@os_agnostic
@_needs_yaml
def test_a_refused_alias_file_does_not_reach_the_caller_as_a_foreign_error(tmp_path: Path) -> None:
    path = tmp_path / "defaults.yaml"
    path.write_text(_alias_bomb(levels=7), encoding="utf-8")
    with pytest.raises(LayerLoadError, match="expands its aliases"):
        read_config(vendor="Acme", app="Demo", slug="demo", default_file=str(path), start_dir=str(tmp_path))
