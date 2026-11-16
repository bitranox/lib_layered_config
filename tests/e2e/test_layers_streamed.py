"""Layers stream into the merge, so a read's peak memory does not grow with the number of files.

Every parsed file used to be held until the last one was parsed: 40 ``.d`` files of 2.2 MB setting
the same keys peaked at 315 MB traced against 21 MB for one. Now each snapshot is merged and dropped
before the next is parsed, and 10 or 40 such files peak at 37 MB. A layer file that does not load
is still reported as ``LayerLoadError`` after others merged.
"""

from __future__ import annotations

import re
import tracemalloc
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.core import LayerLoadError
from lib_layered_config.deploy import read_deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
# About 0.5 MB of TOML; every file sets the same keys, so the merged result does not grow with N.
_BODY = "".join(f"k{i} = '{'v' * 40}'\n" for i in range(10_000))


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    created.start_dir.mkdir(parents=True, exist_ok=True)
    return created


def _defaults_with(directory: Path, files: int) -> Path:
    directory.mkdir()
    base = directory / "config.toml"
    base.write_text("x = 0\n", encoding="utf-8")
    _add_dot_d_files(directory, start=0, stop=files)
    return base


def _add_dot_d_files(directory: Path, *, start: int, stop: int) -> None:
    dot_d = directory / "config.d"
    dot_d.mkdir(exist_ok=True)
    for index in range(start, stop):
        (dot_d / f"{index:03d}.toml").write_text(_BODY, encoding="utf-8")


def _read(sandbox: LayeredSandbox, defaults: Path) -> object:
    return read_config(vendor=VENDOR, app=APP, slug=SLUG, default_file=defaults, start_dir=sandbox.start_dir)


def _read_for_deploy(_sandbox: LayeredSandbox, defaults: Path) -> object:
    return read_deploy_config(defaults, vendor=VENDOR, app=APP, slug=SLUG, skip=[])


def _peak_bytes(call: Callable[[], object]) -> int:
    tracemalloc.start()
    try:
        call()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _dot_d_home(sandbox: LayeredSandbox, tmp_path: Path, where: str) -> tuple[Path, Path]:
    """Return (the defaults file the read gets, the directory whose ``config.d`` grows)."""
    defaults = _defaults_with(tmp_path / "defaults", files=0)
    if where == "defaults":
        return defaults, defaults.parent
    user_file = sandbox.write("user", "config.toml", content="y = 0\n")
    return defaults, user_file.parent


@os_agnostic
@pytest.mark.parametrize("where", ["defaults", "user"])
@pytest.mark.parametrize("reader", [_read, _read_for_deploy], ids=["read_config", "read_deploy_config"])
def test_peak_memory_does_not_grow_with_the_number_of_dot_d_files(
    sandbox: LayeredSandbox, tmp_path: Path, reader: Callable[[LayeredSandbox, Path], object], where: str
) -> None:
    defaults, grows = _dot_d_home(sandbox, tmp_path, where)
    _add_dot_d_files(grows, start=0, stop=2)
    reader(sandbox, defaults)  # warm imports and caches outside the measurement
    few_peak = _peak_bytes(lambda: reader(sandbox, defaults))

    _add_dot_d_files(grows, start=2, stop=16)
    many_peak = _peak_bytes(lambda: reader(sandbox, defaults))

    # Held all at once, 16 files peak about four times what 2 do; streamed, about the same.
    assert many_peak < few_peak * 1.5, (few_peak, many_peak)


@os_agnostic
def test_a_file_that_does_not_load_after_others_merged_is_a_layer_load_error(
    sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    defaults = _defaults_with(tmp_path / "defaults", files=2)
    (defaults.parent / "config.d" / "999-broken.toml").write_text("x = [", encoding="utf-8")

    with pytest.raises(LayerLoadError, match=re.escape("999-broken.toml")):
        _read(sandbox, defaults)
