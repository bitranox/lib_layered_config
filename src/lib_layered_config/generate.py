"""Example configuration asset generation helpers.

Produce reproducible configuration scaffolding referenced in documentation and
onboarding materials. This module belongs to the outer ring of the architecture
and has no runtime coupling to the composition root.

Contents:
    - ``DEFAULT_HOST_PLACEHOLDER``: filename stub for host examples.
    - ``ExampleSpec``: dataclass capturing a relative path and text content.
    - ``generate_examples``: public orchestration expressed through helper
      verbs.
    - ``generate_examples_report`` / ``ExamplesReport``: the same run, also naming the files it
      kept, for the CLI's ``--json`` envelope.
    - ``_build_specs``: yields platform-aware specifications.
    - ``_refuse_unwritable_examples``: refuses an example path it would write through, or whose
      directory cannot be made, before anything is written.
    - ``_write_spec`` / ``_should_write`` / ``_ensure_parent``: tiny filesystem
      helpers that narrate how files are written.

System Role:
    Called by docs/scripts to create filesystem layouts demonstrating how layered
    configuration works.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from ._platform import normalise_examples_platform
from .adapters._file_write import write_data
from .adapters._path_probe import PathKind, is_symlink_or_raise, kind_or_raise, uncreatable_reason
from .adapters.env.default import default_env_prefix
from .domain.errors import GenerateDestinationError
from .domain.identifiers import ExamplePlatform, validate_identifier, validate_vendor_app
from .domain.printable import escape_controls

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "DEFAULT_HOST_PLACEHOLDER",
    "ExamplePlan",
    "ExampleSpec",
    "ExamplesReport",
    "generate_examples",
    "generate_examples_report",
    "generated_before_failure",
]


DEFAULT_HOST_PLACEHOLDER = "your-hostname"
"""Filename stub used for host-specific example files (documented in README)."""

# Deploy's refusals, worded for generate: a reader of either error sees the same two rules.
_LINK_REFUSAL: Final = "is a symbolic link; generate neither writes through nor replaces one"
_NOT_REGULAR_REFUSAL: Final = "is not a regular file; generate writes only regular files"

# The attribute a failed run attaches its written paths under, read by generated_before_failure.
_WRITTEN_BEFORE_FAILURE: Final = "_lib_layered_config_generated_before_failure"


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
        platform: Normalised directory layout to write.
    """

    destination: Path
    slug: str
    vendor: str
    app: str
    force: bool
    platform: ExamplePlatform


