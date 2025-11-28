"""Test runner with linting, type-checking, and coverage support.

This module provides a unified test runner that:
- Runs ruff format/lint checks
- Validates import contracts with import-linter
- Type-checks with pyright
- Scans for security issues with bandit
- Audits dependencies with pip-audit
- Executes pytest with optional coverage
- Uploads coverage to Codecov

Parallel execution is supported for independent checks (ruff, pyright, bandit,
import-linter) to reduce total execution time.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import click

from ._utils import (
    RunResult,
    bootstrap_dev,
    get_project_metadata,
    run,
    sync_metadata_module,
)
from .toml_config import load_pyproject_config

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

# Thread-safe lock for console output
_output_lock = threading.Lock()


@dataclass(frozen=True)
class StepResult:
    """Result of a test step execution."""

    name: str
    success: bool
    output: str = ""
    error: str = ""
    duration: float = 0.0
    command: str = ""


# ---------------------------------------------------------------------------
# Pip-Audit Data Structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditVulnerability:
    """A single vulnerability from pip-audit output."""

    vuln_id: str
    fix_versions: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AuditVulnerability:
        """Parse a vulnerability entry from pip-audit JSON."""
        vuln_id = data.get("id")
        if not isinstance(vuln_id, str):
            vuln_id = "<unknown>"

        fix_versions: tuple[str, ...] = ()
        raw_fix = data.get("fix_versions")
        if isinstance(raw_fix, list):
            typed_fix = cast(list[object], raw_fix)
            fix_versions = tuple(str(v) for v in typed_fix if v is not None)

        aliases: tuple[str, ...] = ()
        raw_aliases = data.get("aliases")
        if isinstance(raw_aliases, list):
            typed_aliases = cast(list[object], raw_aliases)
            aliases = tuple(str(a) for a in typed_aliases if a is not None)

        description = data.get("description", "")
        if not isinstance(description, str):
            description = ""

        return cls(
            vuln_id=vuln_id,
            fix_versions=fix_versions,
            aliases=aliases,
            description=description,
        )


@dataclass(frozen=True)
class AuditDependency:
    """A dependency entry from pip-audit output."""

    name: str
    version: str = ""
    vulns: tuple[AuditVulnerability, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AuditDependency:
        """Parse a dependency entry from pip-audit JSON."""
        name = data.get("name")
        if not isinstance(name, str):
            name = "<unknown>"

        version = data.get("version", "")
        if not isinstance(version, str):
            version = ""

        vulns: tuple[AuditVulnerability, ...] = ()
        raw_vulns = data.get("vulns")
        if isinstance(raw_vulns, list):
            typed_vulns = cast(list[object], raw_vulns)
            parsed_vulns: list[AuditVulnerability] = []
            for entry in typed_vulns:
                if isinstance(entry, dict):
                    parsed_vulns.append(AuditVulnerability.from_dict(cast(dict[str, object], entry)))
            vulns = tuple(parsed_vulns)

        return cls(name=name, version=version, vulns=vulns)

    def vuln_ids(self) -> tuple[str, ...]:
        """Return all vulnerability IDs for this dependency."""
        return tuple(v.vuln_id for v in self.vulns)


@dataclass(frozen=True)
class AuditResult:
    """Parsed pip-audit JSON output."""

    dependencies: tuple[AuditDependency, ...] = ()

    @classmethod
    def from_json(cls, json_output: str) -> AuditResult:
        """Parse pip-audit JSON output into structured data."""
        try:
            payload: object = json.loads(json_output or "{}")
        except json.JSONDecodeError:
            return cls()

        if not isinstance(payload, dict):
            return cls()

        typed_payload = cast(dict[str, object], payload)
        raw_deps = typed_payload.get("dependencies")
        if not isinstance(raw_deps, list):
            return cls()

        typed_deps = cast(list[object], raw_deps)
        parsed_deps: list[AuditDependency] = []
        for entry in typed_deps:
            if isinstance(entry, dict):
                parsed_deps.append(AuditDependency.from_dict(cast(dict[str, object], entry)))

        return cls(dependencies=tuple(parsed_deps))

    def find_unexpected_vulns(self, ignore_ids: set[str]) -> list[str]:
        """Find vulnerabilities not in the ignore set."""
        unexpected: list[str] = []
        for dep in self.dependencies:
            for vuln_id in dep.vuln_ids():
                if vuln_id not in ignore_ids:
                    unexpected.append(f"{dep.name}: {vuln_id}")
        return unexpected


# ---------------------------------------------------------------------------
# Project Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestConfig:
    """Consolidated test configuration from pyproject.toml."""

    fail_under: int
    bandit_skips: tuple[str, ...]
    pip_audit_ignores: tuple[str, ...]
    pytest_verbosity: str
    coverage_report_file: str
    src_path: str

    @classmethod
    def from_pyproject(cls, pyproject_path: Path) -> TestConfig:
        """Load test configuration from pyproject.toml."""
        config = load_pyproject_config(pyproject_path)
        return cls(
            fail_under=config.tool.coverage.fail_under,
            bandit_skips=config.tool.bandit.skips,
            pip_audit_ignores=config.tool.pip_audit.ignore_vulns,
            pytest_verbosity=config.tool.scripts.pytest_verbosity,
            coverage_report_file=config.tool.scripts.coverage_report_file,
            src_path=config.tool.scripts.src_path,
        )


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


def _resolve_pip_audit_ignores(config: TestConfig) -> list[str]:
    """Return consolidated list of vulnerability IDs to ignore during pip-audit."""
    extra = [token.strip() for token in os.getenv("PIP_AUDIT_IGNORE", "").split(",") if token.strip()]
    ignores: list[str] = []
    for candidate in (*config.pip_audit_ignores, *extra):
        if candidate and candidate not in ignores:
            ignores.append(candidate)
    return ignores


def _run_pip_audit_guarded(config: TestConfig, run_fn: Callable[..., RunResult]) -> None:
    """Run pip-audit with configured ignore list and verify results."""
    ignore_ids = _resolve_pip_audit_ignores(config)
    _run_pip_audit_with_ignores(run_fn, ignore_ids)
    result = _run_pip_audit_json(run_fn)

    if result.code == 0:
        return

    audit_result = AuditResult.from_json(result.out)
    unexpected = audit_result.find_unexpected_vulns(set(ignore_ids))
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


_StepList = list[tuple[str, Callable[[], None]]]


def _empty_step_list() -> _StepList:
    """Return an empty step list with proper typing."""
    return []


@dataclass
class TestSteps:
    """Categorized test steps for sequential and parallel execution."""

    sequential_pre: _StepList = field(default_factory=_empty_step_list)
    parallel: _StepList = field(default_factory=_empty_step_list)
    sequential_post: _StepList = field(default_factory=_empty_step_list)


@dataclass
class ParallelStep:
    """A step configured for parallel execution with its command."""

    name: str
    command: list[str]


def _build_test_steps(
    config: TestConfig,
    *,
    strict_format: bool,
    verbose: bool,
) -> TestSteps:
    """Build categorized test steps for sequential and parallel execution."""
    run_fn = _make_run_fn(verbose)

    def make(cmd: list[str], label: str, capture: bool = True) -> Callable[[], None]:
        return _make_step(cmd, label, capture=capture, verbose=verbose)

    steps = TestSteps()

    # Sequential pre-steps: must run before parallel checks
    # Ruff format modifies files, so it must run first and alone
    steps.sequential_pre.append(("Ruff format (apply)", make(["ruff", "format", "."], "ruff-format-apply")))

    # Parallel steps: can run concurrently after formatting
    if strict_format:
        steps.parallel.append(("Ruff format check", make(["ruff", "format", "--check", "."], "ruff-format-check")))

    steps.parallel.append(("Ruff lint", make(["ruff", "check", "."], "ruff-check")))

    steps.parallel.append(
        (
            "Import-linter contracts",
            make([sys.executable, "-m", "importlinter.cli", "lint", "--config", "pyproject.toml"], "import-linter"),
        )
    )

    steps.parallel.append(("Pyright type-check", make(["pyright"], "pyright")))

    bandit_cmd = ["bandit", "-q", "-r"]
    if config.bandit_skips:
        bandit_cmd.extend(["-s", ",".join(config.bandit_skips)])
    bandit_cmd.append(str(PACKAGE_SRC))
    steps.parallel.append(("Bandit security scan", make(bandit_cmd, "bandit")))

    # Sequential post-steps: must run after parallel checks
    # pip-audit has network calls and complex output, better sequential
    steps.sequential_post.append(("pip-audit (guarded)", lambda: _run_pip_audit_guarded(config, run_fn)))

    return steps


def _build_parallel_commands(config: TestConfig, *, strict_format: bool) -> list[ParallelStep]:
    """Build the list of commands for parallel execution."""
    commands: list[ParallelStep] = []

    if strict_format:
        commands.append(ParallelStep("Ruff format check", ["ruff", "format", "--check", "."]))

    commands.append(ParallelStep("Ruff lint", ["ruff", "check", "."]))

    commands.append(
        ParallelStep(
            "Import-linter contracts",
            [sys.executable, "-m", "importlinter.cli", "lint", "--config", "pyproject.toml"],
        )
    )

    commands.append(ParallelStep("Pyright type-check", ["pyright"]))

    bandit_cmd = ["bandit", "-q", "-r"]
    if config.bandit_skips:
        bandit_cmd.extend(["-s", ",".join(config.bandit_skips)])
    bandit_cmd.append(str(PACKAGE_SRC))
    commands.append(ParallelStep("Bandit security scan", bandit_cmd))

    return commands


def _run_step_subprocess(step: ParallelStep) -> StepResult:
    """Run a step as a subprocess and capture its output."""
    import time

    start_time = time.perf_counter()
    cmd_str = " ".join(step.command)

    result = run(step.command, env=_default_env, check=False, capture=True)

    duration = time.perf_counter() - start_time
    success = result.code == 0

    return StepResult(
        name=step.name,
        success=success,
        output=result.out,
        error=result.err,
        duration=duration,
        command=cmd_str,
    )


def _run_parallel_steps_subprocess(
    steps: list[ParallelStep],
    *,
    max_workers: int | None = None,
) -> list[StepResult]:
    """Run multiple steps in parallel using subprocesses and collect results."""
    if not steps:
        return []

    # Default to number of steps or 4, whichever is smaller
    if max_workers is None:
        max_workers = min(len(steps), 4)

    results: list[StepResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_step = {executor.submit(_run_step_subprocess, step): step.name for step in steps}

        for future in as_completed(future_to_step):
            result = future.result()
            results.append(result)

    # Sort results by original order
    step_order = {step.name: i for i, step in enumerate(steps)}
    results.sort(key=lambda r: step_order.get(r.name, 999))

    return results


def _display_parallel_results(
    results: list[StepResult],
    start_index: int,
    total: int,
    *,
    verbose: bool = False,
) -> bool:
    """Display results from parallel execution. Returns True if all passed."""
    all_passed = True

    for i, result in enumerate(results):
        status = "PASS" if result.success else "FAIL"
        step_num = start_index + i
        duration_str = f" ({result.duration:.1f}s)" if result.duration >= 0.1 else ""

        # Show command and status
        click.echo(f"[{step_num}/{total}] {result.name} [{status}]{duration_str}")

        # Show output based on success and verbosity
        show_output = not result.success or verbose

        if show_output and result.command:
            click.echo(f"  $ {result.command}")

        if not result.success:
            all_passed = False

        # Always show output for failures, optionally for success in verbose mode
        if show_output:
            if result.output:
                # Indent output for readability
                for line in result.output.rstrip().split("\n"):
                    click.echo(f"    {line}")
            if result.error:
                for line in result.error.rstrip().split("\n"):
                    click.echo(f"    {line}", err=True)

    return all_passed


def _run_pytest_step(
    config: TestConfig,
    coverage_mode: str,
    verbose: bool,
) -> None:
    """Execute pytest with optional coverage collection."""
    for path in (Path(".coverage"), Path(config.coverage_report_file)):
        path.unlink(missing_ok=True)

    run_fn = _make_run_fn(verbose)
    enable_coverage = coverage_mode == "on" or (
        coverage_mode == "auto" and (os.getenv("CI") or os.getenv("CODECOV_TOKEN"))
    )

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

    config = TestConfig.from_pyproject(PROJECT_ROOT / "pyproject.toml")
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


def run_tests(
    *,
    coverage: str = "on",
    verbose: bool = False,
    strict_format: bool | None = None,
    parallel: bool = True,
) -> None:
    """Run the complete test suite with all quality checks.

    Args:
        coverage: Coverage mode - "on", "off", or "auto"
        verbose: Enable verbose output
        strict_format: Enforce strict ruff format checking
        parallel: Run independent checks in parallel (default: True)
    """
    env_verbose = os.getenv("TEST_VERBOSE", "").lower()
    if not verbose and env_verbose in _TRUTHY:
        verbose = True

    # Check for PARALLEL env override
    env_parallel = os.getenv("TEST_PARALLEL", "").lower()
    if env_parallel in _FALSY:
        parallel = False
    elif env_parallel in _TRUTHY:
        parallel = True

    sync_metadata_module(PROJECT)
    bootstrap_dev()

    config = TestConfig.from_pyproject(PROJECT_ROOT / "pyproject.toml")
    resolved_strict_format = _resolve_strict_format(strict_format)

    steps = _build_test_steps(config, strict_format=resolved_strict_format, verbose=verbose)

    # Calculate total steps
    total_steps = (
        len(steps.sequential_pre) + len(steps.parallel) + len(steps.sequential_post) + 1  # pytest
    )
    current_step = 0

    # Phase 1: Sequential pre-steps (ruff format)
    for description, action in steps.sequential_pre:
        current_step += 1
        click.echo(f"[{current_step}/{total_steps}] {description}")
        action()

    # Phase 2: Parallel checks (or sequential if parallel=False)
    if parallel and len(steps.parallel) > 1:
        parallel_commands = _build_parallel_commands(config, strict_format=resolved_strict_format)
        click.echo(
            f"[{current_step + 1}-{current_step + len(parallel_commands)}/{total_steps}] Running {len(parallel_commands)} checks in parallel..."
        )
        results = _run_parallel_steps_subprocess(parallel_commands)
        all_passed = _display_parallel_results(results, current_step + 1, total_steps, verbose=verbose)
        current_step += len(parallel_commands)

        if not all_passed:
            # Show which checks failed
            failed = [r.name for r in results if not r.success]
            click.echo(f"Failed checks: {', '.join(failed)}", err=True)
            raise SystemExit(1)
    else:
        # Run sequentially
        for description, action in steps.parallel:
            current_step += 1
            click.echo(f"[{current_step}/{total_steps}] {description}")
            action()

    # Phase 3: Sequential post-steps (pip-audit)
    for description, action in steps.sequential_post:
        current_step += 1
        click.echo(f"[{current_step}/{total_steps}] {description}")
        action()

    # Phase 4: Pytest (always sequential)
    current_step += 1
    pytest_label = "Pytest with coverage" if coverage != "off" else "Pytest"
    click.echo(f"[{current_step}/{total_steps}] {pytest_label}")
    _run_pytest_step(config, coverage, verbose)

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
