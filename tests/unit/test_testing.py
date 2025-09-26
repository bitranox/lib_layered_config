from __future__ import annotations

import pytest

from lib_layered_config.testing import i_should_fail


def test_i_should_fail_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="^i should fail$"):
        i_should_fail()


def test_i_should_fail_reexported() -> None:
    from lib_layered_config import i_should_fail as exported
    from lib_layered_config.testing import i_should_fail as original

    assert exported is original
