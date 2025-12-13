"""Dot-d directory expansion for structured configuration files.

Provide logic to expand a configuration file path into an ordered list
of paths including the base file and any files from a companion .d directory.

Pattern:
    For a file ``foo.toml``, check for ``foo.d/`` directory and yield:
    1. The base file (if it exists)
    2. Files from the .d directory in lexicographical order (if directory exists)

Both the base file and .d directory are optional - either can exist independently.
The .d directory can contain mixed formats (TOML, YAML, JSON).

Contents:
    - ``expand_dot_d``: main function to expand a file path
    - ``_collect_dot_d_files``: helper to collect files from .d directory
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

_ALLOWED_EXTENSIONS = (".toml", ".yaml", ".yml", ".json")
"""File suffixes considered when expanding ``.d`` directories.

Ensure discovery yields only structured configuration formats.
Tuple of lowercase extensions.
"""


def expand_dot_d(path: str) -> Iterable[str]:
    """Expand a configuration file path to include .d directory entries.

    For a file ``foo.toml``, checks for ``foo.d/`` directory (without extension)
    and yields:
    1. The base file (if it exists)
    2. Files from the .d directory in lexicographical order (if directory exists)

    Both the base file and .d directory are optional - either can exist independently.
    The .d directory can contain mixed formats (TOML, YAML, JSON).

    Args:
        path: Absolute path to the configuration file.

    Yields:
        Absolute paths in merge order (base file first, then .d files sorted).

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> from pathlib import Path
        >>> tmp = TemporaryDirectory()
        >>> base = Path(tmp.name) / "config.toml"
        >>> _ = base.write_text("[app]\\nname = 'test'", encoding="utf-8")
        >>> list(expand_dot_d(str(base)))  # doctest: +ELLIPSIS
        ['...config.toml']
        >>> tmp.cleanup()
    """
    base_path = Path(path)
    dot_d_dir = base_path.with_suffix(".d")

    if base_path.is_file():
        yield str(base_path)

    yield from _collect_dot_d_files(dot_d_dir)


def _collect_dot_d_files(dot_d_dir: Path) -> Iterable[str]:
    """Yield config files from a .d directory in lexicographical order.

    Args:
        dot_d_dir: Path to the .d directory (e.g., /etc/app/config.toml.d/).

    Yields:
        Absolute paths to files with supported extensions, sorted by name.

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> from pathlib import Path
        >>> tmp = TemporaryDirectory()
        >>> d = Path(tmp.name) / "config.toml.d"
        >>> d.mkdir()
        >>> (d / "10-db.toml").write_text("[db]\\nhost = 'localhost'", encoding="utf-8")
        8
        >>> (d / "20-cache.yaml").write_text("cache:\\n  enabled: true", encoding="utf-8")
        24
        >>> (d / "README.md").write_text("ignore me", encoding="utf-8")  # Not a config file
        9
        >>> [Path(p).name for p in _collect_dot_d_files(d)]
        ['10-db.toml', '20-cache.yaml']
        >>> tmp.cleanup()
    """
    if not dot_d_dir.is_dir():
        return

    for file_path in sorted(dot_d_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in _ALLOWED_EXTENSIONS:
            yield str(file_path)
