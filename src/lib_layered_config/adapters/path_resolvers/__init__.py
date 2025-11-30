"""Path resolver adapters for platform-specific search order.

Contents
--------
- ``DefaultPathResolver``: main adapter using Strategy pattern
- ``PlatformStrategy``, ``PlatformContext``: base classes for strategies
- ``LinuxStrategy``, ``MacOSStrategy``, ``WindowsStrategy``: platform implementations
- ``DotenvPathFinder``: utility for discovering ``.env`` files
- ``collect_layer``: helper for enumerating config files in a directory
"""

from ._base import PlatformContext, PlatformStrategy, collect_layer
from ._dotenv import DotenvPathFinder
from ._linux import LinuxStrategy
from ._macos import MacOSStrategy
from ._windows import WindowsStrategy
from .default import DefaultPathResolver

__all__ = [
    "DefaultPathResolver",
    "PlatformContext",
    "PlatformStrategy",
    "LinuxStrategy",
    "MacOSStrategy",
    "WindowsStrategy",
    "DotenvPathFinder",
    "collect_layer",
]
