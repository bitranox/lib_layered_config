"""Deploy configuration artifacts into layered directories with per-platform strategies.

Copy a source config file (plus its companion ``.d`` directory) into the app, host, and
user layer locations for the current platform, resolving conflicts safely and hardening
Unix permissions per layer.

Contents:
    - ``DeployAction`` / ``DeployResult``: the outcome vocabulary and per-file record.
    - ``deploy_config``: public entry point that resolves destinations and deploys each.
    - ``DeploymentStrategy`` and its ``Linux`` / ``Mac`` / ``Windows`` subclasses: compute
      per-platform destination paths.
    - Conflict handling (``_handle_conflict`` / ``_execute_action``): backup-and-overwrite
      (``force``), keep-and-write-``.ucf`` (``batch``), or an interactive resolver, with
      identical-content smart-skip.
    - Permission helpers (``_copy_payload`` / ``_write_ucf`` / ``_write_bytes``): write via
      an owner-only temp file then apply the layer's ``LayerModes``, so secrets are never
      briefly world-readable.

System Role:
    Invoked by ``cli/deploy.py`` (and re-exported from the package root as
    ``deploy_config``). Sits in the ``examples`` layer between ``cli`` and ``adapters``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..adapters.path_resolvers.default import DefaultPathResolver
from ..core import read_config_for_deploy
from ..domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from ..domain.deploy_permissions import (
    OVERRIDE_SOURCE,
    SECTION_KEY,
    DeployPermissions,
    DeployPermissionsError,
    LayerModes,
    PermissionProblem,
    deploy_permissions_from_config,
    parse_deploy_permissions,
)
from ..domain.errors import ConfigError, ValidationError
from ..domain.identifiers import DEFAULT_MAX_PROFILE_LENGTH, Layer
from ..domain.permissions import apply_mode, modes_apply

_VALID_TARGETS = {Layer.APP.value, Layer.HOST.value, Layer.USER.value}

#: How to deploy when the configured modes cannot be read. Both modes come first: turning permission
#: setting off leaves every mode to the umask, which can make a user file that holds secrets readable
#: by other accounts. The CLI replaces this with its own spelling (Task 7).
_DEPLOY_ANYWAY_HINT = (
    "to deploy anyway, give both modes (dir_mode and file_mode; the built-in ones are 0o700 and 0o600 for "
    "user, 0o755 and 0o644 for app and host); set_permissions=False also deploys, but leaves every mode to "
    "the umask, which can make a user file that holds secrets readable by other accounts"
)


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
    SKIPPED = "skipped"  # No action taken


def _empty_deploy_results() -> list[DeployResult]:
    """Return an empty list of DeployResult for default_factory."""
    return []


@dataclass
class DeployResult:
    """Result of a single file deployment."""

    destination: Path
    action: DeployAction
    backup_path: Path | None = None  # Set if action is OVERWRITTEN
    ucf_path: Path | None = None  # Set if action is KEPT
    dot_d_results: list[DeployResult] = field(default_factory=_empty_deploy_results)


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
    if not dot_d_dir.is_dir():
        return []
    return sorted(f for f in dot_d_dir.iterdir() if f.is_file())


def _next_available_path(base: Path, suffix: str) -> Path:
    """Find next available path with numbered suffix if needed.

    Examples:
        >>> import tempfile
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td) / "config.toml"
        ...     _next_available_path(p, ".bak").name
        'config.toml.bak'
    """
    candidate = base.parent / (base.name + suffix)
    if not candidate.exists():
        return candidate
    n = 1
    while True:
        candidate = base.parent / f"{base.name}{suffix}.{n}"
        if not candidate.exists():
            return candidate
        n += 1


def _backup_file(path: Path) -> Path:
    """Create backup of existing file as path.bak (with numbered suffix if needed).

    Args:
        path: Path to the file to back up.

    Returns:
        Path to the created backup file.
    """
    backup = _next_available_path(path, ".bak")
    shutil.copy2(path, backup)
    return backup


def _write_ucf(destination: Path, payload: bytes, *, modes: LayerModes | None) -> Path:
    """Write new config as .ucf variant (numbered suffix if needed), hardened like the primary file.

    The .ucf sidecar can hold the same secrets as the primary file, so it gets the
    same layer-appropriate permission hardening (e.g. 0o600 for the user layer) rather
    than being left at the umask default.

    Args:
        destination: Original destination path.
        payload: File content to write.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        Path to the created .ucf file.
    """
    ucf_path = _next_available_path(destination, ".ucf")
    ucf_path.parent.mkdir(parents=True, exist_ok=True)
    if modes is not None:
        apply_mode(ucf_path.parent, modes.directory)
    _write_bytes(ucf_path, payload, restrict=modes is not None)
    if modes is not None:
        apply_mode(ucf_path, modes.file)
    return ucf_path


def _content_matches(destination: Path, payload: bytes) -> bool:
    """Check if the destination file has the same content as the payload.

    Args:
        destination: Path to the existing file.
        payload: New content to compare against.

    Returns:
        True if the file exists and has identical content, False otherwise.
    """
    if not destination.exists():
        return False
    try:
        return destination.read_bytes() == payload
    except OSError:
        return False


def _validate_target(target: str) -> str:
    normalised = target.lower()
    if normalised not in _VALID_TARGETS:
        raise ValidationError(f"Unsupported deployment target: {target}")
    return normalised


def _checked_mode(name: str, *, value: int | None, kind: ModeKind) -> tuple[DeployMode | None, str | None]:
    """Return (mode, None) when *value* is safe, or (None, one refusal line) when it is not."""
    try:
        return (None if value is None else DeployMode(value, kind)), None
    except DeployModeError as exc:
        return None, f"{name}: {exc}"


def _explicit_modes(*, dir_mode: int | None, file_mode: int | None) -> tuple[DeployMode | None, DeployMode | None]:
    """Validate the caller-given modes, one refusal line per bad parameter, both checked first."""
    checked = [
        _checked_mode(name, value=value, kind=kind)
        for name, value, kind in (
            ("dir_mode", dir_mode, ModeKind.DIRECTORY),
            ("file_mode", file_mode, ModeKind.FILE),
        )
    ]
    problems = [problem for _, problem in checked if problem is not None]
    if problems:
        raise DeployModeError("\n".join(problems))
    return checked[0][0], checked[1][0]


def _resolve_layer_modes(
    settings: DeployPermissions,
    layer: str,
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
    dir_mode: int | None,
    file_mode: int | None,
    permissions: DeployPermissions | None,
    permission_overrides: Mapping[str, object] | None,
) -> _ModeRequest:
    """Validate the permission arguments; a mode given with permission setting off is refused.

    ``permission_overrides`` are checked here on every call and platform, like an explicit mode,
    even when the settings are never read (D15); combining them with ``permissions`` is refused.
    """
    explicit_dir, explicit_file = _explicit_modes(dir_mode=dir_mode, file_mode=file_mode)
    request = _ModeRequest(
        set_permissions=set_permissions,
        dir_mode=explicit_dir,
        file_mode=explicit_file,
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


def _paths_written(destinations: Sequence[tuple[Path, str]], *, dot_d_files: Sequence[Path]) -> frozenset[Path]:
    """Every file this call may write, resolved: each destination and each of its ``.d`` copies."""
    written: set[Path] = set()
    for destination, _layer in destinations:
        written.add(destination.resolve())
        dest_dot_d = _get_dot_d_dir(destination)
        written.update((dest_dot_d / source_file.name).resolve() for source_file in dot_d_files)
    return frozenset(written)


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

    The caller's *overrides* are laid over the merged section and validated with it (D15).

    Raises:
        DeployPermissionsError: The configuration cannot be loaded, or the section is invalid.
            Raised outside the ``except`` blocks, so no loader exception is reachable from it.
    """
    try:
        config = read_config_for_deploy(resolver=resolver, default_file=source, skip=written)
    except (ConfigError, OSError, ValueError) as exc:
        # ValueError: the environment loader reports a scalar/mapping collision as a plain ValueError.
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


