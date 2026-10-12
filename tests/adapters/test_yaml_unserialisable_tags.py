"""A YAML ``!!set`` or ``!!binary`` value refuses the file.

PyYAML's safe loader builds ``!!set`` as a Python ``set`` and ``!!binary`` as ``bytes``. Neither
has a JSON form, so a config holding one loaded and then crashed every JSON view
(``Config.to_json``, ``read_config_json``, ``display_config`` in JSON) with an uncaught
``TypeError``. The loader refuses the file instead, naming the file, where each such value sits
and its type, never the value itself. Timestamps and dates serialise and keep loading.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import LayerLoadError, read_config
from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML is an optional extra and is not installed")

# base64 of "s3cr3t-binary", so the decoded secret can be searched for in the message too.
_BINARY_SECRET = "czNjcjN0LWJpbmFyeQ=="


def _refusal(tmp_path: Path, text: str) -> tuple[str, str]:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InvalidFormatError) as caught:
        YAMLFileLoader().load(str(path))
    return str(path), str(caught.value)


@os_agnostic
def test_a_set_refuses_the_file_naming_where_it_sits(tmp_path: Path) -> None:
    path, message = _refusal(tmp_path, "service:\n  hosts: !!set {alpha, beta}\n")

    assert path in message
    assert "!!set" in message
    assert message.endswith(": service.hosts (set)")


@os_agnostic
def test_a_binary_value_refuses_the_file_naming_where_it_sits(tmp_path: Path) -> None:
    path, message = _refusal(tmp_path, f"service:\n  key: !!binary {_BINARY_SECRET}\n")

    assert path in message
    assert "!!binary" in message
    assert message.endswith(": service.key (bytes)")


@os_agnostic
def test_the_refusal_never_carries_a_value(tmp_path: Path) -> None:
    _, message = _refusal(tmp_path, f"a:\n  hosts: !!set {{alpha-host}}\n  key: !!binary {_BINARY_SECRET}\n")

    assert "alpha-host" not in message
    assert _BINARY_SECRET not in message
    assert "s3cr3t-binary" not in message


@os_agnostic
def test_values_nested_in_lists_name_every_position(tmp_path: Path) -> None:
    _, message = _refusal(tmp_path, "items:\n  - name: a\n  - tags: !!set {x}\nblobs:\n  - !!binary aGk=\n")

    assert "items.1.tags (set)" in message
    assert "blobs.0 (bytes)" in message


@os_agnostic
def test_timestamps_and_dates_still_load_and_serialise(
    tmp_path: Path, sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("when:\n  at: 2026-10-12T10:00:00Z\n  day: 2026-10-12\n", encoding="utf-8")

    config = read_config(vendor="Acme", app="Demo", slug="demo", default_file=defaults, start_dir=str(tmp_path))

    assert config.as_dict() == {"when": {"at": config.get("when.at"), "day": config.get("when.day")}}
    assert '"day":"2026-10-12"' in config.to_json()


@os_agnostic
def test_read_config_refuses_a_set_instead_of_crashing_a_json_view_later(
    tmp_path: Path, sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.apply_env(monkeypatch)
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("service:\n  hosts: !!set {alpha}\n", encoding="utf-8")

    with pytest.raises(LayerLoadError, match="!!set"):
        read_config(vendor="Acme", app="Demo", slug="demo", default_file=defaults, start_dir=str(tmp_path))
