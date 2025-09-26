"""Path resolver adapter tests exercising platform-specific discovery.

The scenarios mirror the Linux and Windows path layouts described in the system
design documents. Shared sandbox fixtures (``tests.support.layered``) keep the
setup declarative and aligned with the documented precedence rules.
"""

from __future__ import annotations

from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from tests.support import create_layered_sandbox


def test_linux_path_resolver(tmp_path) -> None:
    """Linux resolver should enumerate app/host/user paths exactly as documented."""

    slug = "config-kit"
    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug=slug,
        platform="linux",
    )

    sandbox.write("app", "config.toml", content="[app]\nvalue = 1\n")
    sandbox.write("app", "config.d/10-user.toml", content="[feature]\nflag = false\n")
    sandbox.write("host", "test-host.toml", content="[host]\nvalue = 2\n")
    sandbox.write("user", "config.toml", content="[user]\nvalue = 3\n")

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug=slug,
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform="linux",
        hostname="test-host",
    )

    app_paths = list(resolver.app())
    assert app_paths[0].endswith("config.toml")
    assert any(path.replace("\\", "/").endswith("config.d/10-user.toml") for path in app_paths)

    host_paths = [path.replace("\\", "/") for path in resolver.host()]
    assert host_paths and host_paths[0].endswith("hosts/test-host.toml")

    user_paths = list(resolver.user())
    assert user_paths and user_paths[0].endswith("config.toml")

    dotenv_paths = list(resolver.dotenv())
    assert dotenv_paths == []


def test_dotenv_extra_path(tmp_path) -> None:
    """Dotenv search should include resolver-provided extras."""

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
    dotenv_paths = list(resolver.dotenv())
    assert str(sandbox.roots["user"] / ".env") in dotenv_paths


def test_windows_path_resolver(tmp_path) -> None:
    """Windows resolver should produce ProgramData/AppData candidates with correct suffixes."""

    sandbox = create_layered_sandbox(
        tmp_path,
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        platform="win32",
    )

    sandbox.write("app", "config.toml", content="[windows]\nvalue=1\n")

    resolver = DefaultPathResolver(
        vendor="Acme",
        app="ConfigKit",
        slug="config-kit",
        env=sandbox.env,
        platform="win32",
        hostname="HOST",
    )

    app_paths = list(resolver.app())
    assert app_paths and app_paths[0].endswith("config.toml")
