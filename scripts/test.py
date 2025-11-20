from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
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

PROJECT = get_project_metadata()
COVERAGE_TARGET = PROJECT.coverage_source
__all__ = ["run_tests", "run_coverage", "COVERAGE_TARGET"]
PACKAGE_SRC = Path("src") / PROJECT.import_package
_toml_module: ModuleType | None = None
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}
_DEFAULT_PIP_AUDIT_IGNORES = ("GHSA-4xh5-x5gv-qwph",)
_AuditPayload = list[dict[str, object]]


def _build_default_env() -> dict[str, str]:
    """Return the base environment for subprocess execution."""
    pythonpath = os.pathsep.join(filter(None, [str(PROJECT_ROOT / "src"), os.environ.get("PYTHONPATH")]))
    return os.environ | {"PYTHONPATH": pythonpath}


_default_env = _build_default_env()


def _refresh_default_env() -> None:
    """Recompute cached default env after environment mutations."""
    global _default_env
    _default_env = _build_default_env()


def run_coverage(*, verbose: bool = False) -> None:
    """Run pytest under coverage using python modules to avoid PATH shim issues."""

    sync_metadata_module(PROJECT)
    bootstrap_dev()
    _prune_coverage_data_files()
    _remove_report_artifacts()
    base_env = _build_default_env() | {"COVERAGE_NO_SQL": "1"}
    with tempfile.TemporaryDirectory() as tmpdir:
        coverage_file = Path(tmpdir) / ".coverage"
        env = base_env | {"COVERAGE_FILE": str(coverage_file)}
        coverage_cmd = [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-vv"]
        click.echo("[coverage] python -m coverage run -m pytest -vv")
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


def _resolve_pip_audit_ignores() -> list[str]:
    """Return consolidated list of vulnerability IDs to ignore during pip-audit."""

    extra = [token.strip() for token in os.getenv("PIP_AUDIT_IGNORE", "").split(",") if token.strip()]
    ignores: list[str] = []
    for candidate in (*_DEFAULT_PIP_AUDIT_IGNORES, *extra):
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


def run_tests(*, coverage: str = "on", verbose: bool = False, strict_format: bool | None = None) -> None:
    env_verbose = os.getenv("TEST_VERBOSE", "").lower()
    if not verbose and env_verbose in _TRUTHY:
        verbose = True

    sync_metadata_module(PROJECT)

    def _display_command(cmd: Sequence[str] | str, label: str | None, env: dict[str, str] | None) -> None:
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

    def _display_result(result: RunResult, label: str | None) -> None:
        """Display verbose result information."""
        if verbose and label:
            click.echo(f"    -> {label}: exit={result.code} out={bool(result.out)} err={bool(result.err)}")

    def _echo_output(output: str, *, to_stderr: bool = False) -> None:
        """Echo output ensuring proper newline handling."""
        click.echo(output, err=to_stderr, nl=False)
        if not output.endswith("\n"):
            click.echo(err=to_stderr)

    def _display_captured_output(result: RunResult, capture: bool) -> None:
        """Display captured stdout/stderr if verbose or on error."""
        if capture and (verbose or result.code != 0):
            if result.out:
                _echo_output(result.out)
            if result.err:
                _echo_output(result.err, to_stderr=True)

    def _run(
        cmd: Sequence[str] | str,
        *,
        env: dict[str, str] | None = None,
        check: bool = True,
        capture: bool = True,
        label: str | None = None,
    ) -> RunResult:
        """Execute command with optional display, capture, and error handling."""
        _display_command(cmd, label, env)
        merged_env = _default_env if env is None else _default_env | env
        result = run(cmd, env=merged_env, check=False, capture=capture)
        _display_result(result, label)
        _display_captured_output(result, capture)
        if check and result.code != 0:
            raise SystemExit(result.code)
        return result

    def _wrap(*, cmd: list[str] | str, label: str, capture: bool = True) -> Callable[[], None]:
        def _runner() -> None:
            _run(cmd, label=label, capture=capture)

        return _runner

    def _pip_audit_guarded() -> None:
        ignore_ids = _resolve_pip_audit_ignores()
        audit_cmd = ["pip-audit", "--skip-editable"]
        for vuln_id in ignore_ids:
            audit_cmd.extend(["--ignore-vuln", vuln_id])
        _run(audit_cmd, label="pip-audit-ignore", capture=False)

        result = _run(
            [
                "pip-audit",
                "--skip-editable",
                "--format",
                "json",
            ],
            label="pip-audit-verify",
            capture=True,
            check=False,
        )

        if result.code == 0:
            return

        try:
            payload = json.loads(result.out or "{}")
        except json.JSONDecodeError as exc:  # pragma: no cover - audit emitted non-JSON output
            click.echo("pip-audit verification output was not valid JSON", err=True)
            raise SystemExit("pip-audit verification failed") from exc

        dependencies = _extract_audit_dependencies(payload)
        allowed_vulns = set(ignore_ids)
        unexpected: list[str] = []
        for item in dependencies:
            name_candidate = item.get("name")
            package = name_candidate if isinstance(name_candidate, str) else "<unknown>"
            vulns_candidate = item.get("vulns", [])
            if not isinstance(vulns_candidate, list):
                continue
            vuln_objects = list(cast(list[object], vulns_candidate))
            vuln_entries = [cast(dict[str, object], entry) for entry in vuln_objects if isinstance(entry, dict)]
            for vuln_payload in vuln_entries:
                vuln_id_candidate = vuln_payload.get("id")
                if not isinstance(vuln_id_candidate, str):
                    continue
                if vuln_id_candidate not in allowed_vulns:
                    unexpected.append(f"{package}: {vuln_id_candidate}")

        if unexpected:
            click.echo("pip-audit reported new vulnerabilities:", err=True)
            for entry in unexpected:
                click.echo(f"  - {entry}", err=True)
            raise SystemExit("Resolve the reported vulnerabilities before continuing.")

    bootstrap_dev()

    steps: list[tuple[str, Callable[[], None]]] = []

    if strict_format is not None:
        resolved_format_strict = strict_format
    else:
        env_value = os.getenv("STRICT_RUFF_FORMAT")
        if env_value is None:
            resolved_format_strict = True
        else:
            token = env_value.strip().lower()
            if token in _TRUTHY:
                resolved_format_strict = True
            elif token in _FALSY or token == "":
                resolved_format_strict = False
            else:
                raise SystemExit("STRICT_RUFF_FORMAT must be one of {0,1,true,false,yes,no,on,off}.")

    steps.append(
        (
            "Ruff format (apply)",
            _wrap(cmd=["ruff", "format", "."], label="ruff-format-apply", capture=False),
        )
    )

    if resolved_format_strict:
        steps.append(
            (
                "Ruff format check",
                _wrap(cmd=["ruff", "format", "--check", "."], label="ruff-format-check", capture=False),
            )
        )

    steps.append(
        (
            "Ruff lint",
            _wrap(cmd=["ruff", "check", "."], label="ruff-check", capture=False),
        )
    )

    steps.append(
        (
            "Import-linter contracts",
            _wrap(
                cmd=[sys.executable, "-m", "importlinter.cli", "lint", "--config", "pyproject.toml"],
                label="import-linter",
                capture=False,
            ),
        )
    )

    steps.append(
        (
            "Pyright type-check",
            _wrap(cmd=["pyright"], label="pyright", capture=False),
        )
    )

    steps.extend(
        [
            (
                "Bandit security scan",
                _wrap(
                    cmd=["bandit", "-q", "-r", str(PACKAGE_SRC)],
                    label="bandit",
                    capture=False,
                ),
            ),
            (
                "pip-audit (guarded)",
                _pip_audit_guarded,
            ),
        ]
    )

    def _run_pytest() -> None:
        for path in (Path(".coverage"), Path("coverage.xml")):
            path.unlink(missing_ok=True)

        if coverage == "on" or (coverage == "auto" and (os.getenv("CI") or os.getenv("CODECOV_TOKEN"))):
            click.echo("[coverage] enabled")
            fail_under = _read_fail_under(Path("pyproject.toml"))
            with tempfile.TemporaryDirectory() as tmp:
                cov_file = Path(tmp) / ".coverage"
                click.echo(f"[coverage] file={cov_file}")
                env = os.environ | {"COVERAGE_FILE": str(cov_file), "COVERAGE_NO_SQL": "1"}
                pytest_result = _run(
                    [
                        "python",
                        "-m",
                        "pytest",
                        f"--cov={COVERAGE_TARGET}",
                        "--cov-report=xml:coverage.xml",
                        "--cov-report=term-missing",
                        f"--cov-fail-under={fail_under}",
                        "-vv",
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
            pytest_result = _run(
                ["python", "-m", "pytest", "-vv"],
                capture=False,
                label="pytest-no-cov",
            )
            if pytest_result.code != 0:
                click.echo("[pytest] failed; skipping Codecov upload", err=True)
                raise SystemExit(pytest_result.code)

    pytest_label = "Pytest with coverage" if coverage != "off" else "Pytest"
    steps.append((pytest_label, _run_pytest))

    total = len(steps)
    for index, (description, action) in enumerate(steps, start=1):
        click.echo(f"[{index}/{total}] {description}")
        action()

    _ensure_codecov_token()

    if Path("coverage.xml").exists():
        _prune_coverage_data_files()
        uploaded = _upload_coverage_report(run_command=_run)
        if uploaded:
            click.echo("All checks passed (coverage uploaded)")
        else:
            click.echo("Checks finished (coverage upload skipped or failed)")
    else:
        click.echo("Checks finished (coverage.xml missing, upload skipped)")


def _get_toml_module() -> ModuleType:
    global _toml_module
    if _toml_module is not None:
        return _toml_module

    try:
        import tomllib as module  # type: ignore[import-not-found]
    except ImportError:
        import tomli as module  # type: ignore[import-not-found,no-redef]

    _toml_module = module
    return module


def _read_fail_under(pyproject: Path) -> int:
    try:
        toml_module = _get_toml_module()
        data = toml_module.loads(pyproject.read_text())
        return int(data["tool"]["coverage"]["report"]["fail_under"])
    except Exception:
        return 80


def _upload_coverage_report(*, run_command: Callable[..., RunResult]) -> bool:
    """Upload ``coverage.xml`` via the official Codecov CLI when available."""

    if not Path("coverage.xml").is_file():
        return False

    if not os.getenv("CODECOV_TOKEN") and not os.getenv("CI"):
        click.echo("[codecov] CODECOV_TOKEN not configured; skipping upload (set CODECOV_TOKEN or run in CI)")
        return False

    uploader = shutil.which("codecovcli")
    if uploader is None:
        click.echo(
            "[codecov] 'codecovcli' not found; install with 'pip install codecov-cli' to enable uploads",
            err=True,
        )
        return False

    commit_sha = _resolve_commit_sha()
    if commit_sha is None:
        click.echo("[codecov] Unable to resolve git commit; skipping upload", err=True)
        return False

    branch = _resolve_git_branch()
    git_service = _resolve_git_service()
    slug = None
    if PROJECT.repo_owner and PROJECT.repo_name:
        slug = f"{PROJECT.repo_owner}/{PROJECT.repo_name}"
    label = "codecov-upload"
    args = [
        uploader,
        "upload-coverage",
        "--file",
        "coverage.xml",
        "--disable-search",
        "--fail-on-error",
        "--sha",
        commit_sha,
        "--name",
        f"local-{platform.system()}-{platform.python_version()}",
        "--flag",
        "local",
    ]
    if branch:
        args.extend(["--branch", branch])
    if git_service:
        args.extend(["--git-service", git_service])
    if slug:
        args.extend(["--slug", slug])

    env_overrides = {"CODECOV_NO_COMBINE": "1"}
    if slug:
        env_overrides.setdefault("CODECOV_SLUG", slug)
    result = run_command(args, env=env_overrides, check=False, capture=False, label=label)
    if result.code == 0:
        click.echo("[codecov] upload succeeded")
        return True

    click.echo(f"[codecov] upload failed (exit {result.code})", err=True)
    return False


def _resolve_commit_sha() -> str | None:
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
    host = (PROJECT.repo_host or "").lower()
    mapping = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",
    }
    return mapping.get(host)


def _ensure_codecov_token() -> None:
    if os.getenv("CODECOV_TOKEN"):
        _refresh_default_env()
        return
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "CODECOV_TOKEN":
            token = value.strip().strip("\"'")
            if token:
                os.environ.setdefault("CODECOV_TOKEN", token)
                _refresh_default_env()
            break


def _prune_coverage_data_files() -> None:
    """Delete SQLite coverage data shards to keep the Codecov CLI simple."""

    for path in Path.cwd().glob(".coverage*"):
        # keep the primary XML report and directories untouched
        if path.is_dir() or path.suffix == ".xml":
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            click.echo(f"[coverage] warning: unable to remove {path}: {exc}", err=True)


def _remove_report_artifacts() -> None:
    """Remove coverage reports that might lock the SQLite database on reruns."""

    for name in ("coverage.xml", "codecov.xml"):
        artifact = Path(name)
        try:
            artifact.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            click.echo(f"[coverage] warning: unable to remove {artifact}: {exc}", err=True)


def main() -> None:
    """Backward-compatible wrapper."""

    run_tests()


if __name__ == "__main__":
    main()
