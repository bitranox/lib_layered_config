from __future__ import annotations

from lib_layered_config.adapters.env.default import DefaultEnvLoader, assign_nested, default_env_prefix


def test_default_env_prefix() -> None:
    assert default_env_prefix("lib-layered-config") == "LIB_LAYERED_CONFIG"


def test_env_loader_nested(monkeypatch) -> None:
    environ = {
        "LIB_LAYERED_CONFIG_DB__HOST": "db.example.com",
        "LIB_LAYERED_CONFIG_DB__PORT": "5432",
        "LIB_LAYERED_CONFIG_FEATURE__ENABLED": "true",
        "OTHER": "ignored",
    }
    loader = DefaultEnvLoader(environ=environ)
    data = loader.load("LIB_LAYERED_CONFIG")
    assert data["db"]["host"] == "db.example.com"
    assert data["db"]["port"] == 5432
    assert data["feature"]["enabled"] is True


def test_assign_nested_overwrites_scalar_raises() -> None:
    container: dict[str, object] = {"A": "value"}
    try:
        assign_nested(container, "A__B", 1)
    except ValueError:
        pass
    else:  # pragma: no cover - ensure failure if no exception
        assert False, "Expected ValueError when overriding scalar"
