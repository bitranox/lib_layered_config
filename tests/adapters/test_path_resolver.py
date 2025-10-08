"""Path resolver adapter tests exercising platform-specific discovery.

The scenarios mirror the Linux and Windows path layouts described in the system
design documents. Shared sandbox fixtures (``tests.support.layered``) keep the
setup declarative and aligned with the documented precedence rules.
"""

from __future__ import annotations

from pathlib import Path
import shutil

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from tests.support import create_layered_sandbox
from tests.support.os_markers import mac_only, posix_only, windows_only, os_agnostic


def _linux_context(tmp_path: Path):
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform="linux",
    )
    sandbox.write("app", "config.toml", content="[app]\nvalue = 1\n")
    sandbox.write("app", "config.d/10-user.toml", content="[feature]\nflag = false\n")
    sandbox.write("host", "test-host.toml", content="[host]\nvalue = 2\n")
    sandbox.write("user", "config.toml", content="[user]\nvalue = 3\n")
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform="linux",
        hostname="test-host",
    )
    return resolver, sandbox


@posix_only
def test_linux_resolver_first_app_path_points_to_config(tmp_path: Path) -> None:
    resolver, _ = _linux_context(tmp_path)
    first_path = list(resolver.app())[0]
    assert first_path.endswith("config.toml")


@posix_only
def test_linux_resolver_includes_override_directory(tmp_path: Path) -> None:
    resolver, _ = _linux_context(tmp_path)
    expectation = any(path.replace("\\", "/").endswith("config.d/10-user.toml") for path in resolver.app())
    assert expectation is True


@posix_only
def test_linux_resolver_host_paths_include_hostname(tmp_path: Path) -> None:
    resolver, _ = _linux_context(tmp_path)
    host_paths = [path.replace("\\", "/") for path in resolver.host()]
    assert host_paths[0].endswith("hosts/test-host.toml")


@posix_only
def test_linux_resolver_user_path_points_to_config(tmp_path: Path) -> None:
    resolver, _ = _linux_context(tmp_path)
    user_paths = list(resolver.user())
    assert user_paths[0].endswith("config.toml")


@posix_only
def test_linux_resolver_dotenv_defaults_to_empty(tmp_path: Path) -> None:
    resolver, _ = _linux_context(tmp_path)
    assert list(resolver.dotenv()) == []


def _mac_context(tmp_path: Path):
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform="darwin",
    )
    sandbox.write("app", "config.toml", content="[app]\nvalue = 1\n")
    sandbox.write("host", "mac-host.toml", content="[host]\nvalue = 2\n")
    sandbox.write("user", "config.toml", content="[user]\nvalue = 3\n")
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform="darwin",
        hostname="mac-host",
    )
    return resolver, sandbox


@mac_only
def test_macos_resolver_app_path_uses_application_support(tmp_path: Path) -> None:
    resolver, _ = _mac_context(tmp_path)
    first_path = Path(list(resolver.app())[0]).as_posix()
    assert first_path.endswith("Library/Application Support/Acme/ConfigKit/config.toml")


@mac_only
def test_macos_resolver_host_path_uses_hosts_directory(tmp_path: Path) -> None:
    resolver, _ = _mac_context(tmp_path)
    host_path = Path(list(resolver.host())[0]).as_posix()
    assert host_path.endswith("Library/Application Support/Acme/ConfigKit/hosts/mac-host.toml")


@mac_only
def test_macos_resolver_user_path_uses_home_library(tmp_path: Path) -> None:
    resolver, _ = _mac_context(tmp_path)
    user_path = Path(list(resolver.user())[0]).as_posix()
    assert user_path.endswith("HomeLibrary/Application Support/Acme/ConfigKit/config.toml")


@mac_only
def test_macos_resolver_dotenv_defaults_to_empty(tmp_path: Path) -> None:
    resolver, _ = _mac_context(tmp_path)
    assert list(resolver.dotenv()) == []


@posix_only
def test_dotenv_extra_path_includes_user_env(tmp_path: Path) -> None:
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform="linux",
    )
    sandbox.write("user", ".env", content="KEY=value\n")
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        env=sandbox.env,
        platform="linux",
    )
    paths = list(resolver.dotenv())
    assert str(sandbox.roots["user"] / ".env") in paths


def _windows_context(tmp_path: Path):
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform="win32",
    )
    sandbox.write("app", "config.toml", content="[windows]\nvalue=1\n")
    sandbox.write("user", "config.toml", content="[user]\nvalue=3\n")
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        env=sandbox.env,
        platform="win32",
        hostname="HOST",
    )
    return resolver, sandbox


