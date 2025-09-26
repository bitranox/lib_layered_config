"""Composition root expressed as a string of tiny orchestration phrases.

Purpose
    Build the configuration stack by delegating to adapters, then merge the
    results into immutable value objects that callers can depend on.

Contents
    - ``LayerLoadError``: domain-flavoured wrapper for adapter failures.
    - ``read_config``: public façade returning :class:`Config` objects.
    - ``read_config_raw``: raw payload access for tooling and orchestration.
    - ``_FILE_LOADERS`` and helper functions: small verbs that describe each
      stage of the composition flow (order paths, load files, merge layers,
      record observability events).

System Integration
    Sits at the top of the Clean Architecture onion. Adapters feed data inward;
    the domain consumes merged results. Every helper keeps effects isolated so
    the orchestration reads like documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .application.merge import merge_layers
from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from .adapters.path_resolvers.default import DefaultPathResolver
from .domain.config import Config, EMPTY_CONFIG
from .domain.errors import ConfigError, InvalidFormat, NotFound, ValidationError
from .observability import bind_trace_id, log_debug, log_info, make_event

LayerEntry = tuple[str, Mapping[str, object], str | None]
"""Data structure passed into :func:`merge_layers`.

Why
    Keeps type annotations compact and narrative when orchestrating the layer
    stack.
"""

# Supported structured file loaders keyed by suffix. Consumers can override the
# mapping by wrapping :func:`read_config_raw` if they need custom formats.
_FILE_LOADERS = {
    ".toml": TOMLFileLoader(),
    ".json": JSONFileLoader(),
    ".yaml": YAMLFileLoader(),
    ".yml": YAMLFileLoader(),
}


class LayerLoadError(ConfigError):
    """Raised when a configuration layer cannot be materialised.

    Why
    ----
    The composition root needs to surface adapter failures using the domain
    error taxonomy so callers can catch a single exception family.

    What
    -----
    Wraps :class:`InvalidFormat` or other adapter exceptions with additional
    context (layer name, file path).
    """


def read_config(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
) -> Config:
    """Return the merged configuration as a :class:`Config` value object.

    Why
    ----
    Consumers need a drop-in immutable mapping that abstracts away adapter
    wiring and precedence rules.

    What
    ----
    Delegates to :func:`read_config_raw` and converts the resulting payload into
    a :class:`Config`, returning :data:`EMPTY_CONFIG` when no layer produced
    content.

    Parameters
    ----------
    vendor / app / slug:
        Naming context propagated to the path resolver (see the design docs).
    prefer:
        Optional sequence of preferred file suffixes (e.g. ``("toml", "json")``)
        used to prioritise ``config.d`` ordering within a layer.
    start_dir:
        Directory used when the dotenv loader searches upwards; useful for
        project-local configuration.

    Returns
    -------
    Config
        Immutable mapping with provenance metadata attached.

    Side Effects
    ------------
    Emits structured logging events for each resolved layer and resets the
    active trace identifier via :func:`bind_trace_id`.

    Examples
    --------
    >>> import os
    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> tmp = TemporaryDirectory()
    >>> root = Path(tmp.name)
    >>> previous_root = os.environ.get("LIB_LAYERED_CONFIG_ETC")
    >>> os.environ["LIB_LAYERED_CONFIG_ETC"] = str(root)
    >>> target = root / "demo"
    >>> _ = target.mkdir(parents=True, exist_ok=True)
    >>> content = os.linesep.join(['[service]', "name='demo'"])
    >>> _ = (target / 'config.toml').write_text(content, encoding='utf-8')
    >>> cfg = read_config(vendor="Acme", app="Demo", slug="demo")
    >>> cfg.get("service.name")
    'demo'
    >>> if previous_root is None:
    ...     _ = os.environ.pop("LIB_LAYERED_CONFIG_ETC")
    ... else:
    ...     os.environ["LIB_LAYERED_CONFIG_ETC"] = previous_root
    >>> tmp.cleanup()
    """

    data, meta = read_config_raw(vendor=vendor, app=app, slug=slug, prefer=prefer, start_dir=start_dir)
    if not data:
        return EMPTY_CONFIG
    return Config(data, meta)


def read_config_raw(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Return the merged configuration data and provenance metadata.

    Why
    ----
    Tooling and automation sometimes need access to primitive structures (for
    serialisation or UI rendering) without the `Mapping` interface provided by
    :class:`Config`.

    What
    ----
    Coordinates adapters, collects layer payloads, merges them via
    :func:`merge_layers`, and returns ``(merged_data, provenance)``.

    Returns
    -------
    tuple[dict[str, object], dict[str, dict[str, object]]]
        ``(merged_data, provenance)`` suitable for constructing a
        :class:`Config` instance.

    Side Effects
    ------------
    - Calls :func:`bind_trace_id` with ``None`` to clear previous trace context.
    - Emits structured log events for each layer and for the final merge.

    Examples
    --------
    The example mirrors :func:`read_config` but shows access to raw data:

    >>> data, meta = read_config_raw(vendor="Acme", app="Demo", slug="demo")
    >>> isinstance(data, dict) and isinstance(meta, dict)
    True
    """

    resolver = _build_resolver(vendor=vendor, app=app, slug=slug, start_dir=start_dir)
    dotenv_loader, env_loader = _build_loaders(resolver)

    bind_trace_id(None)

    layers = _gather_layers(
        resolver=resolver,
        prefer=prefer,
        dotenv_loader=dotenv_loader,
        env_loader=env_loader,
        slug=slug,
        start_dir=start_dir,
    )

    return _merge_or_empty(layers)


