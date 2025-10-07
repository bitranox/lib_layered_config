from __future__ import annotations

import pytest

from lib_layered_config.testing import i_should_fail

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_i_should_fail_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="^i should fail$"):
        i_should_fail()


@os_agnostic
def test_i_should_fail_is_reexported() -> None:
    from lib_layered_config import i_should_fail as exported
    from lib_layered_config.testing import i_should_fail as original

    assert exported is original
