"""The example generator refuses a slug, vendor or app that would leave the destination.

Every other entry point validates these identifiers in the path resolver; the generator turned them
into paths unchecked, so ``slug="../../x"`` wrote ``config.toml`` and its ``hosts/`` and
``config.d/`` files beside the destination, and an absolute slug aimed at the filesystem root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from lib_layered_config import cli
from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.generate import generate_examples
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path

_GOOD = {"slug": "demo", "vendor": "Acme", "app": "Demo"}
_HOSTILE = ["../../escaped", "/absolute-target", "..\\escaped", "a\x00b", ""]


def _files_under(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


@os_agnostic
@pytest.mark.parametrize("platform", ["posix", "windows"])
@pytest.mark.parametrize("field", ["slug", "vendor", "app"])
@pytest.mark.parametrize("value", _HOSTILE, ids=["parent", "absolute", "backslash", "nul", "empty"])
def test_a_hostile_identifier_is_refused_before_anything_is_written(
    tmp_path: Path, platform: str, field: str, value: str
) -> None:
    destination = tmp_path / "dest"
    identifiers = {**_GOOD, field: value}

    with pytest.raises(ValidationError, match=field):
        generate_examples(
            destination,
            platform=platform,
            slug=identifiers["slug"],
            vendor=identifiers["vendor"],
            app=identifiers["app"],
        )

    assert _files_under(tmp_path) == []


@os_agnostic
@pytest.mark.parametrize("platform", ["posix", "windows"])
def test_a_vendor_and_app_with_spaces_are_still_accepted(tmp_path: Path, platform: str) -> None:
    written = generate_examples(tmp_path / "dest", slug="demo", vendor="Acme Corp", app="My App", platform=platform)

    assert written
    assert all(path.resolve().is_relative_to((tmp_path / "dest").resolve()) for path in written)


@os_agnostic
def test_the_cli_refuses_a_traversal_slug_and_writes_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    args = ["generate-examples", "--destination", str(destination), "--slug", "../../escaped"]
    args += ["--vendor", "Acme", "--app", "Demo", "--platform", "posix"]

    result = CliRunner().invoke(cli.cli, args)

    assert isinstance(result.exception, ValidationError)
    assert "slug contains invalid characters" in str(result.exception)
    assert _files_under(tmp_path) == []
