"""Composition root tying adapters, merge policy, and domain objects together.

Implement the orchestration described in ``docs/systemdesign/concept.md`` by
discovering configuration layers, merging them with provenance, and returning a
domain-level :class:`Config` value object. Also provides convenience helpers for
JSON output and CLI wiring.

Contents:
    - ``read_config`` / ``read_config_json`` / ``read_config_raw``: public APIs used
      by library consumers and the CLI.
    - ``read_config_for_deploy``: the narrower read ``deploy_config`` uses to decide
      modes (not exported from the package root).
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

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from ._layers import collect_deploy_layers, collect_layers, merge_or_empty, parse_with_dot_d
from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.path_resolvers.default import DefaultPathResolver
from .domain import json_codec
from .domain.config import EMPTY_CONFIG, Config, adopt_merged
from .domain.errors import (
    ConfigError,
    InvalidFormatError,
    NotFoundError,
    ValidationError,
)
from .domain.identifiers import DEFAULT_MAX_PROFILE_LENGTH
from .domain.redaction import NotSensitiveKeys, redact_mapping

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .application.merge import MergeResult
    from .domain.config import SourceInfo


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
    start_dir: str | Path | None = None,
    default_file: str | Path | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
    dotenv_path: str | Path | None = None,
    not_sensitive: Iterable[str] | None = None,
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
        prefer: Deprecated, no effect: each layer reads only ``config.toml`` and its ``config.d/``
            directory, which is where JSON and YAML files go. Passing it emits a
            ``DeprecationWarning``; it will be removed in a future major release.
        start_dir: Optional directory that seeds `.env` discovery.
        default_file: Optional lowest-precedence file injected before filesystem layers.
        max_profile_length: Maximum allowed profile name length (default: 64).
            A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.
        dotenv_path: Optional explicit path to a ``.env`` file.  When set,
            this file is loaded directly instead of searching upward from
            *start_dir*.
        not_sensitive: Dotted key paths the application declares as not secret although their
            name looks like one (``["performance.max_token_bytes"]``). Redaction leaves them
            visible, and an unquoted ``null``/``none`` in the environment or ``.env`` reads as None
            for them. The returned :class:`Config` carries the declaration.

    Returns:
        Immutable configuration with provenance metadata.

    Raises:
        LayerLoadError: A layer file, ``.env`` or environment value cannot be decoded or parsed.
        ValidationError: *vendor*, *app*, *slug* or *profile* is refused (a ``ValueError`` too).
        TypeError: *not_sensitive* is a single str or holds a non-str entry.
        TypeError: *prefer* is a single str.
        ValueError: A *not_sensitive* entry has an empty segment.

    Examples:
        >>> import os
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     old_etc = os.environ.get("LIB_LAYERED_CONFIG_ETC")
        ...     old_xdg = os.environ.get("XDG_CONFIG_HOME")
        ...     os.environ["LIB_LAYERED_CONFIG_ETC"] = tmp
        ...     os.environ["XDG_CONFIG_HOME"] = tmp
        ...     try:
        ...         config = read_config(
        ...             vendor="Acme",
        ...             app="Demo",
        ...             slug="core-doctest-read-config",
        ...             start_dir=tmp,
        ...             dotenv_path=str(Path(tmp) / "missing.env"),
        ...         )
        ...     finally:
        ...         if old_etc is None:
        ...             del os.environ["LIB_LAYERED_CONFIG_ETC"]
        ...         else:
        ...             os.environ["LIB_LAYERED_CONFIG_ETC"] = old_etc
        ...         if old_xdg is None:
        ...             del os.environ["XDG_CONFIG_HOME"]
        ...         else:
        ...             os.environ["XDG_CONFIG_HOME"] = old_xdg
        >>> isinstance(config, Config)
        True
    """
    # Warned here and not passed on, so the caller gets one warning at its own line.
    _take_deprecated_prefer(prefer)
    declared = NotSensitiveKeys.of(not_sensitive)
    result = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start_dir,
        default_file=default_file,
        max_profile_length=max_profile_length,
        dotenv_path=dotenv_path,
        not_sensitive=declared,
    )
    return _compose_config(result.data, result.provenance, not_sensitive=declared)


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
    dotenv_path: str | Path | None = None,
    not_sensitive: Iterable[str] | None = None,
) -> str:
    """Return configuration and provenance as JSON suitable for tooling.

    CLI commands and automation scripts often prefer JSON to Python objects.

    Args:
        vendor / app / slug / profile / prefer / start_dir / default_file / dotenv_path: Same meaning as
            :func:`read_config`.
        indent: Optional indentation level.  Any non-``None`` value produces
            2-space indented output (always a 2-space indent).
        redact: When ``True``, the values of sensitive keys (passwords, tokens, secrets,
            API keys) and the password of every URL in a string value, under any key
            (``postgres://alice:***REDACTED***@db/app``), are replaced with
            ``***REDACTED***`` in the config data.
        max_profile_length: Maximum allowed profile name length (default: 64).
            A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.
        not_sensitive: Same meaning as in :func:`read_config`; declared keys stay visible when
            *redact* is set.

    Returns:
        JSON document containing ``{"config": ..., "provenance": ...}``.

    Raises:
        LayerLoadError: A layer file, ``.env`` or environment value cannot be decoded or parsed.
        ValidationError: *vendor*, *app*, *slug* or *profile* is refused (a ``ValueError`` too).
        TypeError: *not_sensitive* is a single str or holds a non-str entry.
        TypeError: *prefer* is a single str.
        ValueError: A *not_sensitive* entry has an empty segment.

    Examples:
        >>> import json
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     defaults = Path(tmp) / "defaults.toml"
        ...     _ = defaults.write_text('[db]\\nport = 5432\\npassword = "hunter2"\\n', encoding="utf-8")
        ...     text = read_config_json(
        ...         vendor="Acme",
        ...         app="Demo",
        ...         slug="core-doctest-read-config-json",
        ...         default_file=defaults,
        ...         dotenv_path=Path(tmp) / "missing.env",
        ...         redact=True,
        ...     )
        >>> json.loads(text)["config"]
        {'db': {'port': 5432, 'password': '***REDACTED***'}}
    """
    _take_deprecated_prefer(prefer)
    declared = NotSensitiveKeys.of(not_sensitive)
    result = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start_dir,
        default_file=default_file,
        max_profile_length=max_profile_length,
        dotenv_path=dotenv_path,
        not_sensitive=declared,
    )
    data = result.data
    if redact:
        data = redact_mapping(data, not_sensitive=declared)
    return _dump_json({"config": data, "provenance": result.provenance}, indent)


