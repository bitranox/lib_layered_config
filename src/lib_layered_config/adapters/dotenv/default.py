"""`.env` adapter.

Purpose
-------
Implement the :class:`lib_layered_config.application.ports.DotEnvLoader`
protocol by scanning for `.env` files using the search discipline captured in
``docs/systemdesign/module_reference.md``.

Contents
--------
* :class:`DefaultDotEnvLoader` – entry point with optional extra search paths.
* Helper functions (`_iter_candidates`, `_parse_dotenv`, `_assign_nested`, etc.)
  that perform parsing and nested assignment.

System Role
-----------
Feeds `.env` key/value pairs into the merge pipeline using the same nesting
semantics as the environment adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Iterable

from ...domain.errors import InvalidFormat
from ...observability import log_debug, log_error


class DefaultDotEnvLoader:
    """Load a dotenv file into a nested configuration dictionary.

    Why
    ----
    `.env` files supply secrets and developer overrides. They need deterministic
    discovery and identical nesting semantics to environment variables.
    """

    def __init__(self, *, extras: Iterable[str] | None = None) -> None:
        """Initialise the loader with optional *extras* supplied by the path resolver.

        Parameters
        ----------
        extras:
            Additional absolute paths (typically OS-specific config directories)
            appended to the search order.
        """

        self._extras = [Path(p) for p in extras or []]
        self.last_loaded_path: str | None = None

    def load(self, start_dir: str | None = None) -> Mapping[str, object]:
        """Return the first parsed dotenv file discovered in the search order.

        Why
        ----
        Provide the precedence layer ``dotenv`` used by the composition root.

        Parameters
        ----------
        start_dir:
            Directory that seeds the upward search (often the project root).

        Returns
        -------
        Mapping[str, object]
            Nested mapping representing parsed key/value pairs.

        Side Effects
        ------------
        Sets :attr:`last_loaded_path` and emits structured logging events.

        Examples
        --------
        >>> from tempfile import TemporaryDirectory
        >>> tmp = TemporaryDirectory()
        >>> path = Path(tmp.name) / '.env'
        >>> _ = path.write_text(
        ...     'SERVICE__TOKEN=secret',
        ...     encoding='utf-8',
        ... )
        >>> loader = DefaultDotEnvLoader()
        >>> loader.load(tmp.name)["service"]["token"]
        'secret'
        >>> loader.last_loaded_path == str(path)
        True
        >>> tmp.cleanup()
        """

        candidates = list(_iter_candidates(start_dir)) + self._extras
        self.last_loaded_path = None
        for candidate in candidates:
            if candidate.is_file():
                self.last_loaded_path = str(candidate)
                data = _parse_dotenv(candidate)
                log_debug("dotenv_loaded", layer="dotenv", path=self.last_loaded_path, keys=sorted(data.keys()))
                return data
        log_debug("dotenv_not_found", layer="dotenv", path=None)
        return {}


def _iter_candidates(start_dir: str | None) -> Iterable[Path]:
    """Yield candidate dotenv paths walking from ``start_dir`` to filesystem root.

    Why
    ----
    Support layered overrides by checking the working directory and all parent
    directories.

    Examples
    --------
    >>> from pathlib import Path
    >>> base = Path('.')
    >>> next(_iter_candidates(str(base))).name
    '.env'
    """

    base = Path(start_dir) if start_dir else Path.cwd()
    for directory in [base, *base.parents]:
        yield directory / ".env"


def _parse_dotenv(path: Path) -> Mapping[str, object]:
    """Parse ``path`` into a nested dictionary, raising ``InvalidFormat`` on malformed lines.

    Why
    ----
    Ensure dotenv parsing is strict and produces dictionaries compatible with
    the merge algorithm.

    Returns
    -------
    Mapping[str, object]
        Nested dictionary representing the parsed file.

    Examples
    --------
    >>> import os
    >>> tmp = Path('example.env')
    >>> body = os.linesep.join(['FEATURE=true', 'SERVICE__TIMEOUT=10']) + os.linesep
    >>> _ = tmp.write_text(body, encoding='utf-8')
    >>> parsed = _parse_dotenv(tmp)
    >>> parsed["service"]["timeout"]
    '10'
    >>> tmp.unlink()
    """

    result: dict[str, object] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                log_error("dotenv_invalid_line", layer="dotenv", path=str(path), line=line_number)
                raise InvalidFormat(f"Malformed line {line_number} in {path}")
            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_quotes(value.strip())
            _assign_nested(result, key, value)
    return result


def _strip_quotes(value: str) -> str:
    """Trim surrounding quotes and inline comments from ``value``.

    Why
    ----
    `.env` syntax allows quoted strings and trailing inline comments; stripping
    them keeps behaviour aligned with community conventions.

    Examples
    --------
    >>> _strip_quotes('"token"')
    'token'
    >>> _strip_quotes("value # comment")
    'value'
    """

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    if value.startswith("#"):
        return ""
    if " #" in value:
        return value.split(" #", 1)[0].strip()
    return value


def _assign_nested(target: dict[str, object], key: str, value: object) -> None:
    """Assign ``value`` in ``target`` using case-insensitive dotted syntax.

    Why
    ----
    Ensure dotenv keys with ``__`` delimiters mirror environment variable
    nesting rules.

    Examples
    --------
    >>> data: dict[str, object] = {}
    >>> _assign_nested(data, 'SERVICE__TOKEN', 'secret')
    >>> data
    {'service': {'token': 'secret'}}
    """

    parts = key.split("__")
    cursor = target
    for part in parts[:-1]:
        cursor = _ensure_child_mapping(cursor, part, error_cls=InvalidFormat)
    final_key = _resolve_key(cursor, parts[-1])
    cursor[final_key] = value


def _resolve_key(mapping: dict[str, object], key: str) -> str:
    """Return an existing key with matching case-insensitive name or create a new lowercase entry.

    Why
    ----
    Preserve original casing when keys repeat while avoiding duplicates that
    differ only by case.
    """

    lower = key.lower()
    for existing in mapping.keys():
        if existing.lower() == lower:
            return existing
    return lower


def _ensure_child_mapping(mapping: dict[str, object], key: str, *, error_cls: type[Exception]) -> dict[str, object]:
    """Ensure ``mapping[key]`` is a ``dict`` or raise ``error_cls`` when a scalar blocks nesting.

    Why
    ----
    Nested keys should never overwrite scalar values without an explicit error.
    This keeps configuration shapes predictable.
    """

    resolved = _resolve_key(mapping, key)
    if resolved not in mapping:
        mapping[resolved] = {}
    child = mapping[resolved]
    if not isinstance(child, dict):
        raise error_cls(f"Cannot overwrite scalar with mapping for key {key}")
    return child
