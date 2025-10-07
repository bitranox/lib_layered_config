"""`.env` adapter.

Purpose
-------
Implement the :class:`lib_layered_config.application.ports.DotEnvLoader`
protocol by scanning for `.env` files using the search discipline captured in
``docs/systemdesign/module_reference.md``.

Contents
    - ``DefaultDotEnvLoader``: public loader that composes the helpers.
    - ``_iter_candidates`` / ``_build_search_list``: gather candidate paths.
    - ``_parse_dotenv``: strict parser converting dotenv files into nested dicts.
    - ``_assign_nested`` and friends: ensure ``__`` nesting mirrors environment
      variable semantics.
    - ``_log_dotenv_*``: appetite of logging helpers that narrate discovery and
      parsing outcomes.

System Role
-----------
Feeds `.env` key/value pairs into the merge pipeline using the same nesting
semantics as the environment adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Iterable, cast

from ...domain.errors import InvalidFormat
from ...observability import log_debug, log_error

DOTENV_LAYER = "dotenv"
"""Layer name used for structured logging calls.

Why
----
Tag observability events with a stable layer identifier.

What
----
Constant shared across logging helpers within this module.
"""


def _log_dotenv_loaded(path: Path, keys: Mapping[str, object]) -> None:
    """Record a successful dotenv load with sorted key names.

    Why
    ----
    Provide visibility into which dotenv file was applied and which keys were
    present without dumping values.

    Parameters
    ----------
    path:
        Path to the loaded dotenv file.
    keys:
        Mapping of parsed keys (values are ignored; only key names are logged).
    """

    log_debug("dotenv_loaded", layer=DOTENV_LAYER, path=str(path), keys=sorted(keys.keys()))


def _log_dotenv_missing() -> None:
    """Record that no dotenv file was discovered.

    Why
    ----
    Signal to operators that the dotenv layer was absent (useful for debugging
    precedence expectations).
    """

    log_debug("dotenv_not_found", layer=DOTENV_LAYER, path=None)


def _log_dotenv_error(path: Path, line_number: int) -> None:
    """Capture malformed line diagnostics.

    Why
    ----
    Provide actionable telemetry when dotenv parsing fails on a particular line.

    Parameters
    ----------
    path:
        Path to the dotenv file being parsed.
    line_number:
        Line number containing the malformed entry.
    """

    log_error("dotenv_invalid_line", layer=DOTENV_LAYER, path=str(path), line=line_number)


class DefaultDotEnvLoader:
    """Load a dotenv file into a nested configuration dictionary.

    Why
    ----
    `.env` files supply secrets and developer overrides. They need deterministic
    discovery and identical nesting semantics to environment variables.

    What
    ----
    Searches for candidate files, parses the first hit, records provenance, and
    exposes the loaded path for diagnostics.
    """

    def __init__(self, *, extras: Iterable[str] | None = None) -> None:
        """Initialise the loader with optional *extras* supplied by the path resolver.

        Why
        ----
        Allow callers to append OS-specific directories to the search order.

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

        What
        ----
        Builds the search list, parses the first existing file into a nested
        mapping, stores the loaded path, and logs success or absence.

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

        candidates = _build_search_list(start_dir, self._extras)
        self.last_loaded_path = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            self.last_loaded_path = str(candidate)
            data = _parse_dotenv(candidate)
            _log_dotenv_loaded(candidate, data)
            return data
        _log_dotenv_missing()
        return {}


def _build_search_list(start_dir: str | None, extras: Iterable[Path]) -> list[Path]:
    """Return ordered candidate paths including *extras* supplied by adapters.

    Why
    ----
    Combine project-relative candidates with platform-specific extras while
    preserving precedence order.

    Parameters
    ----------
    start_dir:
        Directory that seeds the upward search.
    extras:
        Additional absolute paths appended after the upward search.

    Returns
    -------
    list[Path]
        Ordered candidate paths for dotenv discovery.
    """

    return [*list(_iter_candidates(start_dir)), *extras]


def _iter_candidates(start_dir: str | None) -> Iterable[Path]:
    """Yield candidate dotenv paths walking from ``start_dir`` to filesystem root.

    Why
    ----
    Support layered overrides by checking the working directory and all parent
    directories.

    Parameters
    ----------
    start_dir:
        Starting directory for the upward search; ``None`` uses the current
        working directory.

    Returns
    -------
    Iterable[Path]
        Sequence of candidate `.env` paths ordered from closest to farthest.

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

    Parameters
    ----------
    path:
        Absolute path to the dotenv file to parse.

    Returns
    -------
    Mapping[str, object]
        Nested dictionary representing the parsed file.

    Raises
    ------
    InvalidFormat
        When a line lacks an ``=`` delimiter or contains invalid syntax.

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
                _log_dotenv_error(path, line_number)
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

    Parameters
    ----------
    value:
        Raw value token read from the dotenv file.

    Returns
    -------
    str
        Cleaned value with quotes and trailing comments removed.

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

    What
    ----
    Splits the key on ``__``, ensures each intermediate mapping exists, resolves
    case-insensitive keys, and assigns the final value.

    Parameters
    ----------
    target:
        Mapping being mutated.
    key:
        Dotenv key using ``__`` separators.
    value:
        Parsed string value to assign.

    Returns
    -------
    None

    Side Effects
    ------------
    Mutates ``target``.

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

    Parameters
    ----------
    mapping:
        Mutable mapping being inspected.
    key:
        Raw key from the dotenv file.

    Returns
    -------
    str
        Existing key or lowercase variant suitable for insertion.
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

    What
    ----
    Resolves the key, creates an empty mapping when missing, or raises the
    provided error when a scalar is encountered.

    Parameters
    ----------
    mapping:
        Mapping being mutated.
    key:
        Key segment to ensure.
    error_cls:
        Exception type raised on scalar collisions.

    Returns
    -------
    dict[str, object]
        Child mapping stored at the resolved key.

    Side Effects
    ------------
    Mutates ``mapping`` by inserting a new child mapping when missing.
    """

    resolved = _resolve_key(mapping, key)
    if resolved not in mapping:
        mapping[resolved] = dict[str, object]()
    child = mapping[resolved]
    if not isinstance(child, dict):
        raise error_cls(f"Cannot overwrite scalar with mapping for key {key}")
    typed_child = cast(dict[str, object], child)
    mapping[resolved] = typed_child
    return typed_child