def read_config_raw(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,
    prefer: Sequence[str] | None = None,
    start_dir: str | Path | None = None,
    default_file: str | Path | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
    dotenv_path: str | Path | None = None,
    not_sensitive: Iterable[str] | None = None,
) -> MergeResult:
    """Return raw merged data and provenance for advanced tooling.

    Unlike :func:`read_config`, returns mutable dictionaries instead of the
    immutable :class:`Config` abstraction. Raises :class:`LayerLoadError`
    when a structured file loader encounters invalid content.

    Args:
        vendor / app / slug / profile / prefer / start_dir / default_file / dotenv_path: Same as :func:`read_config`.
        max_profile_length: Maximum allowed profile name length (default: 64).
            A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.
        not_sensitive: Dotted key paths the application declares as not secret although their
            name looks like one (``["performance.max_token_bytes"]``). An unquoted ``null``/``none``
            in the environment or ``.env`` reads as None for them.

    Returns:
        The merged data and its provenance, both plain mutable dictionaries: ``data`` nested like
        the configuration, ``provenance`` keyed by dotted path.

    Raises:
        LayerLoadError: A layer file, ``.env`` or environment value cannot be decoded or parsed.
        ValidationError: *vendor*, *app*, *slug* or *profile* is refused (a ``ValueError`` too).
        TypeError: *not_sensitive* is a single str or holds a non-str entry.
        TypeError: *prefer* is a single str.
        ValueError: A *not_sensitive* entry has an empty segment.

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     defaults = Path(tmp) / "defaults.toml"
        ...     _ = defaults.write_text("[db]\\nport = 5432\\n", encoding="utf-8")
        ...     result = read_config_raw(
        ...         vendor="Acme",
        ...         app="Demo",
        ...         slug="core-doctest-read-config-raw",
        ...         default_file=defaults,
        ...         dotenv_path=Path(tmp) / "missing.env",
        ...     )
        >>> result.data
        {'db': {'port': 5432}}
        >>> result.provenance["db.port"]["layer"]
        'defaults'
    """
    _take_deprecated_prefer(prefer)
    declared = NotSensitiveKeys.of(not_sensitive)
    # An empty start_dir or default_file string means not given, as before 9.0.0; an empty
    # dotenv_path is a path (the current directory) and is refused as a directory by the loader.
    start = _as_path(start_dir or None)
    resolver = _build_resolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        start_dir=start,
        max_profile_length=max_profile_length,
    )

    try:
        # Inside the try: building the loaders probes the platform .env location, and a path it
        # cannot read must surface as LayerLoadError like every other layer.
        dotenv_loader, env_loader = _build_loaders(
            resolver, not_sensitive=declared, searches_dotenv=dotenv_path is None
        )
    except InvalidFormatError as exc:
        raise LayerLoadError(str(exc)) from exc
    layers = collect_layers(
        resolver=resolver,
        default_file=_as_path(default_file or None),
        dotenv_loader=dotenv_loader,
        env_loader=env_loader,
        slug=slug,
        start_dir=start,
        dotenv_path=_as_path(dotenv_path),
    )
    # The layers are read lazily inside the merge's loop, so this one wrap covers a file that does
    # not load and the merge's own refusal (nesting past its depth) alike.
    try:
        return merge_or_empty(layers)
    except InvalidFormatError as exc:
        raise LayerLoadError(str(exc)) from exc


