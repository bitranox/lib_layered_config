"""Adapter contract tests for the default ports implementation.

Purpose
-------
Verify the default adapters continue to satisfy the application-layer ports
defined in ``src/lib_layered_config/application/ports.py``. This is part of the
contract-testing strategy documented in ``docs/systemdesign/module_reference.md``
so that dependency inversion remains enforceable through automated tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib_layered_config.application import ports
from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader, default_env_prefix
from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic


@pytest.fixture()
def sandbox(tmp_path: Path):
    return create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")


@pytest.fixture()
def resolver_context(sandbox):
    sandbox.write("app", "config.toml", content="[service]\nvalue=1\n")
    sandbox.write("host", "contract-host.toml", content="[service]\nvalue=2\n")
    sandbox.write("user", "config.toml", content="[service]\nvalue=3\n")
    resolver = DefaultPathResolver(
        vendor=sandbox.vendor,
        app=sandbox.app,
        slug=sandbox.slug,
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform=sandbox.platform,
        hostname="contract-host",
    )
    return resolver, sandbox


@os_agnostic
def test_default_path_resolver_implements_protocol(resolver_context) -> None:
    resolver, _ = resolver_context
    assert isinstance(resolver, ports.PathResolver)


@os_agnostic
def test_default_path_resolver_app_paths_are_strings(resolver_context) -> None:
    resolver, _ = resolver_context
    assert all(isinstance(candidate, str) for candidate in resolver.app())


@os_agnostic
def test_default_path_resolver_host_paths_include_hostname(resolver_context) -> None:
    resolver, _ = resolver_context
    assert all("contract-host" in candidate for candidate in resolver.host())


@os_agnostic
def test_default_path_resolver_user_paths_reference_slug_or_app(resolver_context) -> None:
    resolver, sandbox = resolver_context
    expectation = all(any(token in candidate for token in (sandbox.slug, sandbox.app)) for candidate in resolver.user())
    assert expectation is True


@os_agnostic
def test_default_path_resolver_dotenv_iteration_is_listable(resolver_context) -> None:
    resolver, _ = resolver_context
    assert isinstance(list(resolver.dotenv()), list)


def _env_loader_context() -> tuple[DefaultEnvLoader, str]:
    prefix = default_env_prefix("demo")
    environ = {
        f"{prefix}SERVICE__ENABLED": "true",
        f"{prefix}SERVICE__RETRIES": "3",
        "IRRELEVANT": "ignored",
    }
    return DefaultEnvLoader(environ=environ), prefix


@os_agnostic
def test_default_env_loader_implements_protocol() -> None:
    loader, _ = _env_loader_context()
    assert isinstance(loader, ports.EnvLoader)


@os_agnostic
def test_default_env_loader_coerces_boolean_values() -> None:
    loader, prefix = _env_loader_context()
    payload = loader.load(prefix)
    assert payload["service"]["enabled"] is True


@os_agnostic
def test_default_env_loader_coerces_integer_values() -> None:
    loader, prefix = _env_loader_context()
    payload = loader.load(prefix)
    assert payload["service"]["retries"] == 3


@os_agnostic
def test_default_dotenv_loader_implements_protocol(sandbox) -> None:
    sandbox.write("user", ".env", content="SERVICE__TIMEOUT=15\n")
    loader = DefaultDotEnvLoader()
    assert isinstance(loader, ports.DotEnvLoader)


@os_agnostic
def test_default_dotenv_loader_reads_first_file(sandbox) -> None:
    sandbox.write("user", ".env", content="SERVICE__TIMEOUT=15\n")
    payload = DefaultDotEnvLoader().load(str(sandbox.roots["user"]))
    assert payload["service"]["timeout"] == "15"


STRUCTURED_LOADERS = [TOMLFileLoader, JSONFileLoader]
if structured_module.yaml is not None:
    STRUCTURED_LOADERS.append(YAMLFileLoader)


def _write_sample(path: Path, loader_cls) -> None:
    if loader_cls is TOMLFileLoader:
        path.write_text("[service]\nvalue = 1\n", encoding="utf-8")
    elif loader_cls is JSONFileLoader:
        path.write_text('{"service": {"value": 1}}', encoding="utf-8")
    else:
        path.write_text("service:\n  value: 1\n", encoding="utf-8")


@os_agnostic
@pytest.mark.parametrize("loader_cls", STRUCTURED_LOADERS)
def test_structured_loader_implements_protocol(tmp_path: Path, loader_cls) -> None:
    loader = loader_cls()
    assert isinstance(loader, ports.FileLoader)


@os_agnostic
@pytest.mark.parametrize("loader_cls", STRUCTURED_LOADERS)
def test_structured_loader_decodes_value(tmp_path: Path, loader_cls) -> None:
    loader = loader_cls()
    if loader_cls is TOMLFileLoader:
        path = tmp_path / "config.toml"
    elif loader_cls is JSONFileLoader:
        path = tmp_path / "config.json"
    else:
        path = tmp_path / "config.yaml"
    _write_sample(path, loader_cls)
    data = loader.load(str(path))
    assert data["service"]["value"] == 1
