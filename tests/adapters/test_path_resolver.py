"""Path resolver adapter tests exercising platform-specific discovery.

The scenarios mirror the Linux and Windows path layouts described in the system
design documents. Shared sandbox fixtures (``tests.support.layered``) keep the
setup declarative and aligned with the documented precedence rules.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from lib_layered_config.adapters.path_resolvers import (
    DefaultPathResolver,
    LinuxStrategy,
    MacOSStrategy,
    PlatformContext,
    WindowsStrategy,
    collect_layer,
)
from lib_layered_config.adapters.path_resolvers._dotenv import DotenvPathFinder
from tests.support import create_layered_sandbox
from tests.support.os_markers import mac_only, os_agnostic, posix_only, windows_only


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
def test_linux_resolver_yields_config_toml_when_config_d_exists(tmp_path: Path) -> None:
    """Resolver yields config.toml when config.d directory exists (for .d expansion)."""
    resolver, _ = _linux_context(tmp_path)
    app_paths = list(resolver.app())
    # config.toml is yielded because config.d exists; actual .d expansion happens in _layers
    assert len(app_paths) == 1
    assert app_paths[0].endswith("config.toml")


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


def _make_context(
    tmp_path: Path,
    *,
    platform: str,
    hostname: str = "example-host",
    env_override: dict[str, str] | None = None,
) -> tuple[PlatformContext, dict[str, Path]]:
    """Create a PlatformContext and sandbox roots for strategy testing."""
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform=platform,
    )
    env = {**sandbox.env, **(env_override or {})}
    ctx = PlatformContext(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        cwd=sandbox.start_dir,
        env=env,
        hostname=hostname,
    )
    return ctx, sandbox.roots


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
    assert resolver._iter_layer("app") == []


@os_agnostic
def test_platform_dotenv_path_returns_none_for_unknown_platform(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, platform="plan9")
    assert resolver._dotenv_finder._platform_path() is None


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
    ctx = PlatformContext(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, env=env, hostname="HOST")
    strategy = WindowsStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert str(target) in user_paths


@os_agnostic
def test_mac_paths_fall_silent_for_unknown_layer(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="darwin")
    # Test that unknown layers return empty via the resolver's internal dispatch
    assert resolver._iter_layer("shadow") == []


@os_agnostic
def test_mac_host_paths_ignore_missing_candidates(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="darwin", hostname="mac-host")
    strategy = MacOSStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert host_paths == []


@os_agnostic
def test_mac_host_paths_return_file_when_present(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="darwin", hostname="mac-host")
    target = roots["host"] / "mac-host.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[host]\nvalue=2\n", encoding="utf-8")
    strategy = MacOSStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert host_paths == [str(target)]


@os_agnostic
def test_mac_user_paths_collect_config_directory(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="darwin")
    config = roots["user"] / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=3\n", encoding="utf-8")
    strategy = MacOSStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_windows_paths_fall_silent_for_unknown_layer(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="win32")
    # Test that unknown layers return empty via the resolver's internal dispatch
    assert resolver._iter_layer("shadow") == []


@os_agnostic
def test_platform_paths_route_to_mac_helpers(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="darwin")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    paths = resolver.app()
    assert str(target) in paths


@os_agnostic
def test_platform_paths_route_to_windows_helpers(tmp_path: Path) -> None:
    resolver, roots = _make_resolver(tmp_path, platform="win32")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[windows]\nvalue=1\n", encoding="utf-8")
    paths = resolver.app()
    assert str(target) in paths


@os_agnostic
def test_mac_app_paths_collect_layer_entries(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="darwin")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    strategy = MacOSStrategy(ctx)
    app_paths = list(strategy.app_paths())
    assert app_paths == [str(target)]


@os_agnostic
def test_windows_app_paths_collect_layer_entries(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="win32")
    target = roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[app]\nvalue=1\n", encoding="utf-8")
    strategy = WindowsStrategy(ctx)
    app_paths = list(strategy.app_paths())
    assert app_paths == [str(target)]


@os_agnostic
def test_windows_host_paths_ignore_missing_candidates(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="win32", hostname="HOST")
    strategy = WindowsStrategy(ctx)
    assert list(strategy.host_paths()) == []


@os_agnostic
def test_windows_host_paths_return_file_when_present(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="win32", hostname="HOST")
    target = roots["app"] / "hosts" / "HOST.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[host]\nvalue=2\n", encoding="utf-8")
    strategy = WindowsStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert [Path(entry) for entry in host_paths] == [target]


@os_agnostic
def test_windows_user_paths_fall_back_to_local_when_roaming_absent(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="win32", hostname="HOST")
    roaming = roots["user"]
    if roaming.exists():
        shutil.rmtree(roaming)
    local_root = Path(ctx.env["LIB_LAYERED_CONFIG_LOCALAPPDATA"])
    config = local_root / ctx.vendor / ctx.app / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=7\n", encoding="utf-8")
    strategy = WindowsStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_windows_user_paths_return_roaming_when_present(tmp_path: Path) -> None:
    ctx, roots = _make_context(tmp_path, platform="win32", hostname="HOST")
    roaming = roots["user"]
    config = roaming / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[user]\nvalue=9\n", encoding="utf-8")
    strategy = WindowsStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert user_paths == [str(config)]


@os_agnostic
def test_program_data_root_honours_environment_override(tmp_path: Path) -> None:
    override = tmp_path / "CustomProgramData"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_PROGRAMDATA": str(override)},
    )
    strategy = WindowsStrategy(ctx)
    assert strategy._program_data_root() == override


@os_agnostic
def test_appdata_root_prefers_explicit_override(tmp_path: Path) -> None:
    override = tmp_path / "Roaming"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_APPDATA": str(override)},
    )
    strategy = WindowsStrategy(ctx)
    assert strategy._appdata_root() == override


@os_agnostic
def test_localappdata_root_prefers_explicit_override(tmp_path: Path) -> None:
    override = tmp_path / "Local"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_LOCALAPPDATA": str(override)},
    )
    strategy = WindowsStrategy(ctx)
    assert strategy._localappdata_root() == override


@os_agnostic
def test_platform_dotenv_path_returns_linux_candidate(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="linux")
    strategy = LinuxStrategy(ctx)
    expected = strategy.dotenv_path()
    assert expected == Path(ctx.env["XDG_CONFIG_HOME"]) / ctx.slug / ".env"


@os_agnostic
def test_platform_dotenv_path_returns_mac_candidate(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="darwin")
    strategy = MacOSStrategy(ctx)
    expected = strategy.dotenv_path()
    assert expected.as_posix().endswith("Application Support/Acme/ConfigKit/.env")


@os_agnostic
def test_platform_dotenv_path_returns_windows_candidate(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="win32")
    strategy = WindowsStrategy(ctx)
    expected = strategy.dotenv_path()
    assert expected.as_posix().endswith("AppData/Roaming/Acme/ConfigKit/.env")


@os_agnostic
def test_dotenv_paths_append_platform_file_when_present(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(tmp_path, platform="linux")
    fallback = Path(resolver.env["XDG_CONFIG_HOME"]) / resolver.slug / ".env"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text("KEY=value\n", encoding="utf-8")
    collected = {Path(path).as_posix() for path in resolver.dotenv()}
    assert fallback.as_posix() in collected


@os_agnostic
def test_project_dotenv_paths_skip_duplicate_candidates(tmp_path: Path) -> None:
    ctx, _ = _make_context(tmp_path, platform="linux")
    strategy = LinuxStrategy(ctx)
    finder = DotenvPathFinder(tmp_path, strategy)
    duplicate = _RepeatingDirectory(tmp_path)
    finder.cwd = duplicate  # type: ignore[assignment]
    paths = list(finder._project_paths())
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


# ---------------------------------------------------------------------------
# UNC path tests (Windows network paths)
# ---------------------------------------------------------------------------


@os_agnostic
def test_windows_unc_app_paths_resolve_from_network_share(tmp_path: Path) -> None:
    """UNC network paths resolve correctly for Windows app layer."""
    unc_root = "//server/share"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_PROGRAMDATA": unc_root},
    )
    strategy = WindowsStrategy(ctx)
    # Verify the path construction includes the UNC root
    program_data = strategy._program_data_root()
    assert program_data == Path(unc_root)
    assert program_data.as_posix().startswith("//server/share")
    # Verify app_paths() can be called without error (paths may not exist)
    list(strategy.app_paths())


@os_agnostic
def test_windows_unc_user_paths_resolve_from_network_share(tmp_path: Path) -> None:
    """UNC network paths resolve correctly for Windows user layer."""
    unc_root = "//fileserver/users"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_APPDATA": unc_root},
    )
    strategy = WindowsStrategy(ctx)
    appdata = strategy._appdata_root()
    assert appdata == Path(unc_root)
    assert appdata.as_posix().startswith("//fileserver/users")


@os_agnostic
def test_windows_unc_localappdata_resolves_from_network_share(tmp_path: Path) -> None:
    """UNC network paths resolve correctly for Windows LocalAppData fallback."""
    unc_root = "//nas/local"
    ctx, _ = _make_context(
        tmp_path,
        platform="win32",
        env_override={"LIB_LAYERED_CONFIG_LOCALAPPDATA": unc_root},
    )
    strategy = WindowsStrategy(ctx)
    localappdata = strategy._localappdata_root()
    assert localappdata == Path(unc_root)
    assert localappdata.as_posix().startswith("//nas/local")


@os_agnostic
def test_pathlib_preserves_unc_path_format() -> None:
    """Verify pathlib.Path preserves UNC path format for cross-platform compatibility."""
    unc_path = Path("//server/share/config")
    # Path should preserve the UNC format
    assert unc_path.as_posix() == "//server/share/config"
    # Path operations should work correctly
    child = unc_path / "vendor" / "app" / "config.toml"
    assert child.as_posix() == "//server/share/config/vendor/app/config.toml"


@os_agnostic
def test_collect_layer_yields_config_toml_when_config_d_exists(tmp_path: Path) -> None:
    """collect_layer yields config.toml when config.d exists (filtering happens in expand_dot_d)."""
    base = tmp_path / "layer"
    base.mkdir()
    (base / "config.d").mkdir()
    (base / "config.d" / "10-extra.txt").write_text("ignored", encoding="utf-8")

    # config.toml is yielded because config.d exists; filtering of .txt happens in expand_dot_d
    paths = list(collect_layer(base))
    assert len(paths) == 1
    assert paths[0].endswith("config.toml")


# ---------------------------------------------------------------------------
# Profile path tests
# ---------------------------------------------------------------------------


def _make_context_with_profile(
    tmp_path: Path,
    *,
    platform: str,
    profile: str | None = None,
    hostname: str = "example-host",
) -> tuple[PlatformContext, dict[str, Path]]:
    """Create a PlatformContext with profile and sandbox roots for strategy testing."""
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform=platform,
    )
    ctx = PlatformContext(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        cwd=sandbox.start_dir,
        env=sandbox.env,
        hostname=hostname,
        profile=profile,
    )
    return ctx, sandbox.roots


@os_agnostic
def test_linux_profile_app_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="linux", profile="test")
    # Create config in profile path
    profile_dir = roots["app"] / "profile" / "test"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[profile]\nenv = 'test'\n", encoding="utf-8")

    strategy = LinuxStrategy(ctx)
    app_paths = list(strategy.app_paths())
    assert str(config) in app_paths


@os_agnostic
def test_linux_profile_host_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="linux", profile="staging", hostname="test-host")
    # Create host config in profile path
    profile_dir = roots["app"] / "profile" / "staging" / "hosts"
    profile_dir.mkdir(parents=True, exist_ok=True)
    host_config = profile_dir / "test-host.toml"
    host_config.write_text("[host]\nenv = 'staging'\n", encoding="utf-8")

    strategy = LinuxStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert str(host_config) in host_paths


@os_agnostic
def test_linux_profile_user_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="linux", profile="prod")
    # Create user config in profile path
    profile_dir = roots["user"] / "profile" / "prod"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[user]\nenv = 'prod'\n", encoding="utf-8")

    strategy = LinuxStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert str(config) in user_paths


@os_agnostic
def test_linux_profile_dotenv_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, _ = _make_context_with_profile(tmp_path, platform="linux", profile="dev")
    strategy = LinuxStrategy(ctx)
    dotenv = strategy.dotenv_path()
    assert dotenv is not None
    assert "profile/dev/.env" in dotenv.as_posix()


@os_agnostic
def test_linux_no_profile_paths_unchanged(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="linux", profile=None)
    # Create config in non-profile path
    config = roots["app"] / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[app]\nvalue = 1\n", encoding="utf-8")

    strategy = LinuxStrategy(ctx)
    app_paths = list(strategy.app_paths())
    # Without profile, the config.toml should be directly in the slug dir, not in profile/<name>/
    assert str(config) in app_paths
    # Verify the config path ends with /<slug>/config.toml (not profile/<name>/config.toml)
    assert str(config).replace("\\", "/").endswith(f"/{ctx.slug}/config.toml")


@os_agnostic
def test_macos_profile_app_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="darwin", profile="test")
    # Create config in profile path
    profile_dir = roots["app"] / "profile" / "test"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[profile]\nenv = 'test'\n", encoding="utf-8")

    strategy = MacOSStrategy(ctx)
    app_paths = list(strategy.app_paths())
    assert str(config) in app_paths


@os_agnostic
def test_macos_profile_host_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="darwin", profile="staging", hostname="mac-host")
    # Create host config in profile path
    profile_dir = roots["app"] / "profile" / "staging" / "hosts"
    profile_dir.mkdir(parents=True, exist_ok=True)
    host_config = profile_dir / "mac-host.toml"
    host_config.write_text("[host]\nenv = 'staging'\n", encoding="utf-8")

    strategy = MacOSStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert str(host_config) in host_paths


@os_agnostic
def test_macos_profile_user_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="darwin", profile="prod")
    # Create user config in profile path
    profile_dir = roots["user"] / "profile" / "prod"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[user]\nenv = 'prod'\n", encoding="utf-8")

    strategy = MacOSStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert str(config) in user_paths


@os_agnostic
def test_macos_profile_dotenv_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, _ = _make_context_with_profile(tmp_path, platform="darwin", profile="dev")
    strategy = MacOSStrategy(ctx)
    dotenv = strategy.dotenv_path()
    assert dotenv is not None
    assert "profile/dev/.env" in dotenv.as_posix()


@os_agnostic
def test_windows_profile_app_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="win32", profile="test")
    # Create config in profile path
    profile_dir = roots["app"] / "profile" / "test"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[profile]\nenv = 'test'\n", encoding="utf-8")

    strategy = WindowsStrategy(ctx)
    app_paths = list(strategy.app_paths())
    assert str(config) in app_paths


@os_agnostic
def test_windows_profile_host_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="win32", profile="staging", hostname="WIN-HOST")
    # Create host config in profile path
    profile_dir = roots["app"] / "profile" / "staging" / "hosts"
    profile_dir.mkdir(parents=True, exist_ok=True)
    host_config = profile_dir / "WIN-HOST.toml"
    host_config.write_text("[host]\nenv = 'staging'\n", encoding="utf-8")

    strategy = WindowsStrategy(ctx)
    host_paths = list(strategy.host_paths())
    assert str(host_config) in host_paths


@os_agnostic
def test_windows_profile_user_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, roots = _make_context_with_profile(tmp_path, platform="win32", profile="prod")
    # Create user config in profile path
    profile_dir = roots["user"] / "profile" / "prod"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "config.toml"
    config.write_text("[user]\nenv = 'prod'\n", encoding="utf-8")

    strategy = WindowsStrategy(ctx)
    user_paths = list(strategy.user_paths())
    assert str(config) in user_paths


@os_agnostic
def test_windows_profile_dotenv_path_includes_profile_segment(tmp_path: Path) -> None:
    ctx, _ = _make_context_with_profile(tmp_path, platform="win32", profile="dev")
    strategy = WindowsStrategy(ctx)
    dotenv = strategy.dotenv_path()
    assert dotenv is not None
    assert "profile/dev/.env" in dotenv.as_posix()


@os_agnostic
def test_resolver_with_profile_creates_correct_context(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        profile="test",
        cwd=tmp_path,
        platform="linux",
    )
    assert resolver.profile == "test"
    assert resolver._ctx.profile == "test"


@os_agnostic
def test_resolver_without_profile_has_none_context(tmp_path: Path) -> None:
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo",
        cwd=tmp_path,
        platform="linux",
    )
    assert resolver.profile is None
    assert resolver._ctx.profile is None
