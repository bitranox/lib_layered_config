"""Test runner with linting, type-checking, and coverage support.

This module provides a unified test runner that:
- Runs ruff format/lint checks
- Validates import contracts with import-linter
- Type-checks with pyright
- Scans for security issues with bandit
- Audits dependencies with pip-audit
- Executes pytest with optional coverage
- Uploads coverage to Codecov
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import cast

import click

from ._utils import (
    RunResult,
    bootstrap_dev,
    get_project_metadata,
    run,
    sync_metadata_module,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT = get_project_metadata()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_TARGET = PROJECT.coverage_source
PACKAGE_SRC = Path("src") / PROJECT.import_package

__all__ = ["run_tests", "run_coverage", "COVERAGE_TARGET"]

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}
_AuditPayload = list[dict[str, object]]


# ---------------------------------------------------------------------------
# TOML Configuration Reader
# ---------------------------------------------------------------------------


@dataclass
class ProjectConfig:
    """Configuration values read from pyproject.toml."""

    fail_under: int = 80
    bandit_skips: list[str] = field(default_factory=list)
    pip_audit_ignores: list[str] = field(default_factory=list)
    pytest_verbosity: str = "-vv"
    coverage_report_file: str = "coverage.xml"
    src_path: str = "src"

    @classmethod
    def from_pyproject(cls, pyproject_path: Path) -> ProjectConfig:
        """Load configuration from pyproject.toml."""
        try:
            toml = _get_toml_module()
            data = toml.loads(pyproject_path.read_text())
            tool = data.get("tool", {})

            fail_under = int(tool.get("coverage", {}).get("report", {}).get("fail_under", 80))
            bandit_skips = list(tool.get("bandit", {}).get("skips", []))
            pip_audit_ignores = list(tool.get("pip-audit", {}).get("ignore-vulns", []))

            scripts_test = tool.get("scripts", {}).get("test", {})
            pytest_verbosity = str(scripts_test.get("pytest-verbosity", "-vv"))
            coverage_report_file = str(scripts_test.get("coverage-report-file", "coverage.xml"))
            src_path = str(scripts_test.get("src-path", "src"))

            return cls(
                fail_under=fail_under,
                bandit_skips=bandit_skips,
                pip_audit_ignores=pip_audit_ignores,
                pytest_verbosity=pytest_verbosity,
                coverage_report_file=coverage_report_file,
                src_path=src_path,
            )
        except Exception:
            return cls()


_toml_module: ModuleType | None = None


def _get_toml_module() -> ModuleType:
    """Return the TOML parsing module (tomllib or tomli fallback)."""
    global _toml_module
    if _toml_module is not None:
        return _toml_module

    try:
        import tomllib as module  # type: ignore[import-not-found]
    except ImportError:
        import tomli as module  # type: ignore[import-not-found,no-redef]

    _toml_module = module
    return module


# ---------------------------------------------------------------------------
# Environment Management
# ---------------------------------------------------------------------------


def _build_default_env(src_path: str = "src") -> dict[str, str]:
    """Return the base environment for subprocess execution."""
    pythonpath = os.pathsep.join(filter(None, [str(PROJECT_ROOT / src_path), os.environ.get("PYTHONPATH")]))
    return os.environ | {"PYTHONPATH": pythonpath}


_default_env = _build_default_env()


def _refresh_default_env() -> None:
    """Recompute cached default env after environment mutations."""
    global _default_env
    _default_env = _build_default_env()


# ---------------------------------------------------------------------------
# Git Utilities
# ---------------------------------------------------------------------------


def _resolve_commit_sha() -> str | None:
    """Resolve the current git commit SHA from environment or git."""
    sha = os.getenv("GITHUB_SHA")
    if sha:
        return sha.strip()
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    candidate = proc.stdout.strip()
    return candidate or None


def _resolve_git_branch() -> str | None:
    """Resolve the current git branch from environment or git."""
    branch = os.getenv("GITHUB_REF_NAME")
    if branch:
        return branch.strip()
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    candidate = proc.stdout.strip()
    if candidate in {"", "HEAD"}:
        return None
    return candidate


def _resolve_git_service() -> str | None:
    """Map repository host to Codecov git service identifier."""
    host = (PROJECT.repo_host or "").lower()
    mapping = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",
    }
    return mapping.get(host)


# ---------------------------------------------------------------------------
# Display Helpers
# ---------------------------------------------------------------------------


def _echo_output(output: str, *, to_stderr: bool = False) -> None:
    """Echo output ensuring proper newline handling."""
    click.echo(output, err=to_stderr, nl=False)
    if not output.endswith("\n"):
        click.echo(err=to_stderr)


def _display_command(cmd: Sequence[str] | str, label: str | None, env: dict[str, str] | None, verbose: bool) -> None:
    """Display command being executed with optional label and environment."""
    display = cmd if isinstance(cmd, str) else " ".join(cmd)
    if label and not verbose:
        click.echo(f"[{label}] $ {display}")
    if verbose:
        click.echo(f"  $ {display}")
        if env:
            overrides = {k: v for k, v in env.items() if os.environ.get(k) != v}
            if overrides:
                env_view = " ".join(f"{k}={v}" for k, v in overrides.items())
                click.echo(f"    env {env_view}")


def _display_result(result: RunResult, label: str | None, verbose: bool) -> None:
    """Display verbose result information."""
    if verbose and label:
        click.echo(f"    -> {label}: exit={result.code} out={bool(result.out)} err={bool(result.err)}")


def _display_captured_output(result: RunResult, capture: bool, verbose: bool) -> None:
    """Display captured stdout/stderr if verbose or on error."""
    if capture and (verbose or result.code != 0):
        if result.out:
            _echo_output(result.out)
        if result.err:
            _echo_output(result.err, to_stderr=True)


# ---------------------------------------------------------------------------
# Command Execution
# ---------------------------------------------------------------------------


def _run_command(
    cmd: Sequence[str] | str,
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture: bool = True,
    label: str | None = None,
    verbose: bool = False,
) -> RunResult:
    """Execute command with optional display, capture, and error handling."""
    _display_command(cmd, label, env, verbose)
    merged_env = _default_env if env is None else _default_env | env
    result = run(cmd, env=merged_env, check=False, capture=capture)
    _display_result(result, label, verbose)
    _display_captured_output(result, capture, verbose)
    if check and result.code != 0:
        raise SystemExit(result.code)
    return result


def _make_step(
    cmd: list[str] | str,
    label: str,
    *,
    capture: bool = True,
    verbose: bool = False,
) -> Callable[[], None]:
    """Create a step function that executes a command."""

    def runner() -> None:
        _run_command(cmd, label=label, capture=capture, verbose=verbose)

    return runner


def _make_run_fn(verbose: bool) -> Callable[..., RunResult]:
    """Create a run function with the specified verbosity.

    This factory function creates a run_fn that can be passed to other functions,
    avoiding the need for nested function definitions.
    """

    def run_fn(
        cmd: Sequence[str] | str,
        *,
        env: dict[str, str] | None = None,
        check: bool = True,
        capture: bool = True,
        label: str | None = None,
    ) -> RunResult:
        return _run_command(cmd, env=env, check=check, capture=capture, label=label, verbose=verbose)

    return run_fn


# ---------------------------------------------------------------------------
# Coverage File Management
# ---------------------------------------------------------------------------


def _prune_coverage_data_files() -> None:
    """Delete SQLite coverage data shards to keep the Codecov CLI simple."""
    for path in Path.cwd().glob(".coverage*"):
        if path.is_dir() or path.suffix == ".xml":
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            click.echo(f"[coverage] warning: unable to remove {path}: {exc}", err=True)


def _remove_report_artifacts(coverage_report_file: str = "coverage.xml") -> None:
    """Remove coverage reports that might lock the SQLite database on reruns."""
    for name in (coverage_report_file, "codecov.xml"):
        artifact = Path(name)
        try:
            artifact.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            click.echo(f"[coverage] warning: unable to remove {artifact}: {exc}", err=True)


# ---------------------------------------------------------------------------
# Codecov Integration
# ---------------------------------------------------------------------------


def _ensure_codecov_token() -> None:
    """Load CODECOV_TOKEN from .env file if not already set."""
    if os.getenv("CODECOV_TOKEN"):
        _refresh_default_env()
        return
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "CODECOV_TOKEN":
            token = value.strip().strip("\"'")
            if token:
                os.environ.setdefault("CODECOV_TOKEN", token)
                _refresh_default_env()
            break


def _upload_coverage_report(*, run_fn: Callable[..., RunResult], coverage_report_file: str = "coverage.xml") -> bool:
    """Upload coverage report via the official Codecov CLI when available."""
    uploader = _check_codecov_prerequisites(coverage_report_file)
    if uploader is None:
        return False

    commit_sha = _resolve_commit_sha()
    if commit_sha is None:
        click.echo("[codecov] Unable to resolve git commit; skipping upload", err=True)
        return False

    args = _build_codecov_args(uploader, commit_sha, coverage_report_file)
    env_overrides = _build_codecov_env()

    result = run_fn(args, env=env_overrides, check=False, capture=False, label="codecov-upload")
    return _handle_codecov_result(result)


def _check_codecov_prerequisites(coverage_report_file: str = "coverage.xml") -> str | None:
    """Check prerequisites for codecov upload, return uploader path or None."""
    if not Path(coverage_report_file).is_file():
        return None

    if not os.getenv("CODECOV_TOKEN") and not os.getenv("CI"):
        click.echo("[codecov] CODECOV_TOKEN not configured; skipping upload (set CODECOV_TOKEN or run in CI)")
        return None

    uploader = shutil.which("codecovcli")
    if uploader is None:
        click.echo(
            "[codecov] 'codecovcli' not found; install with 'pip install codecov-cli' to enable uploads",
            err=True,
        )
        return None

    return uploader


def _build_codecov_args(uploader: str, commit_sha: str, coverage_report_file: str = "coverage.xml") -> list[str]:
    """Build the codecov CLI arguments."""
    args = [
        uploader,
        "upload-coverage",
        "--file",
        coverage_report_file,
        "--disable-search",
        "--fail-on-error",
        "--sha",
        commit_sha,
        "--name",
        f"local-{platform.system()}-{platform.python_version()}",
        "--flag",
        "local",
    ]

    branch = _resolve_git_branch()
    if branch:
        args.extend(["--branch", branch])

    git_service = _resolve_git_service()
    if git_service:
        args.extend(["--git-service", git_service])

    slug = _get_repo_slug()
    if slug:
        args.extend(["--slug", slug])

    return args


def _build_codecov_env() -> dict[str, str]:
    """Build environment overrides for codecov upload."""
    env_overrides: dict[str, str] = {"CODECOV_NO_COMBINE": "1"}
    slug = _get_repo_slug()
    if slug:
        env_overrides["CODECOV_SLUG"] = slug
    return env_overrides


def _get_repo_slug() -> str | None:
    """Get the repository slug (owner/name) if available."""
    if PROJECT.repo_owner and PROJECT.repo_name:
        return f"{PROJECT.repo_owner}/{PROJECT.repo_name}"
    return None


def _handle_codecov_result(result: RunResult) -> bool:
    """Handle the codecov upload result."""
    if result.code == 0:
        click.echo("[codecov] upload succeeded")
        return True
    click.echo(f"[codecov] upload failed (exit {result.code})", err=True)
    return False


# ---------------------------------------------------------------------------
# Pip-Audit Utilities
# ---------------------------------------------------------------------------


def _resolve_pip_audit_ignores(config: ProjectConfig) -> list[str]:
    """Return consolidated list of vulnerability IDs to ignore during pip-audit."""
    extra = [token.strip() for token in os.getenv("PIP_AUDIT_IGNORE", "").split(",") if token.strip()]
    ignores: list[str] = []
    for candidate in (*config.pip_audit_ignores, *extra):
        if candidate and candidate not in ignores:
            ignores.append(candidate)
    return ignores


def _extract_audit_dependencies(payload: object) -> _AuditPayload:
    """Normalise `pip-audit --format json` output into dictionaries."""
    if not isinstance(payload, dict):
        return []

    payload_dict = cast(dict[str, object], payload)
    raw_candidates = payload_dict.get("dependencies", [])
    if not isinstance(raw_candidates, list):
        return []

    candidate_list = cast(list[object], raw_candidates)
    return [cast(dict[str, object], candidate) for candidate in candidate_list if isinstance(candidate, dict)]


def _run_pip_audit_guarded(config: ProjectConfig, run_fn: Callable[..., RunResult]) -> None:
    """Run pip-audit with configured ignore list and verify results."""
    ignore_ids = _resolve_pip_audit_ignores(config)
    _run_pip_audit_with_ignores(run_fn, ignore_ids)
    result = _run_pip_audit_json(run_fn)

    if result.code == 0:
        return

    payload = _parse_audit_json(result.out)
    unexpected = _find_unexpected_vulns(payload, ignore_ids)
    _report_unexpected_vulns(unexpected)


def _run_pip_audit_with_ignores(run_fn: Callable[..., RunResult], ignore_ids: list[str]) -> None:
    """Run pip-audit with the configured ignore list."""
    audit_cmd: list[str] = ["pip-audit", "--skip-editable"]
    for vuln_id in ignore_ids:
        audit_cmd.extend(["--ignore-vuln", vuln_id])
    run_fn(audit_cmd, label="pip-audit-ignore", capture=False)


def _run_pip_audit_json(run_fn: Callable[..., RunResult]) -> RunResult:
    """Run pip-audit in JSON mode for verification."""
    return run_fn(
        ["pip-audit", "--skip-editable", "--format", "json"],
        label="pip-audit-verify",
        capture=True,
        check=False,
    )


def _parse_audit_json(output: str) -> object:
    """Parse pip-audit JSON output, raising SystemExit on failure."""
    try:
        return json.loads(output or "{}")
    except json.JSONDecodeError as exc:
        click.echo("pip-audit verification output was not valid JSON", err=True)
        raise SystemExit("pip-audit verification failed") from exc


def _find_unexpected_vulns(payload: object, ignore_ids: list[str]) -> list[str]:
    """Find vulnerabilities not in the ignore list."""
    dependencies = _extract_audit_dependencies(payload)
    allowed_vulns = set(ignore_ids)
    unexpected: list[str] = []

    for item in dependencies:
        package = _extract_package_name(item)
        for vuln_id in _extract_vuln_ids(item):
            if vuln_id not in allowed_vulns:
                unexpected.append(f"{package}: {vuln_id}")

    return unexpected


def _extract_package_name(item: dict[str, object]) -> str:
    """Extract package name from audit dependency item."""
    name_candidate = item.get("name")
    return name_candidate if isinstance(name_candidate, str) else "<unknown>"


def _extract_vuln_ids(item: dict[str, object]) -> list[str]:
    """Extract vulnerability IDs from audit dependency item."""
    vulns_candidate = item.get("vulns", [])
    if not isinstance(vulns_candidate, list):
        return []
    vuln_objects = list(cast(list[object], vulns_candidate))
    vuln_entries = [cast(dict[str, object], entry) for entry in vuln_objects if isinstance(entry, dict)]
    vuln_ids: list[str] = []
    for vuln_payload in vuln_entries:
        vuln_id = vuln_payload.get("id")
        if isinstance(vuln_id, str):
            vuln_ids.append(vuln_id)
    return vuln_ids


def _report_unexpected_vulns(unexpected: list[str]) -> None:
    """Report unexpected vulnerabilities and exit if any found."""
    if not unexpected:
        return
    click.echo("pip-audit reported new vulnerabilities:", err=True)
    for entry in unexpected:
        click.echo(f"  - {entry}", err=True)
    raise SystemExit("Resolve the reported vulnerabilities before continuing.")


# ---------------------------------------------------------------------------
# Test Step Builders
# ---------------------------------------------------------------------------


def _resolve_strict_format(strict_format: bool | None) -> bool:
    """Resolve the strict format setting from parameter or environment."""
    if strict_format is not None:
        return strict_format

    env_value = os.getenv("STRICT_RUFF_FORMAT")
    if env_value is None:
        return True

    token = env_value.strip().lower()
    if token in _TRUTHY:
        return True
    if token in _FALSY or token == "":
        return False
    raise SystemExit("STRICT_RUFF_FORMAT must be one of {0,1,true,false,yes,no,on,off}.")


def _build_test_steps(
    config: ProjectConfig,
    *,
    strict_format: bool,
    verbose: bool,
) -> list[tuple[str, Callable[[], None]]]:
    """Build the list of test steps to execute."""
    steps: list[tuple[str, Callable[[], None]]] = []
    run_fn = _make_run_fn(verbose)

    def make(cmd: list[str], label: str, capture: bool = False) -> Callable[[], None]:
        return _make_step(cmd, label, capture=capture, verbose=verbose)

    # Ruff format
    steps.append(("Ruff format (apply)", make(["ruff", "format", "."], "ruff-format-apply")))

    if strict_format:
        steps.append(("Ruff format check", make(["ruff", "format", "--check", "."], "ruff-format-check")))

    # Ruff lint
    steps.append(("Ruff lint", make(["ruff", "check", "."], "ruff-check")))

    # Import-linter
    steps.append(
        (
            "Import-linter contracts",
            make([sys.executable, "-m", "importlinter.cli", "lint", "--config", "pyproject.toml"], "import-linter"),
        )
    )

    # Pyright
    steps.append(("Pyright type-check", make(["pyright"], "pyright")))

    # Bandit
    bandit_cmd = ["bandit", "-q", "-r"]
    if config.bandit_skips:
        bandit_cmd.extend(["-s", ",".join(config.bandit_skips)])
    bandit_cmd.append(str(PACKAGE_SRC))
    steps.append(("Bandit security scan", make(bandit_cmd, "bandit")))

    # Pip-audit
    steps.append(("pip-audit (guarded)", lambda: _run_pip_audit_guarded(config, run_fn)))

    return steps


def _run_pytest_step(
    config: ProjectConfig,
    coverage_mode: str,
    verbose: bool,
) -> None:
    """Execute pytest with optional coverage collection."""
    for path in (Path(".coverage"), Path(config.coverage_report_file)):
        path.unlink(missing_ok=True)

    run_fn = _make_run_fn(verbose)
    enable_coverage = coverage_mode == "on" or (coverage_mode == "auto" and (os.getenv("CI") or os.getenv("CODECOV_TOKEN")))

    if enable_coverage:
        click.echo("[coverage] enabled")
        with tempfile.TemporaryDirectory() as tmp:
            cov_file = Path(tmp) / ".coverage"
            click.echo(f"[coverage] file={cov_file}")
            env = os.environ | {"COVERAGE_FILE": str(cov_file), "COVERAGE_NO_SQL": "1"}
            pytest_result = run_fn(
                [
                    "python",
                    "-m",
                    "pytest",
                    f"--cov={COVERAGE_TARGET}",
                    f"--cov-report=xml:{config.coverage_report_file}",
                    "--cov-report=term-missing",
                    f"--cov-fail-under={config.fail_under}",
                    config.pytest_verbosity,
                ],
                env=env,
                capture=False,
                label="pytest",
            )
            if pytest_result.code != 0:
                click.echo("[pytest] failed; skipping Codecov upload", err=True)
                raise SystemExit(pytest_result.code)
    else:
        click.echo("[coverage] disabled (set --coverage=on to force)")
        pytest_result = run_fn(
            ["python", "-m", "pytest", config.pytest_verbosity],
            capture=False,
            label="pytest-no-cov",
        )
        if pytest_result.code != 0:
            click.echo("[pytest] failed; skipping Codecov upload", err=True)
            raise SystemExit(pytest_result.code)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_coverage(*, verbose: bool = False) -> None:
    """Run pytest under coverage using python modules to avoid PATH shim issues."""
    sync_metadata_module(PROJECT)
    bootstrap_dev()

    config = ProjectConfig.from_pyproject(PROJECT_ROOT / "pyproject.toml")
    _prune_coverage_data_files()
    _remove_report_artifacts(config.coverage_report_file)
    base_env = _build_default_env(config.src_path) | {"COVERAGE_NO_SQL": "1"}

    with tempfile.TemporaryDirectory() as tmpdir:
        coverage_file = Path(tmpdir) / ".coverage"
        env = base_env | {"COVERAGE_FILE": str(coverage_file)}

        coverage_cmd = [sys.executable, "-m", "coverage", "run", "-m", "pytest", config.pytest_verbosity]
        click.echo(f"[coverage] python -m coverage run -m pytest {config.pytest_verbosity}")
        result = run(coverage_cmd, env=env, capture=not verbose, check=False)
        if result.code != 0:
            if result.out:
                click.echo(result.out, nl=False)
            if result.err:
                click.echo(result.err, err=True, nl=False)
            raise SystemExit(result.code)

        report_cmd = [sys.executable, "-m", "coverage", "report", "-m"]
        click.echo("[coverage] python -m coverage report -m")
        report = run(report_cmd, env=env, capture=not verbose, check=False)
        if report.code != 0:
            if report.out:
                click.echo(report.out, nl=False)
            if report.err:
                click.echo(report.err, err=True, nl=False)
            raise SystemExit(report.code)
        if report.out and not verbose:
            click.echo(report.out, nl=False)


def run_tests(*, coverage: str = "on", verbose: bool = False, strict_format: bool | None = None) -> None:
    """Run the complete test suite with all quality checks."""
    env_verbose = os.getenv("TEST_VERBOSE", "").lower()
    if not verbose and env_verbose in _TRUTHY:
        verbose = True

    sync_metadata_module(PROJECT)
    bootstrap_dev()

    config = ProjectConfig.from_pyproject(PROJECT_ROOT / "pyproject.toml")
    resolved_strict_format = _resolve_strict_format(strict_format)

    steps = _build_test_steps(config, strict_format=resolved_strict_format, verbose=verbose)
    pytest_label = "Pytest with coverage" if coverage != "off" else "Pytest"
    steps.append((pytest_label, lambda: _run_pytest_step(config, coverage, verbose)))

    total = len(steps)
    for index, (description, action) in enumerate(steps, start=1):
        click.echo(f"[{index}/{total}] {description}")
        action()

    _ensure_codecov_token()

    if Path(config.coverage_report_file).exists():
        _prune_coverage_data_files()
        run_fn = _make_run_fn(verbose)
        uploaded = _upload_coverage_report(run_fn=run_fn, coverage_report_file=config.coverage_report_file)
        if uploaded:
            click.echo("All checks passed (coverage uploaded)")
        else:
            click.echo("Checks finished (coverage upload skipped or failed)")
    else:
        click.echo(f"Checks finished ({config.coverage_report_file} missing, upload skipped)")


def main() -> None:
    """Entry point for direct script execution."""
    run_tests()


if __name__ == "__main__":
    main()
