from __future__ import annotations

from click.testing import CliRunner
import sys
import types

import scripts.build as build
import scripts.dev as dev
import scripts.install as install
import scripts.run_cli as run_cli
import scripts.test as test_script
from scripts import _utils
from scripts._utils import RunResult


def _make_run_recorder(record):
    def _run(cmd, *, check=True, capture=True, cwd=None, env=None, dry_run=False):
        record.append(
            (
                cmd,
                {
                    "check": check,
                    "capture": capture,
                    "cwd": cwd,
                    "env": env,
                    "dry_run": dry_run,
                },
            )
        )
        return RunResult(0, "", "")

    return _run


def test_get_project_metadata_fields():
    meta = _utils.get_project_metadata()
    assert meta.name == "lib_layered_config"
    assert meta.slug == "lib-layered-config"
    assert meta.import_package == "lib_layered_config"
    assert meta.coverage_source == "src/lib_layered_config"
    assert meta.github_tarball_url("1.2.3").endswith("/bitranox/lib_layered_config/archive/refs/tags/v1.2.3.tar.gz")


def test_build_script_uses_metadata(monkeypatch):
    recorded: list[tuple[object, dict]] = []
    monkeypatch.setattr(build, "run", _make_run_recorder(recorded))
    monkeypatch.setattr(build, "cmd_exists", lambda name: True)
    runner = CliRunner()
    result = runner.invoke(build.main, [])
    assert result.exit_code == 0
    commands = [" ".join(cmd) if isinstance(cmd, list) else str(cmd) for cmd, _ in recorded]
    assert any("python -m build" in cmd for cmd in commands)
    assert any("brew install --build-from-source packaging/brew/Formula/lib-layered-config.rb" in cmd for cmd in commands)


def test_dev_script_installs_dev_extras(monkeypatch):
    recorded: list[tuple[object, dict]] = []
    monkeypatch.setattr(dev, "run", _make_run_recorder(recorded))
    runner = CliRunner()
    result = runner.invoke(dev.main, [])
    assert result.exit_code == 0
    assert recorded[0][0] == [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]


def test_install_script_installs_package(monkeypatch):
    recorded: list[tuple[object, dict]] = []
    monkeypatch.setattr(install, "run", _make_run_recorder(recorded))
    runner = CliRunner()
    result = runner.invoke(install.main, [])
    assert result.exit_code == 0
    assert recorded[0][0] == [sys.executable, "-m", "pip", "install", "-e", "."]


def test_run_cli_imports_dynamic_package(monkeypatch):
    seen: list[str] = []

    def fake_import(name: str):
        seen.append(name)
        if name.endswith(".__main__"):
            return types.SimpleNamespace()
        if name.endswith(".cli"):
            return types.SimpleNamespace(main=lambda args=None: 0)
        raise AssertionError(f"unexpected import {name}")

    monkeypatch.setattr(run_cli, "import_module", fake_import)
    runner = CliRunner()
    result = runner.invoke(run_cli.main, [])
    assert result.exit_code == 0
    package = run_cli.PACKAGE
    assert seen == [f"{package}.__main__", f"{package}.cli"]


def test_test_script_uses_pyproject_configuration(monkeypatch):
    recorded: list[tuple[object, dict]] = []
    monkeypatch.setattr(test_script, "bootstrap_dev", lambda: None)
    monkeypatch.setattr(test_script, "sync_packaging", lambda: None)
    monkeypatch.setattr(test_script, "cmd_exists", lambda name: False)
    monkeypatch.setattr(test_script, "run", _make_run_recorder(recorded))
    runner = CliRunner()
    result = runner.invoke(test_script.main, [])
    assert result.exit_code == 0
    pytest_commands = [cmd for cmd, _ in recorded if isinstance(cmd, list) and cmd[:3] == ["python", "-m", "pytest"]]
    assert pytest_commands, "pytest not invoked"
    assert any(f"--cov={test_script.COVERAGE_TARGET}" in cmd for cmd in (" ".join(c) for c in pytest_commands))
