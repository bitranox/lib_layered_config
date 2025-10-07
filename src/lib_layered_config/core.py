"""Composition root tying adapters, merge policy, and domain objects together.

Purpose
-------
Implement the orchestration described in ``docs/systemdesign/concept.md`` by
discovering configuration layers, merging them with provenance, and returning a
domain-level :class:`Config` value object. Also provides convenience helpers for
JSON output and CLI wiring.

Contents
--------
- ``read_config`` / ``read_config_json`` / ``read_config_raw``: public APIs used
  by library consumers and the CLI.
- ``LayerLoadError``: wraps adapter failures with a consistent exception type.
- Private helpers for resolver/builder construction, JSON dumping, and
  configuration composition.

System Role
-----------
This module sits at the composition layer of the architecture. It instantiates
adapters from ``lib_layered_config.adapters.*``, invokes
``lib_layered_config._layers.collect_layers``, and converts merge results into
domain objects returned to callers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, cast

from ._layers import collect_layers, merge_or_empty
from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.path_resolvers.default import DefaultPathResolver
from .application.merge import SourceInfoPayload
from .domain.config import Config, EMPTY_CONFIG, SourceInfo
from .domain.errors import ConfigError, InvalidFormat, NotFound, ValidationError
from .observability import bind_trace_id


class LayerLoadError(ConfigError):
    """Adapter failure raised during layer collection.

    Why
    ----
    Provides a single exception type for callers who need to distinguish merge
    orchestration errors from other configuration issues.
    """


def read_config(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
) -> Config:
    """Return an immutable :class:`Config` built from all reachable layers.

    Why
    ----
    Most consumers want the merged configuration value object rather than raw
    dictionaries. This function wraps the lower-level helper and constructs the
    domain aggregate in one step.

    Parameters
    ----------
    vendor / app / slug:
        Identifiers used by adapters to compute filesystem paths and prefixes.
    prefer:
        Optional sequence of preferred file suffixes (``["toml", "json"]``).
    start_dir:
        Optional directory that seeds `.env` discovery.
    default_file:
        Optional lowest-precedence file injected before filesystem layers.

    Returns
    -------
    Config
        Immutable configuration with provenance metadata.

    Examples
    --------
    >>> from pathlib import Path
    >>> tmp = Path('.')  # doctest: +SKIP (illustrative)
    >>> config = read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(tmp))  # doctest: +SKIP
    >>> isinstance(config, Config)
    True
    """

    data, raw_meta = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=prefer,
        start_dir=start_dir,
        default_file=_stringify_path(default_file),
    )
    return _compose_config(data, raw_meta)


def read_config_json(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None = None,
    start_dir: str | Path | None = None,
    indent: int | None = None,
    default_file: str | Path | None = None,
) -> str:
    """Return configuration and provenance as JSON suitable for tooling.

    Why
    ----
    CLI commands and automation scripts often prefer JSON to Python objects.

    Parameters
    ----------
    vendor / app / slug / prefer / start_dir / default_file:
        Same meaning as :func:`read_config`.
    indent:
        Optional indentation level passed to ``json.dumps``.

    Returns
    -------
    str
        JSON document containing ``{"config": ..., "provenance": ...}``.
    """

    data, meta = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=prefer,
        start_dir=_stringify_path(start_dir),
        default_file=_stringify_path(default_file),
    )
    return _dump_json({"config": data, "provenance": meta}, indent)


def read_config_raw(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
) -> tuple[dict[str, object], dict[str, SourceInfoPayload]]:
    """Return raw data and provenance dictionaries for advanced tooling.

    Why
    ----
    Some consumers need dictionaries they can mutate or serialise differently
    without enforcing the `Config` abstraction.

    Returns
    -------
    tuple[dict[str, object], dict[str, SourceInfoPayload]]
        Data and provenance mappings produced directly by the merge policy.
    """

    resolver = _build_resolver(vendor=vendor, app=app, slug=slug, start_dir=start_dir)
    dotenv_loader, env_loader = _build_loaders(resolver)

    bind_trace_id(None)

    try:
        layers = collect_layers(
            resolver=resolver,
            prefer=prefer,
            default_file=_stringify_path(default_file),
            dotenv_loader=dotenv_loader,
            env_loader=env_loader,
            slug=slug,
            start_dir=start_dir,
        )
    except InvalidFormat as exc:  # pragma: no cover - adapter tests exercise
        raise LayerLoadError(str(exc)) from exc

    return merge_or_empty(layers)


def _compose_config(
    data: dict[str, object],
    raw_meta: dict[str, SourceInfoPayload],
) -> Config:
    """Wrap merged data and provenance into an immutable :class:`Config`.

    Why
    ----
    Keeps the conversion from plain dictionaries into the domain aggregate in
    one place, ensuring metadata is cast to :class:`SourceInfo`.

    Side Effects
    ------------
    None. Returns ``EMPTY_CONFIG`` when *data* is empty.
    """

    if not data:
        return EMPTY_CONFIG
    meta = {key: cast(SourceInfo, details) for key, details in raw_meta.items()}
    return Config(data, meta)


def _build_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    start_dir: str | None,
) -> DefaultPathResolver:
    """Create a path resolver configured with optional ``start_dir`` context."""

    return DefaultPathResolver(vendor=vendor, app=app, slug=slug, cwd=Path(start_dir) if start_dir else None)


def _build_loaders(resolver: DefaultPathResolver) -> tuple[DefaultDotEnvLoader, DefaultEnvLoader]:
    """Instantiate dotenv and environment loaders sharing resolver context."""

    return DefaultDotEnvLoader(extras=resolver.dotenv()), DefaultEnvLoader()


def _stringify_path(value: str | Path | None) -> str | None:
    """Convert ``Path`` or string inputs into plain string values for adapters."""

    if isinstance(value, Path):
        return str(value)
    return value


def _dump_json(payload: object, indent: int | None) -> str:
    """Serialise *payload* to JSON while preserving non-ASCII characters."""

    return json.dumps(payload, indent=indent, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "Config",
    "ConfigError",
    "InvalidFormat",
    "ValidationError",
    "NotFound",
    "LayerLoadError",
    "read_config",
    "read_config_json",
    "read_config_raw",
    "default_env_prefix",
]
