"""Reading configuration from many threads at once gives every thread the same answer.

The package declares free-threading support (``Free Threading :: 3 - Stable``). On a free-threaded
interpreter these threads truly run in parallel; under the GIL they still interleave. Either way
each concurrent ``read_config`` must return exactly what a single-threaded read returns.

On a free-threaded interpreter the package must also keep the GIL off: orjson and rtoml have no
free-threaded build, and importing either would turn the GIL back on.
"""

from __future__ import annotations

import json
import os
import subprocess
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


#: Run in a fresh interpreter: a test module in the same worker may import rtoml or orjson itself
#: (to compare backends), which would turn the GIL on for every later test in that process.
_GIL_PROBE = """
import json, sys
from lib_layered_config import read_config
config = read_config(vendor=sys.argv[1], app=sys.argv[2], slug=sys.argv[3], default_file=sys.argv[4],
                     start_dir=sys.argv[5], dotenv_path=sys.argv[6])
config.to_json()
print(json.dumps({
    "name": config.get("service.name"),
    "loaded": sorted(name for name in ("orjson", "rtoml") if name in sys.modules),
    "gil": sys._is_gil_enabled(),
}))
"""


@os_agnostic
@pytest.mark.skipif(not _FREE_THREADED, reason="only a free-threaded interpreter can lose the GIL")
def test_the_gil_stays_off_after_reading_toml_and_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _layers(tmp_path, monkeypatch)
    # PYTHON_GIL=0 would force the GIL off whatever gets imported, so the check would assert nothing.
    env = {name: value for name, value in os.environ.items() if name != "PYTHON_GIL"}
    argv = [VENDOR, APP, SLUG, str(tmp_path / "defaults.json"), str(tmp_path), str(tmp_path / "threads.env")]

    probe = subprocess.run(  # noqa: S603 - argv is this interpreter and constants, no shell
        [sys.executable, "-W", "error::RuntimeWarning", "-c", _GIL_PROBE, *argv],
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == {"name": "app", "loaded": [], "gil": False}
