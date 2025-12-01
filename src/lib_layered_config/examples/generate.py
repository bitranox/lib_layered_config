"""Example configuration asset generation helpers.

Produce reproducible configuration scaffolding referenced in documentation and
onboarding materials. This module belongs to the outer ring of the architecture
and has no runtime coupling to the composition root.

Contents:
    - ``DEFAULT_HOST_PLACEHOLDER``: filename stub for host examples.
    - ``ExampleSpec``: dataclass capturing a relative path and text content.
    - ``generate_examples``: public orchestration expressed through helper
      verbs.
    - ``_build_specs``: yields platform-aware specifications.
    - ``_write_spec`` / ``_should_write`` / ``_ensure_parent``: tiny filesystem
      helpers that narrate how files are written.

System Role:
    Called by docs/scripts to create filesystem layouts demonstrating how layered
    configuration works.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .._platform import normalise_examples_platform

DEFAULT_HOST_PLACEHOLDER = "your-hostname"
"""Filename stub used for host-specific example files (documented in README)."""


@dataclass(slots=True)
class ExampleSpec:
    """Describe a single example file to be written to disk.

    Encapsulate metadata for templated files so generation logic stays simple
    and testable.

    Attributes:
        relative_path: Path relative to the destination directory where the example will be
            created.
        content: File contents (UTF-8 text) including explanatory comments.
    """

    relative_path: Path
    content: str


@dataclass(frozen=True, slots=True)
class ExamplePlan:
    """Plan describing how example files should be generated.

    Attributes:
        destination: Target directory where files will be written.
        slug: Configuration slug used in templates.
        vendor: Vendor name interpolated into paths/content.
        app: Application name interpolated into paths/content.
        force: Whether generation should overwrite existing files.
        platform: Normalised platform key (``"posix"`` or ``"windows"``).
    """

    destination: Path
    slug: str
    vendor: str
    app: str
    force: bool
    platform: str


def generate_examples(
    destination: str | Path,
    *,
    slug: str,
    vendor: str,
    app: str,
    force: bool = False,
    platform: str | None = None,
) -> list[Path]:
    """Write canonical example files for each configuration layer.

    Creates directories and files under *destination* mirroring the recommended
    filesystem layout. Returns paths of files written. Use *force=True* to
    overwrite existing files; *platform* overrides OS detection ("posix"/"windows").
    """
    plan = _build_example_plan(
        destination=destination,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=platform,
    )
    specs = _build_specs(plan.destination, slug=plan.slug, vendor=plan.vendor, app=plan.app, platform=plan.platform)
    return _write_examples(plan.destination, specs, plan.force)


def _build_example_plan(
    *,
    destination: str | Path,
    slug: str,
    vendor: str,
    app: str,
    force: bool,
    platform: str | None,
) -> ExamplePlan:
    """Compose an example generation plan.

    Args:
        destination: Root destination directory (string or :class:`Path`).
        slug: Identifiers embedded into generated content.
        vendor: Identifiers embedded into generated content.
        app: Identifiers embedded into generated content.
        force: Whether existing files may be overwritten.
        platform: Optional platform override supplied by the caller.

    Returns:
        ExamplePlan: Immutable plan consumed by downstream helpers.
    """
    dest = Path(destination)
    return ExamplePlan(
        destination=dest,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=_normalise_platform(platform),
    )


def _write_examples(destination: Path, specs: Iterator[ExampleSpec], force: bool) -> list[Path]:
    """Write all ``specs`` under *destination* honouring the *force* flag.

    Centralise the loop that applies ``force`` semantics and records written paths.

    Args:
        destination: Root directory that will receive the examples.
        specs: Iterator of example specifications to materialise.
        force: When ``True`` existing files are overwritten.

    Returns:
        list[Path]: Paths written during this invocation.

    Side Effects:
        Creates directories and writes files to disk.
    """
    written: list[Path] = []
    for spec in specs:
        path = destination / spec.relative_path
        if not _should_write(path, force):
            continue
        _ensure_parent(path)
        _write_spec(path, spec)
        written.append(path)
    return written


def _write_spec(path: Path, spec: ExampleSpec) -> None:
    """Persist ``spec`` content at *path* using UTF-8 encoding.

    Keep the actual write primitive isolated for easy stubbing in tests.

    Args:
        path: Destination path for the example file.
        spec: Example specification containing content to write.

    Side Effects:
        Writes UTF-8 text to *path*.
    """
    path.write_text(spec.content, encoding="utf-8")


def _should_write(path: Path, force: bool) -> bool:
    """Return ``True`` when *path* should be written respecting *force*.

    Avoid clobbering existing content unless the caller explicitly requests it.

    Args:
        path: Destination path under consideration.
        force: Whether overwriting is allowed.

    Returns:
        bool: ``True`` when writing should proceed.

    Examples:
        >>> from tempfile import NamedTemporaryFile
        >>> tmp = NamedTemporaryFile(delete=True)
        >>> _should_write(Path(tmp.name), force=False)
        False
        >>> _should_write(Path(tmp.name), force=True)
        True
        >>> tmp.close()
    """
    return force or not path.exists()


def _ensure_parent(path: Path) -> None:
    """Create parent directories for *path* when missing.

    Ensure example generation works even on fresh directories.

    Args:
        path: Target file path whose parent directories should exist.

    Side Effects:
        Creates directories on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def _build_specs(destination: Path, *, slug: str, vendor: str, app: str, platform: str) -> Iterator[ExampleSpec]:
    """Yield :class:`ExampleSpec` instances for each canonical layer.

    Keep file templates in one place so they stay aligned with documentation.

    Args:
        destination: Destination root (currently unused; reserved for future dynamic templates).
        slug: Metadata interpolated into template content.
        vendor: Metadata interpolated into template content.
        app: Metadata interpolated into template content.
        platform: Normalised platform key (``"posix"`` or ``"windows"``).

    Yields:
        ExampleSpec: Specification describing one file to render.

    Examples:
        >>> specs = list(_build_specs(Path('.'), slug='demo', vendor='Acme', app='ConfigKit', platform='posix'))
        >>> specs[0].relative_path.as_posix()
        'xdg/demo/config.toml'
    """
    yield from _platform_specs(slug=slug, vendor=vendor, app=app, platform=platform)
    yield _env_example(slug)


