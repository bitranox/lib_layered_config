"""Module-level lookup tables are read-only, and the Enum-keyed one covers its whole Enum.

A table built once at import and read by every call must not change under a caller who holds it, so
each is a ``MappingProxyType``. These are module tables only: nothing a ``Config`` or a returned
record holds is a ``MappingProxyType``, which cannot be pickled or deep-copied.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from lib_layered_config import _layers, _platform, deploy
from lib_layered_config.domain import deploy_permissions
from lib_layered_config.domain.deploy_mode import ModeKind
from tests.support.os_markers import os_agnostic

_TABLES: dict[str, object] = {
    "deploy._TARGET_LAYERS": deploy._TARGET_LAYERS,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "deploy._MODE_PARAMETERS": deploy._MODE_PARAMETERS,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "deploy._SOURCE_REFUSALS": deploy._SOURCE_REFUSALS,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "deploy_permissions._MODE_FIELDS": deploy_permissions._MODE_FIELDS,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "_platform._CANONICAL_RESOLVER": _platform._CANONICAL_RESOLVER,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "_platform._CANONICAL_EXAMPLES": _platform._CANONICAL_EXAMPLES,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
    "_layers._FILE_LOADERS": _layers._FILE_LOADERS,  # pyright: ignore[reportPrivateUsage] - the module table itself is the subject
}


@os_agnostic
@pytest.mark.parametrize("name", sorted(_TABLES))
def test_the_table_is_read_only(name: str) -> None:
    table = _TABLES[name]

    assert isinstance(table, MappingProxyType)
    assert table, "an empty table would pass the read-only check without guarding anything"


@os_agnostic
def test_every_mode_kind_names_its_deploy_parameter() -> None:
    assert set(deploy._MODE_PARAMETERS) == set(ModeKind)  # pyright: ignore[reportPrivateUsage] - pins the table to its Enum
