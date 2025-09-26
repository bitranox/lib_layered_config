from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._utils import (  # noqa: E402
    RunResult,
    bootstrap_dev,
    cmd_exists,
    get_project_metadata,
    run,
    sync_packaging,
)

PROJECT = get_project_metadata()
COVERAGE_TARGET = PROJECT.coverage_source
CODECOV_COMMIT_MESSAGE = "test: auto commit before Codecov upload"
_TOML_MODULE: ModuleType | None = None
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_default_env() -> dict[str, str]:
    """Return the base environment for subprocess execution."""
    pythonpath = os.pathsep.join(filter(None, [str(PROJECT_ROOT / "src"), os.environ.get("PYTHONPATH")]))
    return os.environ | {"PYTHONPATH": pythonpath}


DEFAULT_ENV = _build_default_env()


def _refresh_default_env() -> None:
    """Recompute DEFAULT_ENV after environment mutations."""
    global DEFAULT_ENV
    DEFAULT_ENV = _build_default_env()


@click.command(help="Run lints, type-check, tests with coverage, and Codecov upload if configured")
@click.option("--coverage", type=click.Choice(["on", "auto", "off"]), default="on")
@click.option("--verbose", "-v", is_flag=True, help="Print executed commands before running them")
def main(coverage: str, verbose: bool) -> None:
    env_verbose = os.getenv("TEST_VERBOSE", "").lower()
    if not verbose and env_verbose in {"1", "true", "yes", "on"}:
        verbose = True

    def _run(
        cmd: list[str] | str,
        *,
        env: dict[str, str] | None = None,
        check: bool = True,
        capture: bool = True,
        label: str | None = None,
    ) -> RunResult:
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
        merged_env = DEFAULT_ENV if env is None else DEFAULT_ENV | env
        merged_env = merged_env.copy()
        prefix = str(Path(__file__).resolve().parents[1] / "src")
        merged_env["PYTHONPATH"] = (
            prefix if not merged_env.get("PYTHONPATH") else prefix + os.pathsep + merged_env["PYTHONPATH"]
        )
        result = run(cmd, env=merged_env, check=check, capture=capture)  # type: ignore[arg-type]
        if verbose and label:
            click.echo(f"    -> {label}: exit={result.code} out={bool(result.out)} err={bool(result.err)}")
        return result

    bootstrap_dev()

    click.echo("[0/5] Sync packaging (conda/brew/nix) with pyproject")
    sync_packaging()

    click.echo("[1/5] Ruff lint")
    _run(["ruff", "check", "."], check=False)  # type: ignore[list-item]

    click.echo("[2/5] Ruff format (apply)")
    _run(["ruff", "format", "."], check=False)  # type: ignore[list-item]

    click.echo("[3/5] Import-linter contracts")
    _run([sys.executable, "-m", "lint_imports", "--config", "pyproject.toml"], check=False)

    click.echo("[4/5] Pyright type-check")
    _run(["pyright"], check=False)  # type: ignore[list-item]

    click.echo("[5/5] Pytest with coverage")
    for f in (".coverage", "coverage.xml"):
        try:
            Path(f).unlink()
        except FileNotFoundError:
            pass

    if coverage == "on" or (coverage == "auto" and (os.getenv("CI") or os.getenv("CODECOV_TOKEN"))):
        click.echo("[coverage] enabled")
        fail_under = _read_fail_under(Path("pyproject.toml"))
        with tempfile.TemporaryDirectory() as tmp:
            cov_file = Path(tmp) / ".coverage"
            click.echo(f"[coverage] file={cov_file}")
            env = os.environ | {"COVERAGE_FILE": str(cov_file)}
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
                click.echo("[pytest] failed; skipping commit and Codecov upload", err=True)
                raise SystemExit(pytest_result.code)
    else:
        click.echo("[coverage] disabled (set --coverage=on to force)")
        pytest_result = _run(["python", "-m", "pytest", "-vv"], capture=False, label="pytest-no-cov")  # type: ignore[list-item]
        if pytest_result.code != 0:
            click.echo("[pytest] failed; skipping commit and Codecov upload", err=True)
            raise SystemExit(pytest_result.code)

    _ensure_codecov_token()

    upload_result: RunResult | None = None
    uploaded = False
    commit_sha: str | None = None

    if Path("coverage.xml").exists():
        try:
            commit_sha = _commit_before_upload()
        except RuntimeError as exc:
            click.echo(f"[git] {exc}", err=True)
            click.echo("[git] Aborting Codecov upload")
            return

        try:
            click.echo(f"[git] Prepared commit {commit_sha} for Codecov upload")
            click.echo("Uploading coverage to Codecov")
            codecov_name = f"local-{platform.system()}-{platform.python_version()}"
            if cmd_exists("codecov"):
                upload_result = _run(
                    [
                        "codecov",
                        "-f",
                        "coverage.xml",
                        "-F",
                        "local",
                        "-n",
                        codecov_name,
                    ],
                    check=False,
                    capture=False,
                    label="codecov-upload-cli",
                )
            else:
                token = os.getenv("CODECOV_TOKEN")
                download = _run(
                    ["curl", "-s", "https://codecov.io/bash", "-o", "codecov.sh"],
                    capture=False,
                    label="codecov-download",
                )
                if download.code == 0:
                    upload_cmd = [
                        "bash",
                        "codecov.sh",
                        "-f",
                        "coverage.xml",
                        "-F",
                        "local",
                        "-n",
                        codecov_name,
                    ]
                    if token:
                        upload_cmd.extend(["-t", token])
                    upload_result = _run(
                        upload_cmd,
                        check=False,
                        capture=False,
                        label="codecov-upload-fallback",
                    )
                else:
                    click.echo("[codecov] failed to download uploader", err=True)
                try:
                    Path("codecov.sh").unlink()
                except FileNotFoundError:
                    pass

            if upload_result is not None:
                if upload_result.code == 0:
                    click.echo("[codecov] upload succeeded")
                    uploaded = True
                else:
                    click.echo(f"[codecov] upload failed (exit {upload_result.code})")
        finally:
            _cleanup_codecov_commit(commit_sha)
    else:
        click.echo("Skipping Codecov upload: coverage.xml not found")

    if Path("coverage.xml").exists():
        if uploaded:
            click.echo("All checks passed (coverage uploaded)")
        else:
            click.echo("Checks finished (coverage upload not confirmed)")
    else:
        click.echo("Checks finished (coverage.xml missing, upload skipped)")


