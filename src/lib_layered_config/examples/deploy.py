"""Deploy configuration artifacts into layered directories.

Purpose
    Copy a source file into the canonical locations recognised by
    :func:`lib_layered_config.core.read_config` while avoiding accidental
    overwrites.

Contents
    - ``deploy_config``: public API orchestrating copy decisions.
    - ``_prepare_resolver``: builds a path resolver with optional platform
      override.
    - ``_destinations_for`` / ``_resolve_destination``: map target names to
      concrete filesystem paths.
    - ``_copy_payload`` / ``_should_copy`` / ``_write_bytes``: tiny helpers that
      narrate how files are written or skipped.

System Integration
    Mirrors the logic from :class:`lib_layered_config.adapters.path_resolvers.default.DefaultPathResolver`
    ensuring generated files align with the runtime search strategy.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from ..adapters.path_resolvers.default import DefaultPathResolver

_VALID_TARGETS = {"app", "host", "user"}


def deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    targets: Sequence[str],
    slug: str | None = None,
    platform: str | None = None,
    force: bool = False,
) -> list[Path]:
    """Copy *source* into the requested configuration layers without overwriting existing files.

    Parameters
    ----------
    source:
        Path to the configuration artifact that should be deployed.
    vendor / app:
        Metadata used to resolve OS-specific directories (mirrors
        :func:`read_config`).
    targets:
        Iterable containing any combination of ``"app"``, ``"host"``, ``"user"``.
        Order matters; the function attempts deployment in the provided order.
    slug:
        Optional slug identifying the configuration family. Defaults to ``app``
        for convenience when a dedicated slug is not available.
    platform:
        Optional override for the platform. Accepted values are ``"posix"``
        and ``"windows"``. When omitted the running interpreter platform
        is used.
    force:
        When ``True`` existing files are overwritten and included in the
        returned path list. Defaults to ``False`` to preserve any manual
        edits in place.

    Returns
    -------
    list[pathlib.Path]
        Destination paths that were created or overwritten. When ``force`` is
        ``False`` existing files remain untouched and therefore are omitted.

    Raises
    ------
    FileNotFoundError
        If the *source* file does not exist.
    ValueError
        If *targets* contains an unsupported layer name.
    """

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Configuration source not found: {source_path}")

    resolver = _prepare_resolver(vendor=vendor, app=app, slug=slug or app, platform=platform)
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
    platform: str | None,
) -> DefaultPathResolver:
    """Construct a :class:`DefaultPathResolver` for deployment decisions."""

    kwargs = {"vendor": vendor, "app": app, "slug": slug}
    if platform is not None:
        kwargs["platform"] = platform
    return DefaultPathResolver(**kwargs)


def _destinations_for(
    resolver: DefaultPathResolver,
    targets: Sequence[str],
) -> Iterator[Path]:
    """Yield destination paths for requested *targets* in order."""

    for raw_target in targets:
        target = raw_target.lower()
        if target not in _VALID_TARGETS:
            raise ValueError(f"Unsupported deployment target: {raw_target}")
        destination = _resolve_destination(resolver, target)
        if destination is None:
            continue
        yield destination


def _should_copy(source: Path, destination: Path, force: bool) -> bool:
    """Return ``True`` when *destination* should be overwritten with *source*."""

    if destination.resolve() == source.resolve():
        return False
    if destination.exists() and not force:
        return False
    return True


def _copy_payload(destination: Path, payload: bytes) -> None:
    """Create parent directories and write *payload* to *destination*."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(destination, payload)


def _write_bytes(path: Path, payload: bytes) -> None:
    """Persist *payload* at *path*."""

    path.write_bytes(payload)


def _resolve_destination(resolver: DefaultPathResolver, target: str) -> Path | None:
    """Return the canonical file path for *target* according to *resolver*.

    The helper reproduces the OS-specific logic used by
    :class:`DefaultPathResolver` but returns paths regardless of whether they
    already exist.
    """

    if resolver.platform.startswith("linux") or resolver.platform == "linux":
        return _resolve_for_linux(resolver, target)
    if resolver.platform == "darwin":
        return _resolve_for_macos(resolver, target)
    if resolver.platform.startswith("win"):
        return _resolve_for_windows(resolver, target)
    # Fallback to POSIX-style defaults when the platform is unknown.
    return _resolve_for_linux(resolver, target)


def _resolve_for_linux(resolver: DefaultPathResolver, target: str) -> Path | None:
    etc_root = Path(resolver.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
    slug = resolver.slug
    if target == "app":
        return etc_root / slug / "config.toml"
    if target == "host":
        return etc_root / slug / "hosts" / f"{resolver.hostname}.toml"
    if target == "user":
        xdg = resolver.env.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / slug / "config.toml"
    return None


def _resolve_for_macos(resolver: DefaultPathResolver, target: str) -> Path | None:
    vendor = resolver.vendor
    app = resolver.application
    default_root = Path("/Library/Application Support")
    app_root = Path(resolver.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root)) / vendor / app
    if target == "app":
        return app_root / "config.toml"
    if target == "host":
        return app_root / "hosts" / f"{resolver.hostname}.toml"
    if target == "user":
        home_default = Path.home() / "Library/Application Support"
        home_root = Path(resolver.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))
        return home_root / vendor / app / "config.toml"
    return None


def _resolve_for_windows(resolver: DefaultPathResolver, target: str) -> Path | None:
    vendor = resolver.vendor
    app = resolver.application

    program_data = Path(
        resolver.env.get(
            "LIB_LAYERED_CONFIG_PROGRAMDATA",
            resolver.env.get("ProgramData", os.environ.get("ProgramData", r"C:\\ProgramData")),
        )
    )
    if target == "app":
        return program_data / vendor / app / "config.toml"
    if target == "host":
        return program_data / vendor / app / "hosts" / f"{resolver.hostname}.toml"

    appdata = Path(
        resolver.env.get(
            "LIB_LAYERED_CONFIG_APPDATA",
            resolver.env.get("APPDATA", os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")),
        )
    )
    if target == "user":
        return appdata / vendor / app / "config.toml"
    return None
