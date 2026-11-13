from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, TypeGuard

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lib_layered_config.adapters._value_coercion import coerce_value
from lib_layered_config.adapters.dotenv.default import (
    DefaultDotEnvLoader,
)
from lib_layered_config.adapters.dotenv.default import (
    _parse_dotenv as parse,  # pyright: ignore[reportPrivateUsage] - unit test of the dotenv line parser itself
)
from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from hypothesis.strategies import DrawFn


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _section(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload[key]
    assert _is_mapping(value)
    return value


def _write_sample_dotenv(tmp_path: Path) -> tuple[DefaultDotEnvLoader, Mapping[str, object], Path]:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DB__HOST=localhost\nDB__PASSWORD='s3cret'\nFEATURE=true # comment\n",
        encoding="utf-8",
    )
    loader = DefaultDotEnvLoader()
    return loader, loader.load(str(tmp_path)), env_file


@os_agnostic
def test_dotenv_loader_preserves_plain_text_host(tmp_path: Path) -> None:
    _loader, data, _ = _write_sample_dotenv(tmp_path)
    assert _section(data, "db")["host"] == "localhost"


@os_agnostic
def test_dotenv_loader_preserves_password_literal(tmp_path: Path) -> None:
    _loader, data, _ = _write_sample_dotenv(tmp_path)
    assert _section(data, "db")["password"] == "s3cret"


@os_agnostic
def test_dotenv_loader_converts_an_unquoted_boolean(tmp_path: Path) -> None:
    _loader, data, _ = _write_sample_dotenv(tmp_path)
    assert data["feature"] is True


@os_agnostic
def test_dotenv_loader_records_last_loaded_path(tmp_path: Path) -> None:
    loader, _, env_file = _write_sample_dotenv(tmp_path)
    assert loader.last_loaded_path == str(env_file)


@os_agnostic
def test_dotenv_loader_returns_empty_mapping_when_missing(tmp_path: Path) -> None:
    payload = DefaultDotEnvLoader().load(str(tmp_path))
    assert payload == {}


SEGMENT = st.text(min_size=1, max_size=5, alphabet=st.characters(min_codepoint=65, max_codepoint=90))
DOTENV_VALUE = st.text(min_size=1, max_size=8, alphabet=st.characters(min_codepoint=97, max_codepoint=122))


def _no_prefix(paths: list[list[str]]) -> bool:
    seen: list[list[str]] = []
    for parts in paths:
        for existing in seen:
            if parts[: len(existing)] == existing or existing[: len(parts)] == parts:
                return False
        seen.append(parts)
    return True


@st.composite
def dotenv_entries(draw: DrawFn) -> dict[str, str]:
    path_lists = draw(st.lists(st.lists(SEGMENT, min_size=1, max_size=3), min_size=1, max_size=5).filter(_no_prefix))
    values = draw(st.lists(DOTENV_VALUE, min_size=len(path_lists), max_size=len(path_lists)))
    return {"__".join(parts): value for parts, value in zip(path_lists, values, strict=False)}


@os_agnostic
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=dotenv_entries())
def test_dotenv_loader_handles_random_namespace(entries: dict[str, str], tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{key}={value}" for key, value in entries.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))

    def lookup(root: Mapping[str, object], raw_key: str) -> object:
        cursor: object = root
        for fragment in raw_key.lower().split("__"):
            assert _is_mapping(cursor)
            cursor = cursor[fragment]
        return cursor

    expectation = all(lookup(data, raw_key) == coerce_value(raw_key, value) for raw_key, value in entries.items())
    assert expectation is True


@os_agnostic
def test_dotenv_loader_reports_invalid_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("INVALID", encoding="utf-8")
    loader = DefaultDotEnvLoader()
    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(InvalidFormatError):
        loader.load(str(tmp_path))
    assert any(record.message == "dotenv_invalid_line" for record in caplog.records)


@os_agnostic
def test_parse_dotenv_interprets_inline_hash_as_empty(tmp_path: Path) -> None:
    env_file = tmp_path / "plain.env"
    env_file.write_text("GROUP__SECRET=#hidden\n", encoding="utf-8")
    result = parse(env_file)
    assert _section(result, "group")["secret"] == ""


@os_agnostic
def test_dotenv_loader_loads_explicit_path(tmp_path: Path) -> None:
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("APP__MODE=staging\n", encoding="utf-8")
    loader = DefaultDotEnvLoader()
    data = loader.load(dotenv_path=str(custom_env))
    assert _section(data, "app")["mode"] == "staging"
    assert loader.last_loaded_path == str(custom_env)


@os_agnostic
def test_dotenv_loader_explicit_path_skips_directory_search(tmp_path: Path) -> None:
    # Place a .env in start_dir that should be ignored
    (tmp_path / ".env").write_text("IGNORED__KEY=should_not_load\n", encoding="utf-8")
    custom_env = tmp_path / "other.env"
    custom_env.write_text("USED__KEY=loaded\n", encoding="utf-8")
    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path), dotenv_path=str(custom_env))
    assert "used" in data
    assert "ignored" not in data
    assert loader.last_loaded_path == str(custom_env)


