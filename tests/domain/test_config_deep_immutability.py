"""Nothing a caller does to a value read from a ``Config`` changes the ``Config``.

``Config`` promises one immutable snapshot, but it used to be read-only only at its top level: a
nested table or list handed out by ``cfg["db"]`` or ``cfg.get(...)`` was the stored object
itself, so changing it in place changed every later read, and a nested table of the mapping a
``Config`` was built from stayed shared with it. A ``Config`` now owns a deep copy and hands out
copies of containers, keeping their types, and can be copied and pickled.
"""

from __future__ import annotations

import copy
import json
import pickle
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config import Config, read_config
from lib_layered_config.domain.config import EMPTY_CONFIG, SourceInfo
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, NotSensitiveKeys
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "Snapshot"
SLUG = "snapshot-probe"


def _config() -> Config:
    data: dict[str, Any] = {"db": {"host": "real", "hosts": ["a", "b"], "token": "t0p"}, "debug": False}
    meta = {"db.host": SourceInfo(layer="app", path="/opt/app/config.toml", key="db.host")}
    return Config(data, meta, NotSensitiveKeys.of(["db.token"]))


@os_agnostic
def test_a_write_into_a_section_read_by_key_does_not_reach_the_config() -> None:
    cfg = _config()

    cfg["db"]["host"] = "evil"

    assert cfg.get("db.host") == "real"


@os_agnostic
def test_an_append_to_a_list_read_by_dotted_path_does_not_reach_the_config() -> None:
    cfg = _config()

    cfg.get("db.hosts").append("x")
    cfg.get("db")["hosts"].append("y")

    assert cfg.get("db.hosts") == ["a", "b"]


@os_agnostic
def test_a_write_through_items_or_values_does_not_reach_the_config() -> None:
    cfg = _config()

    dict(cfg.items())["db"]["host"] = "via-items"
    next(iter(cfg.values()))["host"] = "via-values"

    assert cfg.get("db.host") == "real"


@os_agnostic
def test_changing_the_source_mapping_afterwards_does_not_reach_the_config() -> None:
    source: dict[str, Any] = {"db": {"host": "real", "hosts": ["a"]}}
    cfg = Config(source, {})

    source["db"]["host"] = "evil"
    source["db"]["hosts"].append("x")

    assert cfg.get("db.host") == "real"
    assert cfg.get("db.hosts") == ["a"]


@os_agnostic
def test_a_write_into_a_provenance_record_does_not_reach_the_config() -> None:
    cfg = _config()

    origin = cfg.origin("db.host")
    assert origin is not None
    origin["layer"] = "evil"

    assert cfg.origin("db.host") == {"layer": "app", "path": "/opt/app/config.toml", "key": "db.host"}


@os_agnostic
def test_read_values_keep_their_types_and_serialise() -> None:
    cfg = _config()

    assert type(cfg["db"]) is dict
    assert type(cfg.get("db.hosts")) is list
    assert json.loads(json.dumps(cfg["db"])) == {"host": "real", "hosts": ["a", "b"], "token": "t0p"}
    assert cfg["debug"] is False


def _assert_carries_the_same(twin: object, cfg: Config) -> None:
    assert isinstance(twin, Config)
    assert twin == cfg
    assert twin.origin("db.host") == cfg.origin("db.host")
    # db.token is declared not sensitive, so it stays visible only if the declaration came along.
    assert twin.as_dict(redact=True) == cfg.as_dict(redact=True)
    assert twin.as_dict(redact=True)["db"]["token"] == "t0p"
    twin["db"]["host"] = "evil"
    assert twin.get("db.host") == "real"
    assert cfg.get("db.host") == "real"


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
@os_agnostic
def test_a_config_pickles_and_unpickles_with_every_protocol(protocol: int) -> None:
    cfg = _config()

    twin = pickle.loads(pickle.dumps(cfg, protocol=protocol))  # noqa: S301 - bytes this test just made from its own Config

    _assert_carries_the_same(twin, cfg)


@pytest.mark.parametrize("duplicate", [copy.deepcopy, copy.copy])
@os_agnostic
def test_a_config_can_be_copied_and_deep_copied(duplicate: Any) -> None:
    cfg = _config()

    twin = duplicate(cfg)

    _assert_carries_the_same(twin, cfg)


@os_agnostic
def test_a_structure_holding_a_config_deep_copies_and_keeps_one_copy_per_config() -> None:
    cfg = _config()
    settings: dict[str, Any] = {"primary": cfg, "same_again": cfg, "retries": [1, 2]}

    clone = copy.deepcopy(settings)

    _assert_carries_the_same(clone["primary"], cfg)
    assert clone["primary"] is clone["same_again"]
    assert clone["primary"] is not cfg


@os_agnostic
def test_the_empty_config_pickles_and_deep_copies() -> None:
    restored = pickle.loads(pickle.dumps(EMPTY_CONFIG))  # noqa: S301 - bytes this test just made from its own Config

    assert restored == EMPTY_CONFIG
    assert copy.deepcopy(EMPTY_CONFIG) == EMPTY_CONFIG
    assert len(restored) == 0


@os_agnostic
def test_a_config_from_read_config_unpickles_in_a_fresh_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
    default_file = tmp_path / "defaults.toml"
    default_file.write_text('[db]\nhost = "real"\npassword = "pw"\n', encoding="utf-8")
    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)
    (tmp_path / "config.pickle").write_bytes(pickle.dumps(config))

    # A fresh interpreter has none of this process's objects: what loads is only what the bytes name.
    child = subprocess.run(
        [sys.executable, "-I", "-"],
        input=_UNPICKLE_AND_REPORT,
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == {
        "host": "real",
        "layer": "defaults",
        "redacted": REDACTED_PLACEHOLDER,
        "equal_to_dump": True,
    }


_UNPICKLE_AND_REPORT = """
import json, pickle
from pathlib import Path
config = pickle.loads(Path("config.pickle").read_bytes())
print(json.dumps({
    "host": config.get("db.host"),
    "layer": config.origin("db.host")["layer"],
    "redacted": config.as_dict(redact=True)["db"]["password"],
    "equal_to_dump": config.as_dict() == {"db": {"host": "real", "password": "pw"}},
}))
"""


@os_agnostic
def test_a_config_with_overrides_is_just_as_immutable() -> None:
    merged = _config().with_overrides({"db": {"port": 5432}})

    merged["db"]["host"] = "evil"
    merged.get("db.hosts").append("x")

    assert merged.get("db.host") == "real"
    assert merged.get("db.hosts") == ["a", "b"]
    assert merged.get("db.port") == 5432


@os_agnostic
def test_a_config_from_read_config_does_not_change_when_a_read_value_is_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG).apply_env(monkeypatch)
    default_file = tmp_path / "defaults.toml"
    default_file.write_text('[db]\nhost = "real"\nhosts = ["a", "b"]\npassword = "pw"\n', encoding="utf-8")

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)
    config["db"]["host"] = "evil"
    config.get("db.hosts").append("x")

    assert config.get("db.host") == "real"
    assert config.get("db.hosts") == ["a", "b"]
    assert config.as_dict(redact=True)["db"]["password"] == REDACTED_PLACEHOLDER
