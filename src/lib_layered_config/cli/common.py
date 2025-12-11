"""Utilities shared by CLI command modules.

Tell the CLI story in small, declarative helpers so commands remain tiny. These
functions construct read queries, choose output modes, format human summaries,
and surface metadata drawn from ``__init__conf__``.

Contents:
    * :class:`ReadQuery` — frozen bundle capturing the parameters for configuration reads.
    * :class:`OutputFormat` — enum for CLI output format selection.
    * Metadata helpers (:func:`version_string`, :func:`describe_distribution`).
    * Query shaping (:func:`build_read_query`, :func:`normalise_prefer`, :func:`stringify`).
    * Output shaping (:func:`json_payload`, :func:`human_payload`, :func:`render_human`).
    * Human-friendly utilities (:func:`format_scalar`, :func:`json_paths`).

System Role:
    Commands import these helpers to stay declarative. They rely on the application
    layer (`read_config*` functions) and on platform utilities for normalisation.
    Updates here must be mirrored in ``docs/systemdesign/module_reference.md`` to
    keep documentation and behaviour aligned.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, cast

import rich_click as click

from .. import __init__conf__
from .._platform import normalise_examples_platform as _normalise_examples_platform
from .._platform import normalise_resolver_platform as _normalise_resolver_platform
from ..application.ports import SourceInfoPayload
from ..core import read_config, read_config_json, read_config_raw
from .constants import DEFAULT_JSON_INDENT


class _PackageMetadata(Protocol):
    """Protocol describing package metadata exported by ``__init__conf__``."""

    name: str
    title: str
    version: str
    homepage: str
    author: str
    author_email: str
    shell_command: str

    def info_lines(self) -> tuple[str, ...]:
        """Return human-readable info lines for CLI display."""
        ...

    def metadata_fields(self) -> tuple[tuple[str, str], ...]:
        """Return key-value pairs of package metadata."""
        ...


package_metadata: _PackageMetadata = cast(_PackageMetadata, __init__conf__)


class OutputFormat(str, Enum):
    """Output format options for CLI commands.

    Provides type-safe selection between human-readable and machine-readable output.
    """

    HUMAN = "human"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class ReadQuery:
    """Immutable bundle of parameters required to execute read commands.

    Capture CLI parameters in a frozen dataclass so functions can accept a
    self-explanatory object rather than many loose arguments.

    Attributes:
        vendor: Vendor namespace requested by the user.
        app: Application identifier within the vendor namespace.
        slug: Configuration slug (environment/project).
        profile: Optional profile name for environment-specific configuration paths.
        prefer: Ordered tuple of preferred file extensions, lowercased; ``None`` when the CLI falls back to defaults.
        start_dir: Starting directory as a string or ``None`` to use the current working directory.
        default_file: Optional baseline configuration file to load before layered overrides.
    """

    vendor: str
    app: str
    slug: str
    profile: str | None
    prefer: tuple[str, ...] | None
    start_dir: str | None
    default_file: str | None


def version_string() -> str:
    """Echo the project version declared in ``__init__conf__``.

    The CLI `--version` option should reflect the single source of truth
    maintained by release automation.

    Returns:
        Semantic version string from the generated metadata module.
    """
    return package_metadata.version


def describe_distribution() -> Iterable[str]:
    """Yield human-readable metadata lines sourced from ``__init__conf__``.

    Support the `info` command with pre-formatted lines so the CLI stays thin.

    Returns:
        Sequence of descriptive lines suitable for printing with ``click.echo``.
    """
    lines_provider = getattr(package_metadata, "info_lines", None)
    if callable(lines_provider):
        yield from cast(Iterable[str], lines_provider())
        return
    yield from _fallback_info_lines()


def build_read_query(
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    prefer: Sequence[str],
    start_dir: Path | None,
    default_file: Path | None,
) -> ReadQuery:
    """Shape CLI parameters into a :class:`ReadQuery`.

    Centralise normalisation so every command builds queries in the same way.

    Args:
        vendor: Raw CLI string describing the vendor namespace.
        app: Raw CLI string describing the application name.
        slug: Raw CLI string describing the configuration slice to read.
        profile: Optional profile name for environment-specific configuration.
        prefer: List of extensions supplied via ``--prefer`` (possibly empty).
        start_dir: Optional explicit starting directory.
        default_file: Optional explicit baseline file.

    Returns:
        Frozen, normalised dataclass instance.
    """
    return ReadQuery(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        prefer=normalise_prefer(prefer),
        start_dir=stringify(start_dir),
        default_file=stringify(default_file),
    )


def normalise_prefer(values: Sequence[str]) -> tuple[str, ...] | None:
    """Normalise preferred extensions by lowercasing and trimming dots.

    Returns:
        Tuple of cleaned extensions, or ``None`` when no values were supplied.
    """
    if not values:
        return None
    return tuple(value.lower().lstrip(".") for value in values)


def normalise_targets(values: Sequence[str]) -> tuple[str, ...]:
    """Normalise deployment targets to lowercase for resolver routing.

    Deployment helpers expect stable lowercase slugs regardless of user input.

    Returns:
        Lowercased targets suitable for lookups.
    """
    return tuple(value.lower() for value in values)


def normalise_platform_option(value: str | None) -> str | None:
    """Map friendly platform aliases to canonical resolver identifiers.

    Keep command options flexible without leaking resolver-specific tokens.

    Raises:
        click.BadParameter: When the alias is unrecognised.
    """
    try:
        return _normalise_resolver_platform(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc


def normalise_examples_platform_option(value: str | None) -> str | None:
    """Map example-generation platform aliases to canonical values.

    Example templates use only ``posix`` or ``windows``; synonyms must collapse
    to those keys.

    Raises:
        click.BadParameter: When the alias is unrecognised.
    """
    try:
        return _normalise_examples_platform(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc


def stringify(path: Path | None) -> str | None:
    """Return an absolute path string or ``None`` when the input is ``None``.

    Downstream helpers prefer plain strings (for JSON serialization) while
    preserving the absence of a path.
    """
    return None if path is None else str(path)


def wants_json(output_format: OutputFormat) -> bool:
    """State plainly whether the caller requested JSON output.

    Commands toggle between human and JSON representations; clarity matters.
    """
    return output_format == OutputFormat.JSON


def parse_output_format(value: str) -> OutputFormat:
    """Parse a string into an OutputFormat enum at the CLI boundary.

    Args:
        value: Raw string from CLI (e.g., "human", "json").

    Returns:
        Corresponding OutputFormat enum member.
    """
    return OutputFormat(value.strip().lower())


def resolve_indent(enabled: bool) -> int | None:
    """Return the default JSON indentation when pretty-printing is enabled.

    Provide a single source for the CLI's JSON formatting decision.
    """
    return DEFAULT_JSON_INDENT if enabled else None


def json_payload(query: ReadQuery, indent: int | None, include_provenance: bool) -> str:
    """Build a JSON payload for the provided query.

    Commands should share the same logic when emitting machine-readable output.

    Args:
        query: Normalised read parameters.
        indent: Indentation width or ``None`` for compact output.
        include_provenance: When ``True`` use :func:`read_config_json` to include source metadata.

    Returns:
        JSON document ready for ``click.echo``.
    """
    if include_provenance:
        return read_config_json(
            vendor=query.vendor,
            app=query.app,
            slug=query.slug,
            profile=query.profile,
            prefer=query.prefer,
            start_dir=query.start_dir,
            default_file=query.default_file,
            indent=indent,
        )
    config = read_config(
        vendor=query.vendor,
        app=query.app,
        slug=query.slug,
        profile=query.profile,
        prefer=query.prefer,
        start_dir=query.start_dir,
        default_file=query.default_file,
    )
    return config.to_json(indent=indent)


def render_human(data: Mapping[str, object], provenance: Mapping[str, SourceInfoPayload]) -> str:
    """Render configuration values and provenance as friendly prose.

    Args:
        data: Nested mapping of configuration values.
        provenance: Mapping of dotted keys to source metadata.

    Returns:
        Multi-line description highlighting value and origin.
    """
    entries = list(iter_leaf_items(data))
    if not entries:
        return "No configuration values were found."

    lines: list[str] = []
    for dotted, value in entries:
        lines.append(f"{dotted}: {format_scalar(value)}")
        info = provenance.get(dotted)
        if info:
            path = info["path"] or "(memory)"
            lines.append(f"  provenance: layer={info['layer']}, path={path}")
    return "\n".join(lines)


def iter_leaf_items(mapping: Mapping[str, object], prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, object]]:
    """Yield dotted paths and values for every leaf node in *mapping*.

    Flatten nested structures so human-readable output can focus on leaves.
    """
    for key, value in mapping.items():
        dotted = ".".join((*prefix, key))
        if isinstance(value, Mapping):
            nested = cast(Mapping[str, object], value)
            yield from iter_leaf_items(nested, (*prefix, key))
        else:
            yield dotted, value


def format_scalar(value: object) -> str:
    """Format a scalar value for human output.

    Keep representation consistent across CLI messages (booleans lowercase,
    ``None`` as ``null``).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def json_paths(paths: Iterable[Path]) -> str:
    """Return a JSON array of stringified paths written by helper commands.

    Provide machine-readable artifacts for deployment/generation commands.
    """
    return json.dumps([str(path) for path in paths], indent=2)


