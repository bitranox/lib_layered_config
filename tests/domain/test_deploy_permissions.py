"""DeployPermissions: the [lib_layered_config.default_permissions] section, read in one pass."""

from __future__ import annotations

import copy
import sys
from typing import TYPE_CHECKING, Any

import pytest

from lib_layered_config.domain.config import Config
from lib_layered_config.domain.deploy_mode import DeployMode, DeployModeError, ModeKind, brief_repr
from lib_layered_config.domain.deploy_permissions import (
    OVERRIDE_SOURCE,
    SECTION_KEY,
    DeployPermissions,
    DeployPermissionsError,
    LayerModes,
    PermissionProblem,
    deploy_permissions_from_config,
    parse_deploy_permissions,
)
from lib_layered_config.domain.errors import ConfigError
from lib_layered_config.domain.permissions import LAYER_PERMISSIONS
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Callable


def _config(section: object, *, sources: dict[str, tuple[str, str | None]] | None = None) -> Config:
    """Build a Config holding *section* under lib_layered_config.default_permissions."""
    provenance: dict[str, Any] = {}
    for key, (layer, path) in (sources or {}).items():
        provenance[key] = {"layer": layer, "path": path, "key": key}
    return Config({"lib_layered_config": {"default_permissions": section}}, provenance)


def _problems(section: object, **kwargs: Any) -> list[str]:
    with pytest.raises(DeployPermissionsError) as caught:
        deploy_permissions_from_config(_config(section, **kwargs))
    return str(caught.value).splitlines()


@os_agnostic
def test_an_absent_section_gives_the_built_in_layer_modes() -> None:
    settings = deploy_permissions_from_config(Config({}, {}))
    for layer, modes in LAYER_PERMISSIONS.items():
        assert settings.for_layer(layer).directory.value == modes["dir"]
        assert settings.for_layer(layer).file.value == modes["file"]
    assert settings.enabled is True
    assert settings == DeployPermissions.defaults()


@os_agnostic
def test_a_configured_mode_replaces_only_its_own_default() -> None:
    settings = deploy_permissions_from_config(_config({"user_directory": "0o750", "app_file": "640"}))
    assert settings.user.directory.value == 0o750
    assert settings.app.file.value == 0o640
    assert settings.user.file.value == 0o600
    assert settings.host.directory.value == 0o755


@os_agnostic
def test_enabled_false_is_read() -> None:
    assert deploy_permissions_from_config(_config({"enabled": False})).enabled is False


@os_agnostic
@pytest.mark.parametrize(
    ("section", "line"),
    [
        ({"enabled": "maybe"}, f"{SECTION_KEY}.enabled: must be true or false, got str 'maybe'"),
        ({"enabled": 1}, f"{SECTION_KEY}.enabled: must be true or false, got int 1"),
        (5, f"{SECTION_KEY}: must be a table, got int"),
        (
            {"user_dir": "0o700"},
            f"{SECTION_KEY}: unknown setting 'user_dir'; expected one of app_directory, app_file, enabled, "
            "host_directory, host_file, user_directory, user_file",
        ),
        ({"user_directory": "7_5_0"}, f"{SECTION_KEY}.user_directory: '7_5_0' is not a plain octal literal"),
        ({"user_file": "10000"}, f"{SECTION_KEY}.user_file: '10000' is outside 0..0o7777"),
        ({"app_directory": "770"}, f"{SECTION_KEY}.app_directory: unsafe directory mode 0o770: group write (0o020)"),
        ({"user_file": 444}, f"{SECTION_KEY}.user_file: a bare integer is read as decimal (444 = 0o674)"),
    ],
)
def test_each_refusal_is_one_line_naming_the_key(section: object, line: str) -> None:
    lines = _problems(section)
    assert len(lines) == 1
    assert lines[0].startswith(line)


@os_agnostic
def test_a_non_table_namespace_is_refused() -> None:
    with pytest.raises(DeployPermissionsError, match=r"^lib_layered_config: must be a table, got int$"):
        deploy_permissions_from_config(Config({"lib_layered_config": 5}, {}))


@os_agnostic
def test_every_bad_value_is_reported_at_once() -> None:
    lines = _problems({"user_file": 444, "enabled": "maybe", "app_directory": "0o755"})
    assert len(lines) == 2
    assert lines[0].startswith(f"{SECTION_KEY}.user_file: ")
    assert lines[1].startswith(f"{SECTION_KEY}.enabled: ")


@os_agnostic
@pytest.mark.parametrize(
    ("layer", "path", "suffix"), [("user", "/cfg/config.toml", "/cfg/config.toml"), ("env", None, "env")]
)
def test_a_problem_names_the_file_or_layer_it_came_from(layer: str, path: str | None, suffix: str) -> None:
    key = f"{SECTION_KEY}.user_file"
    lines = _problems({"user_file": 444}, sources={key: (layer, path)})
    assert lines[0].endswith(f"(source: {suffix})")


