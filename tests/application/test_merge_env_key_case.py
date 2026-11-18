"""An environment or ``.env`` key overrides a file key whatever the file's spelling.

Environment variable names lose their case on the way in (``MYAPP___A__DBPASSWORD``), so the env
and ``.env`` layers deliver lowercase keys. A file may spell the same key ``dbPassword``. The merge
matches those two layers' keys case-insensitively against what the lower layers stored, keeping
the stored spelling; file layers stay case-sensitive.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import core
from lib_layered_config.application.merge import LayerSnapshot, merge_layers
from lib_layered_config.domain.identifiers import Layer
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from tests.support import LayeredSandbox


@os_agnostic
@pytest.mark.parametrize("layer", [Layer.ENV, Layer.DOTENV], ids=["env", "dotenv"])
def test_a_case_folded_key_overrides_the_camel_case_file_key(layer: Layer) -> None:
    result = merge_layers(
        [
            LayerSnapshot(Layer.APP, {"a": {"dbPassword": "x"}}, Path("app.toml")),
            LayerSnapshot(layer, {"a": {"dbpassword": "s3"}}, None),
        ]
    )

    assert result.data == {"a": {"dbPassword": "s3"}}
    assert result.provenance["a.dbPassword"]["layer"] == layer.value
    assert "a.dbpassword" not in result.provenance


@os_agnostic
def test_a_case_folded_table_name_reaches_the_camel_case_table() -> None:
    result = merge_layers(
        [
            LayerSnapshot(Layer.APP, {"dbPool": {"maxSize": 1, "minSize": 1}}, Path("app.toml")),
            LayerSnapshot(Layer.ENV, {"dbpool": {"maxsize": 5}}, None),
        ]
    )

    assert result.data == {"dbPool": {"maxSize": 5, "minSize": 1}}


@os_agnostic
def test_file_layers_keep_keys_that_differ_only_by_case_apart() -> None:
    result = merge_layers(
        [
            LayerSnapshot(Layer.APP, {"Key": 1}, Path("app.toml")),
            LayerSnapshot(Layer.USER, {"key": 2}, Path("user.toml")),
        ]
    )

    assert result.data == {"Key": 1, "key": 2}


@os_agnostic
def test_two_stored_spellings_leave_the_override_where_it_was_and_warn(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    result = merge_layers(
        [
            LayerSnapshot(Layer.APP, {"a": {"dbPassword": "x", "DBPASSWORD": "y"}}, Path("app.toml")),
            LayerSnapshot(Layer.ENV, {"a": {"dbpassword": "s3"}}, None),
        ]
    )

    assert result.data == {"a": {"dbPassword": "x", "DBPASSWORD": "y", "dbpassword": "s3"}}
    warnings = [record for record in caplog.records if record.message == "case_folded_key_ambiguous"]
    assert len(warnings) == 1


@os_agnostic
def test_read_config_applies_an_environment_override_to_a_camel_case_key(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[a]\ndbPassword = "x"\n', encoding="utf-8")
    monkeypatch.setenv("DEMO___A__DBPASSWORD", "s3")
    start = tmp_path / "start"
    start.mkdir()

    config = core.read_config(vendor="Acme", app="Demo", slug="demo", default_file=defaults, start_dir=str(start))

    assert config.get("a.dbPassword") == "s3"
    assert config.get("a.dbpassword") is None
    origin = config.origin("a.dbPassword")
    assert origin is not None
    assert origin["layer"] == "env"
