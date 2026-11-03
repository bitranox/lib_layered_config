"""Adapter contract tests for the default ports implementation.

Purpose
-------
Verify the default adapters continue to satisfy the application-layer ports
defined in ``src/lib_layered_config/application/ports.py``. This is part of the
contract-testing strategy documented in ``docs/systemdesign/module_reference.md``
so that dependency inversion remains enforceable through automated tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

import pytest

from lib_layered_config.adapters.dotenv.default import DefaultDotEnvLoader
from lib_layered_config.adapters.env.default import DefaultEnvLoader, default_env_prefix
from lib_layered_config.adapters.file_loaders import structured as structured_module
from lib_layered_config.adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.application import ports
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from collections.abc import Iterable

LoaderClass = type[TOMLFileLoader] | type[JSONFileLoader] | type[YAMLFileLoader]


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _section(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload[key]
    assert _is_mapping(value)
    return value


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")


@pytest.fixture()
def resolver_context(sandbox: LayeredSandbox) -> tuple[DefaultPathResolver, dict[str, Path]]:
    written = {
        "app": sandbox.write("app", "config.toml", content="[service]\nvalue=1\n"),
        "host": sandbox.write("host", "contract-host.toml", content="[service]\nvalue=2\n"),
        "user": sandbox.write("user", "config.toml", content="[service]\nvalue=3\n"),
        "dotenv": sandbox.write("user", ".env", content="SERVICE__VALUE=4\n"),
    }
    resolver = DefaultPathResolver(
        vendor=sandbox.vendor,
        app=sandbox.app,
        slug=sandbox.slug,
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform=sandbox.platform,
        hostname="contract-host",
    )
    return resolver, written


def _resolved(candidates: Iterable[str]) -> set[Path]:
    return {Path(candidate).resolve() for candidate in candidates}


@os_agnostic
def test_default_path_resolver_implements_protocol(
    resolver_context: tuple[DefaultPathResolver, dict[str, Path]],
) -> None:
    resolver, _ = resolver_context
    assert isinstance(resolver, ports.PathResolver)


@os_agnostic
@pytest.mark.parametrize("layer", ["app", "host", "user", "dotenv"])
def test_default_path_resolver_finds_the_file_written_for_each_layer(
    resolver_context: tuple[DefaultPathResolver, dict[str, Path]], layer: str
) -> None:
    resolver, written = resolver_context

    candidates = list(getattr(resolver, layer)())

    assert all(isinstance(candidate, str) for candidate in candidates)
    assert written[layer].resolve() in _resolved(candidates)


@os_agnostic
def test_default_path_resolver_host_layer_ignores_another_hosts_file(sandbox: LayeredSandbox) -> None:
    sandbox.write("host", "other-host.toml", content="[service]\nvalue=2\n")
    resolver = DefaultPathResolver(
        vendor=sandbox.vendor,
        app=sandbox.app,
        slug=sandbox.slug,
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform=sandbox.platform,
        hostname="contract-host",
    )

    assert list(resolver.host()) == []


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
    assert _section(payload, "service")["enabled"] is True


@os_agnostic
def test_default_env_loader_coerces_integer_values() -> None:
    loader, prefix = _env_loader_context()
    payload = loader.load(prefix)
    assert _section(payload, "service")["retries"] == 3


@os_agnostic
def test_default_dotenv_loader_implements_protocol(sandbox: LayeredSandbox) -> None:
    sandbox.write("user", ".env", content="SERVICE__TIMEOUT=15\n")
    loader = DefaultDotEnvLoader()
    assert isinstance(loader, ports.DotEnvLoader)


@os_agnostic
def test_default_dotenv_loader_reads_first_file(sandbox: LayeredSandbox) -> None:
    sandbox.write("user", ".env", content="SERVICE__TIMEOUT=15\n")
    payload = DefaultDotEnvLoader().load(str(sandbox.roots["user"]))
    assert _section(payload, "service")["timeout"] == 15


STRUCTURED_LOADERS: list[LoaderClass] = [TOMLFileLoader, JSONFileLoader]
if structured_module.yaml is not None:
    STRUCTURED_LOADERS.append(YAMLFileLoader)


def _write_sample(path: Path, loader_cls: LoaderClass) -> None:
    if loader_cls is TOMLFileLoader:
        path.write_text("[service]\nvalue = 1\n", encoding="utf-8")
    elif loader_cls is JSONFileLoader:
        path.write_text('{"service": {"value": 1}}', encoding="utf-8")
    else:
        path.write_text("service:\n  value: 1\n", encoding="utf-8")


@os_agnostic
@pytest.mark.parametrize("loader_cls", STRUCTURED_LOADERS)
def test_structured_loader_implements_protocol(tmp_path: Path, loader_cls: LoaderClass) -> None:
    loader = loader_cls()
    assert isinstance(loader, ports.FileLoader)


@os_agnostic
@pytest.mark.parametrize("loader_cls", STRUCTURED_LOADERS)
def test_structured_loader_decodes_value(tmp_path: Path, loader_cls: LoaderClass) -> None:
    loader = loader_cls()
    if loader_cls is TOMLFileLoader:
        path = tmp_path / "config.toml"
    elif loader_cls is JSONFileLoader:
        path = tmp_path / "config.json"
    else:
        path = tmp_path / "config.yaml"
    _write_sample(path, loader_cls)
    data = loader.load(str(path))
    assert _section(data, "service")["value"] == 1
