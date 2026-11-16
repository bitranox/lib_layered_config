"""An identifier ending in a newline is refused like one ending in a carriage return.

The slug, vendor/app and hostname patterns were ``^...$`` used with ``.match``, and Python's ``$`` also
matches just before a final newline, so ``"demo\\n"`` passed: ``read_config`` loaded it and
``deploy_config`` wrote ``.../demo\\n/config.toml``. User decision 2026-11-16 (N-1): refuse it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import read_config
from lib_layered_config.deploy import deploy_config
from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.domain.identifiers import validate_hostname, validate_identifier, validate_vendor_app
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_VALIDATORS: dict[str, Callable[[str], str]] = {
    "slug": lambda value: validate_identifier(value, "slug"),
    "vendor": lambda value: validate_vendor_app(value, "vendor"),
    "hostname": validate_hostname,
}


def _message(check: Callable[[str], str], value: str) -> str:
    with pytest.raises(ValidationError) as caught:
        check(value)
    return str(caught.value)


@os_agnostic
@pytest.mark.parametrize("name", list(_VALIDATORS))
def test_a_trailing_newline_is_refused_with_the_carriage_return_message(name: str) -> None:
    check = _VALIDATORS[name]

    newline, carriage_return = _message(check, "demo\n"), _message(check, "demo\r")

    # Both characters are printed as escapes (user decision 2026-11-16, R2-F4), so the messages differ
    # only there.
    assert newline == carriage_return.replace("\\u000d", "\\u000a")
    assert newline.endswith("contains invalid characters: demo\\u000a")


@os_agnostic
@pytest.mark.parametrize("field", ["slug", "vendor", "app"])
def test_a_read_refuses_an_identity_ending_in_a_newline(
    field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    identity = {"vendor": "Acme", "app": "Demo", "slug": "demo", field: "demo\n"}

    with pytest.raises(ValidationError, match="contains invalid characters"):
        read_config(vendor=identity["vendor"], app=identity["app"], slug=identity["slug"], start_dir=str(tmp_path))


@os_agnostic
def test_a_deploy_refuses_a_slug_ending_in_a_newline_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = create_layered_sandbox(tmp_path / "home", vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    source = tmp_path / "source.toml"
    source.write_text("a = 1\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="contains invalid characters"):
        deploy_config(source, vendor="Acme", app="Demo", slug="demo\n", targets=["user"], set_permissions=False)

    assert not [path for path in (tmp_path / "home").rglob("*") if "\n" in path.name]
