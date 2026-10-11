"""Dotenv path discovery utilities.

Provide reusable helpers for discovering ``.env`` files via upward
directory traversal and platform-specific fallback locations.

Contents:
    - ``DotenvPathFinder``: encapsulates dotenv discovery logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._path_probe import PathKind, checked_kind, probe_path

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from ._base import PlatformStrategy


class DotenvPathFinder:
    """Discover ``.env`` files by walking upward and checking platform fallbacks.

    ``.env`` files may live near the project root or in OS-specific config
    directories. This class provides unified discovery respecting precedence rules.
    """

    def __init__(self, cwd: Path | None, strategy: PlatformStrategy | None) -> None:
        """Store context for dotenv discovery.

        Args:
            cwd: Starting directory for upward traversal; ``None`` (the OS cannot name the
                working directory) searches nothing.
            strategy: Platform strategy providing the fallback ``.env`` location.
        """
        self.cwd = cwd
        self.strategy = strategy

    def find_paths(self) -> Iterable[str]:
        """Yield candidate ``.env`` paths in precedence order.

        Projects often co-locate ``.env`` files near the repository root;
        walking upward mirrors ``dotenv`` tooling semantics.

        Returns:
            Ordered ``.env`` path strings.
        """
        yield from self._project_paths()
        extra = self._platform_path()
        if extra and checked_kind(extra) is PathKind.FILE:
            yield str(extra)

    def _project_paths(self) -> Iterable[str]:
        """Yield ``.env`` files discovered by walking upward from cwd.

        Returns:
            ``.env`` paths discovered while traversing parent directories.
        """
        if self.cwd is None:
            return
        seen: set[Path] = set()
        for directory in [self.cwd, *self.cwd.parents]:
            candidate = directory / ".env"
            if candidate in seen:
                continue
            seen.add(candidate)
            # The search cannot read a .env in a directory it cannot enter, so it holds none for it -
            # the same answer on every Python.
            if probe_path(candidate).kind is PathKind.FILE:
                yield str(candidate)

    def _platform_path(self) -> Path | None:
        """Return the platform-specific ``.env`` fallback location.

        Returns:
            Platform fallback path or ``None`` if no strategy is set.
        """
        if self.strategy is None:
            return None
        return self.strategy.dotenv_path()
