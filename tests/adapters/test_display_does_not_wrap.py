"""The human display never breaks a line, so its output reads back as TOML at any width.

Rich wraps each printed line at the console width (80, or ``COLUMNS``, on a pipe). A wrapped
``# layer:`` comment or note continues on a line without ``#``, and a wrapped value splits a
string: either way a TOML parser refuses the output the docs say reads back as one key per line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import Config, OutputFormat, display_config
from tests.support.os_markers import os_agnostic
from tests.support.toml_read import loads_toml

if TYPE_CHECKING:
    from lib_layered_config.domain.config import SourceInfo

_LONG_PATH = "/opt/" + "/".join(["a-directory-name-long-enough"] * 6) + "/config.toml"
_LONG_VALUE = "v" * 150


def _source(key: str) -> SourceInfo:
    return {"layer": "user", "path": _LONG_PATH, "key": key}


@os_agnostic
@pytest.mark.parametrize("columns", ["40", "80"])
def test_a_long_comment_and_value_still_read_back_as_toml(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, columns: str
) -> None:
    monkeypatch.setenv("COLUMNS", columns)
    data = {"db": {"host": _LONG_VALUE}, "top": _LONG_VALUE}
    config = Config(data, {"db.host": _source("db.host"), "top": _source("top")})

    display_config(config, output_format=OutputFormat.HUMAN)

    out = capsys.readouterr().out
    assert f"# layer:user profile:none ({_LONG_PATH})" in out
    assert loads_toml(out) == data