class _RepeatingDirectory:
    """Return the same candidate twice to exercise duplicate guards."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __truediv__(self, child: str) -> Path:
        return self._path / child

    @property
    def parents(self):  # type: ignore[override]
        return [self]


def _make_resolver(
    tmp_path: Path,
    *,
    platform: str,
    hostname: str = "example-host",
    env_override: dict[str, str] | None = None,
) -> tuple[DefaultPathResolver, dict[str, Path]]:
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform=platform,
    )
    env = {**sandbox.env, **(env_override or {})}
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        cwd=sandbox.start_dir,
        env=env,
        platform=platform,
        hostname=hostname,
    )
    return resolver, sandbox.roots


@windows_only
def test_windows_resolver_app_path_points_to_programdata(tmp_path: Path) -> None:
    resolver, _ = _windows_context(tmp_path)
    app_paths = list(resolver.app())
    assert app_paths[0].endswith("config.toml")


@windows_only
def test_windows_resolver_host_path_uses_hosts_folder(tmp_path: Path) -> None:
    resolver, sandbox = _windows_context(tmp_path)
    sandbox.write("host", "HOST.toml", content="[host]\nvalue=2\n")
    host_paths = list(resolver.host())
    assert any(Path(path).as_posix().endswith("hosts/HOST.toml") for path in host_paths)


@windows_only
def test_windows_resolver_user_paths_cover_roaming_appdata(tmp_path: Path) -> None:
    resolver, _ = _windows_context(tmp_path)
    user_paths = list(resolver.user())
    expectation = any("AppData" in path for path in user_paths)
    assert expectation is True


@os_agnostic
def test_platform_paths_returns_empty_for_unknown_platform(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, platform="plan9")
    assert resolver._platform_paths("app") == []


@os_agnostic
def test_platform_dotenv_path_returns_none_for_unknown_platform(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, platform="plan9")
    assert resolver._platform_dotenv_path() is None


@windows_only
def test_windows_user_paths_fall_back_to_localappdata(tmp_path: Path) -> None:
    env = {
        "ProgramData": str(tmp_path / "ProgramData"),
        "APPDATA": str(tmp_path / "Roaming"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    local_base = Path(env["LOCALAPPDATA"]) / "Acme" / "Demo"
    local_base.mkdir(parents=True, exist_ok=True)
    target = local_base / "config.toml"
    target.write_text("[service]\nvalue=1\n", encoding="utf-8")
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", env=env, platform="win32", hostname="HOST")
    user_paths = list(resolver._windows_user_paths())
    assert str(target) in user_paths


@os_agnostic
def test_mac_paths_fall_silent_for_unknown_layer(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="darwin")
    assert list(resolver._mac_paths("shadow")) == []


@os_agnostic
def test_mac_host_paths_ignore_missing_candidates(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="darwin", hostname="mac-host")
    host_paths = list(resolver._mac_host_paths())
    assert host_paths == []


@os_agnostic
def test_mac_host_paths_return_file_when_present(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="darwin", hostname="mac-host")
    target = roots["host"] / "mac-host.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[host]\nvalue=2\n", encoding="utf-8")
    host_paths = list(resolver._mac_host_paths())
    assert host_paths == [str(target)]


@os_agnostic
def test_mac_user_paths_collect_config_directory(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="darwin")
    config = roots["user"] / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=3\n", encoding="utf-8")
    user_paths = list(resolver._mac_user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_windows_paths_fall_silent_for_unknown_layer(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="win32")
    assert list(resolver._windows_paths("shadow")) == []


@os_agnostic
def test_platform_paths_route_to_mac_helpers(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="darwin")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    paths = resolver._platform_paths("app")
    assert str(target) in paths


@os_agnostic
def test_platform_paths_route_to_windows_helpers(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[windows]\nvalue=1\n", encoding="utf-8")
    paths = resolver._platform_paths("app")
    assert str(target) in paths


@os_agnostic
def test_mac_app_paths_collect_layer_entries(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="darwin")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    app_paths = list(resolver._mac_app_paths())
    assert app_paths == [str(target)]


@os_agnostic
def test_windows_app_paths_collect_layer_entries(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    app_paths = list(resolver._windows_app_paths())
    assert app_paths == [str(target)]


@os_agnostic
def test_windows_host_paths_ignore_missing_candidates(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="win32", hostname="HOST")
    assert list(resolver._windows_host_paths()) == []


@os_agnostic
def test_windows_host_paths_return_file_when_present(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32", hostname="HOST")
    target = roots["app"] / "hosts" / "HOST.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[host]\nvalue=2\n", encoding="utf-8")
    host_paths = list(resolver._windows_host_paths())
    assert [Path(entry) for entry in host_paths] == [target]


@os_agnostic
def test_windows_user_paths_fall_back_to_local_when_roaming_absent(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32", hostname="HOST")
    roaming = roots["user"]
    if roaming.exists():
        shutil.rmtree(roaming)
    local_root = Path(resolver.env["LIB_LAYERED_CONFIG_LOCALAPPDATA"])
    config = local_root / resolver.vendor / resolver.application / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=7\n", encoding="utf-8")
    user_paths = list(resolver._windows_user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_windows_user_paths_return_roaming_when_present(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32", hostname="HOST")
    roaming = roots["user"]
    config = roaming / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=9\n", encoding="utf-8")
    user_paths = list(resolver._windows_user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_program_data_root_honours_environment_override(tmp_path: Path) -> None:
    override = tmp_path / "CustomProgramData"
    resolver, _ = _make_resolver(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_PROGRAMDATA": str(override)},
    )
    assert resolver._program_data_root() == override


@os_agnostic
def test_appdata_root_prefers_explicit_override(tmp_path: Path) -> None:
    override = tmp_path / "Roaming"
    resolver, _ = _make_resolver(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_APPDATA": str(override)},
    )
    assert resolver._appdata_root() == override


@os_agnostic
def test_localappdata_root_prefers_explicit_override(tmp_path: Path) -> None:
    override = tmp_path / "Local"
    resolver, _ = _make_resolver(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_LOCALAPPDATA": str(override)},
    )
    assert resolver._localappdata_root() == override


@os_agnostic
def test_platform_dotenv_path_returns_linux_candidate(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="linux")
    expected = Path(resolver._platform_dotenv_path())
    assert expected == Path(resolver.env["XDG_CONFIG_HOME"]) / resolver.slug / ".env"


@os_agnostic
def test_platform_dotenv_path_returns_mac_candidate(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="darwin")
    expected = Path(resolver._platform_dotenv_path())
    assert expected.as_posix().endswith("Application Support/Acme/ConfigKit/.env")


@os_agnostic
def test_platform_dotenv_path_returns_windows_candidate(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="win32")
    expected = Path(resolver._platform_dotenv_path())
    assert expected.as_posix().endswith("AppData/Roaming/Acme/ConfigKit/.env")


@os_agnostic
def test_dotenv_paths_append_platform_file_when_present(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="linux")
    fallback = Path(resolver.env["XDG_CONFIG_HOME"]) / resolver.slug / ".env"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text("KEY=value\n", encoding="utf-8")
    collected = {Path(path).as_posix() for path in resolver.dotenv()}
    assert fallback.as_posix() in collected


@os_agnostic
def test_project_dotenv_paths_skip_duplicate_candidates(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="linux")
    duplicate = _RepeatingDirectory(tmp_path)
    resolver.cwd = duplicate  # type: ignore[assignment]
    paths = list(resolver._project_dotenv_paths())
    assert paths == []


@windows_only
def test_windows_user_paths_use_localappdata_when_roaming_empty(tmp_path: Path) -> None:
    env = {
        "ProgramData": str(tmp_path / "ProgramData"),
        "APPDATA": str(tmp_path / "Roaming"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    roaming_base = Path(env["APPDATA"]) / "Acme" / "Demo"
    roaming_base.mkdir(parents=True, exist_ok=True)

    local_base = Path(env["LOCALAPPDATA"]) / "Acme" / "Demo"
    local_base.mkdir(parents=True, exist_ok=True)
    target = local_base / "config.toml"
    target.write_text("[service]\nvalue=2\n", encoding="utf-8")

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        env=env,
        platform="win32",
        hostname="HOST",
    )

    user_paths = list(resolver.user())
    assert str(target) in user_paths


@windows_only
def test_windows_user_paths_empty_when_no_user_directories(tmp_path: Path) -> None:
    env = {
        "ProgramData": str(tmp_path / "ProgramData"),
        "APPDATA": str(tmp_path / "Roaming"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        env=env,
        platform="win32",
        hostname="HOST",
    )

    assert list(resolver.user()) == []


@os_agnostic
def test_collect_layer_discards_unknown_extensions(tmp_path: Path) -> None:
    base = tmp_path / "layer"
    base.mkdir()
    (base / "config.d").mkdir()
    (base / "config.d" / "10-extra.txt").write_text("ignored", encoding="utf-8")
    from lib_layered_config.adapters.path_resolvers.default import _collect_layer

    assert list(_collect_layer(base)) == []
