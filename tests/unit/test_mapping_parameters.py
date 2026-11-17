"""redact_mapping and the environment-taking constructors accept any Mapping, not only a dict.

Each call here is also a pyright-strict check: with a ``dict`` annotation on the parameter, passing a
``Config`` or a ``MappingProxyType`` is a type error, which the gate's pyright run reports for this
file. The runtime assertions show the calls do what they say.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from lib_layered_config import Config
from lib_layered_config.adapters.env.default import DefaultEnvLoader
from lib_layered_config.adapters.path_resolvers import DefaultPathResolver, PlatformContext
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, redact_mapping
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


@os_agnostic
def test_redact_mapping_takes_a_config() -> None:
    config = Config({"db": {"password": "hunter2", "port": 5432}}, {})

    assert redact_mapping(config) == {"db": {"password": REDACTED_PLACEHOLDER, "port": 5432}}


@os_agnostic
def test_redact_mapping_takes_a_read_only_mapping() -> None:
    data = MappingProxyType({"token": "abc", "name": "demo"})

    assert redact_mapping(data) == {"token": REDACTED_PLACEHOLDER, "name": "demo"}


@os_agnostic
def test_the_env_loader_takes_a_read_only_environment() -> None:
    environ = MappingProxyType({"DEMO___DB__PORT": "5432", "OTHER": "x"})

    assert DefaultEnvLoader(environ=environ).load("DEMO") == {"db": {"port": 5432}}


@os_agnostic
def test_the_resolver_takes_a_read_only_environment_override(tmp_path: Path) -> None:
    env = MappingProxyType({"XDG_CONFIG_HOME": str(tmp_path / "xdg")})

    resolver = DefaultPathResolver(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, env=env, platform="linux")

    assert resolver.env["XDG_CONFIG_HOME"] == str(tmp_path / "xdg")


@os_agnostic
def test_the_platform_context_takes_a_read_only_environment(tmp_path: Path) -> None:
    env = MappingProxyType({"HOME": str(tmp_path)})

    context = PlatformContext(vendor="Acme", app="Demo", slug="demo", cwd=tmp_path, env=env, host_file_name=None)

    assert context.env["HOME"] == str(tmp_path)
