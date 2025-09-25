from __future__ import annotations

import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - pyproject parsing will degrade gracefully
        tomllib = None  # type: ignore


@dataclass(slots=True)
class RunResult:
    code: int
    out: str
    err: str


@dataclass(slots=True)
class ProjectMetadata:
    name: str
    slug: str
    repo_url: str
    repo_host: str
    repo_owner: str
    repo_name: str
    homepage: str
    import_package: str
    coverage_source: str

    @property
    def brew_formula_path(self) -> str:
        return f"packaging/brew/Formula/{self.slug}.rb"

    def github_tarball_url(self, version: str) -> str:
        if self.repo_host == "github.com" and self.repo_owner and self.repo_name:
            return f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/tags/v{version}.tar.gz"
        return ""


_PYPROJECT_DATA_CACHE: dict[Path, dict[str, Any]] = {}
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
    return subprocess.call(["bash", "-lc", f"command -v {shlex.quote(name)} >/dev/null 2>&1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def _normalize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or value.replace("_", "-").lower()


def _load_pyproject(pyproject: Path) -> dict[str, Any]:
    path = pyproject.resolve()
    cached = _PYPROJECT_DATA_CACHE.get(path)
    if cached is not None:
        return cached
    text = path.read_text(encoding="utf-8")
    data: dict[str, Any] = {}
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except Exception:
            data = {}
    _PYPROJECT_DATA_CACHE[path] = data
    return data


def _derive_import_package(data: dict[str, Any], fallback: str) -> str:
    try:
        packages = data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {}).get("packages", [])
        if isinstance(packages, list) and packages:
            first = packages[0]
            if isinstance(first, str) and first:
                return Path(first).name
    except AttributeError:
        pass
    project_scripts = data.get("project", {}).get("scripts", {})
    if isinstance(project_scripts, dict):
        for value in project_scripts.values():
            if isinstance(value, str) and ":" in value:
                module = value.split(":", 1)[0]
                return module.split(".", 1)[0]
    return fallback.replace("-", "_")


def _derive_coverage_source(data: dict[str, Any], fallback: str) -> str:
    try:
        sources = data.get("tool", {}).get("coverage", {}).get("run", {}).get("source", [])
        if isinstance(sources, list) and sources:
            first = sources[0]
            if isinstance(first, str) and first:
                return first
    except AttributeError:
        pass
    return fallback


def get_project_metadata(pyproject: Path = Path("pyproject.toml")) -> ProjectMetadata:
    path = pyproject.resolve()
    cached = _METADATA_CACHE.get(path)
    if cached is not None:
        return cached

    data = _load_pyproject(pyproject)
    project = data.get("project", {}) if isinstance(data, dict) else {}
    name = str(project.get("name") or pyproject.stem).strip() or "project"
    slug = _normalize_slug(name)

    urls = project.get("urls", {}) if isinstance(project, dict) else {}
    repo_url = str(urls.get("Repository") or "")
    homepage = str(urls.get("Homepage") or project.get("homepage") or "")
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

    meta = ProjectMetadata(
        name=name,
        slug=slug,
        repo_url=repo_url,
        repo_host=repo_host,
        repo_owner=repo_owner,
        repo_name=repo_name,
        homepage=homepage,
        import_package=import_package,
        coverage_source=coverage_source,
    )
    _METADATA_CACHE[path] = meta
    return meta


def read_version_from_pyproject(pyproject: Path = Path("pyproject.toml")) -> str:
    data = _load_pyproject(pyproject)
    project = data.get("project", {}) if isinstance(data, dict) else {}
    version = str(project.get("version") or "").strip()
    if version:
        return version
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([0-9]+(?:\.[0-9]+){2})"', text)
    return match.group(1) if match else ""


def ensure_clean_git_tree() -> None:
    dirty = subprocess.call(["bash", "-lc", "! git diff --quiet || ! git diff --cached --quiet"], stdout=subprocess.DEVNULL)
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
    return subprocess.call(["bash", "-lc", f"git rev-parse -q --verify {shlex.quote('refs/tags/' + name)} >/dev/null"], stdout=subprocess.DEVNULL) == 0


def git_create_annotated_tag(name: str, message: str) -> None:
    run(["git", "tag", "-a", name, "-m", message])


def git_push(remote: str, ref: str) -> None:
    run(["git", "push", remote, ref])


def gh_available() -> bool:
    return cmd_exists("gh")


def gh_release_exists(tag: str) -> bool:
    return subprocess.call(["bash", "-lc", f"gh release view {shlex.quote(tag)} >/dev/null 2>&1"], stdout=subprocess.DEVNULL) == 0


def gh_release_create(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "create", tag, "-t", title, "-n", body], check=False)


def gh_release_edit(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "edit", tag, "-t", title, "-n", body], check=False)


def sync_packaging() -> None:
    run([sys.executable, "scripts/bump_version.py", "--sync-packaging"], check=False)


def bootstrap_dev() -> None:
    if not (cmd_exists("ruff") and cmd_exists("pyright")):
        print("[bootstrap] Installing dev dependencies via 'pip install -e .[dev]'")
        run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"])
    try:
        from importlib import import_module

        import_module("sqlite3")
    except Exception:
        run([sys.executable, "-m", "pip", "install", "pysqlite3-binary"], check=False)