#: What a caller passing ``prefer`` is told. A layer has one main file, ``config.toml``, so a suffix
#: ranking never had a second candidate to choose between.
_PREFER_DEPRECATION = (
    "prefer has no effect and will be removed in a future major release: each layer reads only "
    "config.toml and its config.d/ directory, which is where JSON and YAML files go"
)


def _take_deprecated_prefer(prefer: Sequence[str] | None) -> None:
    """Refuse *prefer* given as one ``str``, and warn that any other *prefer* has no effect.

    A ``str`` is itself a sequence of strings, so the type checker accepts ``prefer="toml"``; it
    stays refused so a caller's mistake does not turn silent while the parameter is deprecated.

    Raises:
        TypeError: *prefer* is a single str.
    """
    if isinstance(prefer, str):
        raise TypeError(f"prefer takes a sequence of suffixes, not a single str: write [{prefer!r}]")
    if prefer is not None:
        # stacklevel 3: this helper, the public read function, then the caller's own line.
        warnings.warn(_PREFER_DEPRECATION, DeprecationWarning, stacklevel=3)


def read_config_for_deploy(
    *,
    resolver: DefaultPathResolver,
    default_file: Path,
    skip: frozenset[Path],
) -> Config:
    """Merge what decides deploy modes; see :func:`lib_layered_config._layers.collect_deploy_layers`.

    Unlike :func:`read_config` it takes the deploy's own resolver (so a ``platform`` override reads
    that platform's paths), never reads ``.env``, and skips the files the deploy writes.

    Raises:
        LayerLoadError: A layer file cannot be decoded or parsed (a content-free message), or two
            environment variables set a value and a key below it.
    """
    try:
        layers = collect_deploy_layers(
            resolver=resolver, default_file=default_file, env_loader=DefaultEnvLoader(), skip=skip
        )
        result = merge_or_empty(layers)
    except InvalidFormatError as exc:
        raise LayerLoadError(str(exc)) from exc
    return _compose_config(result.data, result.provenance)


def refuse_an_unusable_deploy_source(source: Path) -> None:
    """Refuse a deploy *source*, or a file in its ``.d`` directory, that cannot be read or loaded.

    It runs before anything is written and before deploy reads its configured modes, which read the
    source too and would report an unreadable one as unknown modes - a remedy (give both modes)
    that cannot work, since the copy reads the same file.

    Raises:
        OSError: A file cannot be read; the read's own error (``PermissionError`` behind a
            permission wall), as the copy would raise it.
        LayerLoadError: The source is not a ``.toml`` file, or a file does not parse (the loader's
            content-free message, naming the file).
    """
    if source.suffix.lower() != ".toml":
        # Every deploy destination is config.toml or <hostname>.toml, read only as TOML: a valid
        # JSON or YAML source deployed fine and then broke every read. ``.d`` files keep their
        # own format, since the ``.d`` reader takes TOML, YAML and JSON.
        raise LayerLoadError(
            f"{source} is not a .toml file, but deploy writes it as config.toml or <hostname>.toml, "
            "which are read only as TOML"
        )
    try:
        parse_with_dot_d(source)
    except InvalidFormatError as exc:
        unreadable = exc.__cause__
        if isinstance(unreadable, OSError):
            raise unreadable from None
        raise LayerLoadError(str(exc)) from exc


