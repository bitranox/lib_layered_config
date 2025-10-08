from __future__ import annotations

import argparse
import datetime as _dt
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bump version in pyproject.toml and CHANGELOG.md")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--version", help="Explicit new version X.Y.Z")
    group.add_argument(
        "--part",
        choices=["major", "minor", "patch"],
        default="patch",
        help="Semver part to bump when --version not supplied",
    )
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    return parser.parse_args()


def bump_semver(current: str, part: str) -> str:
    major, minor, patch = (int(token) for token in (current.split(".") + ["0", "0"])[:3])
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def _write_new_version(pyproject: Path, version: str) -> str:
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("version not found in pyproject.toml")
    previous = match.group(1)
    replacement = text[: match.start(1)] + version + text[match.end(1) :]
    pyproject.write_text(replacement, encoding="utf-8")
    print(f"[bump] pyproject.toml: {previous} -> {version}")
    return previous


def _update_changelog(changelog: Path, version: str) -> None:
    today = _dt.date.today().isoformat()
    entry = f"## [{version}] - {today}\n\n- _Describe changes here._\n\n"
    if changelog.exists():
        lines = changelog.read_text(encoding="utf-8").splitlines(True)
        insert_idx = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        lines[insert_idx:insert_idx] = [entry]
        changelog.write_text("".join(lines), encoding="utf-8")
    else:
        changelog.write_text("# Changelog\n\n" + entry, encoding="utf-8")
    print(f"[bump] CHANGELOG.md: inserted section for {version}")


def main() -> int:
    ns = parse_args()
    pyproject = Path(ns.pyproject)
    changelog = Path(ns.changelog)

    if ns.version:
        target = ns.version
    else:
        text = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        if not match:
            raise SystemExit("version not found in pyproject.toml")
        target = bump_semver(match.group(1), ns.part)

    _write_new_version(pyproject, target)
    _update_changelog(changelog, target)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
