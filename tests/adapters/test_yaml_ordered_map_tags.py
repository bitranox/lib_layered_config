"""A YAML ``!!omap`` or ``!!pairs`` value refuses the file.

PyYAML's safe loader turns both tags into a list of ``(key, value)`` tuples, so a key such as
``password`` arrives as a tuple element, never as a mapping key: redaction cannot see it, dotted
lookup cannot reach it, and every redacted view prints its value. The loader refuses the file
instead, naming the file and where each such value sits, never anything from inside it. A plain
YAML mapping already keeps its order, so nothing is lost by writing one.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

_SECRET_VALUE = "s3cr3t-value-never-logged"


def _refusal(tmp_path: Path, text: str) -> tuple[str, str]:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))
    return str(path), str(caught.value)


@os_agnostic
@pytest.mark.parametrize("tag", ["!!omap", "!!pairs"])
def test_an_ordered_map_tag_refuses_the_file_naming_where_it_sits(tmp_path: Path, tag: str) -> None:
    path, message = _refusal(tmp_path, f"creds: {tag}\n  - password: {_SECRET_VALUE}\n  - user: bob\n")

    assert path in message
    assert "!!omap or !!pairs" in message
    assert "plain mapping" in message
    assert message.endswith(": creds")


@os_agnostic
@pytest.mark.parametrize("tag", ["!!omap", "!!pairs"])
def test_the_refusal_never_carries_a_value(tmp_path: Path, tag: str) -> None:
    _, message = _refusal(tmp_path, f"creds: {tag}\n  - password: {_SECRET_VALUE}\n")

    assert _SECRET_VALUE not in message
    assert "password" not in message


@os_agnostic
def test_tags_nested_in_a_list_and_in_a_mapping_name_every_position(tmp_path: Path) -> None:
    _, message = _refusal(
        tmp_path,
        "items:\n  - name: a\n  - creds: !!pairs\n      - token: t\nouter:\n  inner: !!omap\n    - key: k\n",
    )

    assert "items.1.creds" in message
    assert "outer.inner" in message


@os_agnostic
def test_plain_lists_of_mappings_and_dates_still_load(tmp_path: Path) -> None:
    # !!set and !!binary are refused for a reason of their own: tests/adapters/test_yaml_unserialisable_tags.py.
    path = tmp_path / "config.yaml"
    path.write_text("hosts:\n  - name: a\n    password: p\nday: 2026-10-12\n", encoding="utf-8")

    loaded = YAMLFileLoader().load(str(path))

    assert loaded["hosts"] == [{"name": "a", "password": "p"}]
    assert str(loaded["day"]) == "2026-10-12"


@os_agnostic
def test_read_config_refuses_an_ordered_map_in_an_app_dot_d_yaml_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox: LayeredSandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="ConfigKit", slug="config-kit")
    sandbox.apply_env(monkeypatch)
    sandbox.write("app", "config.d/10-creds.yaml", content=f"creds: !!omap\n  - password: {_SECRET_VALUE}\n")

    with pytest.raises(LayerLoadError, match=r"!!omap or !!pairs") as caught:
        read_config(vendor="Acme", app="ConfigKit", slug="config-kit", start_dir=str(sandbox.start_dir))

    assert _SECRET_VALUE not in str(caught.value)