def _compose_config(
    data: dict[str, object],
    raw_meta: dict[str, SourceInfo],
    *,
    not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE,
) -> Config:
    """Wrap merged data and provenance into an immutable :class:`Config`.

    Keep the boundary between application-layer dictionaries and the domain
    value object explicit so provenance typing stays consistent.

    Args:
        data: Mutable mapping returned by :func:`merge_layers`; adopted, not copied, so the caller
            must hold no other reference to it.
        raw_meta: Provenance mapping keyed by dotted path as produced by the merge policy; adopted the
            same way.
        not_sensitive: Paths the application declared not sensitive; carried on the result.

    Returns:
        Immutable configuration aggregate. Returns :data:`EMPTY_CONFIG` only when *data* is
        empty and nothing was declared, so a later ``with_overrides`` keeps the declaration.

    Side Effects:
        The returned :class:`Config` takes over *data* and *raw_meta*.

    Examples:
        >>> cfg = _compose_config({'debug': True}, {'debug': {'layer': 'env', 'path': None, 'key': 'debug'}})
        >>> cfg['debug'], cfg.origin('debug')['layer']
        (True, 'env')
    """
    if not data and not_sensitive == NotSensitiveKeys.NONE:
        return EMPTY_CONFIG
    return adopt_merged(data, raw_meta, not_sensitive)


def _build_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    start_dir: Path | None,
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
            A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.

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
        cwd=start_dir,
        max_profile_length=max_profile_length,
    )


def _build_loaders(
    resolver: DefaultPathResolver, *, not_sensitive: NotSensitiveKeys, searches_dotenv: bool
) -> tuple[DefaultDotEnvLoader, DefaultEnvLoader]:
    """Instantiate dotenv and environment loaders sharing resolver context and the declaration.

    Keeps loader construction aligned with the resolver extras (e.g., additional
    dotenv directories) and centralises wiring for tests.

    Args:
        resolver: Resolver supplying platform-specific extras for dotenv discovery.
        not_sensitive: Paths the application declared not sensitive.
        searches_dotenv: False when an explicit ``dotenv_path`` replaces the search, so the search's
            locations are never probed (one the user cannot read must not refuse a read that skips it).

    Returns:
        Pair of loader instances ready for layer collection.
    """
    extras: list[Path] = list(resolver.dotenv()) if searches_dotenv else []
    return (
        DefaultDotEnvLoader(extras=extras, not_sensitive=not_sensitive),
        DefaultEnvLoader(not_sensitive=not_sensitive),
    )


def _as_path(value: str | Path | None) -> Path | None:
    """Return *value* as a :class:`Path`, the type the adapters take; ``None`` stays ``None``.

    The public functions accept a string or a ``Path``; this is the one place it is converted.

    Args:
        value: Optional path expressed as either a string or :class:`pathlib.Path`.

    Returns:
        The path, or ``None`` when *value* is ``None``.

    Examples:
        >>> _as_path('config.toml') == Path('config.toml')
        True
        >>> _as_path(None) is None
        True
    """
    return None if value is None else Path(value)


def _dump_json(payload: object, indent: int | None) -> str:
    """Serialise *payload* to JSON while preserving non-ASCII characters.

    Args:
        payload: JSON-serialisable object to dump.
        indent: When set to any non-``None`` value, produces 2-space indented
            output (always a 2-space indent).  ``None``
            produces compact output.

    Returns:
        JSON document encoded as UTF-8 friendly text.

    Examples:
        >>> _dump_json({"a": 1}, indent=None)
        '{"a":1}'
        >>> "\\n" in _dump_json({"a": 1}, indent=2)
        True
    """
    return json_codec.dumps(payload, indent=indent is not None)


__all__ = [
    "Config",
    "ConfigError",
    "InvalidFormatError",
    "LayerLoadError",
    "NotFoundError",
    "ValidationError",
    "default_env_prefix",
    "read_config",
    "read_config_for_deploy",
    "read_config_json",
    "read_config_raw",
    "refuse_an_unusable_deploy_source",
]