class DeploymentStrategy:
    """Base class for computing deployment destinations on a specific platform."""

    def __init__(self, resolver: DefaultPathResolver) -> None:
        """Initialise strategy with a path resolver providing identifiers."""
        self.resolver = resolver

    def _profile_segment(self) -> Path:
        """Return the profile path segment or an empty path."""
        if self.resolver.profile:
            return Path("profile") / self.resolver.profile
        return Path()

    def iter_destinations(self, targets: Sequence[str]) -> Iterator[Path]:
        """Yield destination paths for each valid target in *targets*."""
        for raw_target in targets:
            target = raw_target.lower()
            if target not in _VALID_TARGETS:
                raise ValidationError(f"Unsupported deployment target: {raw_target}")
            destination = self.destination_for(target)
            if destination is not None:
                yield destination

    def destination_for(self, target: str) -> Path | None:  # pragma: no cover - abstract
        """Return the destination path for *target*, or None if unsupported."""
        raise NotImplementedError


class LinuxDeployment(DeploymentStrategy):
    """Linux deployment using XDG Base Directory paths."""

    def destination_for(self, target: str) -> Path | None:
        """Return Linux-specific destination path for *target*."""
        mapping = {
            "app": self._app_path,
            "host": self._host_path,
            "user": self._user_path,
        }
        builder = mapping.get(target)
        return builder() if builder else None

    def _etc_root(self) -> Path:
        return Path(self.resolver.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))

    def _app_path(self) -> Path:
        profile_seg = self._profile_segment()
        return self._etc_root() / "xdg" / self.resolver.slug / profile_seg / "config.toml"

    def _host_path(self) -> Path:
        profile_seg = self._profile_segment()
        return self._etc_root() / "xdg" / self.resolver.slug / profile_seg / "hosts" / f"{self.resolver.hostname}.toml"

    def _user_path(self) -> Path:
        candidate = self.resolver.env.get("XDG_CONFIG_HOME")
        base = Path(candidate) if candidate else Path.home() / ".config"
        profile_seg = self._profile_segment()
        return base / self.resolver.slug / profile_seg / "config.toml"


