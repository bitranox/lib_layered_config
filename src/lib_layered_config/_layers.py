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
    """Return layer snapshots in precedence order.

    Why
    ----
    Centralises discovery so :func:`lib_layered_config.core.read_config_raw`
    stays focused on error handling and orchestration while keeping precedence
    logic self-contained.

    Parameters
    ----------
    resolver:
        Path resolver supplying filesystem candidates for ``app``/``host``/``user``
        layers.
    prefer:
        Optional ordered list of preferred suffixes (e.g. ``["toml", "json"]``)
        influencing filesystem candidate sorting.
    default_file:
        Optional lowest-precedence configuration file injected before filesystem
        layers.
    dotenv_loader:
        Loader used to parse ``.env`` files.
    env_loader:
        Loader used to translate environment variables using the documented
        prefix rules.
    slug:
        Slug identifying the configuration family (used for environment prefix
        construction when no ``default_file`` is provided).
    start_dir:
        Optional directory that seeds the ``.env`` upward search.

    Returns
    -------
    list[LayerSnapshot]
        Snapshot sequence ordered from lowest to highest precedence.

    Side Effects
    ------------
    Emits structured logging events via ``_note_layer_loaded`` when layers are
    discovered.

    Examples
    --------
    >>> from tempfile import TemporaryDirectory
    >>> class StubResolver:
    ...     def app(self):
    ...         return ()
    ...     def host(self):
    ...         return ()
    ...     def user(self):
    ...         return ()
    >>> class StubDotenv:
    ...     last_loaded_path = None
    ...     def load(self, start_dir):
    ...         return {}
    >>> class StubEnv:
    ...     def load(self, prefix):
    ...         return {}
    >>> tmp = TemporaryDirectory()
    >>> defaults = Path(tmp.name) / 'defaults.toml'
    >>> _ = defaults.write_text('value = 1', encoding='utf-8')
    >>> snapshots = collect_layers(
    ...     resolver=StubResolver(),
    ...     prefer=None,
    ...     default_file=str(defaults),
    ...     dotenv_loader=StubDotenv(),
    ...     env_loader=StubEnv(),
    ...     slug='demo',
    ...     start_dir=None,
    ... )
    >>> [(snap.name, snap.origin.endswith('defaults.toml')) for snap in snapshots]
    [('defaults', True)]
    >>> tmp.cleanup()
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

    Why
    ----
    Capture the precedence hierarchy (`defaults → app → host → user → dotenv → env`)
    in one generator so callers cannot accidentally skip a layer.

    Parameters
    ----------
    resolver / prefer / default_file / dotenv_loader / env_loader / slug / start_dir:
        Same meaning as :func:`collect_layers`.

    Yields
    ------
    LayerSnapshot
        Snapshot tuples ready for the merge policy.
    """

    yield from _default_snapshots(default_file)
    yield from _filesystem_snapshots(resolver, prefer)
    yield from _dotenv_snapshots(dotenv_loader, start_dir)
    yield from _env_snapshots(env_loader, slug)


def merge_or_empty(layers: list[LayerSnapshot]) -> tuple[dict[str, object], dict[str, SourceInfoPayload]]:
    """Merge collected layers or return empty dictionaries when none exist.

    Why
    ----
    Provides a guard so callers do not have to special-case empty layer collections.

    Parameters
    ----------
    layers:
        Layer snapshots in precedence order.

    Returns
    -------
    tuple[dict[str, object], dict[str, SourceInfoPayload]]
        Pair containing merged configuration data and provenance mappings.

    Side Effects
    ------------
    Emits ``configuration_empty`` or ``configuration_merged`` events depending on
    the layer count.
    """

    if not layers:
        _note_configuration_empty()
        return {}, {}

    merged = merge_layers(layers)
    _note_merge_complete(len(layers))
    return merged


def _default_snapshots(default_file: str | None) -> Iterator[LayerSnapshot]:
    """Yield a defaults snapshot when *default_file* is supplied.

    Parameters
    ----------
    default_file:
        Absolute path string to the optional defaults file.

    Yields
    ------
    LayerSnapshot
        Snapshot describing the defaults layer.

    Side Effects
    ------------
    Emits ``layer_loaded`` events when a defaults file is parsed.
    """

    if not default_file:
        return

    snapshot = _load_entry("defaults", default_file)
    if snapshot is None:
        return

    _note_layer_loaded(snapshot.name, snapshot.origin, {"keys": len(snapshot.payload)})
    yield snapshot


