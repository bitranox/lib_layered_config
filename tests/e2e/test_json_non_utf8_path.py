"""JSON output under a config directory whose name is not valid UTF-8.

On POSIX a file name is bytes, and Python hands each byte that is not UTF-8 over as a lone
surrogate (``b"x\\xffy"`` reads as ``"x\\udcffy"``). Such a path in provenance, a deploy result or
an error message made every JSON output fail with ``TypeError: str is not valid UTF-8``: no
envelope, exit 22, and a deploy that wrote its files and then printed nothing. User decision
2026-11-16 (R1-F1, "Escape the byte as \\xNN", form "\\xff, the byte on disk"): JSON writes such a
byte as the four characters ``\\xff``.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, cast

import pytest

from lib_layered_config import cli, read_config_json
from tests.support import create_layered_sandbox
from tests.support.os_markers import posix_only

# Undecodable bytes reach Python as surrogate escapes only when the filesystem encoding is UTF-8; under
# another locale (LC_ALL=de_AT.iso88591 with PYTHONUTF8=0) the same bytes decode as ordinary text.
_NEEDS_UTF8_FILESYSTEM = pytest.mark.skipif(
    sys.getfilesystemencoding().lower() != "utf-8", reason="needs a UTF-8 filesystem encoding"
)
pytestmark = _NEEDS_UTF8_FILESYSTEM

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support import LayeredSandbox

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
IDENTITY = ["--vendor", VENDOR, "--app", APP, "--slug", SLUG]

#: The directory name ``b"x\xffy"`` as Python reads it from a POSIX file system. Built with
#: surrogateescape rather than ``os.fsdecode``: Windows decodes file names as strict UTF-8, so
#: ``fsdecode`` raised while importing this module there, before ``posix_only`` could skip it.
_BAD_NAME = b"x\xffy".decode("utf-8", "surrogateescape")
#: How JSON output writes that name.
_ESCAPED_NAME = "x\\xffy"


def _bad_root(tmp_path: Path) -> Path:
    root = tmp_path / _BAD_NAME
    try:
        root.mkdir()
    except OSError as error:  # macOS APFS refuses a name that is not UTF-8
        pytest.skip(f"this file system refuses a name that is not UTF-8: {error}")
    return root


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(_bad_root(tmp_path), vendor=VENDOR, app=APP, slug=SLUG)
    created.apply_env(monkeypatch)
    created.start_dir.mkdir(parents=True, exist_ok=True)
    return created


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object]]:
    code = cli.main(list(argv), restore_traceback=True)
    document = json.loads(capsys.readouterr().out)
    assert isinstance(document, dict)
    return code, cast("dict[str, object]", document)


def _escaped(path: Path) -> str:
    return str(path).replace(_BAD_NAME, _ESCAPED_NAME)


@posix_only
def test_read_config_json_writes_the_byte_as_an_escape(sandbox: LayeredSandbox) -> None:
    sandbox.write("user", "config.toml", content="a = 1\n")

    document = json.loads(read_config_json(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir)))

    assert document["config"] == {"a": 1}
    assert document["provenance"]["a"]["path"] == _escaped(sandbox.roots["user"] / "config.toml")


@posix_only
@pytest.mark.parametrize("command", [["read", "--json"], ["read-json", "--json"], ["read-json"]])
def test_the_cli_read_prints_its_json_with_the_byte_escaped(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    sandbox.write("user", "config.toml", content="a = 1\n")

    code, document = _run(capsys, command[0], *IDENTITY, "--start-dir", str(sandbox.start_dir), *command[1:])

    assert code == 0
    data = document.get("data", document)
    assert isinstance(data, dict)
    provenance = cast("dict[str, dict[str, object]]", data["provenance"])
    assert provenance["a"]["path"] == _escaped(sandbox.roots["user"] / "config.toml")


@posix_only
def test_a_broken_file_there_reports_its_load_error_in_the_envelope(
    sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox.write("user", "config.toml", content="a = = 1\n")

    code, document = _run(capsys, "read", *IDENTITY, "--start-dir", str(sandbox.start_dir), "--json")

    error = cast("dict[str, object]", document["error"])
    assert (code, document["ok"], error["type"], error["exit_code"]) == (1, False, "LayerLoadError", 1)
    assert _ESCAPED_NAME in cast("str", error["message"])


@posix_only
def test_deploy_prints_its_envelope_after_writing(sandbox: LayeredSandbox, capsys: pytest.CaptureFixture[str]) -> None:
    source = sandbox.start_dir / "source.toml"
    source.write_text("c = 3\n", encoding="utf-8")

    code, document = _run(
        capsys, "deploy", "--source", str(source), *IDENTITY, "--target", "user", "--no-permissions", "--json"
    )

    assert (code, document["ok"]) == (0, True)
    data = cast("dict[str, list[str]]", document["data"])
    assert data["created"] == [_escaped(sandbox.roots["user"] / "config.toml")]
    assert (sandbox.roots["user"] / "config.toml").read_text(encoding="utf-8") == "c = 3\n"
