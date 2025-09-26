from __future__ import annotations

import pytest

from lib_layered_config.testing import i_should_fail


def test_i_should_fail_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="^i should fail$"):
        i_should_fail()