@dataclass(frozen=True, slots=True)
class ExamplesReport:
    """What one example generation did with each file of the tree.

    Attributes:
        created: Files written by this run, in generation order.
        kept: Files that already existed and were left unchanged because *force* was off.
    """

    created: list[Path]
    kept: list[Path]


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
    filesystem layout.

    Args:
        destination: Directory that receives the example tree; created when it is missing.
        slug: Configuration slug used in paths and file contents.
        vendor: Vendor namespace used in Windows paths and file contents.
        app: Application name used in Windows paths and file contents.
        force: Overwrite existing example files instead of keeping them.
        platform: The layout to write instead of the running OS's: ``posix`` (or ``linux``,
            ``darwin``, ``mac``, ``macos``) writes ``xdg/`` and ``home/``, ``windows`` (or ``win``,
            ``win32``, ``wine``) writes ``ProgramData/`` and ``AppData/Roaming/``; both write
            ``.env.example``.

    Returns:
        The files written, in the order they were written. An existing example file kept because
        *force* is not set is left out; :func:`generate_examples_report` lists those too.

    Raises:
        ValidationError: Before anything is written, when *slug*, *vendor* or *app* is not a
            safe path segment, or *platform* is not a known platform name.
        GenerateDestinationError: Before anything is written, one line per path: with *force*,
            an example path that is a symbolic link or not a regular file (a directory, FIFO,
            device or socket); without it, an example path that is a link resolving to nothing,
            which a create would write through. Without *force* anything else already at an
            example path is kept. In both modes, a missing example path that cannot be created:
            the nearest existing path above it is not a directory (a regular file where
            *destination* or a directory an example needs belongs), or nothing above it exists (a
            Windows drive that is not mapped).

    Any error raised after the first write carries the examples already written, read back with
    :func:`generated_before_failure`.

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     written = generate_examples(tmp, slug="demo", vendor="Acme", app="Demo", platform="posix")
        ...     again = generate_examples(tmp, slug="demo", vendor="Acme", app="Demo", platform="posix")
        >>> sorted(path.name for path in written), again
        (['.env.example', '10-override.toml', 'config.toml', 'config.toml', 'your-hostname.toml'], [])
    """
    return generate_examples_report(
        destination, slug=slug, vendor=vendor, app=app, force=force, platform=platform
    ).created


def generate_examples_report(
    destination: str | Path,
    *,
    slug: str,
    vendor: str,
    app: str,
    force: bool = False,
    platform: str | None = None,
) -> ExamplesReport:
    """Run :func:`generate_examples` and report the files it kept as well as those it wrote.

    Args:
        destination: Directory that receives the example tree.
        slug: Configuration slug used in paths and file contents.
        vendor: Vendor namespace used in Windows paths and file contents.
        app: Application name used in Windows paths and file contents.
        force: Overwrite existing example files instead of keeping them.
        platform: Optional platform override, as for :func:`generate_examples`.

    Returns:
        ExamplesReport: The files created and the existing files left unchanged.

    Raises:
        ValidationError: As for :func:`generate_examples`.
        GenerateDestinationError: As for :func:`generate_examples`.

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     first = generate_examples_report(tmp, slug="demo", vendor="Acme", app="Demo", platform="posix")
        ...     again = generate_examples_report(tmp, slug="demo", vendor="Acme", app="Demo", platform="posix")
        >>> (again.created, again.kept == first.created)
        ([], True)
    """
    plan = _build_example_plan(
        destination=destination,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=platform,
    )
    specs = _build_specs(plan)
    return _write_examples(plan.destination, specs, force=plan.force)


def generated_before_failure(error: BaseException) -> list[Path]:
    """Return the example files a :func:`generate_examples` run that raised *error* had already written.

    The examples are written one after another in a fixed order, so a failure part-way (a permission
    wall, a full disk, an interrupt) leaves the earlier ones written. ``generate_examples`` and
    ``generate_examples_report`` raise the original exception unchanged and attach those paths to
    it, as ``deploy_config`` does (user decision 2026-11-16, R2-F2, for deploy).

    Args:
        error: An exception, normally one ``generate_examples`` raised.

    Returns:
        The paths in the order they were written; empty when nothing was written, or when *error*
        did not come out of ``generate_examples`` (a refusal before the first write, for one).

    Examples:
        >>> generated_before_failure(ValueError("not from generate_examples"))
        []
    """
    return list(cast("list[Path]", getattr(error, _WRITTEN_BEFORE_FAILURE, [])))


def _record_written(error: BaseException, written: list[Path]) -> None:
    """Attach a copy of *written* to *error*, read back by :func:`generated_before_failure`."""
    # An exception class that refuses new attributes (a custom __setattr__) must not have its own
    # error replaced by ours; it then simply carries no list.
    with contextlib.suppress(AttributeError, TypeError):
        setattr(error, _WRITTEN_BEFORE_FAILURE, list(written))


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

    Raises:
        ValidationError: When *slug*, *vendor* or *app* is not a safe path segment. They become
            directory names under *destination*, so ``"../x"`` or an absolute value would write
            outside it; the path resolver applies the same checks for every other entry point.
    """
    dest = Path(destination)
    return ExamplePlan(
        destination=dest,
        slug=validate_identifier(slug, "slug"),
        vendor=validate_vendor_app(vendor, "vendor"),
        app=validate_vendor_app(app, "app"),
        force=force,
        platform=_normalise_platform(platform),
    )


