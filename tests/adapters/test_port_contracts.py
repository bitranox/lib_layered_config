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


@pytest.fixture()
def sandbox(tmp_path):
    """Provide a deterministic sandbox so adapters can be validated against documented paths."""

    return create_layered_sandbox(tmp_path, vendor="Acme", app="Demo", slug="demo")


def test_default_path_resolver_contract(sandbox) -> None:
    """DefaultPathResolver must fulfil the PathResolver protocol and surface all layer variants."""

    resolver = DefaultPathResolver(
        vendor=sandbox.vendor,
        app=sandbox.app,
        slug=sandbox.slug,
        cwd=sandbox.start_dir,
        env=sandbox.env,
        platform=sandbox.platform,
        hostname="contract-host",
    )

    assert isinstance(resolver, ports.PathResolver)

    sandbox.write("app", "config.toml", content="[service]\nvalue=1\n")
    sandbox.write("host", "contract-host.toml", content="[service]\nvalue=2\n")
    sandbox.write("user", "config.toml", content="[service]\nvalue=3\n")

    for candidate in resolver.app():
        assert isinstance(candidate, str)
    for candidate in resolver.host():
        assert "contract-host" in candidate
    for candidate in resolver.user():
        assert sandbox.slug in candidate or sandbox.app in candidate
    # ensure dotenv iteration returns deterministic list interface
    list(resolver.dotenv())


def test_default_env_loader_contract() -> None:
    """DefaultEnvLoader should satisfy EnvLoader and coerce primitives as per docs."""

    prefix = default_env_prefix("demo")
    environ = {
        f"{prefix}_SERVICE__ENABLED": "true",
        f"{prefix}_SERVICE__RETRIES": "3",
        "IRRELEVANT": "ignored",
    }
    loader = DefaultEnvLoader(environ=environ)

    assert isinstance(loader, ports.EnvLoader)

    payload = loader.load(prefix)
    assert payload["service"]["enabled"] is True
    assert payload["service"]["retries"] == 3


def test_default_dotenv_loader_contract(sandbox) -> None:
    """DefaultDotEnvLoader must parse the first discovered file and expose timeout values."""

    sandbox.write("user", ".env", content="SERVICE__TIMEOUT=15\n")

    loader = DefaultDotEnvLoader()
    assert isinstance(loader, ports.DotEnvLoader)

    payload = loader.load(str(sandbox.roots["user"]))
    assert payload["service"]["timeout"] == "15"


loaders = [TOMLFileLoader, JSONFileLoader]
if structured_module.yaml is not None:
    loaders.append(YAMLFileLoader)


@pytest.mark.parametrize("loader_cls", loaders)
def test_structured_loader_contract(tmp_path: Path, loader_cls) -> None:
    """Each structured loader should satisfy FileLoader and decode its target format."""

    loader = loader_cls()
    assert isinstance(loader, ports.FileLoader)

    if isinstance(loader, TOMLFileLoader):
        path = tmp_path / "config.toml"
        path.write_text("[service]\nvalue = 1\n", encoding="utf-8")
    elif isinstance(loader, JSONFileLoader):
        path = tmp_path / "config.json"
        path.write_text('{"service": {"value": 1}}', encoding="utf-8")
    else:
        path = tmp_path / "config.yaml"
        path.write_text("service:\n  value: 1\n", encoding="utf-8")

    data = loader.load(str(path))
    assert data["service"]["value"] == 1
