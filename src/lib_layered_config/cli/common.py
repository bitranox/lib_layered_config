"""Utilities shared by CLI command modules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, cast

import lib_cli_exit_tools
import rich_click as click

from .._platform import normalise_examples_platform as _normalise_examples_platform
from .._platform import normalise_resolver_platform as _normalise_resolver_platform
from ..application.ports import SourceInfoPayload
from ..core import default_env_prefix as compute_default_env_prefix
from .constants import DEFAULT_JSON_INDENT
from ..core import read_config, read_config_json, read_config_raw


@dataclass(frozen=True)
class ReadQuery:
    """Immutable bundle of parameters required to execute read commands."""

    vendor: str
    app: str
    slug: str
    prefer: tuple[str, ...] | None
    start_dir: str | None
    default_file: str | None


def toggle_traceback(show: bool) -> None:
    """Synchronise ``lib_cli_exit_tools`` traceback flags with *show*."""

    lib_cli_exit_tools.config.traceback = show
    lib_cli_exit_tools.config.traceback_force_color = show


def version_string() -> str:
    """Return the installed distribution version or a fallback placeholder."""

    try:
        return metadata.version("lib_layered_config")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def describe_distribution() -> Iterable[str]:
    """Yield human-readable metadata lines about the installed distribution."""

    meta = load_distribution_metadata()
    if meta is None:
        yield "lib_layered_config (metadata unavailable)"
        return
    yield f"Info for {meta.get('Name', 'lib_layered_config')}:"
    yield f"  Version         : {meta.get('Version', version_string())}"
    yield f"  Requires-Python : {meta.get('Requires-Python', '>=3.13')}"
    summary = meta.get("Summary")
    if summary:
        yield f"  Summary         : {summary}"
    for entry in meta.get_all("Project-URL") or []:
        yield f"  {entry}"


def load_distribution_metadata() -> metadata.PackageMetadata | None:
    """Return importlib metadata when the package is installed locally."""

    try:
        return metadata.metadata("lib_layered_config")
    except metadata.PackageNotFoundError:
        return None


def build_read_query(
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str],
    start_dir: Optional[Path],
    default_file: Optional[Path],
) -> ReadQuery:
    """Shape CLI parameters into a read query."""

    return ReadQuery(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=normalise_prefer(prefer),
        start_dir=stringify(start_dir),
        default_file=stringify(default_file),
    )


def normalise_prefer(values: Sequence[str]) -> tuple[str, ...] | None:
    """Lowercase supplied extensions and strip leading dots."""

    if not values:
        return None
    return tuple(value.lower().lstrip(".") for value in values)


def normalise_targets(values: Sequence[str]) -> tuple[str, ...]:
    """Normalise deployment targets to lowercase for resolver routing."""

    return tuple(value.lower() for value in values)


def normalise_platform_option(value: Optional[str]) -> Optional[str]:
    """Map user-friendly platform aliases to canonical resolver identifiers."""

    try:
        return _normalise_resolver_platform(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc


def normalise_examples_platform_option(value: Optional[str]) -> Optional[str]:
    """Map example-generation platform aliases to canonical values."""

    try:
        return _normalise_examples_platform(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc


def stringify(path: Optional[Path]) -> Optional[str]:
    """Return stringified path or ``None`` when *path* is ``None``."""

    return None if path is None else str(path)


def wants_json(output_format: str) -> bool:
    """Return ``True`` when JSON output was requested."""

    return output_format.strip().lower() == "json"


def resolve_indent(enabled: bool) -> int | None:
    """Return default JSON indentation when *enabled* is true."""

    return DEFAULT_JSON_INDENT if enabled else None


def json_payload(query: ReadQuery, indent: int | None, include_provenance: bool) -> str:
    """Build JSON payload for a query."""

    if include_provenance:
        return read_config_json(
            vendor=query.vendor,
            app=query.app,
            slug=query.slug,
            prefer=query.prefer,
            start_dir=query.start_dir,
            default_file=query.default_file,
            indent=indent,
        )
    config = read_config(
        vendor=query.vendor,
        app=query.app,
        slug=query.slug,
        prefer=query.prefer,
        start_dir=query.start_dir,
        default_file=query.default_file,
    )
    return config.to_json(indent=indent)


def render_human(data: Mapping[str, object], provenance: Mapping[str, SourceInfoPayload]) -> str:
    """Return a human-readable description of config values and provenance."""

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
    """Yield dotted paths and values for every leaf entry in *mapping*."""

    for key, value in mapping.items():
        dotted = ".".join((*prefix, key))
        if isinstance(value, Mapping):
            nested = cast(Mapping[str, object], value)
            yield from iter_leaf_items(nested, (*prefix, key))
        else:
            yield dotted, value


def format_scalar(value: object) -> str:
    """Return string representation used in human output for *value*."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def json_paths(paths: Iterable[Path]) -> str:
    """Return JSON array of stringified paths written by helper commands."""

    return json.dumps([str(path) for path in paths], indent=2)


def human_payload(query: ReadQuery) -> str:
    """Return prose describing config values and provenance."""

    data, meta = read_config_raw(
        vendor=query.vendor,
        app=query.app,
        slug=query.slug,
        prefer=query.prefer,
        start_dir=query.start_dir,
        default_file=query.default_file,
    )
    return render_human(data, meta)


def default_env_prefix(slug: str) -> str:
    """Expose the canonical environment prefix for CLI/commands."""

    return compute_default_env_prefix(slug)
