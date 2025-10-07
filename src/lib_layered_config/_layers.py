"""Assemble configuration layers prior to merging.

Purpose
-------
Provide a composition helper that coordinates filesystem discovery, dotenv
loading, environment ingestion, and defaults injection before passing
``LayerSnapshot`` instances to the merge policy.

Contents
--------
- ``collect_layers``: orchestrator returning a list of snapshots.
- ``merge_or_empty``: convenience wrapper combining collect/merge behaviour.
- Internal generators that yield defaults, filesystem, dotenv, and environment
  snapshots in documented precedence order.

System Role
-----------
Invoked exclusively by ``lib_layered_config.core``. Keeps orchestration logic
separate from adapters while remaining independent of the domain layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from .application.merge import LayerSnapshot, SourceInfoPayload, merge_layers
from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from .adapters.path_resolvers.default import DefaultPathResolver
from .domain.errors import InvalidFormat, NotFound
from .observability import log_debug, log_info, make_event

_FILE_LOADERS = {
    ".toml": TOMLFileLoader(),
    ".json": JSONFileLoader(),
    ".yaml": YAMLFileLoader(),
    ".yml": YAMLFileLoader(),
}

__all__ = ["collect_layers", "merge_or_empty"]


def collect_layers(
    *,
    resolver: DefaultPathResolver,
    prefer: Sequence[str] | None,
    default_file: str | None,
    dotenv_loader: DefaultDotEnvLoader,
    env_loader: DefaultEnvLoader,
    slug: str,
    start_dir: str | None,
) -> list[LayerSnapshot]:
    """Return layer snapshots in precedence order.

    Why
    ----
    Centralises discovery so :func:`lib_layered_config.core.read_config_raw`
    stays focused on error handling and orchestration.
    """

    return list(
        _snapshots_in_merge_sequence(
            resolver=resolver,
            prefer=prefer,
            default_file=default_file,
            dotenv_loader=dotenv_loader,
            env_loader=env_loader,
            slug=slug,
            start_dir=start_dir,
        )
    )


def _snapshots_in_merge_sequence(
    *,
    resolver: DefaultPathResolver,
    prefer: Sequence[str] | None,
    default_file: str | None,
    dotenv_loader: DefaultDotEnvLoader,
    env_loader: DefaultEnvLoader,
    slug: str,
    start_dir: str | None,
) -> Iterator[LayerSnapshot]:
    """Yield layer snapshots in the documented merge order."""

    yield from _default_snapshots(default_file)
    yield from _filesystem_snapshots(resolver, prefer)
    yield from _dotenv_snapshots(dotenv_loader, start_dir)
    yield from _env_snapshots(env_loader, slug)


def merge_or_empty(layers: list[LayerSnapshot]) -> tuple[dict[str, object], dict[str, SourceInfoPayload]]:
    """Merge collected layers or return empty dictionaries when none exist."""

    if not layers:
        _note_configuration_empty()
        return {}, {}

    merged = merge_layers(layers)
    _note_merge_complete(len(layers))
    return merged


def _default_snapshots(default_file: str | None) -> Iterator[LayerSnapshot]:
    """Yield a defaults snapshot when *default_file* is supplied."""

    if not default_file:
        return

    snapshot = _load_entry("defaults", default_file)
    if snapshot is None:
        return

    _note_layer_loaded(snapshot.name, snapshot.origin, {"keys": len(snapshot.payload)})
    yield snapshot


def _filesystem_snapshots(resolver: DefaultPathResolver, prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield filesystem-backed layer snapshots in precedence order."""

    for layer, paths in (
        ("app", resolver.app()),
        ("host", resolver.host()),
        ("user", resolver.user()),
    ):
        snapshots = list(_snapshots_from_paths(layer, paths, prefer))
        if snapshots:
            _note_layer_loaded(layer, None, {"files": len(snapshots)})
            yield from snapshots


def _dotenv_snapshots(loader: DefaultDotEnvLoader, start_dir: str | None) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for dotenv-provided values when present."""

    data = loader.load(start_dir)
    if not data:
        return
    _note_layer_loaded("dotenv", loader.last_loaded_path, {"keys": len(data)})
    yield LayerSnapshot("dotenv", data, loader.last_loaded_path)


def _env_snapshots(loader: DefaultEnvLoader, slug: str) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for environment-variable configuration."""

    prefix = default_env_prefix(slug)
    data = loader.load(prefix)
    if not data:
        return
    _note_layer_loaded("env", None, {"keys": len(data)})
    yield LayerSnapshot("env", data, None)


def _snapshots_from_paths(layer: str, paths: Iterable[str], prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield snapshots for every supported file inside *paths*."""

    for path in _paths_in_preferred_order(paths, prefer):
        snapshot = _load_entry(layer, path)
        if snapshot is not None:
            yield snapshot


def _load_entry(layer: str, path: str) -> LayerSnapshot | None:
    loader = _FILE_LOADERS.get(Path(path).suffix.lower())
    if loader is None:
        return None
    try:
        data = loader.load(path)
    except NotFound:
        return None
    except InvalidFormat as exc:  # pragma: no cover - validated by adapter tests
        _note_layer_error(layer, path, exc)
        raise
    if not data:
        return None
    return LayerSnapshot(layer, data, path)


def _paths_in_preferred_order(paths: Iterable[str], prefer: Sequence[str] | None) -> list[str]:
    """Return candidate paths honouring the optional *prefer* order."""

    ordered = list(paths)
    if not prefer:
        return ordered
    ranking = {suffix.lower().lstrip("."): index for index, suffix in enumerate(prefer)}
    return sorted(ordered, key=lambda candidate: ranking.get(Path(candidate).suffix.lower().lstrip("."), len(ranking)))


def _note_layer_loaded(layer: str, path: str | None, details: Mapping[str, object]) -> None:
    log_debug("layer_loaded", **make_event(layer, path, dict(details)))


def _note_layer_error(layer: str, path: str, exc: Exception) -> None:
    log_debug("layer_error", **make_event(layer, path, {"error": str(exc)}))


def _note_configuration_empty() -> None:
    log_info("configuration_empty", layer="none", path=None)


def _note_merge_complete(total_layers: int) -> None:
    log_info("configuration_merged", layer="final", path=None, total_layers=total_layers)
