"""`.env` adapter.

Implement the :class:`lib_layered_config.application.ports.DotEnvLoader`
protocol by scanning for `.env` files using the search discipline captured in
``docs/systemdesign/module_reference.md``.

Contents:
    - ``DefaultDotEnvLoader``: public loader that composes the helpers.
    - ``_iter_candidates`` / ``_build_search_list``: gather candidate paths.
    - ``_parse_dotenv``: strict parser converting dotenv files into nested dicts. Values stay
      strings, except an unquoted JSON array or object, which becomes a list or table like in
      the environment layer; a quoted value is always the literal text.
    - ``_log_dotenv_*``: logging helpers that narrate discovery and parsing outcomes.
    - Constants for parsing quote characters and delimiters.

Feeds `.env` key/value pairs into the merge pipeline using the same nesting
semantics as the environment adapter.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Final

from ...domain.errors import InvalidFormatError
from ...observability import log_debug, log_error, log_warn
from .._nested_keys import assign_nested
from .._text_decoding import decode_utf8
from .._value_coercion import parse_json_container
from ..file_loaders.structured import ensure_within_size_cap

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Constants for dotenv parsing
_QUOTE_CHARS: Final[frozenset[str]] = frozenset({'"', "'"})
_COMMENT_CHAR: Final[str] = "#"
_INLINE_COMMENT_DELIMITER: Final[str] = " #"
_KEY_VALUE_DELIMITER: Final[str] = "="
_MIN_QUOTED_LENGTH: Final[int] = 2  # shortest possible quoted value, e.g. '' or ""

DOTENV_LAYER = "dotenv"
"""Layer name for structured logging calls."""


def _log_dotenv_loaded(path: Path, keys: Mapping[str, object]) -> None:
    """Log which dotenv file was loaded and its key names."""
    log_debug("dotenv_loaded", layer=DOTENV_LAYER, path=str(path), keys=sorted(keys.keys()))


def _log_dotenv_missing() -> None:
    """Log that no dotenv file was found in the search path."""
    log_debug("dotenv_not_found", layer=DOTENV_LAYER, path=None)


def _log_dotenv_error(path: Path, line_number: int) -> None:
    """Log a malformed line error with file path and line number."""
    log_error("dotenv_invalid_line", layer=DOTENV_LAYER, path=str(path), line=line_number)


def _warn_dotenv_directory_skipped(path: Path) -> None:
    """Warn that a configured dotenv path is a directory and was skipped.

    Args:
        path: The explicit ``dotenv_path`` that resolved to a directory on disk.
    """
    log_warn("config_directory_skipped", layer=DOTENV_LAYER, path=str(path))


class DefaultDotEnvLoader:
    """Load a dotenv file into a nested configuration dictionary.

    Searches candidate paths, parses the first existing file, and tracks
    the loaded path for provenance.
    """

    def __init__(self, *, extras: Iterable[str] | None = None) -> None:
        """Initialise with optional extra search paths from the path resolver."""
        self._extras = [Path(p) for p in extras or []]
        self.last_loaded_path: str | None = None

    def load(self, start_dir: str | None = None, *, dotenv_path: str | None = None) -> Mapping[str, object]:
        """Return the first parsed dotenv file discovered in the search order.

        When *dotenv_path* is given, loads that file directly instead of
        searching upward from *start_dir*.  Otherwise searches from *start_dir*
        upward plus any extras, parses the first existing file into a nested
        mapping, and sets :attr:`last_loaded_path`.
        """
        if dotenv_path is not None:
            return self._load_explicit(Path(dotenv_path))

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

    def _load_explicit(self, path: Path) -> Mapping[str, object]:
        """Load a specific dotenv file without directory search."""
        self.last_loaded_path = None
        if path.is_dir():
            _warn_dotenv_directory_skipped(path)
            return {}
        if not path.is_file():
            _log_dotenv_missing()
            return {}
        self.last_loaded_path = str(path)
        data = _parse_dotenv(path)
        _log_dotenv_loaded(path, data)
        return data


def _build_search_list(start_dir: str | None, extras: Iterable[Path]) -> list[Path]:
    """Combine upward-search candidates with platform-specific extras."""
    return [*list(_iter_candidates(start_dir)), *extras]


def _iter_candidates(start_dir: str | None) -> Iterable[Path]:
    """Yield `.env` paths from start_dir upward to filesystem root."""
    base = Path(start_dir) if start_dir else Path.cwd()
    for directory in [base, *base.parents]:
        yield directory / ".env"


def _parse_dotenv(path: Path) -> Mapping[str, object]:
    """Parse dotenv file into nested dict.

    Raises:
        InvalidFormatError: On malformed lines or bytes, or when the file is larger than
            :data:`~lib_layered_config.adapters.file_loaders.structured.MAX_CONFIG_FILE_BYTES`
            (checked before the file is read, the same cap and refusal shape structured
            configuration files use).
    """
    result: dict[str, object] = {}
    ensure_within_size_cap(str(path), path.stat().st_size)
    text = decode_utf8(path.read_bytes(), path=path)
    # StringIO with newline=None keeps the universal-newline line splitting the text-mode open() had.
    for line_number, raw_line in enumerate(io.StringIO(text, newline=None), start=1):
        _process_line(result, raw_line, line_number, path)
    return result


def _is_ignorable(line: str) -> bool:
    """Return True if line is empty or a comment."""
    return not line or line.startswith(_COMMENT_CHAR)


def _process_line(
    result: dict[str, object],
    raw_line: str,
    line_number: int,
    path: Path,
) -> None:
    """Process a single dotenv line, updating result in place."""
    line = raw_line.strip()
    if _is_ignorable(line):
        return
    if _KEY_VALUE_DELIMITER not in line:
        _log_dotenv_error(path, line_number)
        raise InvalidFormatError(f"Malformed line {line_number} in {path}")
    key, value = line.split(_KEY_VALUE_DELIMITER, 1)
    assign_nested(result, key.strip(), _dotenv_value(value.strip()), error_cls=InvalidFormatError)


def _dotenv_value(raw: str) -> str | list[object] | dict[str, object]:
    """Return a dotenv value: quoted stays the literal text; unquoted JSON array/object becomes a list/table.

    Quoting is the only way to keep a literal string in .env, so it is never parsed further.

    Examples:
        >>> _dotenv_value('[1, 2]'), _dotenv_value("'[1, 2]'"), _dotenv_value('plain # note')
        ([1, 2], '[1, 2]', 'plain')
    """
    if _is_quoted(raw):
        return raw[1:-1]
    text = _strip_quotes(raw)  # the unquoted branch: comment and inline-comment handling
    container = parse_json_container(text)
    return text if container is None else container


def _is_quoted(value: str) -> bool:
    """Check if value is wrapped in matching quotes."""
    return len(value) >= _MIN_QUOTED_LENGTH and value[0] == value[-1] and value[0] in _QUOTE_CHARS


def _strip_inline_comment(value: str) -> str:
    """Remove trailing inline comment from value."""
    return value.split(_INLINE_COMMENT_DELIMITER, 1)[0].strip() if _INLINE_COMMENT_DELIMITER in value else value


def _strip_quotes(value: str) -> str:
    """Remove surrounding quotes and trailing inline comments from value."""
    if _is_quoted(value):
        return value[1:-1]
    if value.startswith(_COMMENT_CHAR):
        return ""
    return _strip_inline_comment(value)