def human_payload(query: ReadQuery) -> str:
    """Return prose describing config values and provenance.

    Offer a human-first view that mirrors the JSON content yet remains readable.
    """
    result = read_config_raw(
        vendor=query.vendor,
        app=query.app,
        slug=query.slug,
        profile=query.profile,
        prefer=query.prefer,
        start_dir=query.start_dir,
        default_file=query.default_file,
    )
    return render_human(result.data, result.provenance)


def _fallback_info_lines() -> tuple[str, ...]:
    """Construct info lines from metadata constants when helpers are absent."""
    fields_provider = getattr(package_metadata, "metadata_fields", None)
    if callable(fields_provider):
        fields = cast(tuple[tuple[str, str], ...], fields_provider())
    else:
        fields: tuple[tuple[str, str], ...] = (
            ("name", package_metadata.name),
            ("title", package_metadata.title),
            ("version", package_metadata.version),
            ("homepage", package_metadata.homepage),
            ("author", package_metadata.author),
            ("author_email", package_metadata.author_email),
            ("shell_command", package_metadata.shell_command),
        )
    pad = max(len(label) for label, _ in fields)
    lines = [f"Info for {package_metadata.name}:", ""]
    lines.extend(f"    {label.ljust(pad)} = {value}" for label, value in fields)
    return tuple(lines)
