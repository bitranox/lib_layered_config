"""A provenance path is shown as written, never read as Rich markup.

A configuration directory can legitimately contain square brackets (``XDG_CONFIG_HOME`` is any
path the user chooses). The human display prints each value's source path; read as Rich markup,
``[red]x[/red]`` vanishes from the path shown and an unmatched ``[/bad]`` raises ``MarkupError``
out of ``display_config``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import Config, OutputFormat, display_config
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from lib_layered_config.domain.config import SourceInfo

_PATHS = ["/c[red]x[/red]/a.toml", "/c[/bad]y/a.toml"]


def _source(key: str, path: str) -> SourceInfo:
    return {"layer": "user", "path": path, "key": key}


@os_agnostic
@pytest.mark.parametrize("path", _PATHS)
def test_a_key_under_a_section_shows_its_bracketed_path_verbatim(capsys: pytest.CaptureFixture[str], path: str) -> None:
    config = Config({"db": {"host": "h"}}, {"db.host": _source("db.host", path)})

    display_config(config, output_format=OutputFormat.HUMAN)

    assert f"# layer:user profile:none ({path})" in capsys.readouterr().out


@os_agnostic
@pytest.mark.parametrize("path", _PATHS)
def test_a_scalar_section_shows_its_bracketed_path_verbatim(capsys: pytest.CaptureFixture[str], path: str) -> None:
    config = Config({"port": 5}, {"port": _source("port", path)})

    display_config(config, output_format=OutputFormat.HUMAN, section="port")

    assert f"# layer:user profile:none ({path})" in capsys.readouterr().out