def _write_examples(destination: Path, specs: Iterator[ExampleSpec], *, force: bool) -> ExamplesReport:
    """Write all ``specs`` under *destination* honouring the *force* flag.

    Centralise the loop that applies ``force`` semantics and records written paths.

    Args:
        destination: Root directory that will receive the examples.
        specs: Iterator of example specifications to materialise.
        force: When ``True`` existing files are overwritten.

    Returns:
        ExamplesReport: Paths written during this invocation, and existing paths left unchanged.

    Side Effects:
        Creates directories and writes files to disk.
    """
    # Materialised up front: every path is checked before the first write. A run has a handful of
    # fixed examples, so holding them costs nothing that grows with any input.
    planned = [(destination / spec.relative_path, spec) for spec in specs]
    _refuse_unwritable_examples([path for path, _ in planned], force=force)
    written: list[Path] = []
    kept: list[Path] = []
    try:
        for path, spec in planned:
            if not _should_write(path, force=force):
                kept.append(path)
                continue
            _ensure_parent(path)
            _write_spec(path, spec)
            written.append(path)
    except BaseException as error:
        # Any failure, an interrupt included: the examples written so far stay written, so say which.
        _record_written(error, written)
        raise
    return ExamplesReport(created=written, kept=kept)


def _write_spec(path: Path, spec: ExampleSpec) -> None:
    """Persist ``spec`` content at *path* as UTF-8, with this platform's line endings.

    Written through deploy's writer with permission setting off (user decision 2026-11-16, R3-F3):
    a temp file renamed into place, so a failed write leaves the old example, except that a file a
    rename would change (hard links, another owner, its own extended attributes) is rewritten in
    place, as deploy does. ``os.linesep`` keeps what a text-mode write produced (CRLF on Windows).

    Args:
        path: Destination path for the example file.
        spec: Example specification containing content to write.

    Side Effects:
        Writes UTF-8 text to *path*.
    """
    write_data(path, spec.content.replace("\n", os.linesep).encode("utf-8"))


def _refuse_unwritable_examples(paths: list[Path], *, force: bool) -> None:
    """Refuse every example path this run would write through, before anything is written.

    Writing through a link changes the file it points at, a FIFO would block the write, and a
    directory, device or socket cannot be an example (user decision 2026-11-16, R3-F3, as deploy).
    Without *force* an existing path is kept untouched, so only a link that resolves to nothing,
    which a create would follow, is refused; a link looping on itself is one of those. A missing
    path whose directory cannot be made is refused in both modes, as deploy refuses it.

    Raises:
        GenerateDestinationError: One line per refused path.
    """
    problems = [problem for problem in (_example_problem(path, force=force) for path in paths) if problem is not None]
    if problems:
        raise GenerateDestinationError("\n".join(problems))


def _example_problem(path: Path, *, force: bool) -> str | None:
    """Why this run cannot write *path*, or ``None`` when it may write or keep it."""
    try:
        return _checked_example_problem(path, force=force)
    except ValueError as error:
        # A NUL character (or a name the OS cannot encode): no file can have it. The OS's own reason
        # names the case; the path is escaped so the message holds no NUL itself.
        return f"{escape_controls(str(path))} cannot be created: {error}"


def _checked_example_problem(path: Path, *, force: bool) -> str | None:
    """:func:`_example_problem` for a path the OS can name."""
    if is_symlink_or_raise(path):
        # A loop reads as missing too (ELOOP); a target behind a permission wall raises the OS error.
        if force or kind_or_raise(path) is PathKind.MISSING:
            return f"{path} {_LINK_REFUSAL}"
        return None
    kind = kind_or_raise(path)
    if kind is PathKind.MISSING:
        return uncreatable_reason(path)
    if not force or kind is PathKind.FILE:
        return None
    return f"{path} {_NOT_REGULAR_REFUSAL}"


def _should_write(path: Path, *, force: bool) -> bool:
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
    return force or kind_or_raise(path) is PathKind.MISSING


