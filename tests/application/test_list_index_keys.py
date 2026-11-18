"""Only ASCII digit keys address list elements, and no key's length can crash the merge.

``str.isdigit`` also accepts superscripts and other scripts' digits, which ``int()`` either refuses
(superscript two, U+00B2) or silently reads (Arabic-Indic one, U+0661, is 1). A list index is the
ASCII digits ``0-9`` and nothing else; any other key over a list replaces it like ``label`` does.
``int()`` refuses more than 4300 digits, so an overlong ASCII key must still merge: as its value
after leading zeros, or out of range.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lib_layered_config import read_config
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic

_HOSTS = ["a", "b"]


def _merge_hosts(key: str) -> object:
    base = LayerSnapshot(Layer.APP, {"hosts": list(_HOSTS)}, Path("app.toml"))
    override = LayerSnapshot(Layer.ENV, {"hosts": {key: "z"}}, None)
    return merge_layers([base, override]).data["hosts"]


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [chr(0x00B2), chr(0x0661), chr(0x0967), chr(0xFF11)],
    ids=["superscript-two", "arabic-indic-one", "devanagari-one", "fullwidth-one"],
)
def test_a_non_ascii_digit_key_replaces_the_list_like_any_other_key(key: str) -> None:
    assert _merge_hosts(key) == {key: "z"}


@os_agnostic
@pytest.mark.parametrize(
    ("key", "expected"),
    [("1", ["a", "z"]), ("01", ["a", "z"]), ("0" * 5000, ["z", "b"])],
    ids=["one", "leading-zero", "five-thousand-zeros"],
)
def test_an_ascii_digit_key_is_the_index_its_digits_name(key: str, expected: list[str]) -> None:
    assert _merge_hosts(key) == expected


@os_agnostic
@pytest.mark.parametrize("key", ["007", "1" + "0" * 5000], ids=["leading-zeros", "five-thousand-digits"])
def test_an_index_past_the_list_warns_and_leaves_it_unchanged(key: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="lib_layered_config"):
        assert _merge_hosts(key) == _HOSTS

    assert any(record.message == "list_index_out_of_range" for record in caplog.records)


@os_agnostic
def test_read_config_takes_a_superscript_key_over_a_list_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('hosts = ["a", "b"]\n', encoding="utf-8")
    monkeypatch.setenv(f"INDEX_KIT___HOSTS__{chr(0x00B2)}", "z")

    config = read_config(
        vendor="Acme",
        app="IndexKit",
        slug="index-kit",
        start_dir=str(tmp_path),
        dotenv_path=str(tmp_path / "absent.env"),
        default_file=str(defaults),
    )

    assert config.as_dict()["hosts"] == {chr(0x00B2): "z"}
