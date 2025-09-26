from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader


def test_dotenv_loader_parses_nested(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DB__HOST=localhost\nDB__PASSWORD='s3cret'\nFEATURE=true # comment\n",
        encoding="utf-8",
    )
    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))
    assert data["db"]["host"] == "localhost"
    assert data["db"]["password"] == "s3cret"
    assert data["feature"] == "true"
    assert loader.last_loaded_path == str(env_file)


def test_dotenv_loader_returns_empty_when_not_found(tmp_path: Path) -> None:
    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))
    assert data == {}


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
    return {"__".join(parts): value for parts, value in zip(path_lists, values)}


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=dotenv_entries())
def test_dotenv_loader_handles_random_namespace(entries, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{key}={value}" for key, value in entries.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loader = DefaultDotEnvLoader()
    data = loader.load(str(tmp_path))

    for raw_key, value in entries.items():
        parts = [part.lower() for part in raw_key.split("__")]
        cursor = data
        for part in parts[:-1]:
            assert isinstance(cursor, dict)
            assert part in cursor
            cursor = cursor[part]
        assert isinstance(cursor, dict)
        assert cursor[parts[-1]] == value