def _filesystem_snapshots(resolver: DefaultPathResolver, prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield filesystem-backed layer snapshots in precedence order.

    Parameters
    ----------
    resolver:
        Path resolver supplying candidate paths per layer.
    prefer:
        Optional suffix ordering applied when multiple files exist.

    Yields
    ------
    LayerSnapshot
        Snapshots for ``app``/``host``/``user`` layers.
    """

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
    """Yield a snapshot for dotenv-provided values when present.

    Parameters
    ----------
    loader:
        Dotenv loader that handles discovery and parsing.
    start_dir:
        Optional starting directory for the upward search.

    Yields
    ------
    LayerSnapshot
        Snapshot representing the ``dotenv`` layer when a file exists.
    """

    data = loader.load(start_dir)
    if not data:
        return
    _note_layer_loaded("dotenv", loader.last_loaded_path, {"keys": len(data)})
    yield LayerSnapshot("dotenv", data, loader.last_loaded_path)


def _env_snapshots(loader: DefaultEnvLoader, slug: str) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for environment-variable configuration.

    Parameters
    ----------
    loader:
        Environment loader converting prefixed variables into nested mappings.
    slug:
        Slug identifying the configuration family.

    Yields
    ------
    LayerSnapshot
        Snapshot for the ``env`` layer when variables are present.
    """

    prefix = default_env_prefix(slug)
    data = loader.load(prefix)
    if not data:
        return
    _note_layer_loaded("env", None, {"keys": len(data)})
    yield LayerSnapshot("env", data, None)


def _snapshots_from_paths(layer: str, paths: Iterable[str], prefer: Sequence[str] | None) -> Iterator[LayerSnapshot]:
    """Yield snapshots for every supported file inside *paths*.

    Parameters
    ----------
    layer:
        Logical layer name the files belong to.
    paths:
        Iterable of candidate file paths.
    prefer:
        Optional suffix ordering hint passed by the CLI/API.

    Yields
    ------
    LayerSnapshot
        Snapshot for each successfully loaded file.
    """

    for path in _paths_in_preferred_order(paths, prefer):
        snapshot = _load_entry(layer, path)
        if snapshot is not None:
            yield snapshot


def _load_entry(layer: str, path: str) -> LayerSnapshot | None:
    """Load *path* using the configured file loaders and return a snapshot.

    Parameters
    ----------
    layer:
        Logical layer name associated with the file.
    path:
        Absolute path to the candidate configuration file.

    Returns
    -------
    LayerSnapshot | None
        Snapshot when parsing succeeds and data is non-empty; otherwise ``None``.

    Raises
    ------
    InvalidFormat
        When the loader encounters invalid content. The exception is logged and
        re-raised so callers can surface context to users.
    """

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
    """Return candidate paths honouring the optional *prefer* order.

    Parameters
    ----------
    paths:
        Iterable of candidate file paths.
    prefer:
        Optional sequence of preferred suffixes ordered by priority.

    Returns
    -------
    list[str]
        Candidate paths sorted according to preferred suffix ranking.

    Examples
    --------
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

    Parameters
    ----------
    layer:
        Logical layer name.
    path:
        Optional path associated with the event.
    details:
        Additional structured metadata (e.g., number of files or keys).

    Side Effects
    ------------
    Calls :func:`log_debug` with the structured event payload.
    """

    log_debug("layer_loaded", **make_event(layer, path, dict(details)))


def _note_layer_error(layer: str, path: str, exc: Exception) -> None:
    """Emit a debug event describing a recoverable layer error.

    Parameters
    ----------
    layer:
        Layer currently being processed.
    path:
        File path that triggered the error.
    exc:
        Exception raised by the loader.
    """

    log_debug("layer_error", **make_event(layer, path, {"error": str(exc)}))


def _note_configuration_empty() -> None:
    """Emit an info event signalling that no configuration was discovered."""

    log_info("configuration_empty", layer="none", path=None)


def _note_merge_complete(total_layers: int) -> None:
    """Emit an info event summarising the merge outcome.

    Parameters
    ----------
    total_layers:
        Number of layers processed in the merge.
    """

    log_info("configuration_merged", layer="final", path=None, total_layers=total_layers)