@os_agnostic
def test_the_hint_is_the_last_line() -> None:
    error = DeployPermissionsError([PermissionProblem("k", "bad")], hint="do this instead")
    assert str(error).splitlines() == ["k: bad", "do this instead"]
    assert error.problems == (PermissionProblem("k", "bad"),)


@os_agnostic
def test_the_refusal_is_a_config_error_and_a_value_error() -> None:
    assert issubclass(DeployPermissionsError, ConfigError)
    assert issubclass(DeployPermissionsError, ValueError)


@os_agnostic
def test_parse_accepts_none_as_absent() -> None:
    assert parse_deploy_permissions(None) == DeployPermissions.defaults()


@os_agnostic
def test_layer_modes_keep_their_kinds() -> None:
    modes = DeployPermissions.defaults().for_layer("user")
    assert modes.directory.kind is ModeKind.DIRECTORY
    assert modes.file.kind is ModeKind.FILE


@os_agnostic
def test_layer_modes_refuses_swapped_kinds() -> None:
    dir_mode = DeployMode.from_text("0o755", ModeKind.DIRECTORY)
    file_mode = DeployMode.from_text("0o644", ModeKind.FILE)
    with pytest.raises(DeployModeError, match="in that order"):
        LayerModes(directory=file_mode, file=dir_mode)


@os_agnostic
def test_layer_modes_refuses_a_directory_field_that_is_not_a_deploy_mode() -> None:
    file_mode = DeployMode.from_text("0o644", ModeKind.FILE)
    with pytest.raises(DeployModeError, match="directory must be a DeployMode, got str"):
        LayerModes(directory="0o755", file=file_mode)  # type: ignore[arg-type]


@os_agnostic
def test_layer_modes_refuses_a_file_field_that_is_not_a_deploy_mode() -> None:
    dir_mode = DeployMode.from_text("0o755", ModeKind.DIRECTORY)
    with pytest.raises(DeployModeError, match="file must be a DeployMode, got NoneType"):
        LayerModes(directory=dir_mode, file=None)  # type: ignore[arg-type]


@os_agnostic
def test_layer_modes_accepts_a_deploy_mode_subclass() -> None:
    """G8: the field check uses isinstance, not type(x) is not DeployMode, so a DeployMode
    subclass (which still satisfies every safety rule DeployMode.__post_init__ enforces) is
    accepted rather than refused."""

    class DeployModeSubclass(DeployMode):
        pass

    dir_mode = DeployModeSubclass(0o755, ModeKind.DIRECTORY)
    file_mode = DeployModeSubclass(0o644, ModeKind.FILE)
    layer = LayerModes(directory=dir_mode, file=file_mode)
    assert layer.directory is dir_mode
    assert layer.file is file_mode


@os_agnostic
def test_deploy_permissions_refuses_a_layer_field_that_is_not_layer_modes() -> None:
    defaults = DeployPermissions.defaults()
    with pytest.raises(DeployModeError, match="app must be a LayerModes, got str"):
        DeployPermissions(app="oops", host=defaults.host, user=defaults.user)  # type: ignore[arg-type]


@os_agnostic
def test_deploy_permissions_refuses_a_non_bool_enabled() -> None:
    defaults = DeployPermissions.defaults()
    with pytest.raises(DeployModeError, match="enabled must be a bool, got str"):
        DeployPermissions(
            app=defaults.app,
            host=defaults.host,
            user=defaults.user,
            enabled="false",  # type: ignore[arg-type]
        )


def _via_reduce(error: DeployPermissionsError) -> DeployPermissionsError:
    """Rebuild *error* the way pickle does, from its reduce tuple (pickle.loads itself trips ruff S301)."""
    reduced = error.__reduce_ex__(5)
    rebuilt = reduced[0](*reduced[1])
    if len(reduced) > 2 and reduced[2]:
        rebuilt.__dict__.update(reduced[2])
    return rebuilt


@os_agnostic
@pytest.mark.parametrize(
    "round_trip", [copy.copy, copy.deepcopy, _via_reduce], ids=["copy", "deepcopy", "pickle-protocol"]
)
def test_the_refusal_survives_pickle_and_copy(
    round_trip: Callable[[DeployPermissionsError], DeployPermissionsError],
) -> None:
    error = DeployPermissionsError(
        [PermissionProblem("k", "bad", "env"), PermissionProblem("j", "worse")], hint="do this instead"
    )
    rebuilt = round_trip(error)
    assert type(rebuilt) is DeployPermissionsError
    assert rebuilt.problems == error.problems
    assert rebuilt.hint == error.hint
    # Exception's own reduce rebuilds from args (the message alone): one character per line (re-review m7).
    assert str(rebuilt) == str(error)


def _add_note(error: BaseException, note: str) -> None:
    """``add_note`` (3.11+) stores its list as the instance attribute ``__notes__``; 3.10 gets the same attribute."""
    if sys.version_info >= (3, 11):
        error.add_note(note)
    else:
        error.__notes__ = [note]