def _build_loaders(
    resolver: DefaultPathResolver,
) -> tuple[DefaultDotEnvLoader, DefaultEnvLoader]:
    """Return loaders bound to resolver-provided hints."""

    return DefaultDotEnvLoader(extras=resolver.dotenv()), DefaultEnvLoader()


def _gather_layers(
    *,
    resolver: DefaultPathResolver,
    prefer: Sequence[str] | None,
    dotenv_loader: DefaultDotEnvLoader,
    env_loader: DefaultEnvLoader,
    slug: str,
    start_dir: str | None,
) -> list[LayerEntry]:
    """Collect all layer entries in precedence order."""

    layers: list[LayerEntry] = []
    layers.extend(_collect_path_layers(resolver, prefer))
    _append_optional(layers, _dotenv_layer(dotenv_loader, start_dir))
    _append_optional(layers, _env_layer(env_loader, slug))
    return layers


def _build_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    start_dir: str | None,
) -> DefaultPathResolver:
    """Create a path resolver anchored at *start_dir* when provided.

    Why
        Keeps :func:`read_config_raw` focused on orchestration rather than
        constructor details.
    """

    cwd = Path(start_dir) if start_dir else None
    return DefaultPathResolver(vendor=vendor, app=app, slug=slug, cwd=cwd)


def _collect_path_layers(
    resolver: DefaultPathResolver,
    prefer: Sequence[str] | None,
) -> list[LayerEntry]:
    """Gather layer entries from filesystem-backed locations."""

    collected: list[LayerEntry] = []
    for layer_name, paths in _iter_path_layers(resolver):
        entries = _load_files(layer_name, paths, prefer)
        if entries:
            _log_layer_loaded(layer_name, None, {"files": len(entries)})
            collected.extend(entries)
    return collected


def _iter_path_layers(
    resolver: DefaultPathResolver,
) -> Iterable[tuple[str, Iterable[str]]]:
    """Yield ``(layer_name, paths)`` pairs in precedence order."""

    yield "app", resolver.app()
    yield "host", resolver.host()
    yield "user", resolver.user()


def _append_optional(layers: list[LayerEntry], entry: LayerEntry | None) -> None:
    """Append *entry* to *layers* when present."""

    if entry is not None:
        layers.append(entry)


def _dotenv_layer(loader: DefaultDotEnvLoader, start_dir: str | None) -> LayerEntry | None:
    """Return a dotenv layer entry when data exists."""

    data = loader.load(start_dir)
    if not data:
        return None
    _log_layer_loaded("dotenv", loader.last_loaded_path, {"keys": len(data)})
    return "dotenv", data, loader.last_loaded_path


def _env_layer(loader: DefaultEnvLoader, slug: str) -> LayerEntry | None:
    """Return an environment layer entry when data exists."""

    prefix = default_env_prefix(slug)
    data = loader.load(prefix)
    if not data:
        return None
    _log_layer_loaded("env", None, {"keys": len(data)})
    return "env", data, None


