"""Dotenv path discovery utilities.

Provide reusable helpers for discovering ``.env`` files via upward
directory traversal and platform-specific fallback locations.

Contents:
    - ``DotenvPathFinder``: encapsulates dotenv discovery logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base import PlatformStrategy


class DotenvPathFinder:
    """Discover ``.env`` files by walking upward and checking platform fallbacks.

    ``.env`` files may live near the project root or in OS-specific config
    directories. This class provides unified discovery respecting precedence rules.
    """

    def __init__(self, cwd: Path, strategy: PlatformStrategy | None) -> None:
        """Store context for dotenv discovery.

        Args:
            cwd: Starting directory for upward traversal.
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
        if extra and extra.is_file():
            yield str(extra)

    def _project_paths(self) -> Iterable[str]:
        """Yield ``.env`` files discovered by walking upward from cwd.

        Returns:
            ``.env`` paths discovered while traversing parent directories.
        """
        seen: set[Path] = set()
        for directory in [self.cwd, *self.cwd.parents]:
            candidate = directory / ".env"
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.is_file():
                yield str(candidate)

    def _platform_path(self) -> Path | None:
        """Return the platform-specific ``.env`` fallback location.

        Returns:
            Platform fallback path or ``None`` if no strategy is set.
        """
        if self.strategy is None:
            return None
        return self.strategy.dotenv_path()
