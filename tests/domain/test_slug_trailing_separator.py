"""A slug ending in ``_`` or ``-`` is refused wherever a slug is taken.

The environment prefix of slug ``app_`` (or ``app-``) is ``APP____``, which starts with ``APP___``,
the prefix of slug ``app``; on a machine running both, ``app`` read ``app_``'s variables as a stray
``_``-named section (measured 2026-11-17). User decision 2026-11-17 ([52] item 4): "Refuse slugs
ending in _ or -", in the next major.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ValidationError, deploy_config, generate_examples, read_config
from lib_layered_config.adapters.env.default import default_env_prefix
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.domain.identifiers import validate_slug
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_TRAILING = ["app_", "app-", "my-app__", "x-_"]


@os_agnostic
@pytest.mark.parametrize("slug", _TRAILING)
def test_validate_slug_refuses_a_trailing_separator(slug: str) -> None:
    with pytest.raises(ValidationError, match=r"^slug cannot end in '_' or '-': "):
        validate_slug(slug)


@os_agnostic
@pytest.mark.parametrize("slug", ["app", "my-app", "my_app_v2", "a-b_c", "a"])
def test_validate_slug_keeps_inner_separators(slug: str) -> None:
    assert validate_slug(slug) == slug


@os_agnostic
@pytest.mark.parametrize("slug", ["", "../etc", "_app_"])
def test_validate_slug_keeps_the_identifier_checks_first(slug: str) -> None:
    # The older refusal (empty, path, leading underscore) still names its own reason.
    with pytest.raises(ValidationError) as caught:
        validate_slug(slug)
    assert "cannot end in" not in str(caught.value)


def _entry_points(tmp_path: Path) -> dict[str, Callable[[str], object]]:
    source = tmp_path / "config.toml"
    source.write_text("a = 1\n", encoding="utf-8")
    return {
        "read_config": lambda slug: read_config(vendor="Acme", app="Demo", slug=slug, start_dir=str(tmp_path)),
        "deploy_config": lambda slug: deploy_config(source, vendor="Acme", app="Demo", slug=slug, targets=["user"]),
        "generate_examples": lambda slug: generate_examples(tmp_path / "out", slug=slug, vendor="Acme", app="Demo"),
        "default_env_prefix": default_env_prefix,
        "DefaultPathResolver": lambda slug: DefaultPathResolver(vendor="Acme", app="Demo", slug=slug),
    }


@os_agnostic
@pytest.mark.parametrize(
    "entry", ["read_config", "deploy_config", "generate_examples", "default_env_prefix", "DefaultPathResolver"]
)
def test_every_entry_point_refuses_it_and_writes_nothing(tmp_path: Path, entry: str) -> None:
    calls = _entry_points(tmp_path)
    before = sorted(p for p in tmp_path.rglob("*"))

    with pytest.raises(ValidationError, match=r"^slug cannot end in '_' or '-': app_$"):
        calls[entry]("app_")
    assert sorted(p for p in tmp_path.rglob("*")) == before