def _get_toml_module() -> ModuleType:
    global _TOML_MODULE
    if _TOML_MODULE is not None:
        return _TOML_MODULE

    try:
        import tomllib as module  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        try:
            import tomli as module  # type: ignore[import-not-found, assignment]
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "tomllib/tomli modules are unavailable. Install the 'tomli' package for Python < 3.11."
            ) from exc

    _TOML_MODULE = module
    return module


def _read_fail_under(pyproject: Path) -> int:
    try:
        toml_module = _get_toml_module()
        data = toml_module.loads(pyproject.read_text())
        return int(data["tool"]["coverage"]["report"]["fail_under"])
    except Exception:
        return 80


def _commit_before_upload() -> str:
    """Create a local commit (allow-empty) before uploading coverage."""

    click.echo("[git] Creating local commit before Codecov upload")

    commit_message = CODECOV_COMMIT_MESSAGE
    commit_proc = subprocess.run(
        ["git", "commit", "--allow-empty", "-m", commit_message],
        capture_output=True,
        text=True,
        check=False,
    )
    if commit_proc.returncode != 0:
        message = commit_proc.stderr.strip() or commit_proc.stdout.strip() or "git commit failed"
        raise RuntimeError(message)
    if commit_proc.stdout.strip():
        click.echo(commit_proc.stdout.strip())
    if commit_proc.stderr.strip():
        click.echo(commit_proc.stderr.strip(), err=True)

    rev_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_proc.returncode != 0:
        message = rev_proc.stderr.strip() or "failed to resolve commit SHA"
        raise RuntimeError(message)

    commit_sha = rev_proc.stdout.strip()
    click.echo(f"[git] Created commit {commit_sha}")
    return commit_sha


def _cleanup_codecov_commit(commit_sha: str | None) -> None:
    """Remove the helper commit when it still sits at HEAD with the expected message."""

    if not commit_sha:
        return

    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head_proc.returncode != 0:
        message = head_proc.stderr.strip() or "failed to resolve HEAD during cleanup"
        click.echo(f"[git] Cleanup skipped: {message}", err=True)
        return

    head_sha = head_proc.stdout.strip()
    if head_sha != commit_sha:
        click.echo("[git] Cleanup skipped: HEAD advanced past Codecov commit")
        return

    message_proc = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=False,
    )
    if message_proc.returncode != 0:
        note = message_proc.stderr.strip() or "unable to read commit message"
        click.echo(f"[git] Cleanup skipped: {note}", err=True)
        return

    commit_message = message_proc.stdout.strip()
    if commit_message != CODECOV_COMMIT_MESSAGE:
        click.echo("[git] Cleanup skipped: top commit message does not match helper")
        return

    reset_proc = subprocess.run(
        ["git", "reset", "--soft", "HEAD~1"],
        capture_output=True,
        text=True,
        check=False,
    )
    if reset_proc.returncode != 0:
        message = reset_proc.stderr.strip() or reset_proc.stdout.strip() or "git reset failed"
        click.echo(f"[git] Cleanup failed: {message}", err=True)
        return

    if reset_proc.stdout.strip():
        click.echo(reset_proc.stdout.strip())
    if reset_proc.stderr.strip():
        click.echo(reset_proc.stderr.strip(), err=True)

    click.echo("[git] Removed temporary Codecov commit")


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


if __name__ == "__main__":
    main()
