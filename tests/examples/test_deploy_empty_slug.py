"""An empty slug is refused by deploy as it is by read, never taken as "no slug given".

``read_config`` and ``generate_examples`` refuse ``slug=""``; the deploy functions once read it as
falsy and deployed under the app name instead, into a directory no read of the same arguments would
ever look in. Leaving the slug out is a ``TypeError`` (tests/unit/test_deploy_slug_required.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ValidationError, deploy_config, deploy_config_paths, read_config, read_deploy_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _calls(source: Path) -> dict[str, Callable[[], object]]:
    return {
        "deploy_config": lambda: deploy_config(source, vendor="Acme", app="Demo", slug="", targets=["user"]),
        "deploy_config_paths": lambda: deploy_config_paths(
            source, vendor="Acme", app="Demo", slug="", targets=["user"]
        ),
        "read_deploy_config": lambda: read_deploy_config(source, vendor="Acme", app="Demo", slug="", skip=[]),
        "read_config": lambda: read_config(vendor="Acme", app="Demo", slug="", start_dir=str(source.parent)),
    }


@os_agnostic
@pytest.mark.parametrize("name", ["deploy_config", "deploy_config_paths", "read_deploy_config", "read_config"])
def test_an_empty_slug_is_refused_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    create_layered_sandbox(tmp_path / "layers", vendor="Acme", app="Demo", slug="Demo").apply_env(monkeypatch)
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")

    with pytest.raises(ValidationError, match=r"^slug cannot be empty$"):
        _calls(source)[name]()
    assert [p for p in (tmp_path / "layers").rglob("*") if p.is_file()] == []
