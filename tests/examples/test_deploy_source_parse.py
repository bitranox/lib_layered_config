"""deploy refuses a source it cannot parse, in every mode, before writing anything.

The source used to be parsed only while reading the configured permission modes, so explicit modes
or ``set_permissions=False`` skipped the read and installed a file the application cannot load. The
refusal is the loader's own message, never the "deploy anyway" permission hint.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING, TypedDict

import pytest

from lib_layered_config import LayerLoadError, deploy_config, deploy_config_paths
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

if TYPE_CHECKING:
    from pathlib import Path


class _Identity(TypedDict):
    """The vendor/app/slug every deploy call here is made with."""

    vendor: str
    app: str
    slug: str


class _DeployMode(TypedDict, total=False):
    """The deploy_config options one parametrized mode sets."""

    dir_mode: int
    file_mode: int
    set_permissions: bool
    force: bool
    batch: bool


_IDENTITY: _Identity = {"vendor": "Acme", "app": "Kit", "slug": "kit"}
_TARGETS = ["app", "user"]
_BROKEN_TOML = "[service\nport = 1\n"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayeredSandbox:
    created = create_layered_sandbox(tmp_path, vendor="Acme", app="Kit", slug="kit")
    created.apply_env(monkeypatch)
    return created


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "src" / "config.toml"
    path.parent.mkdir()
    path.write_text(body, encoding="utf-8")
    return path


def _written(source: Path) -> list[Path]:
    return [path for path in deploy_config_paths(source, targets=_TARGETS, **_IDENTITY) if path.exists()]


@os_agnostic
@pytest.mark.parametrize(
    "mode",
    [{}, {"dir_mode": 0o700, "file_mode": 0o600}, {"set_permissions": False}, {"force": True}, {"batch": True}],
    ids=["configured-modes", "explicit-modes", "no-permissions", "force", "batch"],
)
def test_an_unparseable_source_is_refused_in_every_mode(
    sandbox: LayeredSandbox, tmp_path: Path, mode: _DeployMode
) -> None:
    source = _source(tmp_path, _BROKEN_TOML)

    with pytest.raises(LayerLoadError, match=r"config\.toml is not valid TOML") as caught:
        deploy_config(source, targets=_TARGETS, **_IDENTITY, **mode)

    assert "deploy anyway" not in str(caught.value)
    assert _written(source) == []


_NOT_TOML_SOURCES = {
    "json": ("config.json", '{"service": {"port": 1}}\n'),
    "yaml": ("config.yaml", "service:\n  port: 1\n"),
    "toml-named-conf": ("app.conf", "[service]\nport = 1\n"),
    "no-suffix": ("config", "[service]\nport = 1\n"),
}


@os_agnostic
@pytest.mark.parametrize("named", list(_NOT_TOML_SOURCES.values()), ids=list(_NOT_TOML_SOURCES))
@pytest.mark.parametrize(
    "mode",
    [{}, {"dir_mode": 0o700, "file_mode": 0o600}, {"set_permissions": False}],
    ids=["configured-modes", "explicit-modes", "no-permissions"],
)
def test_a_source_that_is_not_a_toml_file_is_refused_in_every_mode(
    sandbox: LayeredSandbox, tmp_path: Path, named: tuple[str, str], mode: _DeployMode
) -> None:
    # Every destination is config.toml or <hostname>.toml and is read only as TOML, so a valid
    # JSON or YAML source used to deploy with exit 0 and break every read after it.
    name, body = named
    source = tmp_path / "src" / name
    source.parent.mkdir()
    source.write_text(body, encoding="utf-8")

    with pytest.raises(
        LayerLoadError, match=r"is not a \.toml file, but deploy writes it as config\.toml or <hostname>\.toml"
    ) as caught:
        deploy_config(source, targets=_TARGETS, **_IDENTITY, **mode)

    assert name in str(caught.value) and "deploy anyway" not in str(caught.value)
    assert _written(source) == []


@os_agnostic
def test_a_toml_source_whose_suffix_is_upper_case_is_deployed(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = tmp_path / "src" / "CONFIG.TOML"
    source.parent.mkdir()
    source.write_text("[service]\nport = 1\n", encoding="utf-8")

    deploy_config(source, targets=["user"], set_permissions=False, **_IDENTITY)

    assert sandbox.roots["user"].joinpath("config.toml").read_text(encoding="utf-8") == "[service]\nport = 1\n"


@os_agnostic
def test_an_unparseable_file_in_the_source_dot_d_is_refused(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = _source(tmp_path, "[service]\nport = 1\n")
    dot_d = source.parent / "config.d"
    dot_d.mkdir()
    (dot_d / "20-cache.yaml").write_text("cache: [unclosed\n", encoding="utf-8")

    with pytest.raises(LayerLoadError, match=r"20-cache\.yaml"):
        deploy_config(source, targets=_TARGETS, set_permissions=False, **_IDENTITY)

    assert _written(source) == []


@os_agnostic
def test_a_non_config_file_in_the_source_dot_d_is_copied_unparsed(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = _source(tmp_path, "[service]\nport = 1\n")
    dot_d = source.parent / "config.d"
    dot_d.mkdir()
    (dot_d / "README.md").write_text("[not toml\n", encoding="utf-8")

    results = deploy_config(source, targets=["user"], set_permissions=False, **_IDENTITY)

    assert [result.destination.name for result in results] == ["config.toml"]


@os_agnostic
def test_the_cli_refuses_an_unparseable_source_given_explicit_modes(sandbox: LayeredSandbox, tmp_path: Path) -> None:
    source = _source(tmp_path, _BROKEN_TOML)
    identity = ["--vendor", "Acme", "--app", "Kit", "--slug", "kit", "--target", "user"]
    command = [sys.executable, "-m", "lib_layered_config", "deploy", "--source", str(source), *identity]

    result = subprocess.run(  # noqa: S603 - argv is this interpreter, the module and test paths, no shell
        [*command, "--dir-mode", "700", "--file-mode", "600"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **sandbox.env, "NO_COLOR": "1"},
        cwd=str(tmp_path),
        timeout=120,
        check=False,
    )

    assert result.returncode != 0
    assert "is not valid TOML" in result.stderr
    assert "deploy anyway" not in result.stderr
    assert result.stdout == ""
    assert _written(source) == []
