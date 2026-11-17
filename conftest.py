"""Fixtures every test and doctest of the repository gets, ``src`` doctests included.

They live at the root, not in ``tests/conftest.py``, because ``pytest --doctest-modules src`` collects the
docstrings of ``src`` and a conftest only reaches what sits below it.
"""

from __future__ import annotations

import os

import pytest

# The variables a layer root falls back to when no override is set, plus the two app-root overrides that
# have no plain variable to fall back to.
_LAYER_ROOT_VARIABLES = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CONFIG_HOME",
    "LIB_LAYERED_CONFIG_ETC",
    "LIB_LAYERED_CONFIG_MAC_APP_ROOT",
)

# The overrides that have a plain variable behind them. They are deleted, never set: an override beats the
# plain variable, so one set here would beat every test that sets APPDATA itself, and one left in the
# developer's shell would beat the roots set here.
_LAYER_ROOT_OVERRIDES = (
    "LIB_LAYERED_CONFIG_APPDATA",
    "LIB_LAYERED_CONFIG_LOCALAPPDATA",
    "LIB_LAYERED_CONFIG_PROGRAMDATA",
    "LIB_LAYERED_CONFIG_MAC_HOME_ROOT",
)


@pytest.fixture(autouse=True)
def _host_layers_isolated(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every layer root at an empty directory of the test's own.

    A test that calls ``read_config`` or ``deploy_config`` without a sandbox otherwise reads the machine's
    real app, host and user layers for its slug, so a developer who once ran an example (``demo``,
    ``clash-kit``) saw unrelated tests fail on their own config files. A test that sets a root itself (a
    sandbox's ``apply_env``, its own ``monkeypatch.setenv``, an override variable) runs after this fixture and
    wins; one that removes a variable to test a default removes it here too. An override left in the
    developer's shell is removed, so it cannot reach past these roots either.
    """
    roots = tmp_path_factory.mktemp("host-roots")
    for name in _LAYER_ROOT_VARIABLES:
        monkeypatch.setenv(name, str(roots / name.lower()))
    for name in _LAYER_ROOT_OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    # The env layer reads `<PREFIX>___<KEY>` variables, so one exported in the developer's shell (the
    # README's CONFIG_KIT___API__KEY) would reach every read of a test using that slug. No variable outside
    # the env layer's naming holds three underscores, so deleting every one leaves the rest of the shell alone.
    for name in [name for name in os.environ if "___" in name]:
        monkeypatch.delenv(name)
    if os.name == "nt":
        monkeypatch.setenv("ProgramData", str(roots / "programdata"))
        return
    # The library finds ProgramData in any case. Off Windows each spelling is a variable of its own, so one
    # set here would compete with the spelling a test sets; deleting every one leaves the test's alone.
    for name in [name for name in os.environ if name.upper() == "PROGRAMDATA"]:
        monkeypatch.delenv(name)