def _merge_or_empty(layers: list[LayerEntry]) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Return merged output or the empty tuple when no layers existed."""

    if not layers:
        _log_configuration_empty()
        return {}, {}

    merged = merge_layers(layers)
    _log_merge_complete(len(layers))
    return merged


def _log_layer_loaded(layer: str, path: str | None, details: Mapping[str, object]) -> None:
    """Emit a debug log that records a layer's successful load."""

    log_debug("layer_loaded", **make_event(layer, path, dict(details)))


def _log_configuration_empty() -> None:
    """Report that no configuration layers produced data."""

    log_info("configuration_empty", layer="none", path=None)


def _log_merge_complete(total_layers: int) -> None:
    """Announce that merging finished with *total_layers* entries."""

    log_info("configuration_merged", layer="final", path=None, total_layers=total_layers)


def _log_layer_error(layer: str, path: str, exc: Exception) -> None:
    """Capture loader errors with structured metadata."""

    _details = {"error": str(exc)}
    log_debug("layer_error", **make_event(layer, path, _details))


def _load_files(
    layer: str,
    paths: Iterable[str],
    prefer: Sequence[str] | None,
) -> list[LayerEntry]:
    """Load all files enumerated for *layer* returning non-empty mappings only.

    Why
    ----
    Isolate file-loading concerns so error handling and preference ordering stay
    consistent across layers.

    What
    ----
    Orders candidate paths, delegates to structured loaders, filters empty
    mappings, and annotates each entry with the originating path.

    Parameters
    ----------
    layer:
        Logical layer name (``"app"``, ``"host"``, ``"user"``).
    paths:
        Iterable of candidate file paths discovered by the resolver.
    prefer:
        Optional sequence of preferred suffixes used to prioritise file order.

    Returns
    -------
    list[LayerEntry]
        Entries ready for :func:`merge_layers`, each containing the layer name,
        parsed mapping, and optional filepath.

    Side Effects
    ------------
    Emits structured debug logs for successful loads and errors.

    Examples
    --------
    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> tmp = TemporaryDirectory()
    >>> file_path = Path(tmp.name) / "sample.json"
    >>> _ = file_path.write_text('{"flag": true}', encoding="utf-8")
    >>> entries = _load_files("user", [str(file_path)], prefer=None)
    >>> entries[0][1]["flag"]
    True
    >>> tmp.cleanup()
    """

    ordered_paths = _order_paths(paths, prefer)
    entries: list[LayerEntry] = []
    for path in ordered_paths:
        entry = _load_entry(layer, path)
        if entry is not None:
            entries.append(entry)
    return entries


def _load_entry(layer: str, path: str) -> LayerEntry | None:
    """Return a layer entry for *path* when a loader is available."""

    loader = _FILE_LOADERS.get(Path(path).suffix.lower())
    if loader is None:
        return None
    try:
        data = loader.load(path)
    except NotFound:
        return None
    except InvalidFormat as exc:
        _log_layer_error(layer, path, exc)
        raise LayerLoadError(f"Failed to load {layer} layer file {path}: {exc}") from exc
    if not data:
        return None
    return layer, data, path


def _order_paths(paths: Iterable[str], prefer: Sequence[str] | None) -> list[str]:
    """Order ``paths`` so preferred suffixes appear first (stable sort).

    Why
    ----
    Allow callers to prioritise formats (e.g., TOML before YAML) without
    modifying filesystem contents.

    What
    ----
    Builds a ranking map from ``prefer`` and sorts paths while preserving
    original order within the same rank.

    Examples
    --------
    >>> _order_paths(["a.json", "b.toml"], ["toml", "json"])
    ['b.toml', 'a.json']
    """

    path_list = list(paths)
    if not prefer:
        return path_list
    ranking = {suffix.lower().lstrip("."): idx for idx, suffix in enumerate(prefer)}
    return sorted(
        path_list,
        key=lambda p: ranking.get(Path(p).suffix.lower().lstrip("."), len(ranking)),
    )


__all__ = [
    "Config",
    "ConfigError",
    "InvalidFormat",
    "ValidationError",
    "NotFound",
    "LayerLoadError",
    "read_config",
    "read_config_raw",
    "default_env_prefix",
]
