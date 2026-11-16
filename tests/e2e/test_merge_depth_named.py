"""A configuration nested past the merge's 100 tables is a ``LayerLoadError`` that says where.

Before, the merge refused it with a bare ``InvalidFormatError`` ("Configuration nesting exceeds the
maximum depth of 100") that named no file, variable or key, and that escaped the ``LayerLoadError``
every other read failure is reported as, so ``except LayerLoadError`` missed it. User decision
2026-11-16 (C-F5): the merge names the source and the start of the key path, and the read wraps it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config import read_config
from lib_layered_config.core import LayerLoadError
from lib_layered_config.deploy import read_deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    created.start_dir.mkdir(parents=True, exist_ok=True)
    return created


def _nested(levels: int, *, key: str = "a") -> dict[str, Any]:
    value: dict[str, Any] = {"leaf": 1}
    for _ in range(levels):
        value = {key: value}
    return value


def _json_file(directory: Path, levels: int, *, key: str = "a") -> Path:
    path = directory / f"deep{levels}.json"
    path.write_text(json.dumps(_nested(levels, key=key)), encoding="utf-8")
    return path


@os_agnostic
def test_a_file_nested_past_the_limit_is_a_layer_load_error_naming_the_file_and_the_key(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    deep = _json_file(tmp_path, 101)

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, default_file=deep, start_dir=sandbox.start_dir)

    message = str(caught.value)
    assert message.startswith(f"{deep}: ")
    assert "maximum depth of 100" in message
    assert "a.a.a" in message


@os_agnostic
def test_a_file_nested_exactly_to_the_limit_still_loads(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    config = read_config(
        vendor=VENDOR, app=APP, slug=SLUG, default_file=_json_file(tmp_path, 100), start_dir=sandbox.start_dir
    )

    assert config.get(".".join(["a"] * 100 + ["leaf"])) == 1


@os_agnostic
def test_an_environment_key_nested_past_the_limit_names_the_environment_and_the_key(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO___" + "__".join(f"K{i}" for i in range(105)), "1")

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=sandbox.start_dir)

    message = str(caught.value)
    assert message.startswith("environment: ")
    assert "maximum depth of 100" in message
    assert "k0.k1.k2" in message


@os_agnostic
def test_the_deploy_read_names_the_file_too(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    deep = _json_file(tmp_path, 101)

    with pytest.raises(LayerLoadError, match="maximum depth of 100") as caught:
        read_deploy_config(deep, vendor=VENDOR, app=APP, slug=SLUG, skip=[])

    assert str(caught.value).startswith(f"{deep}: ")


@os_agnostic
def test_a_huge_key_does_not_make_a_huge_message(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    deep = _json_file(tmp_path, 101, key="k" * 5_000)

    with pytest.raises(LayerLoadError) as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, default_file=deep, start_dir=sandbox.start_dir)

    assert len(str(caught.value)) < len(str(deep)) + 200
