from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lib_layered_config.adapters._nested_keys import assign_nested as assign
from lib_layered_config.adapters.dotenv.default import (
    DefaultDotEnvLoader,
)
from lib_layered_config.adapters.dotenv.default import (
    _parse_dotenv as parse,
)
from lib_layered_config.domain.errors import InvalidFormatError
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


def _write_sample_dotenv(tmp_path: Path) -> tuple[DefaultDotEnvLoader, dict[str, object], Path]:
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
    assert data["db"]["host"] == "localhost"


@os_agnostic
def test_dotenv_loader_preserves_password_literal(tmp_path: Path) -> None:
    _loader, data, _ = _write_sample_dotenv(tmp_path)
    assert data["db"]["password"] == "s3cret"


@os_agnostic
def test_dotenv_loader_keeps_uncoerced_feature_value(tmp_path: Path) -> None:
    _loader, data, _ = _write_sample_dotenv(tmp_path)
    assert data["feature"] == "true"


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


def _no_prefix(paths):
    seen = []
    for parts in paths:
        for existing in seen:
            if parts[: len(existing)] == existing or existing[: len(parts)] == parts:
                return False
        seen.append(parts)
    return True


@st.composite
def dotenv_entries(draw):
    path_lists = draw(st.lists(st.lists(SEGMENT, min_size=1, max_size=3), min_size=1, max_size=5).filter(_no_prefix))
    values = draw(st.lists(DOTENV_VALUE, min_size=len(path_lists), max_size=len(path_lists)))
    return {"__".join(parts): value for parts, value in zip(path_lists, values, strict=False)}


@os_agnostic
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=dotenv_entries())
def test_dotenv_loader_handles_random_namespace(entries, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{key}={value}" for key, value in entries.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))

    def lookup(root: dict[str, object], raw_key: str) -> object:
        cursor: object = root
        for fragment in raw_key.lower().split("__"):
            cursor = cursor[fragment]  # type: ignore[index]
        return cursor

    expectation = all(lookup(data, raw_key) == value for raw_key, value in entries.items())
    assert expectation is True


@os_agnostic
def test_dotenv_loader_reports_invalid_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("INVALID", encoding="utf-8")
    loader = DefaultDotEnvLoader()
    with pytest.raises(InvalidFormatError):
        loader.load(str(tmp_path))
    assert any(record.message == "dotenv_invalid_line" for record in caplog.records)


@os_agnostic
def test_parse_dotenv_interprets_inline_hash_as_empty(tmp_path: Path) -> None:
    env_file = tmp_path / "plain.env"
    env_file.write_text("GROUP__SECRET=#hidden\n", encoding="utf-8")
    result = parse(env_file)
    assert result["group"]["secret"] == ""  # type: ignore[index]


@os_agnostic
def test_dotenv_loader_loads_explicit_path(tmp_path: Path) -> None:
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("APP__MODE=staging\n", encoding="utf-8")
    loader = DefaultDotEnvLoader()
    data = loader.load(dotenv_path=str(custom_env))
    assert data["app"]["mode"] == "staging"  # type: ignore[index]
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
def test_assign_nested_raises_invalid_format_on_scalar_collision() -> None:
    target: dict[str, object] = {"service": "scalar"}
    with pytest.raises(InvalidFormatError):
        assign(target, "SERVICE__TOKEN", "value", error_cls=InvalidFormatError)
