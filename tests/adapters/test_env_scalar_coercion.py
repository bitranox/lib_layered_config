"""The environment layer turns a value into a number only when the number reads back as the same text."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

KEPT = [
    ("5", 5),
    ("-7", -7),
    ("0", 0),
    ("5432", 5432),
    ("3.5", 3.5),
    ("-0.25", -0.25),
    ("1e+20", 1e20),
    ("true", True),
    ("FALSE", False),
    ("null", None),
    ("none", None),
]
UNCHANGED = [
    "007123",  # a PIN or zip code: the leading zeros are the value
    "0640",
    "-007",
    "-0",
    "1.50",
    "+5",
    "1_000",
    "1e5",
    "nan",
    "inf",
    "Infinity",
    "\u0661\u0662\u0663",  # Arabic-Indic digits: str.isdigit() is True, the text is not ASCII
    "12345678901234567890",  # twenty digits: past the int bound
    " 5",
    "5 ",
    "9" * 5000,  # used to raise ValueError: Exceeds the limit (4300 digits)
]


def _load(value: str) -> object:
    return DefaultEnvLoader(environ={"DEMO___VALUE": value}).load("DEMO")["value"]


@os_agnostic
@pytest.mark.parametrize(("value", "expected"), KEPT)
def test_a_value_that_reads_back_the_same_is_converted(value: str, expected: object) -> None:
    result = _load(value)
    assert result == expected
    assert type(result) is type(expected)


@os_agnostic
@pytest.mark.parametrize("value", UNCHANGED, ids=lambda value: repr(value[:12]))
def test_a_value_that_would_not_read_back_the_same_stays_a_string(value: str) -> None:
    assert _load(value) == value


@os_agnostic
def test_a_leading_zero_secret_reaches_the_configuration_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path, vendor="Probe", app="Probe", slug="coerce-probe").apply_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COERCE_PROBE___EMAIL__SMTP_PASSWORD", "007123")
    monkeypatch.setenv("COERCE_PROBE___EMAIL__HUGE", "9" * 5000)
    config = read_config(vendor="Probe", app="Probe", slug="coerce-probe", dotenv_path=tmp_path / "absent.env")
    assert config.get("email.smtp_password") == "007123"
    assert config.get("email.huge") == "9" * 5000