@os_agnostic
@pytest.mark.parametrize(
    "round_trip", [copy.copy, copy.deepcopy, _via_reduce], ids=["copy", "deepcopy", "pickle-protocol"]
)
def test_the_refusal_keeps_its_notes_through_pickle_and_copy(
    round_trip: Callable[[DeployPermissionsError], DeployPermissionsError],
) -> None:
    # A caller that adds context with add_note must not lose it when the error crosses a process
    # boundary or is copied; a reduce that returns only the constructor arguments drops it (re-review m-c).
    error = DeployPermissionsError([PermissionProblem("k", "bad")], hint="do this instead")
    _add_note(error, "while deploying /etc/xdg/demo")
    rebuilt = round_trip(error)
    assert rebuilt.__notes__ == ["while deploying /etc/xdg/demo"]
    assert rebuilt.problems == error.problems
    assert str(rebuilt) == str(error)


def _file_config(section: object) -> Config:
    """A Config whose permission settings all came from /cfg/config.toml."""
    keys = [f"{SECTION_KEY}.{name}" for name in section] if isinstance(section, dict) else [SECTION_KEY]
    return _config(section, sources=dict.fromkeys(keys, ("app", "/cfg/config.toml")))


@os_agnostic
def test_an_override_replaces_the_configured_value() -> None:
    config = _file_config({"user_file": "0o600", "app_file": "0o640"})
    settings = deploy_permissions_from_config(config, overrides={"user_file": "0o640", "enabled": False})
    assert settings.user.file.value == 0o640
    assert settings.app.file.value == 0o640
    assert settings.enabled is False


@os_agnostic
def test_a_refused_override_names_the_override_as_its_source() -> None:
    with pytest.raises(DeployPermissionsError) as caught:
        deploy_permissions_from_config(_file_config({"user_file": "0o600"}), overrides={"user_file": 444})
    (line,) = str(caught.value).splitlines()
    assert line.startswith(f"{SECTION_KEY}.user_file: a bare integer is read as decimal (444 = 0o674)")
    assert line.endswith(f"(source: {OVERRIDE_SOURCE})")


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [f"{SECTION_KEY}.user_file", "user.file", "USER_FILE", "user\nfile", "k" * 5000],
    ids=["dotted", "dot", "upper", "newline", "long"],
)
def test_an_override_key_must_be_a_flat_setting_name(key: str) -> None:
    with pytest.raises(DeployPermissionsError) as caught:
        deploy_permissions_from_config(Config({}, {}), overrides={key: "0o640"})
    # One bounded line whatever the name holds: it is shown through brief_repr (re-review m-b).
    (line,) = str(caught.value).splitlines()
    assert line.startswith(f"{SECTION_KEY}: unknown setting {brief_repr(key)}; expected one of ")
    assert line.endswith("(source: override)")
    assert len(line) < 300


@os_agnostic
def test_an_unknown_name_in_a_file_is_one_bounded_line_naming_the_file() -> None:
    # A quoted TOML key can hold anything; the problem line must not carry it raw (re-review m-b).
    name = "evil\n" + "x" * 500
    lines = _problems({name: "0o640"}, sources={f"{SECTION_KEY}.{name}": ("app", "/cfg/config.toml")})
    assert lines == [
        f"{SECTION_KEY}: unknown setting {brief_repr(name)}; expected one of app_directory, app_file, enabled, "
        "host_directory, host_file, user_directory, user_file (source: /cfg/config.toml)"
    ]


@os_agnostic
def test_a_configured_problem_keeps_its_file_next_to_a_bad_override() -> None:
    with pytest.raises(DeployPermissionsError) as caught:
        deploy_permissions_from_config(_file_config({"enabled": "maybe"}), overrides={"user_file": 444})
    lines = str(caught.value).splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"{SECTION_KEY}.enabled: ")
    assert lines[0].endswith("(source: /cfg/config.toml)")
    assert lines[1].startswith(f"{SECTION_KEY}.user_file: ")
    assert lines[1].endswith("(source: override)")


@os_agnostic
def test_an_override_masks_the_bad_configured_value_it_replaces() -> None:
    settings = deploy_permissions_from_config(_file_config({"user_file": 444}), overrides={"user_file": "0o640"})
    assert settings.user.file.value == 0o640


@os_agnostic
def test_overrides_do_not_hide_a_non_table_section() -> None:
    with pytest.raises(DeployPermissionsError) as caught:
        deploy_permissions_from_config(_file_config(5), overrides={"user_file": "0o640"})
    assert str(caught.value) == f"{SECTION_KEY}: must be a table, got int (source: /cfg/config.toml)"


@os_agnostic
def test_empty_overrides_read_the_configuration_alone() -> None:
    config = _file_config({"user_file": "0o640"})
    assert deploy_permissions_from_config(config, overrides={}) == deploy_permissions_from_config(config)
