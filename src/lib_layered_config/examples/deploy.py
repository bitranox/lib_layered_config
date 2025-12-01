"""Deploy configuration artifacts into layered directories with per-platform strategies."""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from pathlib import Path

from ..adapters.path_resolvers.default import DefaultPathResolver

_VALID_TARGETS = {"app", "host", "user"}


def _ensure_path(path: Path | None, target: str) -> Path:
    if path is None:
        raise ValueError(f"No destination available for {target!r}")
    return path


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
) -> list[Path]:
    """Copy source into the requested configuration layers without overwriting existing files."""
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Configuration source not found: {source_path}")

    resolver = _prepare_resolver(vendor=vendor, app=app, slug=slug or app, profile=profile, platform=platform)
    payload = source_path.read_bytes()
    created: list[Path] = []
    for destination in _destinations_for(resolver, targets):
        if not _should_copy(source_path, destination, force):
            continue
        _copy_payload(destination, payload)
        created.append(destination)
    return created


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


def _linux_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:  # pyright: ignore[reportUnusedFunction]
    return LinuxDeployment(resolver).destination_for(_validate_target(target))


def _mac_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:  # pyright: ignore[reportUnusedFunction]
    return MacDeployment(resolver).destination_for(_validate_target(target))


def _windows_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:  # pyright: ignore[reportUnusedFunction]
    return WindowsDeployment(resolver).destination_for(_validate_target(target))


def _linux_app_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_linux_destination_for(resolver, "app"), "app")


def _linux_host_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_linux_destination_for(resolver, "host"), "host")


def _linux_user_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_linux_destination_for(resolver, "user"), "user")


def _mac_app_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_mac_destination_for(resolver, "app"), "app")


def _mac_host_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_mac_destination_for(resolver, "host"), "host")


def _mac_user_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_mac_destination_for(resolver, "user"), "user")


def _windows_app_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_windows_destination_for(resolver, "app"), "app")


def _windows_host_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_windows_destination_for(resolver, "host"), "host")


def _windows_user_path(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return _ensure_path(_windows_destination_for(resolver, "user"), "user")


def _windows_program_data(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return WindowsDeployment(resolver)._program_data_root()  # pyright: ignore[reportPrivateUsage]


def _windows_appdata(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return WindowsDeployment(resolver)._appdata_root()  # pyright: ignore[reportPrivateUsage]


def _windows_localappdata(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return WindowsDeployment(resolver)._localappdata_root()  # pyright: ignore[reportPrivateUsage]


def _mac_app_root(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return MacDeployment(resolver)._app_root()  # pyright: ignore[reportPrivateUsage]


def _mac_home_root(resolver: DefaultPathResolver) -> Path:  # pyright: ignore[reportUnusedFunction]
    return MacDeployment(resolver)._home_root()  # pyright: ignore[reportPrivateUsage]


def _should_copy(source: Path, destination: Path, force: bool) -> bool:
    if destination.resolve() == source.resolve():
        return False
    return not (destination.exists() and not force)


def _copy_payload(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(destination, payload)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