def _ensure_parent(path: Path) -> None:
    """Create parent directories for *path* when missing.

    Ensure example generation works even on fresh directories.

    Args:
        path: Target file path whose parent directories should exist.

    Side Effects:
        Creates directories on disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def _build_specs(plan: ExamplePlan) -> Iterator[ExampleSpec]:
    """Yield :class:`ExampleSpec` instances for each canonical layer.

    Keep file templates in one place so they stay aligned with documentation.

    Args:
        plan: The validated identifiers and the layout to write.

    Yields:
        ExampleSpec: Specification describing one file to render.

    Examples:
        >>> plan = _build_example_plan(
        ...     destination='.', slug='demo', vendor='Acme', app='ConfigKit', force=False, platform='posix'
        ... )
        >>> specs = list(_build_specs(plan))
        >>> specs[0].relative_path.as_posix()
        'xdg/demo/config.toml'
    """
    yield from _platform_specs(plan)
    yield _env_example(plan.slug)


def _platform_specs(plan: ExamplePlan) -> Iterator[ExampleSpec]:
    """Dispatch to platform-specific example specifications.

    Args:
        plan: The validated identifiers and the layout to write.

    Yields:
        ExampleSpec: Specifications describing files to create.
    """
    if plan.platform == ExamplePlatform.WINDOWS:
        yield from _windows_specs(plan)
        return
    yield from _posix_specs(plan)


def _windows_specs(plan: ExamplePlan) -> Iterator[ExampleSpec]:
    """Yield Windows layout examples.

    Args:
        plan: The validated identifiers interpolated into paths and template content.

    Yields:
        ExampleSpec: Specification for each Windows example file.
    """
    root = Path("ProgramData") / plan.vendor / plan.app
    yield ExampleSpec(root / "config.toml", _app_defaults_body(plan.slug))
    yield ExampleSpec(root / "hosts" / f"{DEFAULT_HOST_PLACEHOLDER}.toml", _host_override_body())
    user_root = Path("AppData") / "Roaming" / plan.vendor / plan.app
    yield ExampleSpec(user_root / "config.toml", _user_preferences_body(plan.vendor, plan.app))
    yield ExampleSpec(user_root / "config.d" / "10-override.toml", _split_override_body())


def _posix_specs(plan: ExamplePlan) -> Iterator[ExampleSpec]:
    """Yield POSIX layout examples following XDG Base Directory specification.

    Args:
        plan: The validated identifiers interpolated into paths and template content.

    Yields:
        ExampleSpec: Specification for each POSIX example file.
    """
    # System-wide app configuration (XDG-compliant)
    app_root = Path("xdg") / plan.slug
    yield ExampleSpec(app_root / "config.toml", _app_defaults_body(plan.slug))
    yield ExampleSpec(app_root / "hosts" / f"{DEFAULT_HOST_PLACEHOLDER}.toml", _host_override_body())
    # User-level configuration
    user_root = Path("home") / plan.slug
    yield ExampleSpec(user_root / "config.toml", _user_preferences_body(plan.vendor, plan.app))
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

    A ``.env`` key takes no environment prefix (``SERVICE__PASSWORD``), so the template writes the key
    bare and names the prefixed variable only in a comment, for setting the same value in the
    environment instead.

    Args:
        slug: Configuration slug converted into the uppercase environment prefix the comment names.

    Returns:
        str: `.env` template content reminding users to provide secrets.

    Examples:
        >>> print(_env_secrets_body("my-app"), end="")
        # Copy to .env to provide secrets and local overrides.
        # A .env key takes no prefix; in the environment this one is MY_APP___SERVICE__PASSWORD.
        SERVICE__PASSWORD=changeme
    """
    return f"""# Copy to .env to provide secrets and local overrides.
# A .env key takes no prefix; in the environment this one is {default_env_prefix(slug)}SERVICE__PASSWORD.
SERVICE__PASSWORD=changeme
"""


def _default_platform() -> ExamplePlatform:
    """Return the default layout for the running OS."""
    return ExamplePlatform.WINDOWS if os.name == "nt" else ExamplePlatform.POSIX


def _normalise_platform(value: str | None) -> ExamplePlatform:
    """Return a canonical platform key for example generation.

    Args:
        value: Optional platform alias supplied by the caller.

    Returns:
        ExamplePlatform: Normalised directory layout.

    Raises:
        ValidationError: When *value* is not a known platform name; the message lists them.

    Examples:
        >>> _normalise_platform('posix')
        <ExamplePlatform.POSIX: 'posix'>
        >>> _normalise_platform(None) in set(ExamplePlatform)
        True
    """
    if value is None:
        return _default_platform()
    resolved = normalise_examples_platform(value)
    return resolved or _default_platform()
