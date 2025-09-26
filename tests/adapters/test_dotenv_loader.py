from __future__ import annotations

from pathlib import Path

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
