"""Deploy configuration artifacts into layered directories with per-platform strategies."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..adapters.path_resolvers.default import DefaultPathResolver

_VALID_TARGETS = {"app", "host", "user"}


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


def _write_ucf(destination: Path, payload: bytes) -> Path:
    """Write new config as .ucf variant (with numbered suffix if needed).

    Args:
        destination: Original destination path.
        payload: File content to write.

    Returns:
        Path to the created .ucf file.
    """
    ucf_path = _next_available_path(destination, ".ucf")
    ucf_path.parent.mkdir(parents=True, exist_ok=True)
    ucf_path.write_bytes(payload)
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
        raise ValueError(f"Unsupported deployment target: {target}")
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
                raise ValueError(f"Unsupported deployment target: {raw_target}")
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
                self.resolver.env.get("ProgramData", os.environ.get("ProgramData", r"C:\\ProgramData")),  # noqa: SIM112
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

    Returns:
        List of DeployResult objects describing what was done for each destination.
        Each result may contain nested ``dot_d_results`` for .d file deployments.

    Raises:
        FileNotFoundError: If the source file does not exist.
    """
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Configuration source not found: {source_path}")

    # Check for companion .d directory
    source_dot_d = _get_dot_d_dir(source_path)
    dot_d_files = _collect_dot_d_sources(source_dot_d)

    resolver = _prepare_resolver(vendor=vendor, app=app, slug=slug or app, profile=profile, platform=platform)
    payload = source_path.read_bytes()
    results: list[DeployResult] = []

    for destination in _destinations_for(resolver, targets):
        result = _deploy_to_destination(
            destination=destination,
            source_path=source_path,
            payload=payload,
            dot_d_files=dot_d_files,
            source_dot_d=source_dot_d,
            force=force,
            batch=batch,
            conflict_resolver=conflict_resolver,
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
) -> list[DeployResult]:
    """Deploy files from source .d directory to destination .d directory.

    Args:
        dot_d_files: List of source files to deploy.
        dest_dot_d: Destination .d directory path.
        source_dot_d: Source .d directory (for skipping same-file deploys).
        force: If True, backup existing files and overwrite.
        batch: If True, keep existing files and write new as .ucf.
        conflict_resolver: Callback to resolve conflicts interactively.

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
        )
        results.append(result)

    return results


def _handle_conflict(
    destination: Path,
    payload: bytes,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
) -> DeployResult:
    """Handle deployment when file exists with different content.

    Args:
        destination: Target file path.
        payload: File content to write.
        force: If True, backup and overwrite.
        batch: If True, keep existing and write as .ucf.
        conflict_resolver: Callback for interactive conflict resolution.

    Returns:
        DeployResult describing the action taken.
    """
    if force:
        backup_path = _backup_file(destination)
        _copy_payload(destination, payload)
        return DeployResult(destination=destination, action=DeployAction.OVERWRITTEN, backup_path=backup_path)

    if batch:
        ucf_path = _write_ucf(destination, payload)
        return DeployResult(destination=destination, action=DeployAction.KEPT, ucf_path=ucf_path)

    if conflict_resolver is not None:
        action = conflict_resolver(destination)
        return _execute_action(destination, payload, action)

    return DeployResult(destination=destination, action=DeployAction.SKIPPED)


def _deploy_single(
    *,
    destination: Path,
    payload: bytes,
    force: bool,
    batch: bool,
    conflict_resolver: ConflictResolver | None,
) -> DeployResult:
    """Deploy to a single destination with conflict handling."""
    if not destination.exists():
        _copy_payload(destination, payload)
        return DeployResult(destination=destination, action=DeployAction.CREATED)

    if _content_matches(destination, payload):
        return DeployResult(destination=destination, action=DeployAction.SKIPPED)

    return _handle_conflict(destination, payload, force, batch, conflict_resolver)


def _execute_action(destination: Path, payload: bytes, action: DeployAction) -> DeployResult:
    """Execute the chosen action for a conflict."""
    if action == DeployAction.OVERWRITTEN:
        # Smart skip if content is identical
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        backup_path = _backup_file(destination)
        _copy_payload(destination, payload)
        return DeployResult(
            destination=destination,
            action=DeployAction.OVERWRITTEN,
            backup_path=backup_path,
        )

    if action == DeployAction.KEPT:
        # Smart skip if content is identical (no need for UCF)
        if _content_matches(destination, payload):
            return DeployResult(destination=destination, action=DeployAction.SKIPPED)
        ucf_path = _write_ucf(destination, payload)
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
) -> DefaultPathResolver:
    if platform is None:
        return DefaultPathResolver(vendor=vendor, app=app, slug=slug, profile=profile)
    return DefaultPathResolver(vendor=vendor, app=app, slug=slug, profile=profile, platform=platform)


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


def _destinations_for(resolver: DefaultPathResolver, targets: Sequence[str]) -> Iterator[Path]:
    for raw_target in targets:
        destination = _resolve_destination(resolver, raw_target)
        if destination is not None:
            yield destination


def _resolve_destination(resolver: DefaultPathResolver, target: str) -> Path | None:
    normalised = _validate_target(target)
    return _strategy_for(resolver).destination_for(normalised)


def _copy_payload(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(destination, payload)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
