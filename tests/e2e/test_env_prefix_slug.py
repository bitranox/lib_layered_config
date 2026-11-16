"""``default_env_prefix`` and ``env-prefix`` refuse exactly the slugs every reading command refuses.

Before, only an empty slug was refused: ``env-prefix ../x`` printed ``../X___`` with exit 0 while
``read --slug ../x`` and ``deploy --slug ../x`` refused it. User decision 2026-11-16 (F9): the function
validates the slug with ``validate_identifier``, the check ``read``, ``deploy`` and ``generate`` use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import cli, default_env_prefix
from lib_layered_config.domain.errors import ValidationError
from lib_layered_config.domain.identifiers import validate_identifier
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable

_SLUGS = ["my-app", "my_app", "My.App", "app2", "", "../x", "a b", "x/y", "x\\y", chr(0xFC), f"a{chr(0)}b", ".hidden"]


def _refusal(call: Callable[[], object]) -> str | None:
    try:
        call()
    except ValidationError as exc:
        return str(exc)
    return None


@os_agnostic
@pytest.mark.parametrize("slug", _SLUGS)
def test_the_prefix_is_refused_exactly_where_the_slug_check_refuses_it(slug: str) -> None:
    assert _refusal(lambda: default_env_prefix(slug)) == _refusal(lambda: validate_identifier(slug, "slug"))


@os_agnostic
def test_a_slug_the_check_refuses_is_a_usage_error_naming_why(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["env-prefix", "../x"], restore_traceback=False)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "slug contains invalid characters: ../x" in captured.err


@os_agnostic
def test_a_valid_slug_still_gets_its_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["env-prefix", "my-app"], restore_traceback=False)

    assert code == 0
    assert capsys.readouterr().out.strip() == "MY_APP___"
