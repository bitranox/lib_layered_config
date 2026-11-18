"""Assemble configuration layers prior to merging.

Provide a composition helper that coordinates filesystem discovery, dotenv
loading, environment ingestion, and defaults injection before passing
``LayerSnapshot`` instances to the merge policy.

Contents:
- ``collect_layers``: orchestrator yielding snapshots lazily, one parsed file at a time.
- ``collect_deploy_layers``: the narrower set that decides deploy modes (no dotenv,
  the files a deploy writes skipped, no ``app_*``/``host_*`` mode from a user-layer file).
- ``merge_or_empty``: convenience wrapper combining collect/merge behaviour.
- Internal generators that yield defaults, filesystem, dotenv, and environment
  snapshots in documented precedence order.

System Role:
Invoked exclusively by ``lib_layered_config.core``. Keeps orchestration logic
separate from adapters while remaining independent of the domain layer.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from .adapters._path_probe import PathKind, checked_kind
from .adapters.env.default import DefaultEnvLoader, default_env_prefix
from .adapters.file_loaders._dot_d import expand_dot_d
from .adapters.file_loaders.structured import (
    JSONFileLoader,
    TOMLFileLoader,
    YAMLFileLoader,
    special_file_not_config_file,
    unsupported_config_format,
)
from .application.merge import LayerSnapshot, MergeResult, merge_layers
from .domain.deploy_permissions import drop_app_and_host_modes
from .domain.errors import InvalidFormatError, LayerRootNotAbsoluteError, NotFoundError
from .domain.identifiers import Layer
from .observability import log_debug, log_info, log_warn, make_event

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping
    from pathlib import Path

    from .adapters.dotenv.default import DefaultDotEnvLoader
    from .adapters.path_resolvers.default import DefaultPathResolver

#: Mapping from file suffix to loader instance. The ordering preserves the
#: precedence documented for structured configuration formats while keeping all
#: logic in one place.
_FILE_LOADERS: Final = MappingProxyType(
    {
        ".toml": TOMLFileLoader(),
        ".json": JSONFileLoader(),
        ".yaml": YAMLFileLoader(),
        ".yml": YAMLFileLoader(),
    }
)

__all__ = ["collect_deploy_layers", "collect_layers", "merge_or_empty", "parse_with_dot_d"]


def collect_layers(
    *,
    resolver: DefaultPathResolver,
    default_file: Path | None,
    dotenv_loader: DefaultDotEnvLoader,
    env_loader: DefaultEnvLoader,
    slug: str,
    start_dir: Path | None,
    dotenv_path: Path | None = None,
) -> Iterator[LayerSnapshot]:
    """Yield layer snapshots in precedence order (defaults -> app -> host -> user -> dotenv -> env).

    Lazy: nothing is read until the caller iterates, and each file is parsed only when the merge
    asks for it, so a load error surfaces during that iteration (see ``merge_or_empty``).
    Emits structured logging events when layers are discovered.
    """
    return _snapshots_in_merge_sequence(
        resolver=resolver,
        default_file=default_file,
        dotenv_loader=dotenv_loader,
        env_loader=env_loader,
        slug=slug,
        start_dir=start_dir,
        dotenv_path=dotenv_path,
    )


def collect_deploy_layers(
    *,
    resolver: DefaultPathResolver,
    default_file: Path,
    env_loader: DefaultEnvLoader,
    skip: frozenset[Path],
) -> Iterator[LayerSnapshot]:
    """Yield the layers that decide deploy modes: defaults, the app/host/user files not in *skip*, env.

    There is no dotenv layer: its search starts at the working directory, which would give whoever
    controls the directory a deploy runs from a say over the modes of system files. For the same
    reason a user-layer file (under a home directory a root deploy may have inherited from the
    invoking account) keeps only its ``user_*`` and ``enabled`` settings: its ``app_*``/``host_*``
    modes are dropped before the merge, so they neither decide a mode nor hide a lower layer's.
    *skip* holds the resolved paths the deploy is about to write, so a file never decides its own
    replacement.
    """
    yield from _default_snapshots(default_file)
    yield from _without_user_layer_system_modes(_deploy_filesystem_snapshots(resolver, skip=skip))
    yield from _env_snapshots(env_loader, resolver.slug)


def _deploy_filesystem_snapshots(resolver: DefaultPathResolver, *, skip: frozenset[Path]) -> Iterator[LayerSnapshot]:
    """Yield the app/host/user snapshots a deploy reads its modes from; an unrootable layer is absent.

    A deploy for Windows run elsewhere may have no ProgramData root (``C:\\ProgramData`` is relative
    off Windows). A user-only deploy needs none, and no file can sit under a root with no absolute
    path here, so that layer has no modes to give: it is skipped, never read relative to the cwd.
    A deploy that WRITES under such a root still refuses, in the resolver call that picks its
    destination.
    """
    for layer, paths in _filesystem_layer_paths(resolver):
        try:
            # Only the resolver call sits in the try: it refuses a non-absolute root when called.
            candidates = paths()
        except LayerRootNotAbsoluteError as exc:
            log_debug("layer_root_not_absolute", **make_event(layer, None, {"reason": str(exc)}))
            continue
        files = 0
        for snapshot in _snapshots_from_paths(layer, candidates, skip=skip):
            files += 1
            yield snapshot
        if files:
            _note_layer_loaded(layer, None, {"files": files})


def _without_user_layer_system_modes(snapshots: Iterable[LayerSnapshot]) -> Iterator[LayerSnapshot]:
    """Yield *snapshots*, each user-layer one without its ``app_*``/``host_*`` modes.

    A dropped setting is logged by its key and file, never by its value, so an operator can see why a
    mode set there has no effect.
    """
    for snapshot in snapshots:
        if snapshot.name != Layer.USER:
            yield snapshot
            continue
        payload, dropped = drop_app_and_host_modes(snapshot.payload)
        if not dropped:
            yield snapshot
            continue
        log_warn("deploy_setting_ignored", **make_event(snapshot.name, snapshot.origin, {"keys": list(dropped)}))
        yield LayerSnapshot(snapshot.name, payload, snapshot.origin)


def _snapshots_in_merge_sequence(
    *,
    resolver: DefaultPathResolver,
    default_file: Path | None,
    dotenv_loader: DefaultDotEnvLoader,
    env_loader: DefaultEnvLoader,
    slug: str,
    start_dir: Path | None,
    dotenv_path: Path | None = None,
) -> Iterator[LayerSnapshot]:
    """Yield layer snapshots in the documented merge order.

    Capture the precedence hierarchy (`defaults -> app -> host -> user -> dotenv -> env`)
    in one generator so callers cannot accidentally skip a layer.

    Args:
        resolver / default_file / dotenv_loader / env_loader / slug / start_dir:
            Same meaning as :func:`collect_layers`.
        dotenv_path: When set, load this specific file instead of searching.

    Yields:
        LayerSnapshot: Snapshot tuples ready for the merge policy.
    """
    yield from _default_snapshots(default_file)
    yield from _filesystem_snapshots(resolver)
    yield from _dotenv_snapshots(dotenv_loader, start_dir, dotenv_path=dotenv_path)
    yield from _env_snapshots(env_loader, slug)


def merge_or_empty(layers: Iterable[LayerSnapshot]) -> MergeResult:
    """Merge layers as they arrive, or return an empty result when there are none.

    *layers* is consumed once, each snapshot merged and dropped before the next is produced, so peak
    memory is the merged result plus one parsed file however many files the layers hold.

    Args:
        layers: Layer snapshots in precedence order.

    Returns:
        MergeResult: Dataclass containing merged configuration data and provenance mappings.

    Side Effects:
        Emits ``configuration_empty`` or ``configuration_merged`` events depending on
        the layer count.
    """
    counted = _CountedLayers(layers)
    result = merge_layers(counted)
    if counted.total == 0:
        _note_configuration_empty()
        return MergeResult(data={}, provenance={})
    _note_merge_complete(counted.total)
    return result


class _CountedLayers:
    """Pass snapshots through once, counting them, so a streamed merge can still report its count."""

    def __init__(self, layers: Iterable[LayerSnapshot]) -> None:
        self._layers = layers
        self.total = 0

    def __iter__(self) -> Iterator[LayerSnapshot]:
        for snapshot in self._layers:
            self.total += 1
            yield snapshot


def _default_snapshots(default_file: Path | None) -> Iterator[LayerSnapshot]:
    """Yield defaults snapshots when *default_file* is supplied.

    The default file is expanded to include any companion ``.d`` directory files.

    Args:
        default_file: Absolute path to the optional defaults file.

    Yields:
        LayerSnapshot: Snapshots describing the defaults layer.

    Side Effects:
        Emits ``layer_loaded`` events when defaults files are parsed.
    """
    if default_file is None:
        return
    _refuse_an_unloadable_default_file(default_file)

    for snapshot in _load_entry_with_dot_d(Layer.DEFAULTS, default_file):
        _note_layer_loaded(snapshot.name, snapshot.origin, {"keys": len(snapshot.payload)})
        yield snapshot


def _refuse_an_unloadable_default_file(path: Path) -> None:
    """Refuse a *path* that exists but cannot be read as the defaults file.

    Discovered layer paths have fixed names and pass a FIFO or device over
    (``config_path_present``), and a ``.d`` directory skips a README on purpose. A
    ``default_file`` is named by the caller, so an existing path no loader reads is refused,
    never dropped: dropped, the defaults layer vanished without a word. A missing path stays
    no defaults layer.

    Args:
        path: The caller's ``default_file``.

    Raises:
        InvalidFormatError: *path* is a FIFO, device or socket, or a file whose suffix no loader reads.
    """
    kind = checked_kind(path)
    if kind is PathKind.OTHER:
        raise special_file_not_config_file(path)
    if kind is PathKind.FILE and path.suffix.lower() not in _FILE_LOADERS:
        raise unsupported_config_format(path, tuple(_FILE_LOADERS))


def _filesystem_snapshots(
    resolver: DefaultPathResolver,
    *,
    skip: frozenset[Path] = frozenset(),
) -> Iterator[LayerSnapshot]:
    """Yield filesystem-backed layer snapshots in precedence order.

    Args:
        resolver: Path resolver supplying candidate paths per layer.
        skip: Resolved paths that are not loaded (empty for every normal read).

    Yields:
        LayerSnapshot: Snapshots for ``app``/``host``/``user`` layers.
    """
    for layer, paths in _filesystem_layer_paths(resolver):
        # Streamed, so the layer's file count is noted after its files, not before.
        files = 0
        for snapshot in _snapshots_from_paths(layer, paths(), skip=skip):
            files += 1
            yield snapshot
        if files:
            _note_layer_loaded(layer, None, {"files": files})


def _filesystem_layer_paths(resolver: DefaultPathResolver) -> tuple[tuple[Layer, Callable[[], Iterable[Path]]], ...]:
    """Pair each filesystem layer, in precedence order, with the resolver call listing its candidate paths.

    The calls are returned unmade, so a caller decides where a resolver refusal lands.
    """
    return ((Layer.APP, resolver.app), (Layer.HOST, resolver.host), (Layer.USER, resolver.user))


def _dotenv_snapshots(
    loader: DefaultDotEnvLoader,
    start_dir: Path | None,
    *,
    dotenv_path: Path | None = None,
) -> Iterator[LayerSnapshot]:
    """Yield a snapshot for dotenv-provided values when present.

    Args:
        loader: Dotenv loader that handles discovery and parsing.
        start_dir: Optional starting directory for the upward search.
        dotenv_path: When set, load this specific file instead of searching.

    Yields:
        LayerSnapshot: Snapshot representing the ``dotenv`` layer when a file exists.
    """
    loaded = loader.load(start_dir, dotenv_path=dotenv_path)
    if not loaded.data or loaded.path is None:
        return
    _note_layer_loaded(Layer.DOTENV, loaded.path, {"keys": len(loaded.data)})
    yield LayerSnapshot(Layer.DOTENV, loaded.data, loaded.path)


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


def _snapshots_from_paths(
    layer: Layer,
    paths: Iterable[Path],
    *,
    skip: frozenset[Path] = frozenset(),
) -> Iterator[LayerSnapshot]:
    """Yield snapshots for every supported file inside *paths*, in the resolver's order.

    Each path is expanded to include any companion ``.d`` directory files.

    Args:
        layer: The layer the files belong to.
        paths: Iterable of candidate file paths.
        skip: Resolved paths that are not loaded (empty for every normal read).

    Yields:
        LayerSnapshot: Snapshot for each successfully loaded file.
    """
    for path in paths:
        yield from _load_entry_with_dot_d(layer, path, skip=skip)


def _load_entry(layer: Layer, path: Path) -> LayerSnapshot | None:
    """Load *path* using the configured file loaders and return a snapshot.

    Args:
        layer: The layer the file belongs to.
        path: Absolute path to the candidate configuration file.

    Returns:
        LayerSnapshot | None: Snapshot when parsing succeeds and data is non-empty; otherwise ``None``.

    Raises:
        InvalidFormatError: When the loader encounters invalid content. The exception is logged
            and re-raised so callers can surface context to users.
    """
    loader = _FILE_LOADERS.get(path.suffix.lower())
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


def _load_entry_with_dot_d(layer: Layer, path: Path, *, skip: frozenset[Path] = frozenset()) -> Iterator[LayerSnapshot]:
    """Load *path* and any companion .d directory files as snapshots.

    For a file ``foo.toml``, checks for a ``foo.d/`` directory and yields
    snapshots for:
    1. The base file (if it exists)
    2. Files from the .d directory in lexicographical order (if directory exists)

    Both the base file and .d directory are optional.

    Args:
        layer: The layer the files belong to.
        path: Absolute path to the base configuration file.
        skip: Resolved paths that are not loaded, base file or ``.d`` entry alike (empty for
            every normal read).

    Yields:
        LayerSnapshot: Snapshot for each file (base + .d entries) in merge order.

    Raises:
        InvalidFormatError: When any file contains invalid content.
    """
    expanded_paths = list(expand_dot_d(path))
    if len(expanded_paths) > 1:
        _note_dot_d_expanded(path, len(expanded_paths) - 1)

    for expanded_path in expanded_paths:
        if skip and expanded_path.resolve() in skip:
            continue
        snapshot = _load_entry(layer, expanded_path)
        if snapshot is not None:
            yield snapshot


def parse_with_dot_d(path: Path) -> None:
    """Parse *path* and the configuration files of its ``.d`` directory, keeping nothing.

    The same loaders and ``.d`` rules as a layer read, so a file that would fail when the
    application reads it fails here. A suffix no loader reads is not parsed.

    Raises:
        InvalidFormatError: A file does not parse; the message names it.
    """
    for _ in _load_entry_with_dot_d(Layer.DEFAULTS, path):
        pass


def _note_layer_loaded(layer: Layer, path: Path | None, details: Mapping[str, object]) -> None:
    """Emit a debug event capturing successful layer discovery.

    Args:
        layer: The layer that was loaded.
        path: Optional path associated with the event.
        details: Additional structured metadata (e.g., number of files or keys).

    Side Effects:
        Calls :func:`log_debug` with the structured event payload.
    """
    log_debug("layer_loaded", **make_event(layer, path, dict(details)))


def _note_layer_error(layer: Layer, path: Path, exc: Exception) -> None:
    """Emit a debug event describing a recoverable layer error.

    Args:
        layer: Layer currently being processed.
        path: File path that triggered the error.
        exc: Exception raised by the loader.
    """
    log_debug("layer_error", **make_event(layer, path, {"error": str(exc)}))


def _note_dot_d_expanded(base_path: Path, dot_d_count: int) -> None:
    """Emit a debug event when .d directory expansion occurs.

    Args:
        base_path: Path to the base configuration file.
        dot_d_count: Number of files found in the .d directory.
    """
    log_debug("dot_d_expanded", layer="file", path=str(base_path), dot_d_files=dot_d_count)


def _note_configuration_empty() -> None:
    """Emit an info event signalling that no configuration was discovered."""
    log_info("configuration_empty", layer="none", path=None)


def _note_merge_complete(total_layers: int) -> None:
    """Emit an info event summarising the merge outcome.

    Args:
        total_layers: Number of layers processed in the merge.
    """
    log_info("configuration_merged", layer="final", path=None, total_layers=total_layers)
