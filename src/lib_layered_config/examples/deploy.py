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
      an owner-only temp file then apply the layer mode, so secrets are never briefly
      world-readable.

System Role:
    Invoked by ``cli/deploy.py`` (and re-exported from the package root as
    ``deploy_config``). Sits in the ``examples`` layer between ``cli`` and ``adapters``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..adapters.path_resolvers.default import DefaultPathResolver
from ..domain.errors import ValidationError
from ..domain.identifiers import DEFAULT_MAX_PROFILE_LENGTH, Layer
from ..domain.permissions import set_custom_permissions, set_permissions

_VALID_TARGETS = {Layer.APP.value, Layer.HOST.value, Layer.USER.value}


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
    config.toml → config.d (not config.toml.d)

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


def _write_ucf(
    destination: Path,
    payload: bytes,
    *,
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> Path:
    """Write new config as .ucf variant (with numbered suffix if needed).

    The .ucf sidecar can hold the same secrets as the primary file, so it gets the
    same layer-appropriate permission hardening (e.g. 0o600 for the user layer) rather
    than being left at the umask default.

    Args:
        destination: Original destination path.
        payload: File content to write.
        layer: Target layer ("app", "host", or "user").
        set_permissions_flag: If True, set Unix permissions.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Override file mode (None = use layer defaults).

    Returns:
        Path to the created .ucf file.
    """
    ucf_path = _next_available_path(destination, ".ucf")
    ucf_path.parent.mkdir(parents=True, exist_ok=True)
    if set_permissions_flag:
        _apply_directory_permissions(ucf_path.parent, layer, dir_mode, file_mode)
    _write_bytes(ucf_path, payload, restrict=set_permissions_flag)
    if set_permissions_flag:
        _apply_file_permissions(ucf_path, layer, dir_mode, file_mode)
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
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
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
        layer: Target layer ("app", "host", or "user").
        set_permissions_flag: If True, set Unix permissions.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Override file mode (None = use layer defaults).

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
        layer=layer,
        set_permissions_flag=set_permissions_flag,
        dir_mode=dir_mode,
        file_mode=file_mode,
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
            layer=layer,
            set_permissions_flag=set_permissions_flag,
            dir_mode=dir_mode,
            file_mode=file_mode,
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
    set_permissions: bool = True,
    dir_mode: int | None = None,
    file_mode: int | None = None,
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
        set_permissions: If True (default), set Unix permissions on deployed files.
            Uses layer-specific defaults: app/host = 755/644, user = 700/600.
            Skipped on Windows (uses ACLs instead).
        dir_mode: Override directory mode for all targets (None = use layer defaults).
        file_mode: Override file mode for all targets (None = use layer defaults).

    Returns:
        List of DeployResult objects describing what was done for each destination.
        Each result may contain nested ``dot_d_results`` for .d file deployments.

    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError: When profile name is invalid (too long, path traversal, etc.).
    """
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Configuration source not found: {source_path}")

    # Check for companion .d directory
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
    payload = source_path.read_bytes()
    results: list[DeployResult] = []

    for destination, layer in _destinations_for(resolver, targets):
        result = _deploy_to_destination(
            destination=destination,
            source_path=source_path,
            payload=payload,
            dot_d_files=dot_d_files,
            source_dot_d=source_dot_d,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
            layer=layer,
            set_permissions_flag=set_permissions,
            dir_mode=dir_mode,
            file_mode=file_mode,
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
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> list[DeployResult]:
    """Deploy files from source .d directory to destination .d directory.

    Args:
        dot_d_files: List of source files to deploy.
        dest_dot_d: Destination .d directory path.
        source_dot_d: Source .d directory (for skipping same-file deploys).
        force: If True, backup existing files and overwrite.
        batch: If True, keep existing files and write new as .ucf.
        conflict_resolver: Callback to resolve conflicts interactively.
        layer: Target layer ("app", "host", or "user").
        set_permissions_flag: If True, set Unix permissions.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Override file mode (None = use layer defaults).

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
            layer=layer,
            set_permissions_flag=set_permissions_flag,
            dir_mode=dir_mode,
            file_mode=file_mode,
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
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> DeployResult:
    """Handle deployment when file exists with different content.

    Args:
        destination: Target file path.
        payload: File content to write.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.
        layer: Target layer ("app", "host", or "user").
        set_permissions_flag: If True, set Unix permissions.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Override file mode (None = use layer defaults).

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

    return _execute_action(
        destination,
        payload,
        action,
        layer=layer,
        set_permissions_flag=set_permissions_flag,
        dir_mode=dir_mode,
        file_mode=file_mode,
    )


def _deploy_single(
    *,
    destination: Path,
    payload: bytes,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> DeployResult:
    """Deploy to a single destination with conflict handling."""
    if not destination.exists():
        _copy_payload(
            destination,
            payload,
            layer=layer,
            set_permissions_flag=set_permissions_flag,
            dir_mode=dir_mode,
            file_mode=file_mode,
        )
        return DeployResult(destination=destination, action=DeployAction.CREATED)

    if _content_matches(destination, payload):
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)

    return _handle_conflict(
        destination,
        payload,
        force=force,
        batch=batch,
        conflict_resolver=conflict_resolver,
        layer=layer,
        set_permissions_flag=set_permissions_flag,
        dir_mode=dir_mode,
        file_mode=file_mode,
    )


def _execute_action(
    destination: Path,
    payload: bytes,
    action: DeployAction,
    *,
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> DeployResult:
    """Execute the chosen action for a conflict."""
    if action == DeployAction.OVERWRITTEN:
        # Smart skip if content is identical
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        backup_path = _backup_file(destination)
        _copy_payload(
            destination,
            payload,
            layer=layer,
            set_permissions_flag=set_permissions_flag,
            dir_mode=dir_mode,
            file_mode=file_mode,
        )
        return DeployResult(
            destination=destination,
            action=DeployAction.OVERWRITTEN,
            backup_path=backup_path,
        )

    if action == DeployAction.KEPT:
        # Smart skip if content is identical (no need for UCF)
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        ucf_path = _write_ucf(
            destination,
            payload,
            layer=layer,
            set_permissions_flag=set_permissions_flag,
            dir_mode=dir_mode,
            file_mode=file_mode,
        )
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


def _copy_payload(
    destination: Path,
    payload: bytes,
    *,
    layer: str,
    set_permissions_flag: bool,
    dir_mode: int | None,
    file_mode: int | None,
) -> None:
    """Copy payload to destination, optionally setting Unix permissions.

    Args:
        destination: Target file path.
        payload: File content to write.
        layer: Target layer ("app", "host", or "user").
        set_permissions_flag: If True, set Unix permissions.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Override file mode (None = use layer defaults).
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Set directory permissions on all parent directories we may have created
    if set_permissions_flag:
        _apply_directory_permissions(destination.parent, layer, dir_mode, file_mode)

    _write_bytes(destination, payload, restrict=set_permissions_flag)

    # Set file permissions
    if set_permissions_flag:
        _apply_file_permissions(destination, layer, dir_mode, file_mode)


def _apply_directory_permissions(
    directory: Path,
    layer: str,
    dir_mode: int | None,
    file_mode: int | None,
) -> None:
    """Apply permissions to a directory.

    Args:
        directory: Directory to set permissions on.
        layer: Target layer for default permission selection.
        dir_mode: Override directory mode (None = use layer defaults).
        file_mode: Unused, for signature consistency.
    """
    if dir_mode is not None or file_mode is not None:
        # Custom mode specified - use it for directory
        set_custom_permissions(directory, dir_mode=dir_mode, file_mode=file_mode, is_dir=True)
    else:
        # Use layer defaults
        set_permissions(directory, layer, is_dir=True)


def _apply_file_permissions(
    file_path: Path,
    layer: str,
    dir_mode: int | None,
    file_mode: int | None,
) -> None:
    """Apply permissions to a file.

    Args:
        file_path: File to set permissions on.
        layer: Target layer for default permission selection.
        dir_mode: Unused, for signature consistency.
        file_mode: Override file mode (None = use layer defaults).
    """
    if dir_mode is not None or file_mode is not None:
        # Custom mode specified - use it for file
        set_custom_permissions(file_path, dir_mode=dir_mode, file_mode=file_mode, is_dir=False)
    else:
        # Use layer defaults
        set_permissions(file_path, layer, is_dir=False)


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