class MacDeployment(DeploymentStrategy):
    """macOS deployment using Application Support paths."""

    def destination_for(self, target: str) -> Path | None:
        """Return macOS-specific destination path for *target*."""
        mapping = {
            "app": self._app_path,
            "host": self._host_path,
            "user": self._user_path,
        }
        builder = mapping.get(target)
        return builder() if builder else None

    def _app_root(self) -> Path:
        default_root = Path("/Library/Application Support")
        base = Path(self.resolver.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
        return base / self.resolver.vendor / self.resolver.application

    def _home_root(self) -> Path:
        home_default = Path.home() / "Library/Application Support"
        return Path(self.resolver.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))

    def _app_path(self) -> Path:
        profile_seg = self._profile_segment()
        return self._app_root() / profile_seg / "config.toml"

    def _host_path(self) -> Path:
        profile_seg = self._profile_segment()
        return self._app_root() / profile_seg / "hosts" / f"{self.resolver.hostname}.toml"

    def _user_path(self) -> Path:
        profile_seg = self._profile_segment()
        return self._home_root() / self.resolver.vendor / self.resolver.application / profile_seg / "config.toml"


class WindowsDeployment(DeploymentStrategy):
    """Windows deployment using ProgramData and AppData paths."""

    def destination_for(self, target: str) -> Path | None:
        """Return Windows-specific destination path for *target*."""
        mapping = {
            "app": self._app_path,
            "host": self._host_path,
            "user": self._user_path,
        }
        builder = mapping.get(target)
        return builder() if builder else None

    def _program_data_root(self) -> Path:
        return Path(
            self.resolver.env.get(
                "LIB_LAYERED_CONFIG_PROGRAMDATA",
                self.resolver.env.get("ProgramData", os.environ.get("PROGRAMDATA", r"C:\\ProgramData")),
            )
        )

    def _appdata_root(self) -> Path:
        return Path(
            self.resolver.env.get(
                "LIB_LAYERED_CONFIG_APPDATA",
                self.resolver.env.get(
                    "APPDATA",
                    os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"),
                ),
            )
        )

    def _localappdata_root(self) -> Path:
        return Path(
            self.resolver.env.get(
                "LIB_LAYERED_CONFIG_LOCALAPPDATA",
                self.resolver.env.get(
                    "LOCALAPPDATA",
                    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
                ),
            )
        )

    def _app_path(self) -> Path:
        profile_seg = self._profile_segment()
        return (
            self._program_data_root() / self.resolver.vendor / self.resolver.application / profile_seg / "config.toml"
        )

    def _host_path(self) -> Path:
        profile_seg = self._profile_segment()
        host_root = self._program_data_root() / self.resolver.vendor / self.resolver.application / profile_seg / "hosts"
        return host_root / f"{self.resolver.hostname}.toml"

    def _user_path(self) -> Path:
        profile_seg = self._profile_segment()
        appdata_root = self._appdata_root()
        chosen_root = appdata_root
        if "LIB_LAYERED_CONFIG_APPDATA" not in self.resolver.env and not appdata_root.exists():
            chosen_root = self._localappdata_root()
        return chosen_root / self.resolver.vendor / self.resolver.application / profile_seg / "config.toml"


