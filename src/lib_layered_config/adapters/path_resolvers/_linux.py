"""Linux-specific path resolution strategy.

Purpose
    Implement path resolution following XDG Base Directory specification
    and traditional ``/etc`` conventions.

Contents
    - ``LinuxStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ._base import PlatformStrategy, collect_layer


class LinuxStrategy(PlatformStrategy):
    """Resolve paths following Linux/XDG conventions.

    Why
    ----
    Mirror the XDG specification and ``/etc`` conventions documented in the
    system design.

    Path Layouts
    ------------
    - App: ``/etc/xdg/<slug>`` then ``/etc/<slug>``
    - Host: ``<etc>/<slug>/hosts/<hostname>.toml``
    - User: ``$XDG_CONFIG_HOME/<slug>`` or ``~/.config/<slug>``
    - Dotenv: ``$XDG_CONFIG_HOME/<slug>/.env``
    """

    def app_paths(self) -> Iterable[str]:
        """Yield Linux application-default configuration paths.

        Why
        ----
        Provide deterministic discovery following XDG Base Directory specification.
        Checks ``/etc/xdg/<slug>`` first (XDG system-wide default), then falls back
        to ``/etc/<slug>`` for backwards compatibility.

        Returns
        -------
        Iterable[str]
            Paths under ``/etc/xdg`` and ``/etc`` (or overridden root).
        """
        etc_root = Path(self.ctx.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        # Check XDG-compliant location first
        yield from collect_layer(etc_root / "xdg" / self.ctx.slug)
        # Fall back to traditional /etc location for backwards compatibility
        yield from collect_layer(etc_root / self.ctx.slug)

    def host_paths(self) -> Iterable[str]:
        """Yield Linux host-specific configuration paths.

        Why
        ----
        Allow installations to override defaults per hostname following XDG specification.
        Checks ``/etc/xdg/<slug>/hosts`` first, then falls back to ``/etc/<slug>/hosts``.

        Returns
        -------
        Iterable[str]
            Host-level configuration paths (empty when missing).
        """
        etc_root = Path(self.ctx.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
        # Check XDG-compliant location first
        xdg_candidate = etc_root / "xdg" / self.ctx.slug / "hosts" / f"{self.ctx.hostname}.toml"
        if xdg_candidate.is_file():
            yield str(xdg_candidate)
        # Fall back to traditional /etc location for backwards compatibility
        candidate = etc_root / self.ctx.slug / "hosts" / f"{self.ctx.hostname}.toml"
        if candidate.is_file():
            yield str(candidate)

    def user_paths(self) -> Iterable[str]:
        """Yield Linux user-specific configuration paths.

        Why
        ----
        Honour XDG directories while falling back to ``~/.config``.

        Returns
        -------
        Iterable[str]
            User-level configuration paths.
        """
        xdg = self.ctx.env.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        yield from collect_layer(base / self.ctx.slug)

    def dotenv_path(self) -> Path | None:
        """Return Linux-specific ``.env`` fallback path.

        Returns
        -------
        Path
            Path to ``$XDG_CONFIG_HOME/<slug>/.env``.
        """
        base = Path(self.ctx.env.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / self.ctx.slug / ".env"
