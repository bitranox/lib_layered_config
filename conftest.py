"""Fixtures every test and doctest of the repository gets, ``src`` doctests included.

They live at the root, not in ``tests/conftest.py``, because ``pytest --doctest-modules src`` collects the
docstrings of ``src`` and a conftest only reaches what sits below it.
"""

from __future__ import annotations

import os

import pytest

# The variables a layer root falls back to when no override is set, plus the two app-root overrides that
# have no plain variable to fall back to. The other overrides (LIB_LAYERED_CONFIG_APPDATA, _LOCALAPPDATA,
# _PROGRAMDATA, _MAC_HOME_ROOT) are left alone on purpose: an override set here would beat every test that
# sets the plain variable (APPDATA) itself.
_LAYER_ROOT_VARIABLES = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CONFIG_HOME",
    "LIB_LAYERED_CONFIG_ETC",
    "LIB_LAYERED_CONFIG_MAC_APP_ROOT",
)


@pytest.fixture(autouse=True)
def _host_layers_isolated(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every layer root at an empty directory of the test's own.

    A test that calls ``read_config`` or ``deploy_config`` without a sandbox otherwise reads the machine's
    real app, host and user layers for its slug, so a developer who once ran an example (``demo``,
    ``clash-kit``) saw unrelated tests fail on their own config files. A test that sets a root itself (a
    sandbox's ``apply_env``, its own ``monkeypatch.setenv``, an override variable) runs after this fixture and
    wins; one that removes a variable to test a default removes it here too.
    """
    roots = tmp_path_factory.mktemp("host-roots")
    for name in _LAYER_ROOT_VARIABLES:
        monkeypatch.setenv(name, str(roots / name.lower()))
    if os.name == "nt":
        # The library finds ProgramData in any case; off Windows a second spelling set here would compete
        # with the one a test sets, while Windows' own environment treats them as one variable.
        monkeypatch.setenv("ProgramData", str(roots / "programdata"))
