"""An environment or ``.env`` ``null``/``none`` is judged on the key's spelling in the file.

A sensitive key keeps ``null``/``none`` as text, so a secret is never cleared to None by accident.
Environment and ``.env`` key names arrive in lowercase, and the loader judged that lowercase name:
``dbpassword`` has no word boundary, so ``MYAPP___A__DBPASSWORD=null`` cleared a file's
``dbPassword`` to None while ``db_password`` kept the text. The merge, which matches the key to its
stored spelling, now makes the call (user decision 2026-11-18, "Decide in the merge").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import core
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config import Config
    from tests.support import LayeredSandbox


def _read(tmp_path: Path, defaults_toml: str, *, not_sensitive: list[str] | None = None) -> Config:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(defaults_toml, encoding="utf-8")
    start = tmp_path / "start"
    start.mkdir(exist_ok=True)
    return core.read_config(
        vendor="Acme",
        app="Demo",
        slug="demo",
        default_file=defaults,
        start_dir=str(start),
        not_sensitive=not_sensitive,
    )


@os_agnostic
@pytest.mark.parametrize("spelling", ["null", "None"])
def test_an_environment_null_keeps_a_camel_case_secret_as_text(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spelling: str
) -> None:
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv("DEMO___A__DBPASSWORD", spelling)

    config = _read(tmp_path, '[a]\ndbPassword = "real"\n')

    assert config.get("a.dbPassword") == spelling


@os_agnostic
def test_a_dotenv_null_keeps_a_camel_case_secret_as_text(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    start = tmp_path / "start"
    start.mkdir()
    (start / ".env").write_text("A__DBPASSWORD=null\n", encoding="utf-8")

    config = _read(tmp_path, '[a]\ndbPassword = "real"\n')

    assert config.get("a.dbPassword") == "null"


@os_agnostic
def test_a_camel_case_secret_inside_a_list_element_keeps_null_as_text(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv("DEMO___A__ITEMS__0__DBPASSWORD", "null")

    config = _read(tmp_path, '[[a.items]]\ndbPassword = "real"\n')

    assert config.get("a.items")[0]["dbPassword"] == "null"


@os_agnostic
@pytest.mark.parametrize(
    "case",
    [
        ("[a]\ntimeout = 5\n", "DEMO___A__TIMEOUT", "a.timeout"),
        ('[a]\nhosts = ["h"]\n', "DEMO___A__HOSTS__0", None),
        ("[a]\nother = 1\n", "DEMO___A__DBPASSWORD", "a.dbpassword"),
    ],
    ids=["plain-key", "list-slot", "no-stored-spelling"],
)
def test_a_null_for_a_key_that_is_not_sensitive_becomes_none(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: tuple[str, str, str | None]
) -> None:
    defaults_toml, variable, dotted = case
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv(variable, "null")

    config = _read(tmp_path, defaults_toml)

    if dotted is None:
        assert config.get("a.hosts") == [None]
    else:
        assert config.get(dotted, default="absent") is None


@os_agnostic
def test_a_declared_not_sensitive_camel_case_key_reads_null_as_none(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)
    monkeypatch.setenv("DEMO___A__DBPASSWORD", "null")

    config = _read(tmp_path, '[a]\ndbPassword = "real"\n', not_sensitive=["a.dbPassword"])

    assert config.get("a.dbPassword", default="absent") is None
