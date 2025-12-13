"""Assemble configuration layers prior to merging.

Provide a composition helper that coordinates filesystem discovery, dotenv
loading, environment ingestion, and defaults injection before passing
``LayerSnapshot`` instances to the merge policy.

Contents:
- ``collect_layers``: orchestrator returning a list of snapshots.
- ``merge_or_empty``: convenience wrapper combining collect/merge behaviour.
- Internal generators that yield defaults, filesystem, dotenv, and environment
  snapshots in documented precedence order.

System Role:
Invoked exclusively by ``lib_layered_config.core``. Keeps orchestration logic
separate from adapters while remaining independent of the domain layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path

from .adapters.dotenv.default import DefaultDotEnvLoader
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.file_loaders._dot_d import expand_dot_d
from .adapters.file_loaders.structured import JSONFileLoader, TOMLFileLoader, YAMLFileLoader
from .adapters.path_resolvers.default import DefaultPathResolver
from .application.merge import LayerSnapshot, MergeResult, merge_layers
from .domain.errors import InvalidFormatError, NotFoundError
from .domain.identifiers import Layer
from .observability import log_debug, log_info, make_event

#: Mapping from file suffix to loader instance. The ordering preserves the
#: precedence documented for structured configuration formats while keeping all
#: logic in one place.
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
    """Return layer snapshots in precedence order (defaults → app → host → user → dotenv → env).

    Centralises discovery so callers stay focused on error handling.
    Emits structured logging events when layers are discovered.
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
    """Yield layer snapshots in the documented merge order.

    Capture the precedence hierarchy (`defaults → app → host → user → dotenv → env`)
    in one generator so callers cannot accidentally skip a layer.

    Args:
        resolver / prefer / default_file / dotenv_loader / env_loader / slug / start_dir:
            Same meaning as :func:`collect_layers`.

    Yields:
        LayerSnapshot: Snapshot tuples ready for the merge policy.
    """
    yield from _default_snapshots(default_file)
    yield from _filesystem_snapshots(resolver, prefer)
    yield from _dotenv_snapshots(dotenv_loader, start_dir)
    yield from _env_snapshots(env_loader, slug)


def merge_or_empty(layers: list[LayerSnapshot]) -> MergeResult:
    """Merge collected layers or return empty result when none exist.

    Provides a guard so callers do not have to special-case empty layer collections.

    Args:
        layers: Layer snapshots in precedence order.

    Returns:
        MergeResult: Dataclass containing merged configuration data and provenance mappings.

    Side Effects:
        Emits ``configuration_empty`` or ``configuration_merged`` events depending on
        the layer count.
    """
    if not layers:
        _note_configuration_empty()
        return MergeResult(data={}, provenance={})

    result = merge_layers(layers)
    _note_merge_complete(len(layers))
    return result


def _default_snapshots(default_file: str | None) -> Iterator[LayerSnapshot]:
    """Yield defaults snapshots when *default_file* is supplied.

    The default file is expanded to include any companion ``.d`` directory files.

    Args:
        default_file: Absolute path string to the optional defaults file.

    Yields:
        LayerSnapshot: Snapshots describing the defaults layer.

    Side Effects:
        Emits ``layer_loaded`` events when defaults files are parsed.
    """
    if not default_file:
        return

    snapshots = list(_load_entry_with_dot_d(Layer.DEFAULTS, default_file))
    if not snapshots:
        return

    for snapshot in snapshots:
        _note_layer_loaded(snapshot.name, snapshot.origin, {"keys": len(snapshot.payload)})
        yield snapshot


