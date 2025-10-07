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
from typing import Iterator, Sequence

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

    Why
    ----
    Provide a programmatic counterpart to the CLI deployment command while mirroring the runtime search strategy.

    Parameters
    ----------
    source:
        Path to the configuration artifact that should be deployed.
    vendor / app:
        Metadata used to resolve OS-specific directories (mirrors :func:`read_config`).
    targets:
        Iterable containing any combination of ``"app"``, ``"host"``, ``"user"``. Order matters; the function attempts
        deployment in the provided order.
    slug:
        Optional slug identifying the configuration family. Defaults to ``app`` when not supplied.
    platform:
        Optional override for the platform. Accepted values are ``"posix"`` and ``"windows"``. When omitted the running
        interpreter platform is used.
    force:
        When ``True`` existing files are overwritten and included in the returned path list. Defaults to ``False`` to
        preserve manual edits.

    Returns
    -------
    list[pathlib.Path]
        Destination paths that were created or overwritten. When ``force`` is ``False`` existing files remain untouched
        and are therefore omitted.

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
    """Construct a :class:`DefaultPathResolver` for deployment decisions.

    Why
    ----
    Reuse the runtime search strategy when computing deployment destinations.

    Parameters
    ----------
    vendor / app / slug:
        Naming context passed to the resolver.
    platform:
        Optional override for deterministic platform selection.

    Returns
    -------
    DefaultPathResolver
        Resolver supplying canonical paths for each layer.
    """

    if platform is None:
        return DefaultPathResolver(vendor=vendor, app=app, slug=slug)
    return DefaultPathResolver(vendor=vendor, app=app, slug=slug, platform=platform)


def _destinations_for(
    resolver: DefaultPathResolver,
    targets: Sequence[str],
) -> Iterator[Path]:
    """Yield destination paths for requested *targets* in order.

    Why
    ----
    Provide a shared loop that validates target names and preserves user order.

    Parameters
    ----------
    resolver:
        Configured path resolver.
    targets:
        Sequence of target identifiers supplied via CLI/API.

    Yields
    ------
    pathlib.Path
        Canonical destination for each valid target.

    Raises
    ------
    ValueError
        When an unknown target is supplied.
    """

    for raw_target in targets:
        target = raw_target.lower()
        if target not in _VALID_TARGETS:
            raise ValueError(f"Unsupported deployment target: {raw_target}")
        destination = _resolve_destination(resolver, target)
        if destination is None:
            continue
        yield destination


def _should_copy(source: Path, destination: Path, force: bool) -> bool:
    """Return ``True`` when *destination* should be overwritten with *source*.

    Why
    ----
    Protect existing files from accidental overwrites unless ``--force`` is supplied.

    Parameters
    ----------
    source:
        Original configuration file.
    destination:
        Path being considered for deployment.
    force:
        Whether overwrites are allowed.

    Returns
    -------
    bool
        ``True`` when copying should proceed.
    """

    if destination.resolve() == source.resolve():
        return False
    if destination.exists() and not force:
        return False
    return True


