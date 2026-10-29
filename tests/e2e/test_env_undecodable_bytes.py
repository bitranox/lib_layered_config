"""An environment variable whose name or value is not valid UTF-8.

On POSIX an environment value is bytes; Python hands one that is not UTF-8 over with each bad
byte as a lone surrogate (``b"a\\xffb"`` reads as ``"a\\udcffb"``). Such a value loaded, then
crashed every JSON view and the CLI ``read`` with ``TypeError: str is not valid UTF-8``. The
variable is now refused, naming it and the byte offset and never its value, the way a ``.env``
file with the same bytes already is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.core import LayerLoadError
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config import Config

VENDOR = "Acme"
APP = "Probe"
SLUG = "bytes-probe"
PREFIX = "BYTES_PROBE___"

#: ``b"se\xffcret"`` as Python reads it from a POSIX environment.
_UNDECODABLE = "se\udcffcret"


def _read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
    return read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path))


@posix_only
def test_a_value_with_undecodable_bytes_is_refused_naming_the_variable_and_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{PREFIX}DB__PASSWORD", _UNDECODABLE)

    with pytest.raises(
        LayerLoadError, match=rf"environment variable {PREFIX}DB__PASSWORD is not valid UTF-8 \(byte offset 2\)"
    ) as caught:
        _read(tmp_path, monkeypatch)

    assert "cret" not in str(caught.value)


@posix_only
def test_a_name_with_undecodable_bytes_is_refused_with_the_byte_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{PREFIX}DB__N\udcffAME", "plain")

    with pytest.raises(
        LayerLoadError, match=rf"environment variable name {PREFIX}DB__N\\xffAME is not valid UTF-8 \(byte offset 19\)"
    ):
        _read(tmp_path, monkeypatch)


@posix_only
def test_a_variable_outside_the_prefix_is_not_looked_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_OTHER_TOOL", _UNDECODABLE)
    monkeypatch.setenv(f"{PREFIX}DB__NAME", "app")

    config = _read(tmp_path, monkeypatch)

    assert config.get("db.name") == "app"


@os_agnostic
def test_valid_non_ascii_text_still_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}DB__NAME", "Gr\u00fc\u00dfe \U0001f600")

    config = _read(tmp_path, monkeypatch)

    assert config.get("db.name") == "Gr\u00fc\u00dfe \U0001f600"


@os_agnostic
@pytest.mark.parametrize("value", ["a\ud800b", "a\udcffb"], ids=["unpaired-surrogate", "escaped-byte"])
def test_the_loader_refuses_any_lone_surrogate_whatever_platform_put_it_there(value: str) -> None:
    """Windows hands an unpaired UTF-16 surrogate through as one; it has no UTF-8 form either."""
    loader = DefaultEnvLoader(environ={"DEMO___KEY": value})

    with pytest.raises(
        InvalidFormatError, match=r"environment variable DEMO___KEY is not valid UTF-8 \(byte offset 1\)"
    ):
        loader.load("DEMO")
