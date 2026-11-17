"""The root fixture keeps an env-layer variable exported in the developer's shell out of every test.

A variable a shell exports exists before pytest starts, so only a child pytest run with it set can show
whether the fixture removes it; setting it inside a test would run after the fixture.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.support.os_markers import os_agnostic

_ROOT = Path(__file__).resolve().parents[2]


@os_agnostic
def test_an_exported_variable_with_a_test_slugs_prefix_reaches_no_test() -> None:
    """``DEMO___PLANTED=1`` in the shell leaves the tests reading the ``demo`` slug green."""
    env = {**os.environ, "DEMO___PLANTED": "1"}
    env.pop("PYTEST_ADDOPTS", None)
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "tests/unit/test_core.py"],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert run.returncode == 0, run.stdout[-2000:]
