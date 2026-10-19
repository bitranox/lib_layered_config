"""The deploy's own read and the paths it writes, through the public API, on a real filesystem."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import (
    Config,
    LayerLoadError,
    ValidationError,
    deploy_config,
    deploy_config_paths,
    read_config,
    read_deploy_config,
)
from lib_layered_config.domain.deploy_permissions import SECTION_KEY
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable

    from lib_layered_config.examples.deploy import DeployResult

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"
SECTION = "[lib_layered_config.default_permissions]\n"
USER_FILE = f"{SECTION_KEY}.user_file"
APP_FILE = f"{SECTION_KEY}.app_file"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    home = create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)
    home.apply_env(monkeypatch)
    # The .env test plants a file here; the application's own read_config would find it.
    monkeypatch.chdir(tmp_path)
    return home


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.toml"
    path.write_text(f'{SECTION}user_file = "0o600"\n', encoding="utf-8")
    dot_d = tmp_path / "source.d"
    dot_d.mkdir()
    (dot_d / "40-shipped.toml").write_text("[shipped]\nflag = true\n", encoding="utf-8")
    (dot_d / "README.md").write_text("notes\n", encoding="utf-8")
    return path


def _reported(results: list[DeployResult]) -> frozenset[Path]:
    written: set[Path] = set()
    for result in results:
        written.add(result.destination.resolve())
        written.update(nested.destination.resolve() for nested in result.dot_d_results)
    return frozenset(written)


def _read(
    source: Path,
    *,
    skip: Iterable[str | Path] = (),
    profile: str | None = None,
    platform: str | None = None,
) -> Config:
    return read_deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, skip=skip, profile=profile, platform=platform)


@os_agnostic
@pytest.mark.parametrize("profile", [None, "staging"])
def test_the_paths_a_deploy_writes_are_the_ones_it_reports_writing(
    sandbox: LayeredSandbox, source: Path, profile: str | None
) -> None:
    targets = ["app", "host", "user"]
    predicted = deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets, profile=profile)
    results = deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=targets, profile=profile, force=True)
    assert predicted == _reported(results)
    assert len(predicted) == 9  # three layers, each its file plus the two shipped .d files


@os_agnostic
def test_the_paths_are_the_same_before_and_after_the_files_exist(sandbox: LayeredSandbox, source: Path) -> None:
    before = deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"])
    deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"])
    assert deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"]) == before


@os_agnostic
def test_an_unknown_target_is_refused_like_the_deploy_refuses_it(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(ValidationError, match="nonsense"):
        deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user", "nonsense"])


@os_agnostic
def test_a_skipped_broken_file_does_not_stop_the_read(sandbox: LayeredSandbox, source: Path) -> None:
    broken = sandbox.write("user", "config.toml", content="[broken\n")
    sandbox.write("app", "config.d/99-local.toml", content=f'{SECTION}app_file = "0o640"\n')
    config = _read(source, skip=frozenset({broken}))
    assert config.get(APP_FILE) == "0o640"
    assert config.get(USER_FILE) == "0o600"


@os_agnostic
def test_a_broken_file_not_skipped_refuses(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("user", "config.toml", content="[broken\n")
    with pytest.raises(LayerLoadError):
        _read(source)


@os_agnostic
def test_a_skip_path_matches_however_it_is_spelled(sandbox: LayeredSandbox, source: Path) -> None:
    broken = sandbox.write("user", "config.toml", content="[broken\n")
    roundabout = str(broken.parent / "detour" / ".." / broken.name)
    config = _read(source, skip=frozenset({roundabout}))
    assert config.get(USER_FILE) == "0o600"


@os_agnostic
def test_the_deploys_own_read_leaves_out_every_file_it_writes(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("user", "config.toml", content=f'{SECTION}user_file = "0o640"\n')
    sandbox.write("user", "config.d/40-shipped.toml", content="[broken\n")
    written = deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"])
    config = _read(source, skip=written)
    assert config.get(USER_FILE) == "0o600"


@os_agnostic
def test_dotenv_is_never_read(sandbox: LayeredSandbox, source: Path, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE=0o644\n", encoding="utf-8")
    # Liveness: the application's own read finds this .env, so leaving it out is a choice, not a miss.
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG).get(USER_FILE) == "0o644"
    assert _read(source).get(USER_FILE) == "0o600"


@os_agnostic
def test_a_user_file_keeps_only_its_user_modes(sandbox: LayeredSandbox, source: Path) -> None:
    sandbox.write("user", "config.toml", content=f'{SECTION}user_file = "0o640"\napp_file = "0o640"\n')
    # Liveness: the application's own read keeps the user file's app_file.
    assert read_config(vendor=VENDOR, app=APP, slug=SLUG).get(APP_FILE) == "0o640"
    config = _read(source)
    assert config.get(USER_FILE) == "0o640"
    assert config.get(APP_FILE) is None


@os_agnostic
def test_a_platform_override_reads_that_platforms_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: Path
) -> None:
    mac = create_layered_sandbox(tmp_path / "mac", vendor=VENDOR, app=APP, slug=SLUG, platform="darwin")
    mac.apply_env(monkeypatch)
    mac.write("app", "config.toml", content=f'{SECTION}app_file = "0o640"\n')
    assert _read(source, platform="darwin").get(APP_FILE) == "0o640"


@os_agnostic
def test_a_missing_source_is_refused(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    missing = tmp_path / "absent.toml"
    with pytest.raises(FileNotFoundError):
        _read(missing)
    with pytest.raises(FileNotFoundError):
        deploy_config_paths(missing, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"])


@os_agnostic
def test_an_invalid_profile_is_refused(sandbox: LayeredSandbox, source: Path) -> None:
    with pytest.raises(ValueError, match="profile"):
        _read(source, profile="../escape")
    with pytest.raises(ValueError, match="profile"):
        deploy_config_paths(source, vendor=VENDOR, app=APP, slug=SLUG, targets=["user"], profile="../escape")


@os_agnostic
@pytest.mark.parametrize("single", ["config.toml", Path("config.toml")], ids=["str", "Path"])
def test_a_single_path_given_as_skip_is_refused(sandbox: LayeredSandbox, source: Path, single: str | Path) -> None:
    # A str would be iterated as characters and skip nothing the caller meant.
    with pytest.raises(TypeError, match="skip takes an iterable of paths"):
        read_deploy_config(source, vendor=VENDOR, app=APP, slug=SLUG, skip=single)  # pyright: ignore[reportArgumentType] - the refused call under test
