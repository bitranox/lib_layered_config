"""Reading configuration from many threads at once gives every thread the same answer.

The package declares free-threading support (``Free Threading :: 3 - Stable``). On a free-threaded
interpreter these threads truly run in parallel; under the GIL they still interleave. Either way
each concurrent ``read_config`` must return exactly what a single-threaded read returns.

On a free-threaded interpreter the package must also keep the GIL off: orjson and rtoml have no
free-threaded build, and importing either would turn the GIL back on.
"""

from __future__ import annotations

import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config import Config

VENDOR = "Acme"
APP = "Threads"
SLUG = "threads-probe"
_THREADS = 16
_READS_PER_THREAD = 20
_FREE_THREADED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def _read(tmp_path: Path) -> Config:
    return read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        default_file=str(tmp_path / "defaults.json"),
        start_dir=str(tmp_path),
        dotenv_path=str(tmp_path / "threads.env"),
    )


def _layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.toml", content='[service]\nname = "app"\nports = [80, 443]\n[db]\nhost = "db.local"\n')
    (tmp_path / "defaults.json").write_text('{"service": {"timeout": 5, "tags": ["a", "b"]}}', encoding="utf-8")
    (tmp_path / "threads.env").write_text("DB__PASSWORD=from-dotenv\nDB__POOL=8\n", encoding="utf-8")
    monkeypatch.setenv("THREADS_PROBE___SERVICE__RETRIES", "3")


@os_agnostic
def test_concurrent_reads_all_return_the_single_threaded_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _layers(tmp_path, monkeypatch)
    expected = _read(tmp_path)
    assert expected.get("db.pool") == 8
    assert expected.get("service.retries") == 3

    def _reads(_: int) -> list[tuple[str, str]]:
        return [(_read(tmp_path).to_json(), _read(tmp_path).to_json(redact=True)) for _ in range(_READS_PER_THREAD)]

    with ThreadPoolExecutor(max_workers=_THREADS) as pool:
        results = [pair for batch in pool.map(_reads, range(_THREADS)) for pair in batch]

    assert len(results) == _THREADS * _READS_PER_THREAD
    assert set(results) == {(expected.to_json(), expected.to_json(redact=True))}


@os_agnostic
@pytest.mark.skipif(not _FREE_THREADED, reason="only a free-threaded interpreter can lose the GIL")
def test_the_gil_stays_off_after_reading_toml_and_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _layers(tmp_path, monkeypatch)

    config = _read(tmp_path)

    assert config.get("service.name") == "app"
    assert config.to_json()
    assert "orjson" not in sys.modules
    assert "rtoml" not in sys.modules
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    assert callable(is_gil_enabled)
    assert is_gil_enabled() is False