@os_agnostic
def test_dotenv_loader_explicit_path_missing_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.env"
    loader = DefaultDotEnvLoader()
    data = loader.load(dotenv_path=str(missing))
    assert data == {}
    assert loader.last_loaded_path is None


@os_agnostic
def test_dotenv_loader_rejects_file_over_size_cap(tmp_path: Path) -> None:
    cap = structured_module.MAX_CONFIG_FILE_BYTES
    prefix = b"A=1\n"
    env_file = tmp_path / ".env"
    # Bytes, not text: write_text turns "\n" into "\r\n" on Windows, which changes the size.
    env_file.write_bytes(prefix + b"#" * (cap + 1 - len(prefix)))
    assert env_file.stat().st_size == cap + 1
    loader = DefaultDotEnvLoader()
    with pytest.raises(InvalidFormatError):
        loader.load(str(tmp_path))


@os_agnostic
def test_dotenv_loader_accepts_file_at_size_cap(tmp_path: Path) -> None:
    cap = structured_module.MAX_CONFIG_FILE_BYTES
    prefix = b"A=1\n"
    env_file = tmp_path / ".env"
    # Bytes, not text: write_text turns "\n" into "\r\n" on Windows, which changes the size.
    env_file.write_bytes(prefix + b"#" * (cap - len(prefix)))
    assert env_file.stat().st_size == cap
    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))
    assert data["a"] == 1


@os_agnostic
def test_dotenv_loader_explicit_path_that_is_a_directory_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "config.env"
    directory.mkdir()
    loader = DefaultDotEnvLoader()

    with pytest.raises(InvalidFormatError, match="is a directory, not a configuration file") as caught:
        loader.load(dotenv_path=str(directory))

    assert str(directory) in str(caught.value)
    assert loader.last_loaded_path is None


@os_agnostic
def test_dotenv_upward_search_skips_a_directory_named_dot_env(tmp_path: Path) -> None:
    """A virtualenv named ``.env`` on the search path is not a dotenv file and is passed over."""
    (tmp_path / ".env").mkdir()
    start = tmp_path / "project"
    start.mkdir()
    (start / ".env").mkdir()

    loader = DefaultDotEnvLoader()
    loader.load(start_dir=str(start))

    assert loader.last_loaded_path not in {str(start / ".env"), str(tmp_path / ".env")}


#: What Notepad's "UTF-8 with BOM" and PowerShell 5 ``Out-File -Encoding utf8`` write before the text.
_UTF8_BOM_BYTES = b"\xef\xbb\xbf"


@os_agnostic
def test_a_dotenv_saved_with_a_utf8_bom_keeps_its_first_key(tmp_path: Path) -> None:
    (tmp_path / ".env").write_bytes(_UTF8_BOM_BYTES + b"DB__HOST=db.example\nMODE=prod\n")

    data = DefaultDotEnvLoader().load(str(tmp_path))

    assert data == {"db": {"host": "db.example"}, "mode": "prod"}


@os_agnostic
def test_an_explicit_dotenv_path_with_a_utf8_bom_keeps_its_first_key(tmp_path: Path) -> None:
    custom_env = tmp_path / "custom.env"
    custom_env.write_bytes(_UTF8_BOM_BYTES + b"MODE=prod\n")

    data = DefaultDotEnvLoader().load(dotenv_path=str(custom_env))

    assert data == {"mode": "prod"}
