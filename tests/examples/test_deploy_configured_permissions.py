"""Configured [lib_layered_config.default_permissions] through deploy_config, on a real filesystem."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from lib_layered_config import (
    ConfigError,
    DeployModeError,
    DeployPermissions,
    DeployPermissionsError,
    LayerModes,
    read_config,
)
from lib_layered_config.domain.deploy_mode import DeployMode, ModeKind
from lib_layered_config.domain.deploy_permissions import SECTION_KEY
from lib_layered_config.domain.permissions import modes_apply
from lib_layered_config.examples.deploy import DeployAction, DeployResult, deploy_config
from lib_layered_config.observability import TRACE_ID, bind_trace_id
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only, windows_only

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
ENV_KEY = "DEMO___LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__"
SECTION = "[lib_layered_config.default_permissions]\n"
MARK = "secretmarker"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    # The .env tests plant a file here; the application's own read_config would find it.
    monkeypatch.chdir(tmp_path)
    return home


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text("[service]\nflag = true\n", encoding="utf-8")
    return path


def _user_destination(sandbox: LayeredSandbox) -> Path:
    return sandbox.roots["user"] / "config.toml"


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777


def _deploy(source: Path, *, targets: list[str] | None = None, **kwargs: Any) -> list[DeployResult]:
    return deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets or ["user"], **kwargs)


def _break_app_layer(sandbox: LayeredSandbox) -> None:
    sandbox.write("app", "config.toml", content="[broken\n")


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


@posix_only
def test_a_mode_set_in_the_environment_is_applied(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}USER_DIRECTORY", "0o750")
    monkeypatch.setenv(f"{ENV_KEY}USER_FILE", "0o640")
    _deploy(source)
    assert _mode(_user_destination(sandbox).parent) == 0o750
    assert _mode(_user_destination(sandbox)) == 0o640


@posix_only
def test_a_mode_set_in_the_deployed_source_is_applied(sandbox: LayeredSandbox, source: Path) -> None:
    source.write_text(f'{SECTION}user_file = "0o640"\n', encoding="utf-8")
    _deploy(source)
    assert _mode(_user_destination(sandbox)) == 0o640


@posix_only
def test_each_layer_gets_its_own_configured_mode_in_one_call(sandbox: LayeredSandbox, source: Path) -> None:
    source.write_text(f'{SECTION}app_file = "0o640"\n', encoding="utf-8")
    _deploy(source, targets=["app", "user"])
    assert _mode(sandbox.roots["app"] / "config.toml") == 0o640
    assert _mode(_user_destination(sandbox)) == 0o600


@posix_only
def test_an_explicit_mode_wins_over_the_configured_one(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}USER_FILE", "0o640")
    _deploy(source, file_mode=0o600)
    assert _mode(_user_destination(sandbox)) == 0o600


@os_agnostic
def test_a_decimal_integer_in_the_environment_is_refused_and_nothing_is_written(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}USER_FILE", "444")
    if not modes_apply():
        pytest.skip("configuration is not read where modes are not applied")
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source)
    first = str(caught.value).splitlines()[0]
    assert first.startswith(
        "lib_layered_config.default_permissions.user_file: a bare integer is read as decimal (444 = 0o674)"
    )
    assert first.endswith("(source: env)")
    assert not _user_destination(sandbox).exists()


@os_agnostic
@pytest.mark.parametrize(
    ("body", "line"),
    [
        (
            f'{SECTION}enabled = "maybe"\n',
            "lib_layered_config.default_permissions.enabled: must be true or false, got str 'maybe'",
        ),
        (
            "[lib_layered_config]\ndefault_permissions = 5\n",
            "lib_layered_config.default_permissions: must be a table, got int",
        ),
        (
            f'{SECTION}app_directory = "770"\n',
            "lib_layered_config.default_permissions.app_directory: unsafe directory mode 0o770",
        ),
    ],
)
def test_an_invalid_section_is_refused_one_line_per_problem(
    sandbox: LayeredSandbox, source: Path, body: str, line: str
) -> None:
    if not modes_apply():
        pytest.skip("configuration is not read where modes are not applied")
    source.write_text(body, encoding="utf-8")
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source)
    assert str(caught.value).splitlines()[0].startswith(line)
    assert not _user_destination(sandbox).exists()


@posix_only
def test_enabled_false_leaves_modes_to_the_umask(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}ENABLED", "false")
    target_dir = _user_destination(sandbox).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o755)
    _deploy(source)
    assert _mode(target_dir) == 0o755


@posix_only
def test_an_explicit_set_permissions_true_overrides_enabled_false(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}ENABLED", "false")
    _deploy(source, set_permissions=True)
    assert _mode(_user_destination(sandbox).parent) == 0o700


@posix_only
def test_one_explicit_mode_sets_modes_even_when_enabled_is_false(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}ENABLED", "false")
    _deploy(source, dir_mode=0o750)
    assert _mode(_user_destination(sandbox).parent) == 0o750
    assert _mode(_user_destination(sandbox)) == 0o600


@os_agnostic
@pytest.mark.parametrize("modes", [{"dir_mode": 0o750}, {"file_mode": 0o640}, {"dir_mode": 0o750, "file_mode": 0o640}])
def test_an_explicit_mode_with_permission_setting_off_is_refused(
    sandbox: LayeredSandbox, source: Path, modes: dict[str, int]
) -> None:
    with pytest.raises(DeployModeError, match="set_permissions=False"):
        _deploy(source, set_permissions=False, **modes)
    assert not _user_destination(sandbox).exists()


@posix_only
def test_an_unloadable_configuration_refuses_with_the_way_through(sandbox: LayeredSandbox, source: Path) -> None:
    _break_app_layer(sandbox)
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source)
    message = str(caught.value)
    assert "the configuration could not be loaded, so the configured modes are unknown" in message
    # Both modes first: turning permission setting off is the unsafe way through for a secrets file.
    assert message.index("give both modes") < message.index("set_permissions=False")
    assert "umask" in message
    assert "--no-permissions" not in message
    assert not _user_destination(sandbox).exists()


@posix_only
@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("config.toml", f'ok = 1\nsecret = "{MARK}\n'),
        ("config.d/50-broken.json", f'{{"ok": 1,\n "secret": {MARK}}}'),
        ("config.d/50-broken.yaml", f"ok: 1\npassword: {MARK}: x\n"),
    ],
)
def test_a_broken_layer_file_is_named_without_its_content(
    sandbox: LayeredSandbox, source: Path, name: str, body: str
) -> None:
    sandbox.write("app", name, content=body)
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source)
    message = str(caught.value)
    assert name.rsplit("/", 1)[-1] in message
    assert "(line 2, column" in message
    assert all(MARK not in str(link) for link in _chain(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@posix_only
def test_an_environment_collision_is_a_refusal_not_a_crash(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO___LIB_LAYERED_CONFIG", "5")
    monkeypatch.setenv(f"{ENV_KEY}ENABLED", "false")
    with pytest.raises(DeployPermissionsError, match="could not be loaded"):
        _deploy(source)


@os_agnostic
def test_permission_setting_off_deploys_past_an_unloadable_configuration(sandbox: LayeredSandbox, source: Path) -> None:
    _break_app_layer(sandbox)
    results = _deploy(source, set_permissions=False)
    assert results[0].action == DeployAction.CREATED


@posix_only
def test_both_explicit_modes_deploy_past_an_unloadable_configuration(sandbox: LayeredSandbox, source: Path) -> None:
    _break_app_layer(sandbox)
    _deploy(source, dir_mode=0o750, file_mode=0o640)
    assert _mode(_user_destination(sandbox)) == 0o640


@os_agnostic
def test_a_broken_destination_does_not_block_its_own_force_replacement(sandbox: LayeredSandbox, source: Path) -> None:
    destination = _user_destination(sandbox)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("[broken\n", encoding="utf-8")
    results = _deploy(source, force=True)
    assert results[0].action == DeployAction.OVERWRITTEN


@posix_only
@pytest.mark.parametrize("in_dot_d", [False, True])
def test_the_file_being_replaced_does_not_decide_the_new_mode(
    sandbox: LayeredSandbox, source: Path, in_dot_d: bool
) -> None:
    old, new = f'{SECTION}app_file = "0o600"\n', f'{SECTION}app_file = "0o640"\n'
    app_root = sandbox.roots["app"]
    if in_dot_d:
        # The template's real layout: the section ships in defaultconfig.d/40-layered-config.toml.
        (source.parent / "source.d").mkdir()
        (source.parent / "source.d" / "40-layered-config.toml").write_text(new, encoding="utf-8")
        replaced = app_root / "config.d" / "40-layered-config.toml"
    else:
        source.write_text(new, encoding="utf-8")
        replaced = app_root / "config.toml"
    replaced.parent.mkdir(parents=True, exist_ok=True)
    replaced.write_text(old, encoding="utf-8")
    _deploy(source, targets=["app"], force=True)
    assert _mode(app_root / "config.toml") == 0o640
    assert _mode(replaced) == 0o640


@posix_only
def test_a_file_the_deploy_does_not_write_is_still_honoured(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("app", "config.d/99-local.toml", content=f'{SECTION}app_file = "0o640"\n')
    _deploy(source, targets=["app"])
    assert _mode(sandbox.roots["app"] / "config.toml") == 0o640


@posix_only
def test_dotenv_is_never_read_for_modes(sandbox: LayeredSandbox, source: Path, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE=0o644\n", encoding="utf-8")
    # Liveness: the application's own read finds this .env, so deploy ignoring it is a choice, not a miss.
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG).get(f"{SECTION_KEY}.user_file") == "0o644"
    _deploy(source)
    assert _mode(_user_destination(sandbox)) == 0o600


@os_agnostic
def test_a_malformed_dotenv_does_not_block_the_deploy(sandbox: LayeredSandbox, source: Path, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NOT A KEY VALUE LINE\n", encoding="utf-8")
    with pytest.raises(ConfigError):  # liveness: the application's own read does trip over it
        read_config(vendor=VENDOR, app=APP, slug=SLUG)
    assert _deploy(source)[0].action == DeployAction.CREATED


@posix_only
def test_a_platform_override_reads_that_platforms_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: Path
) -> None:
    mac = create_layered_sandbox(tmp_path / "mac", vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    mac.apply_env(monkeypatch)
    mac.write("app", "config.toml", content=f'{SECTION}user_file = "0o640"\n')
    deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"], platform="darwin")
    assert _mode(mac.roots["user"] / "config.toml") == 0o640


@posix_only
def test_the_callers_trace_id_survives_a_deploy(sandbox: LayeredSandbox, source: Path) -> None:
    bind_trace_id("caller-trace")
    try:
        _deploy(source)
        assert TRACE_ID.get() == "caller-trace"
    finally:
        bind_trace_id(None)


@posix_only
def test_a_given_permissions_object_is_used_without_reading_the_configuration(
    sandbox: LayeredSandbox, source: Path
) -> None:
    _break_app_layer(sandbox)
    defaults = DeployPermissions.defaults()
    custom = DeployPermissions(
        app=defaults.app,
        host=defaults.host,
        user=LayerModes(DeployMode(0o750, ModeKind.DIRECTORY), DeployMode(0o640, ModeKind.FILE)),
    )
    _deploy(source, permissions=custom)
    assert _mode(_user_destination(sandbox).parent) == 0o750
    assert _mode(_user_destination(sandbox)) == 0o640


@posix_only
def test_a_given_permissions_object_with_enabled_false_leaves_modes_alone(
    sandbox: LayeredSandbox, source: Path
) -> None:
    defaults = DeployPermissions.defaults()
    off = DeployPermissions(app=defaults.app, host=defaults.host, user=defaults.user, enabled=False)
    target_dir = _user_destination(sandbox).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o755)
    _deploy(source, permissions=off)
    assert _mode(target_dir) == 0o755


@posix_only
def test_a_permission_override_is_applied_over_the_configured_mode(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"{ENV_KEY}USER_FILE", "0o600")
    _deploy(source, permission_overrides={"user_directory": "0o750", "user_file": "0o640"})
    assert _mode(_user_destination(sandbox).parent) == 0o750
    assert _mode(_user_destination(sandbox)) == 0o640


@posix_only
def test_permission_overrides_keep_deploys_own_read(sandbox: LayeredSandbox, source: Path, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE=0o644\n", encoding="utf-8")
    # Liveness: the application's own read finds this .env, so a permissions= object built from that read
    # would carry 0o644 (re-review N1); the override path must not.
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG).get(f"{SECTION_KEY}.user_file") == "0o644"
    _deploy(source, permission_overrides={"user_directory": "0o750"})
    assert _mode(_user_destination(sandbox).parent) == 0o750
    assert _mode(_user_destination(sandbox)) == 0o600


@os_agnostic
@pytest.mark.parametrize("modes", [{}, {"dir_mode": 0o750, "file_mode": 0o640}], ids=["read", "both-modes"])
def test_a_bad_permission_override_is_refused_before_anything_is_written(
    sandbox: LayeredSandbox, source: Path, modes: dict[str, int]
) -> None:
    # With both modes given the settings are never read; the override is refused all the same (D15).
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source, permission_overrides={"user_file": 444}, **modes)
    (line,) = str(caught.value).splitlines()
    assert line.startswith(f"{SECTION_KEY}.user_file: a bare integer is read as decimal (444 = 0o674)")
    assert line.endswith("(source: override)")
    assert not _user_destination(sandbox).exists()


@os_agnostic
def test_a_huge_permission_override_is_refused_with_a_bounded_message_not_a_bare_value_error(
    sandbox: LayeredSandbox, source: Path
) -> None:
    """A 5000-digit override value trips CPython's int-to-str conversion limit inside
    DeployMode.from_config_value's own f-string; it must still surface a bounded
    DeployPermissionsError, never a bare ValueError."""
    huge = 10**5000
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source, permission_overrides={"user_file": huge})
    (line,) = str(caught.value).splitlines()
    assert len(line) < 400  # bounded (the fixed hint sentence dominates); never the ~5000-digit value itself
    assert line.startswith(f"{SECTION_KEY}.user_file: a bare integer is read as decimal (<int, ")
    assert line.endswith("(source: override)")
    assert not _user_destination(sandbox).exists()


@os_agnostic
def test_a_4000_digit_permission_override_is_refused_with_a_bounded_message(
    sandbox: LayeredSandbox, source: Path
) -> None:
    """4000 digits sits under CPython's default 4300-digit int-to-str conversion limit, so the
    old sys.get_int_max_str_digits()-based decision stringified it in full instead of bounding
    the message."""
    huge = 10**4000
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source, permission_overrides={"user_file": huge})
    (line,) = str(caught.value).splitlines()
    assert len(line) < 400
    assert line.startswith(f"{SECTION_KEY}.user_file: a bare integer is read as decimal (<int, ")
    assert line.endswith("(source: override)")
    assert not _user_destination(sandbox).exists()


@os_agnostic
def test_permission_overrides_with_a_permissions_object_are_refused(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(DeployPermissionsError, match=r"^permission_overrides: cannot be combined with permissions"):
        _deploy(source, permissions=DeployPermissions.defaults(), permission_overrides={"user_file": "0o640"})
    assert not _user_destination(sandbox).exists()


@posix_only
def test_a_permission_override_does_not_force_a_read_when_both_modes_are_given(
    sandbox: LayeredSandbox, source: Path
) -> None:
    _break_app_layer(sandbox)
    _deploy(source, dir_mode=0o700, file_mode=0o600, permission_overrides={"user_file": "0o640"})
    assert _mode(_user_destination(sandbox)) == 0o600


@os_agnostic
def test_an_enabled_false_override_deploys_past_an_unloadable_configuration(
    sandbox: LayeredSandbox, source: Path
) -> None:
    # enabled=False decides that no mode is set, so no configured value can change the outcome and the
    # settings are not read (D6, re-review m-d): the caller has said what set_permissions=False says.
    _break_app_layer(sandbox)
    target_dir = _user_destination(sandbox).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o755)
    results = _deploy(source, permission_overrides={"enabled": False})
    assert results[0].action == DeployAction.CREATED
    if modes_apply():
        assert _mode(target_dir) == 0o755  # left as it was, not chmodded to the user layer's 0o700


@posix_only
@pytest.mark.parametrize(
    "kwargs",
    [
        {"permission_overrides": {"enabled": True}},
        {"permission_overrides": {"enabled": False}, "dir_mode": 0o750},
        {"permission_overrides": {"enabled": False}, "set_permissions": True},
    ],
    ids=["enabled-true", "false-with-a-mode", "false-with-set-permissions-true"],
)
def test_an_override_that_leaves_modes_on_still_reads_the_configuration(
    sandbox: LayeredSandbox, source: Path, kwargs: dict[str, Any]
) -> None:
    # Liveness for the test above: the broken layer does block when modes may be set (D6, D7, D14).
    _break_app_layer(sandbox)
    with pytest.raises(DeployPermissionsError, match="could not be loaded"):
        _deploy(source, **kwargs)
    assert not _user_destination(sandbox).exists()


@windows_only
def test_windows_never_reads_the_configuration_for_modes(sandbox: LayeredSandbox, source: Path) -> None:
    _break_app_layer(sandbox)
    results = _deploy(source)
    assert results[0].action == DeployAction.CREATED


def _system_destination(sandbox: LayeredSandbox, source: Path, target: str) -> Path:
    """Deploy *source* to the app or host layer and return the file it wrote."""
    (result,) = _deploy(source, targets=[target])
    assert result.action == DeployAction.CREATED
    return result.destination


@posix_only
@pytest.mark.parametrize("target", ["app", "host"])
def test_a_user_file_does_not_decide_a_system_layer_mode(sandbox: LayeredSandbox, source: Path, target: str) -> None:
    sandbox.write("user", "config.toml", content=f'{SECTION}{target}_file = "0o640"\n')
    # Liveness: the application's own read sees the user file's value, so deploy ignoring it is the rule.
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG).get(f"{SECTION_KEY}.{target}_file") == "0o640"
    assert _mode(_system_destination(sandbox, source, target)) == 0o644


@posix_only
def test_a_user_file_does_not_hide_the_app_layers_mode(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("app", "config.d/99-local.toml", content=f'{SECTION}app_file = "0o640"\n')
    sandbox.write("user", "config.toml", content=f'{SECTION}app_file = "0o644"\n')
    assert _mode(_system_destination(sandbox, source, "app")) == 0o640


@posix_only
def test_the_environment_still_decides_a_system_layer_mode(
    sandbox: LayeredSandbox, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.write("app", "config.d/99-local.toml", content=f'{SECTION}app_file = "0o600"\n')
    monkeypatch.setenv(f"{ENV_KEY}APP_FILE", "0o640")
    assert _mode(_system_destination(sandbox, source, "app")) == 0o640


@posix_only
def test_a_user_file_still_decides_the_user_layer_mode(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("user", "config.d/99-local.toml", content=f'{SECTION}user_file = "0o640"\napp_file = "0o640"\n')
    _deploy(source)
    assert _mode(_user_destination(sandbox)) == 0o640


@posix_only
def test_a_user_file_still_decides_enabled(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("user", "config.d/99-local.toml", content=f"{SECTION}enabled = false\n")
    app_dir = sandbox.roots["app"]
    app_dir.mkdir(parents=True, exist_ok=True)
    app_dir.chmod(0o700)
    _system_destination(sandbox, source, "app")
    assert _mode(app_dir) == 0o700  # left as it was, not chmodded to the app layer's 0o755


@os_agnostic
@pytest.mark.parametrize("value", ['"770"', "444", '"0o4644"', "[1]"], ids=["unsafe", "bare-int", "setuid", "list"])
def test_a_malformed_system_mode_in_a_user_file_does_not_block_a_deploy(
    sandbox: LayeredSandbox, source: Path, value: str
) -> None:
    sandbox.write("user", "config.toml", content=f"{SECTION}app_file = {value}\nhost_directory = {value}\n")
    destination = _system_destination(sandbox, source, "app")
    if modes_apply():
        assert _mode(destination) == 0o644


@os_agnostic
def test_a_malformed_user_mode_in_a_user_file_still_blocks_a_deploy(sandbox: LayeredSandbox, source: Path) -> None:
    # Liveness for the test above: the user file is read, and its own user_* settings are still validated.
    if not modes_apply():
        pytest.skip("configuration is not read where modes are not applied")
    sandbox.write("user", "config.d/99-local.toml", content=f'{SECTION}app_file = "770"\nuser_file = "770"\n')
    with pytest.raises(DeployPermissionsError) as caught:
        _deploy(source, targets=["app"])
    assert [problem.key for problem in caught.value.problems] == [f"{SECTION_KEY}.user_file"]
    assert not (sandbox.roots["app"] / "config.toml").exists()


@posix_only
def test_an_ignored_user_file_setting_is_logged_by_name_without_its_value(
    sandbox: LayeredSandbox, source: Path, caplog: pytest.LogCaptureFixture
) -> None:
    user_file = sandbox.write("user", "config.toml", content=f'{SECTION}host_file = "0o604"\napp_file = "0o604"\n')
    caplog.set_level(logging.WARNING, logger="lib_layered_config")
    _system_destination(sandbox, source, "app")
    (record,) = [record for record in caplog.records if record.message == "deploy_setting_ignored"]
    context = record.__dict__["context"]
    assert context["layer"] == "user"
    assert Path(context["path"]).resolve() == user_file.resolve()
    assert context["keys"] == [f"{SECTION_KEY}.app_file", f"{SECTION_KEY}.host_file"]
    assert "0o604" not in repr(context)
