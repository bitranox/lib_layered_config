"""A YAML file is composed once: the repeated-key check reads the node graph the values are built from.

The loader used to run ``safe_load`` (scan, parse, compose, construct) and then compose the whole
document a second time for the repeated-key check, so every YAML file cost two pure-Python parses.
The count is read with ``sys.setprofile`` on PyYAML's own ``Composer.compose_document``: an observer,
nothing is replaced.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING

import pytest

from lib_layered_config.adapters.file_loaders.structured import YAMLFileLoader
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path
    from types import FrameType

pytestmark = pytest.mark.skipif(importlib.util.find_spec("yaml") is None, reason="PyYAML not available")


def _compositions_while(action: object, path: Path) -> int:
    """Run ``YAMLFileLoader().load(path)`` and count PyYAML's whole-document compositions."""
    # Imported here: PyYAML is an optional extra, and the module skips without it.
    import yaml.composer

    target = yaml.composer.Composer.compose_document.__code__
    calls = 0

    def observe(frame: FrameType, event: str, _arg: object) -> None:
        nonlocal calls
        if event == "call" and frame.f_code is target:
            calls += 1

    sys.setprofile(observe)
    try:
        YAMLFileLoader().load(path)
    except InvalidFormatError:
        if action != "refused":
            raise
    finally:
        sys.setprofile(None)
    return calls


@os_agnostic
def test_a_valid_yaml_file_is_composed_once(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("base: &b {host: h, port: 1}\ndb:\n  <<: *b\n  port: 2\nlist: [1, 2]\n", encoding="utf-8")

    assert _compositions_while("loaded", path) == 1


@os_agnostic
def test_a_file_with_a_repeated_key_is_composed_once_and_still_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("a: 1\nb: {c: 1, c: 2}\n", encoding="utf-8")

    assert _compositions_while("refused", path) == 1
    with pytest.raises(InvalidFormatError, match=r"repeats a key, and only its last value would load: b\.c \(line 2"):
        YAMLFileLoader().load(path)
