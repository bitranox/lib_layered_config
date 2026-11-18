"""Deploy configuration artifacts into layered directories with per-platform strategies.

Copy a source config file (plus its companion ``.d`` directory) into the app, host, and
user layer locations for the current platform, resolving conflicts safely and hardening
Unix permissions per layer.

Contents:
    - ``DeployAction`` / ``DeployResult``: the outcome vocabulary and per-file record.
    - ``deploy_config``: public entry point that resolves destinations and deploys each.
    - ``deploy_config_paths`` / ``read_deploy_config``: the files a deploy writes and the
      configuration it reads for its modes, for a caller that must see what the deploy sees.
    - Conflict handling (``_handle_conflict`` / ``_execute_action``): backup-and-overwrite
      (``force``), keep-and-write-``.ucf`` (``batch``), or an interactive resolver, with
      identical-content smart-skip.
    - Write helpers (``_copy_file`` / ``_write_ucf`` / ``_write_from``): stream the source in
      chunks, so memory does not grow with the file, into a temp file renamed into place, so a
      failed write leaves the old file; with modes the temp file is owner-only and the layer's
      ``LayerModes`` follow, so secrets are never briefly world-readable.

System Role:
    Invoked by ``cli/deploy.py`` (and re-exported from the package root as
    ``deploy_config``). Sits in the ``examples`` layer between ``cli`` and ``adapters``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import shutil
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from ._platform import normalise_resolver_platform
from .adapters._file_mode import apply_mode, modes_apply
from .adapters._file_write import write_file
from .adapters._path_probe import (
    PathKind,
    is_symlink_or_raise,
    kind_or_raise,
    lexists_or_raise,
    uncreatable_reason,
)
from .adapters.file_loaders._dot_d import in_dot_d_order
from .adapters.path_resolvers.default import DefaultPathResolver
from .core import read_config_for_deploy, refuse_an_unusable_deploy_source
from .domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from .domain.deploy_permissions import (
    OVERRIDE_SOURCE,
    SECTION_KEY,
    DeployPermissions,
    DeployPermissionsError,
    LayerModes,
    PermissionProblem,
    deploy_permissions_from_config,
    parse_deploy_permissions,
)
from .domain.errors import ConfigError, DeployDestinationError, ValidationError
from .domain.identifiers import DEFAULT_MAX_PROFILE_LENGTH, DEPLOY_LAYERS, Layer, deploy_layer
from .domain.printable import escape_controls
from .observability import log_warn

if TYPE_CHECKING:
    from .domain.config import Config

__all__ = [
    "ConflictResolver",
    "DeployAction",
    "DeployResult",
    "deploy_config",
    "deploy_config_paths",
    "deployed_before_failure",
    "read_deploy_config",
]


#: The attribute deploy_config sets on an exception it lets through: the results written before it.
_WRITTEN_BEFORE_FAILURE: Final = "_lib_layered_config_deployed_before_failure"
#: The attribute a failed overwrite sets on its error: the result naming the backup it had to keep.
_PARTIAL_RESULT: Final = "_lib_layered_config_failed_overwrite"

#: The layers a deploy writes, by the target name a caller spells (case-insensitively).
_TARGET_LAYERS: Final[Mapping[str, Layer]] = MappingProxyType({layer.value: layer for layer in DEPLOY_LAYERS})

#: The deploy_config parameter each kind of explicit mode comes from, named in its refusal.
_MODE_PARAMETERS: Final[Mapping[ModeKind, str]] = MappingProxyType(
    {ModeKind.DIRECTORY: "dir_mode", ModeKind.FILE: "file_mode"}
)

#: How to deploy when the configured modes cannot be read. Both modes come first: turning permission
#: setting off leaves every mode to the umask, which can make a user file that holds secrets readable
#: by other accounts. The CLI replaces this with its own spelling.
_DEPLOY_ANYWAY_HINT = (
    "to deploy anyway, give both modes (dir_mode and file_mode; the built-in ones are 0o700 and 0o600 for "
    "user, 0o755 and 0o644 for app and host); set_permissions=False also deploys, but leaves every mode to "
    "the umask, which can make a user file that holds secrets readable by other accounts"
)

#: Why a linked destination is refused; the path comes first.
_LINK_REFUSAL = "is a symbolic link; deploy neither writes through nor replaces one"
#: Why a FIFO, device, socket or directory at a destination is refused; reading a FIFO would block.
_NOT_REGULAR_REFUSAL = "is not a regular file; deploy writes only regular files"
#: How much of a file deploy holds at a time while copying or comparing it.
_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class _ModeRequest:
    """What the caller asked for about permissions, validated."""

    set_permissions: bool | None
    dir_mode: DeployMode | None
    file_mode: DeployMode | None
    permissions: DeployPermissions | None
    overrides: Mapping[str, object] | None

    @property
    def modes_decided(self) -> bool:
        """Both modes came with the call, so no configured value can change the outcome."""
        return self.dir_mode is not None and self.file_mode is not None

    @property
    def any_explicit(self) -> bool:
        """At least one mode came with the call; an explicit mode means modes are set."""
        return self.dir_mode is not None or self.file_mode is not None

    @property
    def overrides_turn_modes_off(self) -> bool:
        """``permission_overrides`` holds ``enabled: False`` (a real bool: validated up front, D15).

        With ``set_permissions=None`` and no explicit mode that decides no mode is set, so no
        configured value can change the outcome and the read is skipped (D6, re-review m-d).
        """
        return (
            self.set_permissions is None
            and not self.any_explicit
            and self.overrides is not None
            and self.overrides.get("enabled") is False
        )


class DeployAction(Enum):
    """Action taken during deployment for a single destination."""

    CREATED = "created"  # New file, no conflict
    OVERWRITTEN = "overwritten"  # Backed up and replaced
    KEPT = "kept"  # Existing kept, new saved as .ucf
    SKIPPED = "skipped"  # Byte-identical to the source; nothing written
    CONFLICT = "conflict"  # Differs from the source, left unchanged: no force, batch or resolver


class _Sidecar(str, Enum):
    """The files a deploy writes beside an existing destination; the value is the name suffix."""

    BACKUP = ".bak"  # the replaced file, kept when a deploy overwrites it
    UCF = ".ucf"  # the new file, written beside the kept one for review


class _Destination(NamedTuple):
    """Where a deploy writes one target, and the layer whose modes that file gets."""

    path: Path
    layer: Layer


class _CheckedMode(NamedTuple):
    """One caller-given mode after validation: the mode (None when not given) or why it is refused."""

    mode: DeployMode | None
    problem: str | None


class _ExplicitModes(NamedTuple):
    """The caller-given directory and file mode, validated; None for a side not given."""

    directory: DeployMode | None
    file: DeployMode | None


def _require_deploy_action(action: object) -> None:
    """Refuse an *action* that is not a :class:`DeployAction` (a caller passing ``"created"``).

    The parameter is typed ``object`` on purpose: the field is annotated ``DeployAction``, so a check
    on the field itself reads as always true to the type checker, while at run time a caller can pass
    anything.
    """
    if not isinstance(action, DeployAction):
        raise ValidationError(f"action must be a DeployAction, got {type(action).__name__}")


@dataclass(frozen=True)
class DeployResult:
    """Result of a single file deployment, frozen.

    Attributes:
        destination: The file written, skipped or left in conflict.
        action: What was done.
        backup_path: The ``.bak`` copy of the replaced file; only for ``OVERWRITTEN``.
        ucf_path: The ``.ucf`` file holding the new content beside the kept one; only for ``KEPT``.
        dot_d_results: The results of the destination's ``.d`` copies, in the order written,
            stored as a tuple whatever sequence is passed.

    Raises:
        ValidationError: *action* is not a :class:`DeployAction`, or a path is set for an action
            it does not belong to.

    Examples:
        >>> result = DeployResult(destination=Path("/opt/acme/config.toml"), action=DeployAction.CREATED)
        >>> result.dot_d_results
        ()
        >>> DeployResult(destination=Path("/opt/acme/config.toml"), action=DeployAction.CREATED, ucf_path=Path("x"))
        Traceback (most recent call last):
            ...
        lib_layered_config.domain.errors.ValidationError: ucf_path is set only for a KEPT result, not CREATED
    """

    destination: Path
    action: DeployAction
    backup_path: Path | None = None
    ucf_path: Path | None = None
    dot_d_results: Sequence[DeployResult] = ()

    def __post_init__(self) -> None:
        """Refuse a state no deploy produces and store ``dot_d_results`` as a tuple."""
        _require_deploy_action(self.action)
        if self.backup_path is not None and self.action is not DeployAction.OVERWRITTEN:
            raise ValidationError(f"backup_path is set only for an OVERWRITTEN result, not {self.action.name}")
        if self.ucf_path is not None and self.action is not DeployAction.KEPT:
            raise ValidationError(f"ucf_path is set only for a KEPT result, not {self.action.name}")
        # frozen: the one sanctioned write, normalising the caller's sequence before anyone reads it.
        object.__setattr__(self, "dot_d_results", tuple(self.dot_d_results))


# Type alias for conflict resolution callback
ConflictResolver = Callable[[Path], DeployAction]


def _get_dot_d_dir(source_path: Path) -> Path:
    """Get the companion .d directory path for a source file.

    Uses the same naming convention as expand_dot_d:
    config.toml -> config.d (not config.toml.d)

    Args:
        source_path: Path to the source configuration file.

    Returns:
        Path to the companion .d directory.
    """
    return source_path.with_suffix(".d")


def _collect_dot_d_sources(dot_d_dir: Path) -> list[Path]:
    """Collect all files from a .d directory in lexicographical order.

    Unlike config reading (which filters by extension), deployment copies
    ALL files to preserve documentation, notes, and other supporting files.

    Args:
        dot_d_dir: Path to the .d directory.

    Returns:
        List of paths to all files sorted by name.
    """
    if kind_or_raise(dot_d_dir) is not PathKind.DIRECTORY:
        return []
    return in_dot_d_order(f for f in dot_d_dir.iterdir() if kind_or_raise(f) is PathKind.FILE)


def _next_available_path(base: Path, sidecar: _Sidecar) -> Path:
    """Find next available path with numbered suffix if needed.

    Examples:
        >>> import tempfile
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td) / "config.toml"
        ...     _next_available_path(p, _Sidecar.BACKUP).name
        'config.toml.bak'
    """
    # A dangling link counts as taken: a name chosen past it would be written through the link.
    candidate = base.parent / (base.name + sidecar.value)
    if not lexists_or_raise(candidate):
        return candidate
    n = 1
    while True:
        candidate = base.parent / f"{base.name}{sidecar.value}.{n}"
        if not lexists_or_raise(candidate):
            return candidate
        n += 1


def _backup_file(path: Path) -> Path:
    """Create backup of existing file as path.bak (with numbered suffix if needed).

    Args:
        path: Path to the file to back up.

    Returns:
        Path to the created backup file.
    """
    backup = _next_available_path(path, _Sidecar.BACKUP)
    try:
        # The backup holds the same secrets as the file. Not shutil.copy2: it creates the copy at the
        # umask's mode and copies the file's mode only afterwards, and a reader that opens the copy
        # in between keeps its handle. Written owner-only with the file's Windows access list, the
        # backup takes the file's mode, times and extended attributes once its content is in place.
        _write_from(backup, path, restrict=True, acl_from=path)
        shutil.copystat(path, backup)
    except BaseException:
        # A half-written backup would read as a whole one later; the deploy stops here, path untouched.
        backup.unlink(missing_ok=True)
        raise
    return backup


def _failed_overwrite(destination: Path, backup: Path, error: BaseException) -> None:
    """Settle the backup of an overwrite whose write raised *error*, before it is raised on.

    A destination still identical to its backup was not changed: the backup is deleted, so nothing is
    left behind and a retry does not pile up copies. Otherwise an in-place rewrite stopped part-way and
    the backup is the only intact copy: it stays, and *error* carries the result that names it.
    """
    try:
        unchanged = _content_matches(destination, backup)
    except OSError:
        unchanged = False
    if unchanged:
        # A failed cleanup must not replace the error that stopped the write.
        with contextlib.suppress(OSError):
            backup.unlink()
        return
    partial = DeployResult(destination=destination, action=DeployAction.OVERWRITTEN, backup_path=backup)
    with contextlib.suppress(AttributeError, TypeError):
        setattr(error, _PARTIAL_RESULT, partial)


def _write_ucf(destination: Path, source: Path, *, modes: LayerModes | None) -> Path:
    """Write new config as .ucf variant (numbered suffix if needed), hardened like the primary file.

    The .ucf sidecar can hold the same secrets as the primary file, so it gets the
    same layer-appropriate permission hardening (e.g. 0o600 for the user layer) rather
    than being left at the umask default, and on Windows the primary file's access list.

    Args:
        destination: Original destination path.
        source: The file whose content is written.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        Path to the created .ucf file.
    """
    ucf_path = _next_available_path(destination, _Sidecar.UCF)
    _prepare_directory(ucf_path.parent, modes)
    _write_from(ucf_path, source, restrict=modes is not None, acl_from=destination)
    if modes is not None:
        apply_mode(ucf_path, modes.file)
    return ucf_path


def _content_matches(destination: Path, source: Path) -> bool:
    """Check if the destination file has the same content as *source*, a chunk at a time.

    Args:
        destination: Path to the existing file.
        source: The file deploy would write there.

    Returns:
        True if the file exists and has identical content, False otherwise.
    """
    if kind_or_raise(destination) is PathKind.MISSING:
        return False
    try:
        return _same_content(source, destination)
    except OSError:
        return False


def _same_content(first: Path, second: Path) -> bool:
    """Whether two regular files hold the same bytes, read :data:`_CHUNK_BYTES` at a time."""
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as one, second.open("rb") as other:
        while True:
            chunk = one.read(_CHUNK_BYTES)
            if chunk != other.read(_CHUNK_BYTES):
                return False
            if not chunk:
                return True


def _validate_target(target: Layer | str) -> Layer:
    """Return the layer a caller-spelled *target* names (any case), refusing any other name."""
    return deploy_layer(target)


def _target_text(target: Layer | str) -> str:
    """Return *target* as the text a message names: a member by its value, a str as given.

    An f-string over a ``(str, Enum)`` member reads ``Layer.ENV`` on Python 3.11 and later.
    """
    return target.value if isinstance(target, Layer) else target


def _checked_mode(value: int | DeployMode | None, *, kind: ModeKind) -> _CheckedMode:
    """Return the mode when *value* is safe (None when not given), or one refusal line when it is not.

    A DeployMode was validated when it was built, so only its kind is checked: a file mode's rules
    say nothing about a directory, and the other way round.
    """
    parameter = _MODE_PARAMETERS[kind]
    if isinstance(value, DeployMode):
        if value.kind is kind:
            return _CheckedMode(value, None)
        return _CheckedMode(
            None, f"{parameter}: got a {value.kind.value} mode ({value}); {parameter} takes a {kind.value} mode"
        )
    try:
        return _CheckedMode(None if value is None else DeployMode(value, kind), None)
    except DeployModeError as exc:
        return _CheckedMode(None, f"{parameter}: {exc}")


def _explicit_modes(*, dir_mode: int | DeployMode | None, file_mode: int | DeployMode | None) -> _ExplicitModes:
    """Validate the caller-given modes, one refusal line per bad parameter, both checked first."""
    directory = _checked_mode(dir_mode, kind=ModeKind.DIRECTORY)
    file = _checked_mode(file_mode, kind=ModeKind.FILE)
    problems = [checked.problem for checked in (directory, file) if checked.problem is not None]
    if problems:
        raise DeployModeError("\n".join(problems))
    return _ExplicitModes(directory=directory.mode, file=file.mode)


def _resolve_layer_modes(
    settings: DeployPermissions,
    layer: Layer,
    *,
    dir_mode: DeployMode | None,
    file_mode: DeployMode | None,
) -> LayerModes:
    """Each side: the explicit mode when given, else the setting for *layer*."""
    configured = settings.for_layer(layer)
    return LayerModes(
        dir_mode if dir_mode is not None else configured.directory,
        file_mode if file_mode is not None else configured.file,
    )


def _override_source(_key: str) -> str:
    """Every key checked on its own below came from ``permission_overrides``."""
    return OVERRIDE_SOURCE


def _mode_request(
    *,
    set_permissions: bool | None,
    dir_mode: int | DeployMode | None,
    file_mode: int | DeployMode | None,
    permissions: DeployPermissions | None,
    permission_overrides: Mapping[str, object] | None,
) -> _ModeRequest:
    """Validate the permission arguments; a mode given with permission setting off is refused.

    ``permission_overrides`` are checked here on every call and platform, like an explicit mode,
    even when the settings are never read (D15); combining them with ``permissions`` is refused.
    """
    explicit = _explicit_modes(dir_mode=dir_mode, file_mode=file_mode)
    request = _ModeRequest(
        set_permissions=set_permissions,
        dir_mode=explicit.directory,
        file_mode=explicit.file,
        permissions=permissions,
        overrides=permission_overrides,
    )
    if set_permissions is False and request.any_explicit:
        raise DeployModeError(
            "dir_mode/file_mode given with set_permissions=False: a mode cannot be applied while "
            "permission setting is off; drop the mode, or drop set_permissions=False"
        )
    if permission_overrides is not None:
        if permissions is not None:
            reason = (
                "cannot be combined with permissions; put the overrides into the DeployPermissions you pass, "
                "or drop permissions and let deploy read the settings"
            )
            raise DeployPermissionsError([PermissionProblem("permission_overrides", reason)])
        parse_deploy_permissions(permission_overrides, source_of=_override_source)
    return request


def _permission_settings(
    request: _ModeRequest,
    *,
    load: Callable[[], DeployPermissions],
) -> DeployPermissions | None:
    """Return the settings that decide each mode, or None when no mode is set.

    An explicit mode means modes are set; otherwise set_permissions decides, and when it is None
    the configured (or given) ``enabled`` does, an ``enabled: False`` override first. The
    configuration is read only when it can change the outcome: modes may be set, the platform
    applies them, a side is open, no settings object was passed, and no override already turned
    modes off.
    """
    if request.set_permissions is False or request.overrides_turn_modes_off:
        return None
    given = request.permissions
    if request.modes_decided or not modes_apply():
        return given if given is not None else DeployPermissions.defaults()
    settings = given if given is not None else load()
    if request.set_permissions is None and not request.any_explicit and not settings.enabled:
        return None
    return settings


def _destination_files(destinations: Sequence[_Destination], *, dot_d_files: Sequence[Path]) -> Iterator[Path]:
    """Every file this call may write, as named: each destination and each of its ``.d`` copies."""
    for destination in destinations:
        yield destination.path
        dest_dot_d = _get_dot_d_dir(destination.path)
        yield from (dest_dot_d / source_file.name for source_file in dot_d_files)


def _paths_written(destinations: Sequence[_Destination], *, dot_d_files: Sequence[Path]) -> frozenset[Path]:
    """Every file this call may write, resolved."""
    return frozenset(path.resolve() for path in _destination_files(destinations, dot_d_files=dot_d_files))


def _refuse_unusable_destinations(destinations: Sequence[_Destination], *, dot_d_files: Sequence[Path]) -> None:
    """Refuse every destination that is a link, not a regular file, or cannot be created, before any write.

    Writing through a link changes the file it points at (with modes left to the umask the write
    followed it), and replacing it breaks a link someone made on purpose; deploy does neither. A
    FIFO would block the comparison forever, and a device, socket or directory cannot be a config.
    A missing destination whose nearest existing ancestor is not a directory (a regular file where
    the layer or ``.d`` directory belongs), or that has no existing ancestor at all (a Windows layer
    root on a drive that is not mapped), could never be written.

    Raises:
        DeployDestinationError: One line per refused destination, ``.d`` copies included.
    """
    files = _destination_files(destinations, dot_d_files=dot_d_files)
    problems = [problem for problem in map(_destination_problem, files) if problem is not None]
    if problems:
        raise DeployDestinationError("\n".join(problems))


def _destination_problem(path: Path) -> str | None:
    """Why *path* cannot be deployed to, or ``None`` when it is a regular file or can be created."""
    if is_symlink_or_raise(path):
        return f"{path} {_LINK_REFUSAL}"
    kind = kind_or_raise(path)
    if kind is PathKind.FILE:
        return None
    if kind is PathKind.MISSING:
        return uncreatable_reason(path)
    return f"{path} {_NOT_REGULAR_REFUSAL}"


def _describe_load_failure(exc: Exception) -> str:
    """One line naming what failed: an OSError by its path and reason, else the (content-free) message."""
    if isinstance(exc, OSError):
        reason = exc.strerror or type(exc).__name__
        return f"{exc.filename}: {reason}" if exc.filename else reason
    return " ".join(str(exc).split())


def _load_configured_permissions(
    *,
    resolver: DefaultPathResolver,
    source: Path,
    written: frozenset[Path],
    overrides: Mapping[str, object] | None,
) -> DeployPermissions:
    """Read the section from the source, the files this call does not write, and the environment.

    A user-layer file contributes only ``user_*`` and ``enabled`` (see ``collect_deploy_layers``).

    The caller's *overrides* are laid over the merged section and validated with it (D15).

    Raises:
        DeployPermissionsError: The configuration cannot be loaded, or the section is invalid.
            Raised outside the ``except`` blocks, so no loader exception is reachable from it.
    """
    try:
        config = read_config_for_deploy(resolver=resolver, default_file=source, skip=written)
    except (ConfigError, OSError) as exc:
        problems = [
            PermissionProblem(
                SECTION_KEY,
                "the configuration could not be loaded, so the configured modes are unknown: "
                + _describe_load_failure(exc),
            )
        ]
    else:
        try:
            return deploy_permissions_from_config(config, overrides=overrides)
        except DeployPermissionsError as exc:
            problems = list(exc.problems)
    raise DeployPermissionsError(problems, hint=_DEPLOY_ANYWAY_HINT)


def _deploy_to_destination(
    *,
    destination: Path,
    source_path: Path,
    dot_d_files: list[Path],
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
    written: list[DeployResult],
) -> None:
    """Deploy to a single destination with optional .d directory handling.

    The destination's result is appended to *written* as soon as its file is written; its ``.d``
    copies then replace that entry with one whose ``dot_d_results`` holds them (the record is
    frozen), so a failure part-way leaves *written* holding exactly what was written before it
    (see :func:`deployed_before_failure`).

    Args:
        destination: Target file path.
        source_path: The source file, copied to *destination* (and compared for skip detection).
        dot_d_files: List of .d directory source files.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.
        modes: The directory and file mode to set, or None to leave permissions to the umask.
        written: Receives the destination's result; nothing when source and destination are the same.
    """
    if destination.resolve() == source_path.resolve():
        return

    result = _deploy_recorded(
        written,
        destination=destination,
        source=source_path,
        force=force,
        batch=batch,
        conflict_resolver=conflict_resolver,
        modes=modes,
    )

    if not dot_d_files:
        return
    # The result is frozen, so the .d copies collect in a list and the result in *written* is
    # replaced by one holding them, on success and on failure alike: deployed_before_failure then
    # reports exactly the copies made before the error.
    position = len(written) - 1
    dot_d_written: list[DeployResult] = []
    try:
        _deploy_dot_d_files(
            dot_d_files=dot_d_files,
            dest_dot_d=_get_dot_d_dir(destination),
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
            written=dot_d_written,
        )
    finally:
        written[position] = dataclasses.replace(result, dot_d_results=tuple(dot_d_written))


def deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    slug: str,
    targets: Sequence[Layer | str],
    profile: str | None = None,
    platform: str | None = None,
    force: bool = False,
    batch: bool = False,
    conflict_resolver: ConflictResolver | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
    set_permissions: bool | None = None,
    dir_mode: int | DeployMode | None = None,
    file_mode: int | DeployMode | None = None,
    permissions: DeployPermissions | None = None,
    permission_overrides: Mapping[str, object] | None = None,
) -> list[DeployResult]:
    """Copy source into the requested configuration layers with conflict handling.

    Automatically detects and deploys companion .d directories. For a source file
    like ``config.toml``, if ``config.d/`` exists, its contents are also deployed
    to the corresponding ``.d`` directory at each destination.

    Args:
        source: Path to the configuration file to deploy. The file must exist.
            If a companion .d directory exists (e.g., ``config.d/`` for ``config.toml``),
            its contents are also deployed.
        vendor: Vendor namespace.
        app: Application name.
        targets: Layer targets to deploy to (app, host, user), a sequence such as ``["user"]`` or ``[Layer.USER]``. An
            empty sequence deploys nothing and returns ``[]``, as iterating it does; a single str is
            refused, because it would be read character by character.
        slug: The configuration folder name every layer path uses (``<root>/<slug>/``), the
            same value ``read_config`` takes. Required: there is no fallback to *app*.
        profile: Configuration profile name.
        platform: Override the auto-detected platform. Takes the CLI's ``--platform`` names
            (``linux``, ``darwin``/``macos``/``mac``, ``win32``/``windows``/``win``, ...); any other
            name raises :class:`~lib_layered_config.ValidationError`.
        force: If True, backup existing files and overwrite (no prompt).
        batch: If True, keep existing files and write new as .ucf for review (CI/scripts).
        conflict_resolver: Called with the destination of each file whose content differs;
            returns ``DeployAction.OVERWRITTEN`` or ``DeployAction.KEPT``. Any other answer
            raises :class:`~lib_layered_config.ValidationError`. *force* and *batch* decide
            first: with either set, the resolver is never called. With neither force, batch
            nor a resolver, a differing file is left unchanged and reported as ``CONFLICT``.
        max_profile_length: Maximum allowed profile name length (default: 64).
            A value above 255, or 0 or negative, uses the absolute maximum of 255 characters.
        set_permissions: True sets modes, False leaves them to the umask, None (default) follows
            the configured ``[lib_layered_config.default_permissions].enabled`` (true when unset).
            An explicit dir_mode or file_mode means modes are set; giving one together with
            False is refused. Skipped on Windows (ACLs).
        dir_mode: Directory mode for every target, overriding the configured and built-in ones: an
            int (``0o750``) or a ``DeployMode`` of kind ``ModeKind.DIRECTORY``.
        file_mode: File mode for every target, overriding the configured and built-in ones: an
            int (``0o640``) or a ``DeployMode`` of kind ``ModeKind.FILE``.
        permissions: A complete settings object to use instead of reading the configuration, for a
            caller that builds one on purpose. One built from an application's normal read_config
            includes ``.env``, every deployed destination and a user file's ``app_*``/``host_*``
            modes, which deploy's own read leaves out, so it is not the way to pass runtime
            overrides; use permission_overrides for those.
        permission_overrides: Runtime values for keys of ``[lib_layered_config.default_permissions]``
            (``{"user_file": "0o640"}``; flat setting names only), laid over deploy's own read and
            validated like configured values, a refusal naming ``(source: override)``. Validated on
            every call; applied when the settings are read. ``{"enabled": False}`` (with
            set_permissions None and no mode) turns permission setting off without reading the
            configuration, like set_permissions=False. Cannot be combined with permissions.

    Each side resolves on its own: the explicit mode, else the configured setting for the target's
    layer, else the built-in layer mode (app/host 755/644, user 700/600). The configured setting is
    read only when it can change the outcome, from this source (the defaults layer), the app, host
    and user files this call does not write, and the environment, with permission_overrides laid
    over it; never from ``.env``. A user file decides only ``user_*`` and ``enabled``: its
    ``app_*``/``host_*`` modes are ignored (logged as ``deploy_setting_ignored``, never refused), so
    the highest of the defaults, app, host and environment values applies. Modes are applied to
    each file this call writes; a file whose content is unchanged is skipped and keeps its mode.

    Returns:
        List of DeployResult objects describing what was done for each destination.
        Each result may contain nested ``dot_d_results`` for .d file deployments.

    Raises:
        FileNotFoundError: The source is not a regular file; the message says whether it is missing, a
            directory, or something else (a FIFO, device or socket).
        LayerLoadError: The source is not a ``.toml`` file (every destination is read only as
            TOML), or it or a configuration file in its ``.d`` directory does not parse; refused
            in every mode, before anything is written.
        PermissionError: The source, a file in its ``.d`` directory, or a destination cannot be
            read or sits behind a permission wall (an ``OSError`` in general); the same on every
            Python, and for the source in every mode before anything is written. An existing
            destination that cannot be read raises this whenever it is to be overwritten: with
            ``force=True``, or when a conflict_resolver answers ``OVERWRITTEN`` (the CLI's prompt is
            one), files deployed before it staying written. Otherwise it is a conflict, since its
            content cannot be compared: ``CONFLICT`` by default, or ``KEPT`` with a ``.ucf`` beside
            it under *batch* or a resolver answering ``KEPT``.
        ValidationError: An invalid vendor, app, slug or profile, an unknown target, *targets*
            given as a single str, or force and batch both set (one overwrites an existing file,
            the other keeps it), refused before anything is written; or a conflict_resolver
            answer other than OVERWRITTEN or KEPT, raised when that destination is reached, so
            files deployed before it stay written.
        DeployModeError: dir_mode or file_mode is out of range or unsafe, is a ``DeployMode`` of
            the other kind (a file mode as dir_mode), or a mode was given with set_permissions=False.
        DeployPermissionsError: The configuration cannot be loaded, its permission section is
            invalid, a permission_overrides value is refused, or permission_overrides came with
            permissions; nothing has been written.
        DeployDestinationError: A destination or one of its ``.d`` copies is a symbolic link
            (dangling or not), is not a regular file (a directory, FIFO, device or socket), or
            cannot be created because its nearest existing ancestor is not a directory (a regular
            file where the layer or ``.d`` directory belongs) or because no ancestor exists (a
            Windows layer root on a drive that is not mapped); nothing has been written.
        HomeDirectoryUnknownError: A ``user`` target is requested and the home directory cannot be
            determined (``HOME`` unset and the uid has no passwd entry; on Windows ``USERPROFILE``,
            ``HOMEDRIVE`` and ``HOMEPATH`` all unset), unless the variable naming the user-layer root
            answers instead (``XDG_CONFIG_HOME``, ``LIB_LAYERED_CONFIG_MAC_HOME_ROOT``,
            ``LIB_LAYERED_CONFIG_APPDATA``); nothing has been written.

    Examples:
        >>> import os
        >>> from tempfile import TemporaryDirectory
        >>> from unittest import mock
        >>> with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
        ...     source = Path(tmp) / "source.toml"
        ...     _ = source.write_text("[db]\\nport = 5432\\n", encoding="utf-8")
        ...     results = deploy_config(
        ...         source, vendor="Acme", app="Demo", slug="deploy-doctest", targets=["user"], platform="linux"
        ...     )
        ...     [(r.action.value, r.destination.parent.name, r.destination.name) for r in results]
        [('created', 'deploy-doctest', 'config.toml')]
    """
    if force and batch:
        raise ValidationError("force=True overwrites an existing file and batch=True keeps it; pass one")
    request = _mode_request(
        set_permissions=set_permissions,
        dir_mode=dir_mode,
        file_mode=file_mode,
        permissions=permissions,
        permission_overrides=permission_overrides,
    )
    source_path = _existing_source(source)
    # Every mode, before anything is written: explicit modes skip the configuration read that
    # would otherwise parse the source, and a deployed file the application cannot load is worse
    # than no file.
    refuse_an_unusable_deploy_source(source_path)
    source_dot_d = _get_dot_d_dir(source_path)
    dot_d_files = _collect_dot_d_sources(source_dot_d)
    resolver = _prepare_resolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        platform=platform,
        max_profile_length=max_profile_length,
    )
    # Materialised up front: the self-read must know every path this call writes, and an invalid
    # target is now refused before anything is written.
    destinations = list(_destinations_for(resolver, targets))
    _refuse_unusable_destinations(destinations, dot_d_files=dot_d_files)
    settings = _permission_settings(
        request,
        load=lambda: _load_configured_permissions(
            resolver=resolver,
            source=source_path,
            written=_paths_written(destinations, dot_d_files=dot_d_files),
            overrides=request.overrides,
        ),
    )
    # Opened, never read whole: an unreadable source is refused here, before anything is written.
    with source_path.open("rb"):
        pass
    results: list[DeployResult] = []
    try:
        for destination in destinations:
            modes = (
                None
                if settings is None
                else _resolve_layer_modes(
                    settings, destination.layer, dir_mode=request.dir_mode, file_mode=request.file_mode
                )
            )
            _deploy_to_destination(
                destination=destination.path,
                source_path=source_path,
                dot_d_files=dot_d_files,
                force=force,
                batch=batch,
                conflict_resolver=conflict_resolver,
                modes=modes,
                written=results,
            )
    except BaseException as error:
        # Any failure, an interrupt included: the files written so far stay written, so say which.
        _record_written(error, results)
        raise
    return results


def deployed_before_failure(error: BaseException) -> list[DeployResult]:
    """Return what a :func:`deploy_config` that raised *error* had already written.

    Targets are written one after another in the order given, each with its ``.d`` copies, so a
    failure part-way (a permission wall, a full disk, a declined prompt) leaves the earlier files
    written. ``deploy_config`` raises the original exception unchanged and attaches those results
    to it (user decision 2026-11-16, R2-F2), the last one holding only the ``.d`` copies written
    before the failure.

    Args:
        error: An exception, normally one ``deploy_config`` raised.

    Returns:
        The results in the order they were written; empty when nothing was written, or when *error*
        did not come out of ``deploy_config`` (a refusal before the first write, for one).

    Examples:
        >>> deployed_before_failure(ValueError("not from a deploy"))
        []
    """
    return list(cast("list[DeployResult]", getattr(error, _WRITTEN_BEFORE_FAILURE, [])))


def _record_written(error: BaseException, results: list[DeployResult]) -> None:
    """Attach a copy of *results* to *error*, read back by :func:`deployed_before_failure`."""
    # An exception class that refuses new attributes (a custom __setattr__) must not have its own
    # error replaced by ours; it then simply carries no list.
    with contextlib.suppress(AttributeError, TypeError):
        setattr(error, _WRITTEN_BEFORE_FAILURE, list(results))


def deploy_config_paths(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    slug: str,
    targets: Sequence[Layer | str],
    profile: str | None = None,
    platform: str | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> frozenset[Path]:
    r"""Return every file a :func:`deploy_config` of *source* to *targets* writes, resolved.

    Each target's configuration file and, in its companion ``.d`` directory, a copy of every file
    in the source's own ``.d`` directory, whether or not any of them exists yet. This is the set
    the deploy leaves out of its own read (see :func:`read_deploy_config`), computed by the code
    the deploy itself runs; the arguments mean what they mean there. It does not check the
    source's format or content: a source :func:`deploy_config` refuses (a ``config.json``, a file
    that does not parse) still gets its paths.

    Args:
        source: The configuration file a deploy would copy; its companion ``.d`` directory, when
            there is one, adds the paths of its copies.
        vendor: Vendor namespace.
        app: Application name.
        targets: Layer targets (app, host, user), a sequence such as ``["user"]`` or ``[Layer.USER]``; an empty
            sequence gives an empty set.
        slug / profile / platform / max_profile_length: As for :func:`deploy_config`; *platform*
            chooses whose layer paths are returned.

    Returns:
        The resolved paths.

    Raises:
        FileNotFoundError: The source is not a regular file; the message says whether it is missing, a
            directory, or something else (a FIFO, device or socket).
        PermissionError: The source or its ``.d`` directory sits behind a permission wall.
        ValidationError: An invalid vendor, app, slug, profile or platform; *targets* is a single str, or a
            target is not one of app, host and user; or the layer root a requested target needs is not
            absolute (``LayerRootNotAbsoluteError``: an empty or relative ``HOME`` for ``user``, the app
            root for ``app`` and ``host``). A root no requested target needs is not checked.
        HomeDirectoryUnknownError: A ``user`` target is requested and the home directory cannot be
            determined (``HOME`` unset and the uid has no passwd entry; on Windows ``USERPROFILE``,
            ``HOMEDRIVE`` and ``HOMEPATH`` all unset), unless the variable naming the user-layer root
            answers instead (``XDG_CONFIG_HOME``, ``LIB_LAYERED_CONFIG_MAC_HOME_ROOT``,
            ``LIB_LAYERED_CONFIG_APPDATA``).

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     source = Path(tmp) / "config.toml"
        ...     _ = source.write_text("[service]\nport = 1\n", encoding="utf-8")
        ...     paths = deploy_config_paths(
        ...         source, vendor="Acme", app="Demo", slug="demo", targets=["user"], platform="linux"
        ...     )
        ...     [path.name for path in paths]
        ['config.toml']
    """
    source_path = _existing_source(source)
    resolver = _prepare_resolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        platform=platform,
        max_profile_length=max_profile_length,
    )
    dot_d_files = _collect_dot_d_sources(_get_dot_d_dir(source_path))
    return _paths_written(list(_destinations_for(resolver, targets)), dot_d_files=dot_d_files)


def read_deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    slug: str,
    skip: Iterable[str | Path],
    profile: str | None = None,
    platform: str | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> Config:
    r"""Return the configuration :func:`deploy_config` reads for its modes, with *skip* left out.

    Unlike :func:`~lib_layered_config.read_config`, *source* is the defaults layer, no ``.env``
    file is read, and a user-layer file keeps only its ``user_*`` and ``enabled`` permission
    settings. The deploy's exact read passes ``skip=deploy_config_paths(...)`` for the same
    source and targets; a caller may leave out fewer files, for example only those that no
    longer parse. It does not check that *source* is one :func:`deploy_config` accepts: a
    ``config.json`` source is read like any defaults file, where the deploy refuses it with
    ``LayerLoadError``.

    Args:
        source: The configuration file a deploy would copy; read as the defaults layer.
        vendor / app / slug / profile / platform / max_profile_length: As for
            :func:`deploy_config`; *platform* chooses whose layer paths are read.
        skip: Files to leave out, in any spelling; each is resolved before it is compared.

    Returns:
        The merged configuration, with provenance.

    Raises:
        TypeError: *skip* is a single ``str`` or ``Path`` rather than an iterable of them.
        FileNotFoundError: The source is not a regular file; the message says whether it is missing, a
            directory, or something else (a FIFO, device or socket).
        PermissionError: The source sits behind a permission wall.
        LayerLoadError: A file not left out cannot be read, decoded or parsed.
        ValidationError: An invalid vendor, app, slug, profile or platform. A layer whose root is not
            absolute (an empty or relative ``HOME``, say) is left out of the read, not refused, as the
            deploy's own read does; so is the user layer when the home directory cannot be determined
            (no ``HomeDirectoryUnknownError`` is raised here).

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     source = Path(tmp) / "config.toml"
        ...     _ = source.write_text("[service]\nport = 1\n", encoding="utf-8")
        ...     config = read_deploy_config(source, vendor="Acme", app="Demo", slug="demo", skip=(), platform="linux")
        ...     config.get("service.port")
        1
    """
    if isinstance(skip, (str, Path)):
        raise TypeError(f"skip takes an iterable of paths, not a single {type(skip).__name__}: write [path]")
    source_path = _existing_source(source)
    resolver = _prepare_resolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        platform=platform,
        max_profile_length=max_profile_length,
    )
    left_out = frozenset(Path(path).resolve() for path in skip)
    return read_config_for_deploy(resolver=resolver, default_file=source_path, skip=left_out)


#: What a deploy says of a source that is not a regular file, by what is there. Every one is a
#: ``FileNotFoundError``, so a caller's ``except`` and the CLI's exit code do not depend on the kind.
_SOURCE_REFUSALS: Final[Mapping[PathKind, str]] = MappingProxyType(
    {
        PathKind.MISSING: "Configuration source not found: {path}",
        PathKind.DIRECTORY: "Configuration source is a directory, not a file: {path}",
        PathKind.OTHER: "Configuration source is not a regular file: {path}",
    }
)


def _existing_source(source: str | Path) -> Path:
    """Return *source* as a path, refusing one that is not a regular file with what is there instead."""
    source_path = Path(source)
    try:
        kind = kind_or_raise(source_path)
    except ValueError:
        # A NUL character (or a name the OS cannot encode): no file can have it, so it is not found,
        # like every other source that is not there; escaped, so the message holds no NUL itself.
        raise FileNotFoundError(
            _SOURCE_REFUSALS[PathKind.MISSING].format(path=escape_controls(str(source_path)))
        ) from None
    if kind is not PathKind.FILE:
        raise FileNotFoundError(_SOURCE_REFUSALS[kind].format(path=source_path))
    return source_path


def _deploy_dot_d_files(
    *,
    dot_d_files: list[Path],
    dest_dot_d: Path,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
    written: list[DeployResult],
) -> None:
    """Deploy files from source .d directory to destination .d directory.

    Args:
        dot_d_files: List of source files to deploy.
        dest_dot_d: Destination .d directory path.
        force: If True, backup existing files and overwrite.
        batch: If True, keep existing files and write new as .ucf.
        conflict_resolver: Callback to resolve conflicts interactively.
        modes: The directory and file mode to set, or None to leave permissions to the umask.
        written: Receives each file's result as soon as it is written, so a failure part-way
            leaves it holding the copies made before it.
    """
    for source_file in dot_d_files:
        dest_file = dest_dot_d / source_file.name

        # Skip if source and destination are the same
        if dest_file.resolve() == source_file.resolve():
            continue

        _deploy_recorded(
            written,
            destination=dest_file,
            source=source_file,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
        )


def _handle_conflict(
    destination: Path,
    source: Path,
    *,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult:
    """Handle deployment when file exists with different content.

    Args:
        destination: Target file path.
        source: The file whose content is written.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        DeployResult describing the action taken: ``CONFLICT`` when no policy decides, leaving the
        file unchanged (``SKIPPED`` is kept for a byte-identical file).

    Raises:
        ValidationError: *conflict_resolver* answered anything but ``DeployAction.OVERWRITTEN`` or
            ``DeployAction.KEPT``; nothing is written for that destination.
    """
    # force -> OVERWRITTEN, batch -> KEPT, resolver -> its chosen action. All three route
    # through _execute_action so the backup/overwrite and .ucf logic lives in one place.
    if force:
        action = DeployAction.OVERWRITTEN
    elif batch:
        action = DeployAction.KEPT
    elif conflict_resolver is not None:
        action = _resolver_choice(conflict_resolver, destination)
    else:
        return DeployResult(destination=destination, action=DeployAction.CONFLICT)

    return _execute_action(destination, source, action, modes=modes)


_RESOLVER_CHOICES = (DeployAction.OVERWRITTEN, DeployAction.KEPT)


def _resolver_choice(conflict_resolver: ConflictResolver, destination: Path) -> DeployAction:
    """Return *conflict_resolver*'s answer for *destination*, refusing any but OVERWRITTEN or KEPT.

    The answer is checked rather than trusted: the callback is caller code, and any other value
    has no write behind it, so passing it on would report a result nothing produced.

    Raises:
        ValidationError: The resolver answered anything else, a string or ``None`` included.
    """
    return _checked_resolver_answer(conflict_resolver(destination), destination)


def _checked_resolver_answer(answer: object, destination: Path) -> DeployAction:
    """Narrow *answer* to OVERWRITTEN or KEPT, or raise.

    *answer* is typed ``object`` because the resolver's annotation is no guarantee at runtime.
    """
    if isinstance(answer, DeployAction) and answer in _RESOLVER_CHOICES:
        return answer
    raise ValidationError(
        f"conflict_resolver returned {answer!r} for {destination}; it must return "
        "DeployAction.OVERWRITTEN or DeployAction.KEPT"
    )


def _deploy_recorded(
    written: list[DeployResult],
    *,
    destination: Path,
    source: Path,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult:
    """Run :func:`_deploy_single` and append its result to *written*, a partial one included.

    A failed overwrite whose backup is the only intact copy left carries that result on the error
    (``_failed_overwrite``); it goes into *written* before the error is raised on.
    """
    try:
        result = _deploy_single(
            destination=destination,
            source=source,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
        )
    except BaseException as error:
        partial = getattr(error, _PARTIAL_RESULT, None)
        if isinstance(partial, DeployResult):
            written.append(partial)
        raise
    written.append(result)
    return result


def _deploy_single(
    *,
    destination: Path,
    source: Path,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult:
    """Deploy *source* to a single destination with conflict handling."""
    if kind_or_raise(destination) is PathKind.MISSING:
        _copy_file(destination, source, modes=modes)
        return DeployResult(destination=destination, action=DeployAction.CREATED)

    if _content_matches(destination, source):
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)

    return _handle_conflict(
        destination, source, force=force, batch=batch, conflict_resolver=conflict_resolver, modes=modes
    )


def _execute_action(
    destination: Path,
    source: Path,
    action: DeployAction,
    *,
    modes: LayerModes | None,
) -> DeployResult:
    """Execute *action*, ``OVERWRITTEN`` or ``KEPT`` (``_handle_conflict`` refuses every other)."""
    if action == DeployAction.OVERWRITTEN:
        # Smart skip if content is identical
        if _content_matches(destination, source):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        backup_path = _backup_file(destination)
        try:
            _copy_file(destination, source, modes=modes)
        except BaseException as error:
            _failed_overwrite(destination, backup_path, error)
            raise
        return DeployResult(
            destination=destination,
            action=DeployAction.OVERWRITTEN,
            backup_path=backup_path,
        )

    # KEPT: the only other action _handle_conflict passes on.
    # Smart skip if content is identical (no need for UCF)
    if _content_matches(destination, source):
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)
    ucf_path = _write_ucf(destination, source, modes=modes)
    return DeployResult(
        destination=destination,
        action=DeployAction.KEPT,
        ucf_path=ucf_path,
    )


def _prepare_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    platform: str | None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> DefaultPathResolver:
    """Build the resolver, reading *platform* like the CLI's ``--platform``.

    Raises:
        ValidationError: *platform* names no known layout; an unknown name would otherwise get the
            Linux layout without a word.
    """
    return DefaultPathResolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        platform=normalise_resolver_platform(platform),
        max_profile_length=max_profile_length,
    )


def _destinations_for(resolver: DefaultPathResolver, targets: Sequence[Layer | str]) -> Iterator[_Destination]:
    """Yield the destination of each valid target, with the layer it deploys to.

    Args:
        resolver: Path resolver for computing destinations.
        targets: Target layer names, as the caller spells them.

    Yields:
        One ``_Destination`` per target, in the order given.

    Raises:
        ValidationError: *targets* is a single str, or a target is not one of app, host and user.
    """
    # A str is itself a Sequence[str], so the type checker passes targets="user", which would be
    # read as the targets u, s, e, r, and "" as no target at all. ValidationError, not the
    # TypeError prefer= raises: a non-empty str was already refused with this type.
    if isinstance(targets, str):
        raise ValidationError(
            f"targets takes a sequence of layer names, not a single str: {_str_targets_remedy(_target_text(targets))}"
        )
    for raw_target in targets:
        layer = _validate_target(raw_target)
        yield _Destination(resolver.destination_for(layer), layer)


def _str_targets_remedy(targets: str) -> str:
    """The way out for a str *targets*: the one-item list when it names a layer, else the layer names.

    ``['']`` or ``['x']`` would only be refused next, so they are never suggested.

    Examples:
        >>> _str_targets_remedy("user")
        "write ['user']"
        >>> _str_targets_remedy("")
        'write a list of app, host and user'
    """
    if targets.lower() in _TARGET_LAYERS:
        return f"write [{targets!r}]"
    *first, last = _TARGET_LAYERS
    return f"write a list of {', '.join(first)} and {last}"


def _copy_file(destination: Path, source: Path, *, modes: LayerModes | None) -> None:
    """Copy *source* to destination; with *modes*, harden the directories and then the file."""
    _prepare_directory(destination.parent, modes)
    _write_from(destination, source, restrict=modes is not None)
    if modes is not None:
        apply_mode(destination, modes.file)


def _prepare_directory(directory: Path, modes: LayerModes | None) -> None:
    """Create *directory* and its missing parents; with *modes*, set the layer's mode on them.

    Every directory this call creates gets the mode, and so does *directory* itself, which may
    have existed before. A parent that already existed keeps its mode: it can be a directory the
    user set up (a group-readable layer root) or one reached through a link (user decision
    2026-11-18, "Created dirs only"). Left to ``mkdir(parents=True)``, the parents a deploy
    creates would keep the umask's mode, so a first profile deploy under umask 0002 left the
    user layer's ``profile/`` group-writable.
    """
    created = _make_directories(directory)
    if modes is None:
        return
    for path in created:
        if path != directory:
            _harden_directory(path, modes.directory)
    _harden_directory(directory, modes.directory)


def _make_directories(directory: Path) -> list[Path]:
    """Create *directory* and every missing parent, returning the ones this call created, top first.

    One ``mkdir`` per level, so a directory another process creates at the same moment
    (``FileExistsError``) is not counted as this deploy's. Any other failure stops the walk, and the
    final ``mkdir(parents=True, exist_ok=True)`` raises the error it raised before this helper.
    """
    missing: list[Path] = []
    current = directory
    while kind_or_raise(current) is PathKind.MISSING and current.parent != current:
        missing.append(current)
        current = current.parent
    created: list[Path] = []
    for path in reversed(missing):
        try:
            path.mkdir()
        except FileExistsError:
            continue
        except OSError:
            break
        created.append(path)
    directory.mkdir(parents=True, exist_ok=True)
    return created


def _harden_directory(directory: Path, mode: DeployMode) -> None:
    """Set *mode* on *directory*, unless *directory* is a symbolic link.

    ``chmod`` follows a link, so hardening a layer directory that links to a dotfiles checkout or a
    shared directory would change the mode of a directory deploy neither made nor owns at that path
    (0755 to 0700, or 0750 to 0755 on the app and host layers). The file is still written through
    the link and gets its own mode; only the target directory is left as it was, and that is logged.
    """
    if modes_apply() and is_symlink_or_raise(directory):
        log_warn("deploy_directory_mode_skipped", path=str(directory), reason="symbolic link")
        return
    apply_mode(directory, mode)


def _write_from(path: Path, source: Path, *, restrict: bool = False, acl_from: Path | None = None) -> None:
    """Write the content of *source* to *path*, :data:`_CHUNK_BYTES` at a time, never leaving it torn.

    The content goes to a temp file beside *path* that is renamed into place, so a failed write
    leaves the old file (see ``adapters._file_write``). With ``restrict`` (permissions will be
    tightened) the temp file is owner-only, so a secret is never readable before the chmod. Without
    it the new file keeps the old one's mode, and a destination a rename would change - hard links,
    another owner, its own extended attributes - is rewritten in place. On Windows the new file gets
    the access list of *acl_from*, by default of the file it replaces.
    """
    write_file(path, source, restrict=restrict, chunk_bytes=_CHUNK_BYTES, acl_from=acl_from)
