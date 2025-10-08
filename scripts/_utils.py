"""Shared automation utilities for project scripts.

Purpose
-------
Collect helper functions used by the ``scripts/`` entry points (build, test,
release) so git helpers and subprocess wrappers live in one place. The behaviour mirrors the operational guidance described in
``docs/systemdesign/concept_architecture_plan.md`` and ``DEVELOPMENT.md``.

Contents
--------
* ``run`` – subprocess wrapper returning structured results.
* Metadata helpers (``get_project_metadata`` et al.) for build/test automation.
* GitHub release helpers and subprocess utilities.

System Role
-----------
Provides the scripting boundary of the clean architecture: the core library
remains framework-agnostic while operational scripts reuse these helpers to
avoid duplication and keep CI/CD behaviour consistent with documentation.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Callable, Mapping, Sequence, cast
from urllib.parse import urlparse


@dataclass(slots=True)
class RunResult:
    code: int
    out: str
    err: str


@dataclass(slots=True)
class ProjectMetadata:
    name: str
    description: str
    slug: str
    repo_url: str
    repo_host: str
    repo_owner: str
    repo_name: str
    homepage: str
    import_package: str
    coverage_source: str
    scripts: dict[str, str]

    def github_tarball_url(self, version: str) -> str:
        if self.repo_host == "github.com" and self.repo_owner and self.repo_name:
            return f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/tags/v{version}.tar.gz"
        return ""

    def resolve_cli_entry(self) -> tuple[str, str, str | None] | None:
        """Return ``(script_name, module, attr)`` for the preferred CLI entry point.

        Resolution strategy keeps ``pyproject.toml`` as the single source of truth:
        prefer scripts whose name matches the project slug/name/import package and
        fall back to the first declared script.
        """

        if not self.scripts:
            return None
        candidates = (
            self.slug,
            self.name,
            self.import_package,
            self.import_package.replace("_", "-"),
        )
        return _select_cli_entry(self.scripts, candidates)

    def diagnostic_lines(self) -> tuple[str, ...]:
        """Return human-friendly lines that summarise project metadata."""

        summary = [
            f"name={self.name}",
            f"slug={self.slug}",
            f"package={self.import_package}",
        ]
        if self.repo_url:
            summary.append(f"repository={self.repo_url}")
        if self.homepage:
            summary.append(f"homepage={self.homepage}")
        return tuple(summary)


_PYPROJECT_DATA_CACHE: dict[Path, dict[str, object]] = {}
_METADATA_CACHE: dict[Path, ProjectMetadata] = {}


def run(
    cmd: Sequence[str] | str,
    *,
    check: bool = True,
    capture: bool = True,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    dry_run: bool = False,
) -> RunResult:
    if isinstance(cmd, str):
        display = cmd
        shell = True
        args: Sequence[str] | str = cmd
    else:
        display = " ".join(shlex.quote(p) for p in cmd)
        shell = False
        args = list(cmd)
    if dry_run:
        print(f"[dry-run] {display}")
        return RunResult(0, "", "")
    proc: CompletedProcess[str] = subprocess.run(
        args,
        shell=shell,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
    )
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return RunResult(int(proc.returncode or 0), proc.stdout or "", proc.stderr or "")


def cmd_exists(name: str) -> bool:
    return (
        subprocess.call(
            ["bash", "-lc", f"command -v {shlex.quote(name)} >/dev/null 2>&1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        == 0
    )


def _normalize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or value.replace("_", "-").lower()


def _as_str_mapping(value: object) -> dict[str, object]:
    """Return a shallow copy of mapping entries with string keys."""

    result: dict[str, object] = {}
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        for key_obj, item in mapping.items():
            if isinstance(key_obj, str):
                result[key_obj] = item
    return result


def _as_str_dict(value: object) -> dict[str, str]:
    """Return a mapping containing only string keys and string values."""

    result: dict[str, str] = {}
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        for key_obj, item in mapping.items():
            if isinstance(key_obj, str) and isinstance(item, str):
                result[key_obj] = item
    return result


def _as_sequence(value: object) -> tuple[object, ...]:
    """Return a tuple for list/tuple values, otherwise an empty tuple."""

    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[object], value)
        return tuple(sequence)
    return ()


def _load_pyproject(pyproject: Path) -> dict[str, object]:
    path = pyproject.resolve()
    cached = _PYPROJECT_DATA_CACHE.get(path)
    if cached is not None:
        return cached
    raw_text = path.read_text(encoding="utf-8")
    data: dict[str, object] = {}
    try:
        load_toml = cast(Callable[[str], dict[str, Any]], getattr(tomllib, "loads"))
        parsed_obj = load_toml(raw_text)
    except Exception:
        parsed_obj = {}
    data = {str(key): value for key, value in parsed_obj.items()}
    _PYPROJECT_DATA_CACHE[path] = data
    return data


def _derive_import_package(data: dict[str, Any], fallback: str) -> str:
    tool_table = _as_str_mapping(data.get("tool"))
    hatch_table = _as_str_mapping(tool_table.get("hatch"))
    build_table = _as_str_mapping(hatch_table.get("build"))
    targets_table = _as_str_mapping(build_table.get("targets"))
    wheel_table = _as_str_mapping(targets_table.get("wheel"))
    packages_value = wheel_table.get("packages")
    for entry in _as_sequence(packages_value):
        if isinstance(entry, str) and entry:
            return Path(entry).name
    project_table = _as_str_mapping(data.get("project"))
    scripts_table = _as_str_mapping(project_table.get("scripts"))
    for script_value in scripts_table.values():
        if isinstance(script_value, str) and ":" in script_value:
            module = script_value.split(":", 1)[0]
            return module.split(".", 1)[0]
    return fallback.replace("-", "_")


def _derive_coverage_source(data: dict[str, Any], fallback: str) -> str:
    tool_table = _as_str_mapping(data.get("tool"))
    coverage_table = _as_str_mapping(tool_table.get("coverage"))
    run_table = _as_str_mapping(coverage_table.get("run"))
    sources_value = run_table.get("source")
    for entry in _as_sequence(sources_value):
        if isinstance(entry, str) and entry:
            return entry
    return fallback


def _derive_scripts(data: dict[str, Any]) -> dict[str, str]:
    project_table = _as_str_mapping(data.get("project"))
    scripts_table = _as_str_mapping(project_table.get("scripts"))
    scripts: dict[str, str] = {}
    for name, raw in scripts_table.items():
        if isinstance(raw, str):
            value = raw.strip()
            if value:
                scripts[name] = value
    return scripts


def _normalize_script_key(name: str) -> str:
    return name.replace("_", "-").lower()


def _parse_entrypoint(spec: str) -> tuple[str, str | None]:
    module, _, attr = spec.partition(":")
    module = module.strip()
    attr = attr.strip()
    return module, attr or None


def _select_cli_entry(
    scripts: Mapping[str, str],
    candidates: Sequence[str],
) -> tuple[str, str, str | None] | None:
    normalised: dict[str, tuple[str, str]] = {}
    for script_name, spec in scripts.items():
        if not spec:
            continue
        normalised[_normalize_script_key(script_name)] = (script_name, spec)

    for candidate in candidates:
        normalised_candidate = _normalize_script_key(candidate)
        match = normalised.get(normalised_candidate)
        if match is not None:
            script_name, spec = match
            module, attr = _parse_entrypoint(spec)
            return script_name, module, attr

    if normalised:
        script_name, spec = next(iter(normalised.values()))
        module, attr = _parse_entrypoint(spec)
        return script_name, module, attr

    return None


def get_project_metadata(pyproject: Path = Path("pyproject.toml")) -> ProjectMetadata:
    path = pyproject.resolve()
    cached = _METADATA_CACHE.get(path)
    if cached is not None:
        return cached

    data = _load_pyproject(pyproject)
    project_table = _as_str_mapping(data.get("project"))
    name = str(pyproject.stem)
    name_value = project_table.get("name")
    if isinstance(name_value, str) and name_value.strip():
        name = name_value.strip()
    if not name:
        name = "project"
    slug = _normalize_slug(name)

    description_value = project_table.get("description")
    description = description_value.strip() if isinstance(description_value, str) else ""

    urls_table = _as_str_dict(project_table.get("urls"))
    repo_url = urls_table.get("Repository", "")
    homepage_value = urls_table.get("Homepage")
    homepage_project = project_table.get("homepage")
    homepage = homepage_value or (homepage_project if isinstance(homepage_project, str) else "")
    repo_host = repo_owner = repo_name = ""
    if repo_url:
        parsed = urlparse(repo_url)
        repo_host = parsed.netloc.lower()
        repo_path = parsed.path.strip("/")
        if repo_path.endswith(".git"):
            repo_path = repo_path[:-4]
        parts = [p for p in repo_path.split("/") if p]
        if len(parts) >= 2:
            repo_owner, repo_name = parts[0], parts[1]

    import_package = _derive_import_package(data, name)
    coverage_source = _derive_coverage_source(data, import_package)
    scripts = _derive_scripts(data)

    meta = ProjectMetadata(
        name=name,
        description=description,
        slug=slug,
        repo_url=repo_url,
        repo_host=repo_host,
        repo_owner=repo_owner,
        repo_name=repo_name,
        homepage=homepage,
        import_package=import_package,
        coverage_source=coverage_source,
        scripts=scripts,
    )
    _METADATA_CACHE[path] = meta
    return meta


def read_version_from_pyproject(pyproject: Path = Path("pyproject.toml")) -> str:
    data = _load_pyproject(pyproject)
    project_table = _as_str_mapping(data.get("project"))
    version_value = project_table.get("version")
    if isinstance(version_value, str) and version_value.strip():
        return version_value.strip()
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([0-9]+(?:\.[0-9]+){2})"', text)
    return match.group(1) if match else ""


def ensure_clean_git_tree() -> None:
    dirty = subprocess.call(
        ["bash", "-lc", "! git diff --quiet || ! git diff --cached --quiet"], stdout=subprocess.DEVNULL
    )
    if dirty == 0:
        print("[release] Working tree not clean. Commit or stash changes first.", file=sys.stderr)
        raise SystemExit(1)


def git_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True).out.strip()


def git_delete_tag(name: str, *, remote: str | None = None) -> None:
    run(["git", "tag", "-d", name], check=False, capture=True)
    if remote:
        run(["git", "push", remote, f":refs/tags/{name}"], check=False)


def git_tag_exists(name: str) -> bool:
    return (
        subprocess.call(
            ["bash", "-lc", f"git rev-parse -q --verify {shlex.quote('refs/tags/' + name)} >/dev/null"],
            stdout=subprocess.DEVNULL,
        )
        == 0
    )


def git_create_annotated_tag(name: str, message: str) -> None:
    run(["git", "tag", "-a", name, "-m", message])


def git_push(remote: str, ref: str) -> None:
    run(["git", "push", remote, ref])


def gh_available() -> bool:
    return cmd_exists("gh")


def gh_release_exists(tag: str) -> bool:
    return (
        subprocess.call(
            ["bash", "-lc", f"gh release view {shlex.quote(tag)} >/dev/null 2>&1"], stdout=subprocess.DEVNULL
        )
        == 0
    )


def gh_release_create(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "create", tag, "-t", title, "-n", body], check=False)


def gh_release_edit(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "edit", tag, "-t", title, "-n", body], check=False)


def bootstrap_dev() -> None:
    needs_dev_install = False
    if not (cmd_exists("ruff") and cmd_exists("pyright")):
        needs_dev_install = True
    else:
        try:
            from importlib import import_module

            import_module("pytest_asyncio")
        except ModuleNotFoundError:
            needs_dev_install = True
    # Ensure pip itself is patched so security audits do not flag known CVEs on the runner.
    pip_upgrade = run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        check=False,
        capture=True,
    )
    if pip_upgrade.code != 0:
        combined_output = f"{pip_upgrade.out}\n{pip_upgrade.err}".lower()
        ci_token = os.getenv("CI", "").strip().lower()
        is_ci = ci_token in {"1", "true", "yes"}
        sha_error = "sha256" in combined_output and "hash" in combined_output
        if is_ci and sha_error:
            print("[bootstrap] pip upgrade failed due to SHA256 verification; continuing on CI")
        else:
            if pip_upgrade.out:
                print(pip_upgrade.out, end="")
            if pip_upgrade.err:
                print(pip_upgrade.err, end="", file=sys.stderr)
            raise SystemExit("pip upgrade failed; see output above")
    if needs_dev_install:
        print("[bootstrap] Installing dev dependencies via 'pip install -e .[dev]'")
        install_cmd = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
        if sys.platform.startswith("linux"):
            install_cmd.insert(4, "--break-system-packages")
        run(install_cmd)
    try:
        from importlib import import_module

        import_module("sqlite3")
    except Exception:
        sqlite_cmd = [sys.executable, "-m", "pip", "install", "pysqlite3-binary"]
        if sys.platform.startswith("linux"):
            sqlite_cmd.insert(4, "--break-system-packages")
        run(sqlite_cmd, check=False)