def _filesystem_snapshots(resolver: DefaultPathResolver, prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield filesystem-backed layer snapshots in precedence order.

    Args:
        resolver: Path resolver supplying candidate paths per layer.
        prefer: Optional suffix ordering applied when multiple files exist.

    Yields:
        LayerSnapshot: Snapshots for ``app``/``host``/``user`` layers.
    """
    for layer, paths in (
        (Layer.APP, resolver.app()),
        (Layer.HOST, resolver.host()),
        (Layer.USER, resolver.user()),
    ):
        snapshots = list(_snapshots_from_paths(layer, paths, prefer))
        if snapshots:
            _note_layer_loaded(layer, None, {"files": len(snapshots)})
            yield from snapshots


def _dotenv_snapshots(loader: DefaultDotEnvLoader, start_dir: str | None) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for dotenv-provided values when present.

    Args:
        loader: Dotenv loader that handles discovery and parsing.
        start_dir: Optional starting directory for the upward search.

    Yields:
        LayerSnapshot: Snapshot representing the ``dotenv`` layer when a file exists.
    """
    data = loader.load(start_dir)
    if not data:
        return
    _note_layer_loaded(Layer.DOTENV, loader.last_loaded_path, {"keys": len(data)})
    yield LayerSnapshot(Layer.DOTENV, data, loader.last_loaded_path)


def _env_snapshots(loader: DefaultEnvLoader, slug: str) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for environment-variable configuration.

    Args:
        loader: Environment loader converting prefixed variables into nested mappings.
        slug: Slug identifying the configuration family.

    Yields:
        LayerSnapshot: Snapshot for the ``env`` layer when variables are present.
    """
    prefix = default_env_prefix(slug)
    data = loader.load(prefix)
    if not data:
        return
    _note_layer_loaded(Layer.ENV, None, {"keys": len(data)})
    yield LayerSnapshot(Layer.ENV, data, None)


def _snapshots_from_paths(layer: str, paths: Iterable[str], prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield snapshots for every supported file inside *paths*.

    Each path is expanded to include any companion ``.d`` directory files.

    Args:
        layer: Logical layer name the files belong to.
        paths: Iterable of candidate file paths.
        prefer: Optional suffix ordering hint passed by the CLI/API.

    Yields:
        LayerSnapshot: Snapshot for each successfully loaded file.
    """
    for path in _paths_in_preferred_order(paths, prefer):
        yield from _load_entry_with_dot_d(layer, path)


def _load_entry(layer: str, path: str) -> LayerSnapshot | None:
    """Load *path* using the configured file loaders and return a snapshot.

    Args:
        layer: Logical layer name associated with the file.
        path: Absolute path to the candidate configuration file.

    Returns:
        LayerSnapshot | None: Snapshot when parsing succeeds and data is non-empty; otherwise ``None``.

    Raises:
        InvalidFormatError: When the loader encounters invalid content. The exception is logged
            and re-raised so callers can surface context to users.
    """
    loader = _FILE_LOADERS.get(Path(path).suffix.lower())
    if loader is None:
        return None
    try:
        data = loader.load(path)
    except NotFoundError:
        return None
    except InvalidFormatError as exc:  # pragma: no cover - validated by adapter tests
        _note_layer_error(layer, path, exc)
        raise
    if not data:
        return None
    return LayerSnapshot(layer, data, path)


def _load_entry_with_dot_d(layer: str, path: str) -> Iterator[LayerSnapshot]:
    """Load *path* and any companion .d directory files as snapshots.

    For a file ``foo.toml``, checks for ``foo.toml.d/`` directory and yields
    snapshots for:
    1. The base file (if it exists)
    2. Files from the .d directory in lexicographical order (if directory exists)

    Both the base file and .d directory are optional.

    Args:
        layer: Logical layer name associated with the files.
        path: Absolute path to the base configuration file.

    Yields:
        LayerSnapshot: Snapshot for each file (base + .d entries) in merge order.

    Raises:
        InvalidFormatError: When any file contains invalid content.
    """
    expanded_paths = list(expand_dot_d(path))
    if len(expanded_paths) > 1:
        _note_dot_d_expanded(path, len(expanded_paths) - 1)

    for expanded_path in expanded_paths:
        snapshot = _load_entry(layer, expanded_path)
        if snapshot is not None:
            yield snapshot


def _paths_in_preferred_order(paths: Iterable[str], prefer: Sequence[str] | None) -> list[str]:
    """Return candidate paths honouring the optional *prefer* order.

    Args:
        paths: Iterable of candidate file paths.
        prefer: Optional sequence of preferred suffixes ordered by priority.

    Returns:
        list[str]: Candidate paths sorted according to preferred suffix ranking.

    Examples:
        >>> _paths_in_preferred_order(
        ...     ['a.toml', 'b.yaml'],
        ...     prefer=('yaml', 'toml'),
        ... )
        ['b.yaml', 'a.toml']
    """
    ordered = list(paths)
    if not prefer:
        return ordered
    ranking = {suffix.lower().lstrip("."): index for index, suffix in enumerate(prefer)}
    return sorted(ordered, key=lambda candidate: ranking.get(Path(candidate).suffix.lower().lstrip("."), len(ranking)))


def _note_layer_loaded(layer: str, path: str | None, details: Mapping[str, object]) -> None:
    """Emit a debug event capturing successful layer discovery.

    Args:
        layer: Logical layer name.
        path: Optional path associated with the event.
        details: Additional structured metadata (e.g., number of files or keys).

    Side Effects:
        Calls :func:`log_debug` with the structured event payload.
    """
    log_debug("layer_loaded", **make_event(layer, path, dict(details)))


def _note_layer_error(layer: str, path: str, exc: Exception) -> None:
    """Emit a debug event describing a recoverable layer error.

    Args:
        layer: Layer currently being processed.
        path: File path that triggered the error.
        exc: Exception raised by the loader.
    """
    log_debug("layer_error", **make_event(layer, path, {"error": str(exc)}))


def _note_dot_d_expanded(base_path: str, dot_d_count: int) -> None:
    """Emit a debug event when .d directory expansion occurs.

    Args:
        base_path: Path to the base configuration file.
        dot_d_count: Number of files found in the .d directory.
    """
    log_debug("dot_d_expanded", layer="file", path=base_path, dot_d_files=dot_d_count)


def _note_configuration_empty() -> None:
    """Emit an info event signalling that no configuration was discovered."""
    log_info("configuration_empty", layer="none", path=None)


def _note_merge_complete(total_layers: int) -> None:
    """Emit an info event summarising the merge outcome.

    Args:
        total_layers: Number of layers processed in the merge.
    """
    log_info("configuration_merged", layer="final", path=None, total_layers=total_layers)
