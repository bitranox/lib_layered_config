"""An unquoted value reaches the configuration with the same type from the environment and from .env."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config import read_config
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

SLUG = "parity-probe"
ENV_NAME = "PARITY_PROBE___EMAIL__SMTP_HOSTS"
#: A key no lower layer defines, so a list and a table can both land on it without a type conflict.
FREE_ENV_NAME = "PARITY_PROBE___EMAIL__EXTRA"
CONTAINERS = ['["a.example:587", "b.example:587"]', '{"size": 20, "timeout": 5}']


def _read(tmp_path: Path, dotenv: Path | None = None, *, key: str = "email.smtp_hosts") -> Any:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("[email]\nsmtp_hosts = []\n", encoding="utf-8")
    return read_config(
        vendor="Probe",
        app="Probe",
        slug=SLUG,
        default_file=defaults,
        dotenv_path=dotenv or tmp_path / "absent.env",
    ).get(key)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Points every platform's app/host/user roots into tmp_path (Linux, macOS and Windows variables).
    create_layered_sandbox(tmp_path / "layers", vendor="Probe", app="Probe", slug=SLUG).apply_env(monkeypatch)
    monkeypatch.chdir(tmp_path)


@os_agnostic
@pytest.mark.parametrize("value", CONTAINERS)
def test_an_unquoted_json_container_has_the_same_type_in_both_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"EMAIL__EXTRA={value}\n", encoding="utf-8")
    from_dotenv = _read(tmp_path, dotenv, key="email.extra")
    monkeypatch.setenv(FREE_ENV_NAME, value)
    from_env = _read(tmp_path, key="email.extra")
    assert type(from_dotenv) is type(from_env)
    assert from_dotenv == from_env
    assert isinstance(from_env, (list, dict))


@os_agnostic
@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("value", ["[1]", "{}", *CONTAINERS])
def test_a_quoted_json_value_stays_the_literal_string(tmp_path: Path, quote: str, value: str) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"EMAIL__EXTRA={quote}{value}{quote}\n", encoding="utf-8")
    assert _read(tmp_path, dotenv, key="email.extra") == value


@os_agnostic
@pytest.mark.parametrize("value", ["a.example:587,b.example:587", "[not json"])
def test_a_non_json_value_stays_one_string_in_both_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"EMAIL__SMTP_HOSTS={value}\n", encoding="utf-8")
    assert _read(tmp_path, dotenv) == value
    monkeypatch.setenv(ENV_NAME, value)
    assert _read(tmp_path) == value


@os_agnostic
def test_per_index_keys_fill_a_list_from_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("EMAIL__SMTP_HOSTS__0=a.example:587\nEMAIL__SMTP_HOSTS__1=b.example:587\n", encoding="utf-8")
    assert _read(tmp_path, dotenv) == ["a.example:587", "b.example:587"]


@os_agnostic
@pytest.mark.parametrize(
    ("value", "expected"), [("true", True), ("5", 5), ("none", None), ("12345678", 12345678), ("007123", "007123")]
)
def test_an_unquoted_scalar_has_the_same_type_in_both_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str, expected: object
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"EMAIL__EXTRA={value}\n", encoding="utf-8")
    from_dotenv = _read(tmp_path, dotenv, key="email.extra")
    monkeypatch.setenv(FREE_ENV_NAME, value)
    from_env = _read(tmp_path, key="email.extra")
    assert from_dotenv == from_env == expected
    assert type(from_dotenv) is type(from_env)
