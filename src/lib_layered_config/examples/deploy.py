"""Utilities for deploying configuration files into layered directories.

Purpose
-------
Copy an existing configuration file into the canonical locations recognised by
``lib_layered_config`` without overwriting any files that already exist. The
logic mirrors :class:`lib_layered_config.adapters.path_resolvers.default.DefaultPathResolver`
so generated files land exactly where :func:`read_config` expects them.

Supported targets are ``"app"``, ``"host"``, and ``"user"`` which correspond to

the system-wide, host-specific, and per-user layers respectively. Hostnames are
detected automatically (or influenced via environment variables mirrored by the
path resolver).
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

    Returns
    -------
    list[pathlib.Path]
        List of destination paths that were created. Existing files are left
        untouched and therefore omitted from the list.

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

    resolver = DefaultPathResolver(vendor=vendor, app=app, slug=slug or app)
    created: list[Path] = []
    for raw_target in targets:
        target = raw_target.lower()
        if target not in _VALID_TARGETS:
            raise ValueError(f"Unsupported deployment target: {raw_target}")

        destination = _resolve_destination(resolver, target)
        if destination is None:
            continue
        if destination.exists():
            continue
        if destination.resolve() == source_path.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        created.append(destination)
    return created


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
