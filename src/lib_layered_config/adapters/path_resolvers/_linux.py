"""Linux-specific path resolution strategy.

Implement path resolution following XDG Base Directory specification
and traditional ``/etc`` conventions.

Contents:
    - ``LinuxStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._base import PlatformStrategy, collect_layer, config_path_present, home_directory, override_root

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


__all__ = [
    "LinuxStrategy",
    "etc_root",
    "xdg_config_home",
]


def etc_root(env: Mapping[str, str]) -> Path:
    """``LIB_LAYERED_CONFIG_ETC`` when set, else ``/etc``.

    Raises:
        LayerRootNotAbsoluteError: The override is empty or relative.
    """
    return override_root(env, "LIB_LAYERED_CONFIG_ETC", lambda: Path("/etc"))


def xdg_config_home(env: Mapping[str, str]) -> Path:
    """``$XDG_CONFIG_HOME`` when it is an absolute path, else ``~/.config``.

    The XDG Base Directory specification treats an empty value as unset and says a relative one
    "should be considered invalid and ignored"; both fall back, so no user layer resolves under the
    current working directory. The read, the ``.env`` fallback and deploy all ask here.
    """
    value = env.get("XDG_CONFIG_HOME", "")
    if value and Path(value).root:
        return Path(value)
    return home_directory() / ".config"


class LinuxStrategy(PlatformStrategy):
    """Resolve paths following Linux/XDG conventions.

    Mirror the XDG specification and ``/etc`` conventions documented in the
    system design.

    Path Layouts:
        - App: ``/etc/xdg/<slug>`` then ``/etc/<slug>``
        - Host: ``<etc>/<slug>/hosts/<hostname>.toml``
        - User: ``$XDG_CONFIG_HOME/<slug>`` or ``~/.config/<slug>``
        - Dotenv: ``$XDG_CONFIG_HOME/<slug>/.env``
    """

    def app_paths(self) -> Iterable[str]:
        """Yield Linux application-default configuration paths.

        Provide deterministic discovery following XDG Base Directory specification.
        Yields ``/etc/xdg/<slug>`` (XDG system-wide default) first, then ``/etc/<slug>``;
        both are loaded, so a key set in both takes the ``/etc/<slug>`` value.

        Returns:
            Paths under ``/etc/xdg`` and ``/etc`` (or overridden root).
        """
        etc_root_dir = etc_root(self.ctx.env)
        profile_seg = self._profile_segment()
        yield from collect_layer(etc_root_dir / "xdg" / self.ctx.slug / profile_seg)
        yield from collect_layer(etc_root_dir / self.ctx.slug / profile_seg)

    def host_paths(self) -> Iterable[str]:
        """Yield Linux host-specific configuration paths.

        Allow installations to override defaults per hostname following XDG specification.
        Yields ``/etc/xdg/<slug>/hosts`` first, then ``/etc/<slug>/hosts``; both are loaded.

        Returns:
            Host-level configuration paths (empty when missing).
        """
        host_file = self.ctx.host_file_name
        if host_file is None:
            return
        etc_root_dir = etc_root(self.ctx.env)
        profile_seg = self._profile_segment()
        xdg_candidate = etc_root_dir / "xdg" / self.ctx.slug / profile_seg / "hosts" / host_file
        if config_path_present(xdg_candidate):
            yield str(xdg_candidate)
        candidate = etc_root_dir / self.ctx.slug / profile_seg / "hosts" / host_file
        if config_path_present(candidate):
            yield str(candidate)

    def user_paths(self) -> Iterable[str]:
        """Yield Linux user-specific configuration paths.

        Honour XDG directories while falling back to ``~/.config``.

        Returns:
            User-level configuration paths.
        """
        base = xdg_config_home(self.ctx.env)
        profile_seg = self._profile_segment()
        yield from collect_layer(base / self.ctx.slug / profile_seg)

    def dotenv_path(self) -> Path | None:
        """Return Linux-specific ``.env`` fallback path.

        Returns:
            Path to ``$XDG_CONFIG_HOME/<slug>/.env``.
        """
        base = xdg_config_home(self.ctx.env)
        profile_seg = self._profile_segment()
        return base / self.ctx.slug / profile_seg / ".env"
