"""``prefer`` and ``--prefer`` are deprecated: they never changed what a read loads.

Each layer reads ``config.toml`` and its ``config.d/`` directory, so there was never more than one
main file per layer for a suffix ranking to choose between. Passing ``prefer`` now warns, naming
where JSON and YAML go instead, and the read itself is unchanged.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from lib_layered_config import cli as cli_module
from lib_layered_config import core
from lib_layered_config.domain import json_codec
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.support import LayeredSandbox

_MESSAGE = r"prefer has no effect"

_READERS: list[Callable[..., object]] = [core.read_config, core.read_config_json, core.read_config_raw]


def _defaults(tmp_path: Path) -> Path:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[a]\nb = "c"\n', encoding="utf-8")
    return defaults


def _read(reader: Callable[..., object], tmp_path: Path, **extra: object) -> object:
    start = tmp_path / "start"
    start.mkdir(exist_ok=True)
    return reader(
        vendor="Acme", app="Demo", slug="demo", default_file=_defaults(tmp_path), start_dir=str(start), **extra
    )


@os_agnostic
@pytest.mark.parametrize("reader", _READERS, ids=lambda reader: reader.__name__)
def test_passing_prefer_warns_at_the_callers_line(
    reader: Callable[..., object], sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)

    with pytest.warns(DeprecationWarning, match=_MESSAGE) as caught:
        _read(reader, tmp_path, prefer=["json", "toml"])

    assert len(caught) == 1
    assert caught[0].filename == __file__


@os_agnostic
@pytest.mark.parametrize("reader", _READERS, ids=lambda reader: reader.__name__)
def test_a_read_without_prefer_does_not_warn(
    reader: Callable[..., object], sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _read(reader, tmp_path)

    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


@os_agnostic
def test_prefer_still_changes_nothing_the_read_returns(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)

    with pytest.warns(DeprecationWarning, match=_MESSAGE):
        preferred = _read(core.read_config_json, tmp_path, prefer=["yaml"])

    assert preferred == _read(core.read_config_json, tmp_path)


@os_agnostic
def test_a_single_str_prefer_is_still_refused(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"not a single str"):
        _read(core.read_config, tmp_path, prefer="toml")


def _cli(command: object, tmp_path: Path, *extra: str) -> tuple[int, str, str]:
    start = tmp_path / "start"
    start.mkdir(exist_ok=True)
    result = CliRunner().invoke(
        command,  # pyright: ignore[reportArgumentType] - a click command object
        [
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
            "--default-file",
            str(_defaults(tmp_path)),
            "--start-dir",
            str(start),
            *extra,
        ],
        catch_exceptions=False,
    )
    return result.exit_code, result.stdout, result.stderr


@os_agnostic
@pytest.mark.parametrize(
    "command", [cli_module.cli_read_config, cli_module.cli_read_config_json], ids=["read", "read-json"]
)
def test_the_cli_prefer_flag_warns_on_stderr_and_keeps_stdout_clean(
    command: object, sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)

    code, stdout, stderr = _cli(command, tmp_path, "--prefer", "json", "--json")

    assert code == 0
    assert "--prefer has no effect" in stderr
    envelope = json_codec.loads(stdout)
    assert isinstance(envelope, dict)
    assert envelope["ok"] is True


@os_agnostic
def test_the_cli_without_prefer_prints_no_warning(
    sandbox: LayeredSandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox.apply_env(monkeypatch)

    code, _stdout, stderr = _cli(cli_module.cli_read_config, tmp_path)

    assert code == 0
    assert "--prefer" not in stderr