def _platform_specs(*, slug: str, vendor: str, app: str, platform: str) -> Iterator[ExampleSpec]:
    """Dispatch to platform-specific example specifications.

    Args:
        slug: Metadata interpolated into generated content.
        vendor: Metadata interpolated into generated content.
        app: Metadata interpolated into generated content.
        platform: Normalised platform key (``"posix"`` or ``"windows"``).

    Yields:
        ExampleSpec: Specifications describing files to create.
    """
    if platform == "windows":
        yield from _windows_specs(slug=slug, vendor=vendor, app=app)
        return
    yield from _posix_specs(slug=slug, vendor=vendor, app=app)


def _windows_specs(*, slug: str, vendor: str, app: str) -> Iterator[ExampleSpec]:
    """Yield Windows layout examples.

    Args:
        slug: Metadata interpolated into template content.
        vendor: Metadata interpolated into template content.
        app: Metadata interpolated into template content.

    Yields:
        ExampleSpec: Specification for each Windows example file.
    """
    root = Path("ProgramData") / vendor / app
    yield ExampleSpec(root / "config.toml", _app_defaults_body(slug))
    yield ExampleSpec(root / "hosts" / f"{DEFAULT_HOST_PLACEHOLDER}.toml", _host_override_body())
    user_root = Path("AppData") / "Roaming" / vendor / app
    yield ExampleSpec(user_root / "config.toml", _user_preferences_body(vendor, app))
    yield ExampleSpec(user_root / "config.d" / "10-override.toml", _split_override_body())


def _posix_specs(*, slug: str, vendor: str, app: str) -> Iterator[ExampleSpec]:
    """Yield POSIX layout examples following XDG Base Directory specification.

    Args:
        slug: Metadata interpolated into template content.
        vendor: Metadata interpolated into template content.
        app: Metadata interpolated into template content.

    Yields:
        ExampleSpec: Specification for each POSIX example file.
    """
    # System-wide app configuration (XDG-compliant)
    app_root = Path("xdg") / slug
    yield ExampleSpec(app_root / "config.toml", _app_defaults_body(slug))
    yield ExampleSpec(app_root / "hosts" / f"{DEFAULT_HOST_PLACEHOLDER}.toml", _host_override_body())
    # User-level configuration
    user_root = Path("home") / slug
    yield ExampleSpec(user_root / "config.toml", _user_preferences_body(vendor, app))
    yield ExampleSpec(user_root / "config.d" / "10-override.toml", _split_override_body())


def _env_example(slug: str) -> ExampleSpec:
    """Return the shared .env example specification.

    Args:
        slug: Configuration slug used when building environment variable names.

    Returns:
        ExampleSpec: Specification describing the `.env.example` file.
    """
    return ExampleSpec(Path(".env.example"), _env_secrets_body(slug))


def _app_defaults_body(slug: str) -> str:
    """Describe baseline application defaults.

    Args:
        slug: Configuration slug inserted into the template heading.

    Returns:
        str: TOML content explaining application-wide defaults.
    """
    return f"""# Application-wide defaults for {slug}
[service]
endpoint = "https://api.example.com"
timeout = 10
"""


def _host_override_body() -> str:
    """Describe host-level overrides.

    Returns:
        str: TOML content illustrating host-specific timeout overrides.
    """
    return """# Host overrides (replace filename with the machine hostname)
[service]
timeout = 15
"""


def _user_preferences_body(vendor: str, app: str) -> str:
    """Describe user-level preferences.

    Args:
        vendor: Metadata interpolated into the template to keep prose friendly.
        app: Metadata interpolated into the template to keep prose friendly.

    Returns:
        str: TOML content illustrating user-level overrides.
    """
    return f"""# User-specific preferences for {vendor} {app}
[service]
retry = 2
"""


def _split_override_body() -> str:
    """Describe config.d overrides used for granular layering.

    Returns:
        str: TOML content emphasising lexicographic ordering of split overrides.
    """
    return """# Split overrides live in config.d/ and apply in lexical order
[service]
retry = 3
"""


def _env_secrets_body(slug: str) -> str:
    """Describe .env secrets guidance.

    Args:
        slug: Configuration slug converted into an uppercase environment prefix.

    Returns:
        str: `.env` template content reminding users to provide secrets.
    """
    key = slug.replace("-", "_").upper()
    return f"""# Copy to .env to provide secrets and local overrides
{key}___SERVICE__PASSWORD=changeme
"""


def _default_platform() -> str:
    """Return the default platform based on OS."""
    return "windows" if os.name == "nt" else "posix"


def _normalise_platform(value: str | None) -> str:
    """Return a canonical platform key for example generation.

    Args:
        value: Optional platform alias supplied by the caller.

    Returns:
        str: Normalised platform key (``"posix"`` or ``"windows"``).

    Raises:
        ValueError: When *value* is invalid.

    Examples:
        >>> _normalise_platform('posix')
        'posix'
        >>> _normalise_platform(None) in {'posix', 'windows'}
        True
    """
    if value is None:
        return _default_platform()
    try:
        resolved = normalise_examples_platform(value)
    except ValueError as exc:  # pragma: no cover - validated via CLI helpers
        raise ValueError(str(exc)) from exc
    return resolved or _default_platform()
