"""Composition root tying adapters, merge policy, and domain objects together.

Implement the orchestration described in ``docs/systemdesign/concept.md`` by
discovering configuration layers, merging them with provenance, and returning a
domain-level :class:`Config` value object. Also provides convenience helpers for
JSON output and CLI wiring.

Contents:
    - ``read_config`` / ``read_config_json`` / ``read_config_raw``: public APIs used
      by library consumers and the CLI.
    - ``LayerLoadError``: wraps adapter failures with a consistent exception type.
    - Private helpers for resolver/builder construction, JSON dumping, and
      configuration composition.

System Role:
    This module sits at the composition layer of the architecture. It instantiates
    adapters from ``lib_layered_config.adapters.*``, invokes
    ``lib_layered_config._layers.collect_layers``, and converts merge results into
    domain objects returned to callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import orjson

from ._layers import collect_layers, merge_or_empty
from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.path_resolvers.default import DefaultPathResolver
from .domain.identifiers import DEFAULT_MAX_PROFILE_LENGTH
from .application.merge import MergeResult
from .application.ports import SourceInfoPayload
from .domain.config import EMPTY_CONFIG, Config
from .domain.errors import (
    ConfigError,
    InvalidFormatError,
    NotFoundError,
    ValidationError,
)
from .observability import bind_trace_id


class LayerLoadError(ConfigError):
    """Adapter failure raised during layer collection.

    Provides a single exception type for callers who need to distinguish merge
    orchestration errors from other configuration issues.
    """


def read_config(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> Config:
    """Return an immutable :class:`Config` built from all reachable layers.

    Most consumers want the merged configuration value object rather than raw
    dictionaries. This function wraps the lower-level helper and constructs the
    domain aggregate in one step.

    Args:
        vendor / app / slug: Identifiers used by adapters to compute filesystem paths and prefixes.
        profile: Optional profile name for environment-specific configurations
            (e.g., "test", "production"). When set, paths include a
            ``profile/<name>/`` subdirectory.
        prefer: Optional sequence of preferred file suffixes (``["toml", "json"]``).
        start_dir: Optional directory that seeds `.env` discovery.
        default_file: Optional lowest-precedence file injected before filesystem layers.
        max_profile_length: Maximum allowed profile name length (default: 64).
            Set to 0 or negative to disable length checking.

    Returns:
        Immutable configuration with provenance metadata.

    Raises:
        ValueError: When profile name is invalid (too long, path traversal, etc.).

    Examples:
        >>> from pathlib import Path
        >>> tmp = Path('.')  # doctest: +SKIP (illustrative)
        >>> config = read_config(vendor="Acme", app="Demo", slug="demo", start_dir=str(tmp))  # doctest: +SKIP
        >>> isinstance(config, Config)
        True
    """
    result = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        prefer=prefer,
        start_dir=start_dir,
        default_file=_stringify_path(default_file),
        max_profile_length=max_profile_length,
    )
    return _compose_config(result.data, result.provenance)


def read_config_json(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,
    prefer: Sequence[str] | None = None,
    start_dir: str | Path | None = None,
    indent: int | None = None,
    default_file: str | Path | None = None,
    redact: bool = False,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> str:
    """Return configuration and provenance as JSON suitable for tooling.

    CLI commands and automation scripts often prefer JSON to Python objects.

    Args:
        vendor / app / slug / profile / prefer / start_dir / default_file: Same meaning as :func:`read_config`.
        indent: Optional indentation level.  Any non-``None`` value produces
            2-space indented output (orjson only supports 2-space indentation).
        redact: When ``True``, sensitive values (passwords, tokens, secrets,
            API keys) are replaced with ``***REDACTED***`` in the config data.
        max_profile_length: Maximum allowed profile name length (default: 64).
            Set to 0 or negative to disable length checking.

    Returns:
        JSON document containing ``{"config": ..., "provenance": ...}``.

    Raises:
        ValueError: When profile name is invalid (too long, path traversal, etc.).
    """
    from .domain.redaction import redact_mapping

    result = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        prefer=prefer,
        start_dir=_stringify_path(start_dir),
        default_file=_stringify_path(default_file),
        max_profile_length=max_profile_length,
    )
    data = result.data
    if redact:
        data = redact_mapping(data)
    return _dump_json({"config": data, "provenance": result.provenance}, indent)


def read_config_raw(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> MergeResult:
    """Return raw merged data and provenance for advanced tooling.

    Unlike :func:`read_config`, returns mutable dictionaries instead of the
    immutable :class:`Config` abstraction. Raises :class:`LayerLoadError`
    when a structured file loader encounters invalid content.

    Args:
        vendor / app / slug / profile / prefer / start_dir / default_file: Same as :func:`read_config`.
        max_profile_length: Maximum allowed profile name length (default: 64).
            Set to 0 or negative to disable length checking.

    Raises:
        ValueError: When profile name is invalid (too long, path traversal, etc.).
    """
    resolver = _build_resolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start_dir,
        max_profile_length=max_profile_length,
    )
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
    except InvalidFormatError as exc:  # pragma: no cover - adapter tests exercise
        raise LayerLoadError(str(exc)) from exc

    return merge_or_empty(layers)


def _compose_config(
    data: dict[str, object],
    raw_meta: dict[str, SourceInfoPayload],
) -> Config:
    """Wrap merged data and provenance into an immutable :class:`Config`.

    Keep the boundary between application-layer dictionaries and the domain
    value object explicit so provenance typing stays consistent.

    Args:
        data: Mutable mapping returned by :func:`merge_layers`.
        raw_meta: Provenance mapping keyed by dotted path as produced by the merge policy.

    Returns:
        Immutable configuration aggregate. Returns :data:`EMPTY_CONFIG` when
        *data* is empty.

    Side Effects:
        None beyond constructing the dataclass instance.

    Examples:
        >>> cfg = _compose_config({'debug': True}, {'debug': {'layer': 'env', 'path': None, 'key': 'debug'}})
        >>> cfg['debug'], cfg.origin('debug')['layer']
        (True, 'env')
    """
    if not data:
        return EMPTY_CONFIG
    return Config(data, raw_meta)


def _build_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    start_dir: str | None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> DefaultPathResolver:
    """Create a path resolver configured with optional ``start_dir`` context.

    Reuse the same resolver wiring for CLI and library entry points while
    keeping construction logic centralised for testing.

    Args:
        vendor / app / slug: Identifiers forwarded to :class:`DefaultPathResolver`.
        profile: Optional profile name for environment-specific configuration paths.
        start_dir: Optional directory that seeds project-relative resolution (used for
            `.env` discovery); ``None`` preserves resolver defaults.
        max_profile_length: Maximum allowed profile name length (default: 64).
            Set to 0 or negative to disable length checking.

    Returns:
        Resolver instance ready for layer discovery.

    Examples:
        >>> resolver = _build_resolver(vendor='Acme', app='Demo', slug='demo', profile=None, start_dir=None)
        >>> resolver.slug
        'demo'
    """
    return DefaultPathResolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        cwd=Path(start_dir) if start_dir else None,
        max_profile_length=max_profile_length,
    )


def _build_loaders(resolver: DefaultPathResolver) -> tuple[DefaultDotEnvLoader, DefaultEnvLoader]:
    """Instantiate dotenv and environment loaders sharing resolver context.

    Keeps loader construction aligned with the resolver extras (e.g., additional
    dotenv directories) and centralises wiring for tests.

    Args:
        resolver: Resolver supplying platform-specific extras for dotenv discovery.

    Returns:
        Pair of loader instances ready for layer collection.
    """
    return DefaultDotEnvLoader(extras=resolver.dotenv()), DefaultEnvLoader()


def _stringify_path(value: str | Path | None) -> str | None:
    """Convert ``Path`` or string inputs into plain string values for adapters.

    Adapters expect plain strings while public APIs accept :class:`Path` objects
    for user convenience. Centralising the conversion avoids duplicate logic.

    Args:
        value: Optional path expressed as either a string or :class:`pathlib.Path`.

    Returns:
        Stringified path or ``None`` when *value* is ``None``.

    Examples:
        >>> _stringify_path(Path('/tmp/config.toml'))
        '/tmp/config.toml'
        >>> _stringify_path(None) is None
        True
    """
    if isinstance(value, Path):
        return str(value)
    return value


def _dump_json(payload: object, indent: int | None) -> str:
    """Serialise *payload* to JSON while preserving non-ASCII characters.

    Args:
        payload: JSON-serialisable object to dump.
        indent: When set to any non-``None`` value, produces 2-space indented
            output (orjson only supports 2-space indentation).  ``None``
            produces compact output.

    Returns:
        JSON document encoded as UTF-8 friendly text.

    Examples:
        >>> _dump_json({"a": 1}, indent=None)
        '{"a":1}'
        >>> "\n" in _dump_json({"a": 1}, indent=2)
        True
    """
    option = orjson.OPT_INDENT_2 if indent is not None else 0
    return orjson.dumps(payload, option=option).decode()


__all__ = [
    "Config",
    "ConfigError",
    "InvalidFormatError",
    "ValidationError",
    "NotFoundError",
    "LayerLoadError",
    "read_config",
    "read_config_json",
    "read_config_raw",
    "default_env_prefix",
]
