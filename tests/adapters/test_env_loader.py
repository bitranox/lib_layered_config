"""Environment loader adapter tests clarifying namespace coercion.

The scenarios cover prefix naming, nested assignment, and randomised inputs to
prove the adapter continues to match the documented environment rules.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from lib_layered_config.adapters.env.default import DefaultEnvLoader, assign_nested, default_env_prefix


def test_default_env_prefix() -> None:
    """Slug values should become upper snake-case prefixes used throughout docs."""

    assert default_env_prefix("lib-layered-config") == "LIB_LAYERED_CONFIG"


def test_env_loader_nested(monkeypatch) -> None:
    """Coerce environment variables into nested dictionaries while ignoring out-of-scope keys."""

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
    """Protect existing scalar values from being replaced by new nested assignments."""

    container: dict[str, object] = {"A": "value"}
    try:
        assign_nested(container, "A__B", 1)
    except ValueError:
        pass
    else:  # pragma: no cover - ensure failure if no exception
        assert False, "Expected ValueError when overriding scalar"


SCALAR_VALUES = st.sampled_from(["0", "1", "true", "false", "3.5", "none", "debug"])
NAMESPACE_KEYS = st.sampled_from(["SERVICE__TIMEOUT", "SERVICE__ENDPOINT", "LOGGING__LEVEL"])


@given(st.dictionaries(NAMESPACE_KEYS, SCALAR_VALUES, max_size=3))
def test_env_loader_handles_random_namespace(entries) -> None:
    """Randomised namespace inputs should map to consistent nested/coerced payloads."""

    prefix = "DEMO"
    environ = {f"{prefix}_" + key: value for key, value in entries.items()}
    environ["IGNORED"] = "1"
    loader = DefaultEnvLoader(environ=environ)
    payload = loader.load(prefix)

    def _expect(value: str) -> object:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered in {"none", "null"}:
            return None
        if lowered.startswith("-") and lowered[1:].isdigit():
            return int(lowered)
        if lowered.isdigit():
            return int(lowered)
        try:
            return float(value)
        except ValueError:
            return value

    for key, original in entries.items():
        parts = key.lower().split("__")
        node = payload
        for part in parts[:-1]:
            assert part in node
            node = node[part]
        assert node[parts[-1]] == _expect(original)
    assert "ignored" not in payload