def _copy_payload(destination: Path, payload: bytes) -> None:
    """Create parent directories and write *payload* to *destination*.

    Why
    ----
    Ensure deployments succeed even when intermediate directories are missing.

    Side Effects
    ------------
    Creates directories and writes file contents to disk.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(destination, payload)


def _write_bytes(path: Path, payload: bytes) -> None:
    """Persist *payload* at *path*.

    Why
    ----
    Provide a single location for file writes, making it easier to stub in tests.
    """

    path.write_bytes(payload)


def _resolve_destination(resolver: DefaultPathResolver, target: str) -> Path | None:
    """Return the canonical file path for *target* according to *resolver*."""

    family = _platform_family(resolver.platform)
    dispatch = {
        "linux": _linux_destination_for,
        "mac": _mac_destination_for,
        "windows": _windows_destination_for,
    }
    resolver_fn = dispatch.get(family, _linux_destination_for)
    return resolver_fn(resolver, target)


def _platform_family(platform: str) -> str:
    """Map the resolver platform string to a normalised family name."""

    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "mac"
    return "linux"


def _linux_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:
    """Return the Linux destination for *target* when one exists."""

    story = {
        "app": _linux_app_path,
        "host": _linux_host_path,
        "user": _linux_user_path,
    }
    builder = story.get(target)
    return None if builder is None else builder(resolver)


def _linux_app_path(resolver: DefaultPathResolver) -> Path:
    etc_root = Path(resolver.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
    return etc_root / resolver.slug / "config.toml"


def _linux_host_path(resolver: DefaultPathResolver) -> Path:
    etc_root = Path(resolver.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
    return etc_root / resolver.slug / "hosts" / f"{resolver.hostname}.toml"


def _linux_user_path(resolver: DefaultPathResolver) -> Path:
    candidate = resolver.env.get("XDG_CONFIG_HOME")
    base = Path(candidate) if candidate else Path.home() / ".config"
    return base / resolver.slug / "config.toml"


def _mac_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:
    """Return the macOS destination for *target* when one exists."""

    story = {
        "app": _mac_app_path,
        "host": _mac_host_path,
        "user": _mac_user_path,
    }
    builder = story.get(target)
    return None if builder is None else builder(resolver)


def _mac_app_path(resolver: DefaultPathResolver) -> Path:
    return _mac_app_root(resolver) / "config.toml"


def _mac_host_path(resolver: DefaultPathResolver) -> Path:
    return _mac_app_root(resolver) / "hosts" / f"{resolver.hostname}.toml"


def _mac_user_path(resolver: DefaultPathResolver) -> Path:
    return _mac_home_root(resolver) / resolver.vendor / resolver.application / "config.toml"


def _mac_app_root(resolver: DefaultPathResolver) -> Path:
    default_root = Path("/Library/Application Support")
    base = Path(resolver.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root))
    return base / resolver.vendor / resolver.application


def _mac_home_root(resolver: DefaultPathResolver) -> Path:
    home_default = Path.home() / "Library/Application Support"
    return Path(resolver.env.get("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", home_default))


def _windows_destination_for(resolver: DefaultPathResolver, target: str) -> Path | None:
    """Return the Windows destination for *target* when one exists."""

    story = {
        "app": _windows_app_path,
        "host": _windows_host_path,
        "user": _windows_user_path,
    }
    builder = story.get(target)
    return None if builder is None else builder(resolver)


def _windows_app_path(resolver: DefaultPathResolver) -> Path:
    return _windows_program_data(resolver) / resolver.vendor / resolver.application / "config.toml"


def _windows_host_path(resolver: DefaultPathResolver) -> Path:
    host_root = _windows_program_data(resolver) / resolver.vendor / resolver.application / "hosts"
    return host_root / f"{resolver.hostname}.toml"


def _windows_user_path(resolver: DefaultPathResolver) -> Path:
    appdata_root = _windows_appdata(resolver)
    chosen_root = appdata_root
    if "LIB_LAYERED_CONFIG_APPDATA" not in resolver.env and not appdata_root.exists():
        chosen_root = _windows_localappdata(resolver)
    return chosen_root / resolver.vendor / resolver.application / "config.toml"


def _windows_program_data(resolver: DefaultPathResolver) -> Path:
    return Path(
        resolver.env.get(
            "LIB_LAYERED_CONFIG_PROGRAMDATA",
            resolver.env.get("ProgramData", os.environ.get("ProgramData", r"C:\\ProgramData")),
        )
    )


def _windows_appdata(resolver: DefaultPathResolver) -> Path:
    return Path(
        resolver.env.get(
            "LIB_LAYERED_CONFIG_APPDATA",
            resolver.env.get("APPDATA", os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")),
        )
    )


def _windows_localappdata(resolver: DefaultPathResolver) -> Path:
    return Path(
        resolver.env.get(
            "LIB_LAYERED_CONFIG_LOCALAPPDATA",
            resolver.env.get(
                "LOCALAPPDATA",
                os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"),
            ),
        )
    )