def _deploy_to_destination(
    *,
    destination: Path,
    source_path: Path,
    payload: bytes,
    dot_d_files: list[Path],
    source_dot_d: Path,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult | None:
    """Deploy to a single destination with optional .d directory handling.

    Args:
        destination: Target file path.
        source_path: Original source file path (for skip detection).
        payload: File content to write.
        dot_d_files: List of .d directory source files.
        source_dot_d: Source .d directory path.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        DeployResult or None if source and destination are the same.
    """
    if destination.resolve() == source_path.resolve():
        return None

    result = _deploy_single(
        destination=destination,
        payload=payload,
        force=force,
        batch=batch,
        conflict_resolver=conflict_resolver,
        modes=modes,
    )

    if dot_d_files:
        dest_dot_d = _get_dot_d_dir(destination)
        result.dot_d_results = _deploy_dot_d_files(
            dot_d_files=dot_d_files,
            dest_dot_d=dest_dot_d,
            source_dot_d=source_dot_d,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
        )

    return result


def deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    targets: Sequence[str],
    slug: str | None = None,
    profile: str | None = None,
    platform: str | None = None,
    force: bool = False,
    batch: bool = False,
    conflict_resolver: ConflictResolver | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
    set_permissions: bool | None = None,
    dir_mode: int | None = None,
    file_mode: int | None = None,
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
        targets: Layer targets to deploy to (app, host, user).
        slug: Slug identifying the configuration set.
        profile: Configuration profile name.
        platform: Override auto-detected platform.
        force: If True, backup existing files and overwrite (no prompt).
        batch: If True, keep existing files and write new as .ucf for review (CI/scripts).
        conflict_resolver: Callback to resolve conflicts interactively.
            Called with destination Path, should return DeployAction.
        max_profile_length: Maximum allowed profile name length (default: 64).
            Set to 0 or negative to disable length checking.
        set_permissions: True sets modes, False leaves them to the umask, None (default) follows
            the configured ``[lib_layered_config.default_permissions].enabled`` (true when unset).
            An explicit dir_mode or file_mode means modes are set; giving one together with
            False is refused. Skipped on Windows (ACLs).
        dir_mode: Directory mode for every target, overriding the configured and built-in ones.
        file_mode: File mode for every target, overriding the configured and built-in ones.
        permissions: A complete settings object to use instead of reading the configuration, for a
            caller that builds one on purpose. One built from an application's normal read_config
            includes ``.env`` and every deployed destination, which deploy's own read leaves out,
            so it is not the way to pass runtime overrides; use permission_overrides for those.
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
    over it; never from ``.env``. Modes are applied to each file this call writes; a file whose
    content is unchanged is skipped and keeps its mode.

    Returns:
        List of DeployResult objects describing what was done for each destination.
        Each result may contain nested ``dot_d_results`` for .d file deployments.

    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError: When profile name is invalid (too long, path traversal, etc.).
        ValidationError: An unknown target, refused before anything is written.
        DeployModeError: dir_mode or file_mode is out of range or unsafe, or a mode was given
            with set_permissions=False.
        DeployPermissionsError: The configuration cannot be loaded, its permission section is
            invalid, a permission_overrides value is refused, or permission_overrides came with
            permissions; nothing has been written.
    """
    request = _mode_request(
        set_permissions=set_permissions,
        dir_mode=dir_mode,
        file_mode=file_mode,
        permissions=permissions,
        permission_overrides=permission_overrides,
    )
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Configuration source not found: {source_path}")

    source_dot_d = _get_dot_d_dir(source_path)
    dot_d_files = _collect_dot_d_sources(source_dot_d)
    resolver = _prepare_resolver(
        vendor=vendor,
        app=app,
        slug=slug or app,
        profile=profile,
        platform=platform,
        max_profile_length=max_profile_length,
    )
    # Materialised up front: the self-read must know every path this call writes, and an invalid
    # target is now refused before anything is written.
    destinations = list(_destinations_for(resolver, targets))
    settings = _permission_settings(
        request,
        load=lambda: _load_configured_permissions(
            resolver=resolver,
            source=source_path,
            written=_paths_written(destinations, dot_d_files=dot_d_files),
            overrides=request.overrides,
        ),
    )
    payload = source_path.read_bytes()
    results: list[DeployResult] = []

    for destination, layer in destinations:
        modes = (
            None
            if settings is None
            else _resolve_layer_modes(settings, layer, dir_mode=request.dir_mode, file_mode=request.file_mode)
        )
        result = _deploy_to_destination(
            destination=destination,
            source_path=source_path,
            payload=payload,
            dot_d_files=dot_d_files,
            source_dot_d=source_dot_d,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
        )
        if result is not None:
            results.append(result)

    return results


def _deploy_dot_d_files(
    *,
    dot_d_files: list[Path],
    dest_dot_d: Path,
    source_dot_d: Path,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> list[DeployResult]:
    """Deploy files from source .d directory to destination .d directory.

    Args:
        dot_d_files: List of source files to deploy.
        dest_dot_d: Destination .d directory path.
        source_dot_d: Source .d directory (for skipping same-file deploys).
        force: If True, backup existing files and overwrite.
        batch: If True, keep existing files and write new as .ucf.
        conflict_resolver: Callback to resolve conflicts interactively.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        List of DeployResult objects for each .d file deployed.
    """
    results: list[DeployResult] = []

    for source_file in dot_d_files:
        dest_file = dest_dot_d / source_file.name

        # Skip if source and destination are the same
        if dest_file.resolve() == source_file.resolve():
            continue

        payload = source_file.read_bytes()
        result = _deploy_single(
            destination=dest_file,
            payload=payload,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            modes=modes,
        )
        results.append(result)

    return results


def _handle_conflict(
    destination: Path,
    payload: bytes,
    *,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult:
    """Handle deployment when file exists with different content.

    Args:
        destination: Target file path.
        payload: File content to write.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.
        modes: The directory and file mode to set, or None to leave permissions to the umask.

    Returns:
        DeployResult describing the action taken.
    """
    # force -> OVERWRITTEN, batch -> KEPT, resolver -> its chosen action. All three route
    # through _execute_action so the backup/overwrite and .ucf logic lives in one place.
    if force:
        action = DeployAction.OVERWRITTEN
    elif batch:
        action = DeployAction.KEPT
    elif conflict_resolver is not None:
        action = conflict_resolver(destination)
    else:
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)

    return _execute_action(destination, payload, action, modes=modes)


def _deploy_single(
    *,
    destination: Path,
    payload: bytes,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    modes: LayerModes | None,
) -> DeployResult:
    """Deploy to a single destination with conflict handling."""
    if not destination.exists():
        _copy_payload(destination, payload, modes=modes)
        return DeployResult(destination=destination, action=DeployAction.CREATED)

    if _content_matches(destination, payload):
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)

    return _handle_conflict(
        destination, payload, force=force, batch=batch, conflict_resolver=conflict_resolver, modes=modes
    )


def _execute_action(
    destination: Path,
    payload: bytes,
    action: DeployAction,
    *,
    modes: LayerModes | None,
) -> DeployResult:
    """Execute the chosen action for a conflict."""
    if action == DeployAction.OVERWRITTEN:
        # Smart skip if content is identical
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        backup_path = _backup_file(destination)
        _copy_payload(destination, payload, modes=modes)
        return DeployResult(
            destination=destination,
            action=DeployAction.OVERWRITTEN,
            backup_path=backup_path,
        )

    if action == DeployAction.KEPT:
        # Smart skip if content is identical (no need for UCF)
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        ucf_path = _write_ucf(destination, payload, modes=modes)
        return DeployResult(
            destination=destination,
            action=DeployAction.KEPT,
            ucf_path=ucf_path,
        )

    # SKIPPED or CREATED (shouldn't happen here, but handle gracefully)
    return DeployResult(destination=destination, action=DeployAction.SKIPPED)


def _prepare_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    platform: str | None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> DefaultPathResolver:
    if platform is None:
        return DefaultPathResolver(
            vendor=vendor,
            app=app,
            slug=slug,
            profile=profile,
            max_profile_length=max_profile_length,
        )
    return DefaultPathResolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        platform=platform,
        max_profile_length=max_profile_length,
    )


def _platform_family(platform: str) -> str:
    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "mac"
    return "linux"


def _strategy_for(resolver: DefaultPathResolver) -> DeploymentStrategy:
    family = _platform_family(resolver.platform)
    if family == "windows":
        return WindowsDeployment(resolver)
    if family == "mac":
        return MacDeployment(resolver)
    return LinuxDeployment(resolver)


def _destinations_for(resolver: DefaultPathResolver, targets: Sequence[str]) -> Iterator[tuple[Path, str]]:
    """Yield (destination_path, layer) tuples for each valid target.

    Args:
        resolver: Path resolver for computing destinations.
        targets: Target layer names.

    Yields:
        Tuples of (destination_path, normalised_layer_name).
    """
    for raw_target in targets:
        normalised = _validate_target(raw_target)
        destination = _strategy_for(resolver).destination_for(normalised)
        if destination is not None:
            yield destination, normalised


def _copy_payload(destination: Path, payload: bytes, *, modes: LayerModes | None) -> None:
    """Copy payload to destination; with *modes*, harden the directory and then the file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if modes is not None:
        apply_mode(destination.parent, modes.directory)
    _write_bytes(destination, payload, restrict=modes is not None)
    if modes is not None:
        apply_mode(destination, modes.file)


def _write_bytes(path: Path, payload: bytes, *, restrict: bool = False) -> None:
    """Write *payload* to *path*.

    With ``restrict`` (used whenever permissions will be tightened), the payload is
    written to an owner-only temp file (``mkstemp`` creates it ``0o600``) in the same
    directory and then atomically renamed into place. This closes the TOCTOU window in
    which a secret could be world-readable between a plain create and the follow-up
    chmod - the destination is only ever the old file or the fully-written 0o600 file.
    """
    if not restrict:
        path.write_bytes(payload)
        return
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
