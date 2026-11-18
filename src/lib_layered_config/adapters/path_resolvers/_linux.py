"""Linux-specific path resolution strategy.

Implement path resolution following XDG Base Directory specification
and traditional ``/etc`` conventions.

Contents:
    - ``LinuxStrategy``: yields paths for app, host, user, and dotenv layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._base import PlatformStrategy, home_directory, override_root

if TYPE_CHECKING:
    from collections.abc import Mapping


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
        - Host: ``hosts/<hostname>.toml`` under each app directory; deploy writes the first
        - User: ``$XDG_CONFIG_HOME/<slug>`` or ``~/.config/<slug>``
        - Dotenv: ``$XDG_CONFIG_HOME/<slug>/.env``
    """

    def app_dirs(self) -> tuple[Path, ...]:
        """Return ``<etc>/xdg/<slug>`` (the XDG system-wide default) then ``<etc>/<slug>``.

        Both are read, so a key set in both takes the ``/etc/<slug>`` value; a deploy writes the
        first. ``<etc>`` is ``/etc`` or ``LIB_LAYERED_CONFIG_ETC``.

        Returns:
            The two directories, the profile segment included.
        """
        etc_root_dir = etc_root(self.ctx.env)
        profile_seg = self._profile_segment()
        return (etc_root_dir / "xdg" / self.ctx.slug / profile_seg, etc_root_dir / self.ctx.slug / profile_seg)

    def user_dir(self) -> Path:
        """Return ``$XDG_CONFIG_HOME/<slug>``, or ``~/.config/<slug>`` when it is unset.

        Returns:
            The directory, the profile segment included.
        """
        return xdg_config_home(self.ctx.env) / self.ctx.slug / self._profile_segment()

    def dotenv_path(self) -> Path | None:
        """Return Linux-specific ``.env`` fallback path.

        Returns:
            Path to ``$XDG_CONFIG_HOME/<slug>/.env``.
        """
        base = xdg_config_home(self.ctx.env)
        profile_seg = self._profile_segment()
        return base / self.ctx.slug / profile_seg / ".env"
