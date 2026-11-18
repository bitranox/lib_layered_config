"""An environment or ``.env`` key with an empty segment, and a ``.env`` NUL, are refused.

A key is split on ``__`` into table names. A leading, trailing or doubled ``__`` left an empty name
in the path, so a typo changed the configuration silently: ``APP___A__=1`` replaced a configured
``a = 5`` with ``{"a": {"": 1}}``, and ``APP___DB____PORT=1`` left ``db.port`` alone while adding
``db[""].port``. A NUL in a ``.env`` key or value passed into the configuration as it stood. Each
is now a load error naming the variable, never its value, as a malformed ``.env`` line already was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_SECRET = "s3cr3t-value"
_EMPTY_SEGMENT_KEYS = ["A__", "__A", "DB____PORT", "A____"]


@os_agnostic
@pytest.mark.parametrize("key", _EMPTY_SEGMENT_KEYS)
def test_an_environment_key_with_an_empty_segment_is_refused(key: str) -> None:
    loader = DefaultEnvLoader(environ={f"APP___{key}": _SECRET})

    with pytest.raises(InvalidFormatError) as caught:
        loader.load("APP")

    message = str(caught.value)
    assert f"environment: APP___{key}" in message
    assert "empty key segment" in message
    assert _SECRET not in message


@os_agnostic
@pytest.mark.parametrize("key", [*_EMPTY_SEGMENT_KEYS, ""])
def test_a_dotenv_key_with_an_empty_segment_is_refused(key: str, tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"OK=1\n{key}={_SECRET}\n", encoding="utf-8")

    with pytest.raises(InvalidFormatError) as caught:
        DefaultDotEnvLoader().load(dotenv_path=dotenv)

    message = str(caught.value)
    assert f"{key} (line 2)" in message and str(dotenv) in message
    assert "empty key segment" in message
    assert _SECRET not in message


@os_agnostic
def test_well_formed_nested_keys_still_nest(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("DB__PORT=1\n", encoding="utf-8")

    assert DefaultEnvLoader(environ={"APP___DB__HOST": "h"}).load("APP") == {"db": {"host": "h"}}
    assert DefaultDotEnvLoader().load(dotenv_path=dotenv).data == {"db": {"port": 1}}


@os_agnostic
def test_read_config_reports_an_environment_typo_as_a_layer_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("a = 5\n", encoding="utf-8")
    monkeypatch.setenv("EMPTY_SEGMENT_PROBE___A__", "1")

    with pytest.raises(LayerLoadError, match=r"EMPTY_SEGMENT_PROBE___A__"):
        read_config(
            vendor="Acme",
            app="Demo",
            slug="empty-segment-probe",
            default_file=defaults,
            start_dir=str(tmp_path),
            dotenv_path=tmp_path / "missing.env",
        )


@os_agnostic
@pytest.mark.parametrize("line", [f"A=x\x00{_SECRET}\n", f"A\x00B={_SECRET}\n"], ids=["nul-in-value", "nul-in-key"])
def test_a_dotenv_nul_is_refused(line: str, tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"OK=1\n{line}", encoding="utf-8")

    with pytest.raises(InvalidFormatError) as caught:
        DefaultDotEnvLoader().load(dotenv_path=dotenv)

    message = str(caught.value)
    assert "line 2" in message and str(dotenv) in message and "NUL" in message
    assert _SECRET not in message


@os_agnostic
def test_other_control_characters_and_a_nul_in_a_comment_stay_accepted(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("# note\x00\nA=x\x01y\n", encoding="utf-8")

    assert DefaultDotEnvLoader().load(dotenv_path=dotenv).data == {"a": "x\x01y"}
