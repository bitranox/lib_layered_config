"""Example configuration asset generation helpers.

Purpose
-------
Produce reproducible configuration scaffolding referenced in documentation and
onboarding materials. This module belongs to the outer ring of the architecture
and has no runtime coupling to the composition root.

Contents
--------
* :data:`DEFAULT_HOST_PLACEHOLDER` – placeholder name used in host examples.
* :class:`ExampleSpec` – lightweight dataclass describing one generated file.
* :func:`generate_examples` – public API that writes examples to disk.
* :func:`_build_specs` – internal helper producing the sequence of specs.

System Role
-----------
Called by docs/scripts to create filesystem layouts demonstrating how layered
configuration works.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import os

DEFAULT_HOST_PLACEHOLDER = "your-hostname"
"""Filename stub used for host-specific example files (documented in README)."""


@dataclass(slots=True)
class ExampleSpec:
    """Describe a single example file to be written to disk.

    Why
    ----
    Encapsulate metadata for templated files so generation logic stays simple
    and testable.

    Attributes
    ----------
    relative_path:
        Path relative to the destination directory where the example will be
        created.
    content:
        File contents (UTF-8 text) including explanatory comments.
    """

    relative_path: Path
    content: str


def generate_examples(
    destination: str | Path,
    *,
    slug: str,
    vendor: str,
    app: str,
    force: bool = False,
    platform: str | None = None,
) -> list[Path]:
    """Write the canonical example files for each configuration layer.

    Why
    ----
    Quickly bootstrap demos, tests, or documentation assets that mirror the
    recommended filesystem layout.

    Parameters
    ----------
    destination:
        Directory that will receive the generated structure.
    slug / vendor / app:
        Metadata used to fill placeholders so examples read naturally.
    force:
        When ``True`` existing files are overwritten; otherwise the function
        skips files that already exist.
    platform:
        Optional override for the OS layout (``"posix"`` or ``"windows"``).
        When ``None`` it follows the running interpreter platform.

    Returns
    -------
    list[Path]
        Absolute file paths written during this invocation.

    Side Effects
    ------------
    Creates directories and writes files under ``destination``.

    Examples
    --------
    >>> from tempfile import TemporaryDirectory
    >>> tmp = TemporaryDirectory()
    >>> generated = generate_examples(tmp.name, slug='demo', vendor='Acme', app='ConfigKit')
    >>> any(path.name == 'config.toml' for path in generated)
    True
    >>> tmp.cleanup()
    """

    dest = Path(destination)
    resolved_platform = _normalise_platform(platform)
    specs = _build_specs(dest, slug=slug, vendor=vendor, app=app, platform=resolved_platform)
    written: list[Path] = []
    for spec in specs:
        path = dest / spec.relative_path
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(spec.content, encoding="utf-8")
        written.append(path)
    return written


def _build_specs(destination: Path, *, slug: str, vendor: str, app: str, platform: str) -> Iterator[ExampleSpec]:
    """Yield :class:`ExampleSpec` instances for each canonical layer.

    Why
    ----
    Keep file templates in one place so they stay aligned with documentation.

    Parameters
    ----------
    destination:
        Destination root (unused but kept for future dynamic templates).

    Examples
    --------
    >>> specs = list(_build_specs(Path('.'), slug='demo', vendor='Acme', app='ConfigKit', platform='posix'))
    >>> specs[0].relative_path.as_posix()
    'etc/demo/config.toml'
    """

    if platform == "windows":
        win_app = Path("ProgramData") / vendor / app
        yield ExampleSpec(
            win_app / "config.toml",
            f"""# Application-wide defaults for {slug}\n[service]\nendpoint = \"https://api.example.com\"\ntimeout = 10\n""",
        )
        yield ExampleSpec(
            win_app / "hosts" / f"{DEFAULT_HOST_PLACEHOLDER}.toml",
            """# Host overrides (replace filename with the machine hostname)\n[service]\ntimeout = 15\n""",
        )
        win_user = Path("AppData/Roaming") / vendor / app
        yield ExampleSpec(
            win_user / "config.toml",
            f"""# User-specific preferences for {vendor} {app}\n[service]\nretry = 2\n""",
        )
        yield ExampleSpec(
            win_user / "config.d" / "10-override.toml",
            """# Split overrides live in config.d/ and apply in lexical order\n[service]\nretry = 3\n""",
        )
        yield ExampleSpec(
            Path(".env.example"),
            f"""# Copy to .env to provide secrets and local overrides\n{slug.replace("-", "_").upper()}_SERVICE__PASSWORD=changeme\n""",
        )
        return

    linux_slug = slug
    yield ExampleSpec(
        Path(f"etc/{linux_slug}/config.toml"),
        f"""# Application-wide defaults for {slug}\n[service]\nendpoint = \"https://api.example.com\"\ntimeout = 10\n""",
    )
    yield ExampleSpec(
        Path(f"etc/{linux_slug}/hosts/{DEFAULT_HOST_PLACEHOLDER}.toml"),
        """# Host overrides (replace filename with the machine hostname)\n[service]\ntimeout = 15\n""",
    )
    yield ExampleSpec(
        Path(f"xdg/{linux_slug}/config.toml"),
        f"""# User-specific preferences for {vendor} {app}\n[service]\nretry = 2\n""",
    )
    yield ExampleSpec(
        Path(f"xdg/{linux_slug}/config.d/10-override.toml"),
        """# Split overrides live in config.d/ and apply in lexical order\n[service]\nretry = 3\n""",
    )
    yield ExampleSpec(
        Path(".env.example"),
        f"""# Copy to .env to provide secrets and local overrides\n{slug.replace("-", "_").upper()}_SERVICE__PASSWORD=changeme\n""",
    )


def _normalise_platform(value: str | None) -> str:
    """Return a canonical platform key for example generation."""

    if value is None:
        return "windows" if os.name == "nt" else "posix"
    lowered = value.lower()
    if lowered.startswith("win"):
        return "windows"
    return "posix"
