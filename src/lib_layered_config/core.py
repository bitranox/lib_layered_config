"""Composition root for ``lib_layered_config``.

Purpose
-------
Provide the single entry point that orchestrates path resolution, file loading,
dotenv parsing, environment ingestion, and merge policy enforcement.  The module
implements the Clean Architecture composition root described in
``docs/systemdesign/module_reference.md`` and exports only stable, consumer-ready
APIs.

Contents
--------
* :data:`_FILE_LOADERS` – mapping of file suffixes to loader instances.
* :class:`LayerLoadError` – error raised when a layer fails to materialise.
* :func:`read_config` – high-level API returning a :class:`Config` instance.
* :func:`read_config_raw` – lower-level API returning raw data + provenance.
* :func:`_load_files` / :func:`_order_paths` – internal helpers used by the
  composition flow.

System Role
-----------
This module connects adapters (filesystem, dotenv, environment) with the domain
value object while emitting structured observability signals.  It is the
canonical location for adjusting precedence rules or wiring new adapters.
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

    resolver = DefaultPathResolver(vendor=vendor, app=app, slug=slug, cwd=Path(start_dir) if start_dir else None)
    dot_env_loader = DefaultDotEnvLoader(extras=resolver.dotenv())
    env_loader = DefaultEnvLoader()

    bind_trace_id(None)

    layers: list[tuple[str, Mapping[str, object], str | None]] = []
    for layer_name, paths in (
        ("app", resolver.app()),
        ("host", resolver.host()),
        ("user", resolver.user()),
    ):
        entries = _load_files(layer_name, paths, prefer)
        if entries:
            log_debug("layer_loaded", **make_event(layer_name, None, {"files": len(entries)}))
            layers.extend(entries)

    dotenv_data = dot_env_loader.load(start_dir)
    if dotenv_data:
        layers.append(("dotenv", dotenv_data, dot_env_loader.last_loaded_path))
        log_debug("layer_loaded", **make_event("dotenv", dot_env_loader.last_loaded_path, {"keys": len(dotenv_data)}))

    env_prefix = default_env_prefix(slug)
    env_data = env_loader.load(env_prefix)
    if env_data:
        layers.append(("env", env_data, None))
        log_debug("layer_loaded", **make_event("env", None, {"keys": len(env_data)}))

    if not layers:
        log_info("configuration_empty", layer="none", path=None)
        return {}, {}

    merged = merge_layers(layers)
    log_info("configuration_merged", layer="final", path=None, total_layers=len(layers))
    return merged


def _load_files(
    layer: str, paths: Iterable[str], prefer: Sequence[str] | None
) -> list[tuple[str, Mapping[str, object], str | None]]:
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
    list[tuple[str, Mapping[str, object], str | None]]
        Tuples containing the layer name, parsed mapping, and file path.

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
    collected: list[tuple[str, Mapping[str, object], str | None]] = []
    for path in ordered_paths:
        loader = _FILE_LOADERS.get(Path(path).suffix.lower())
        if loader is None:
            continue
        try:
            data = loader.load(path)
        except NotFound:
            continue
        except InvalidFormat as exc:
            log_debug("layer_error", layer=layer, path=path, error=str(exc))
            raise LayerLoadError(f"Failed to load {layer} layer file {path}: {exc}") from exc
        if data:
            collected.append((layer, data, path))
    return collected


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
