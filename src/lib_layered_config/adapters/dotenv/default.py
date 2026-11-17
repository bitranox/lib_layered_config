"""`.env` adapter.

Implement the :class:`lib_layered_config.application.ports.DotEnvLoader`
protocol by scanning for `.env` files using the search discipline captured in
``docs/systemdesign/module_reference.md``.

Contents:
    - ``DefaultDotEnvLoader``: public loader that composes the helpers.
    - ``_iter_candidates`` / ``_build_search_list``: gather candidate paths.
    - ``_foreign_owner`` / ``_owner_is_trusted``: pass over a searched file another user owns.
    - ``_link_count_if_shared``: pass over a searched file with more than one hard link.
    - ``_parse_dotenv``: strict parser converting dotenv files into nested dicts. An unquoted
      value is converted by ``.._value_coercion.coerce_value``, exactly as the environment layer
      converts it; a quoted value is always the literal text.
    - ``_log_dotenv_*``: logging helpers that narrate discovery and parsing outcomes.
    - Constants for parsing quote characters and delimiters.

Feeds `.env` key/value pairs into the merge pipeline using the same nesting
semantics as the environment adapter.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

from ...domain.errors import InvalidFormatError
from ...domain.redaction import NotSensitiveKeys
from ...observability import log_debug, log_warn
from .._nested_keys import NestedEntry, build_nested
from .._path_probe import PathKind, checked_kind, config_path_unreadable, current_directory, probe_path
from .._text_decoding import UTF8_BOM_CHAR, decode_utf8
from .._value_coercion import coerce_value
from ..file_loaders.structured import directory_not_config_file, read_capped_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "DOTENV_LAYER",
    "DefaultDotEnvLoader",
]


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


def _log_dotenv_missing(path: Path | None = None) -> None:
    """Log that no dotenv file was found: in the search path, or at the explicit *path* given."""
    log_debug("dotenv_not_found", layer=DOTENV_LAYER, path=None if path is None else str(path))


def _log_dotenv_error(path: Path, line_number: int) -> None:
    """Log a malformed line at DEBUG: the ``InvalidFormatError`` raised after it is the report."""
    log_debug("dotenv_invalid_line", layer=DOTENV_LAYER, path=str(path), line=line_number)


class DefaultDotEnvLoader:
    """Load a dotenv file into a nested configuration dictionary.

    Searches candidate paths, parses the first existing file, and tracks
    the loaded path for provenance.
    """

    def __init__(
        self, *, extras: Iterable[str] | None = None, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE
    ) -> None:
        """Initialise with optional extra search paths and the application's not-sensitive paths."""
        self._extras = [Path(p) for p in extras or []]
        self._not_sensitive = not_sensitive
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
            # The search cannot read a .env in a directory it cannot enter, so it holds none for it -
            # the same answer on every Python.
            if probe_path(candidate).kind is not PathKind.FILE:
                continue
            foreign_owner = _foreign_owner(candidate)
            if foreign_owner is not None:
                _log_dotenv_skipped(candidate, foreign_owner)
                continue
            link_count = _link_count_if_shared(candidate)
            if link_count is not None:
                _log_dotenv_skipped_hard_link(candidate, link_count)
                continue
            self.last_loaded_path = str(candidate)
            data = _parse_dotenv(candidate, not_sensitive=self._not_sensitive)
            _log_dotenv_loaded(candidate, data)
            return data
        _log_dotenv_missing()
        return {}

    def _load_explicit(self, path: Path) -> Mapping[str, object]:
        """Load a specific dotenv file without directory search.

        A FIFO or device is read like a file, so ``--env-file <(...)`` works; a path that does not
        exist loads nothing.
        """
        self.last_loaded_path = None
        kind = checked_kind(path)
        if kind is PathKind.DIRECTORY:
            raise directory_not_config_file(path)
        if kind is PathKind.MISSING:
            _log_dotenv_missing(path)
            return {}
        self.last_loaded_path = str(path)
        data = _parse_dotenv(path, not_sensitive=self._not_sensitive)
        _log_dotenv_loaded(path, data)
        return data


def _build_search_list(start_dir: str | None, extras: Iterable[Path]) -> list[Path]:
    """Combine upward-search candidates with the extras, each path once, in first-seen order.

    The extras repeat the walk: the resolver's search list walks upward from the same start
    directory, and its per-user ``.env`` is the walk's own first candidate when ``start_dir`` is the
    user config directory. Without the dedupe a skipped file is owner-checked and reported once per
    copy. Paths are compared as absolute, normalised text, never resolved: resolving would follow a
    symlink, and the owner check judges the link and its target separately.

    Examples:
        >>> [p.as_posix() for p in _build_search_list("/opt/app", [Path("/opt/app/.env"), Path("/srv/.env")])]
        ['/opt/app/.env', '/opt/.env', '/.env', '/srv/.env']
    """
    unique: dict[str, Path] = {}
    for candidate in [*_iter_candidates(start_dir), *extras]:
        unique.setdefault(os.path.normpath(candidate.absolute()), candidate)
    return list(unique.values())


def _iter_candidates(start_dir: str | None) -> Iterable[Path]:
    """Yield `.env` paths from start_dir upward to the filesystem root.

    Without a start_dir the search starts in the current directory; it yields nothing only when
    the current directory cannot be resolved.
    """
    base = Path(start_dir) if start_dir else current_directory()
    if base is None:
        return
    for directory in [base, *base.parents]:
        yield directory / ".env"


def _owner_is_trusted(owner_uid: int, *, euid: int) -> bool:
    """Return True when a file owned by *owner_uid* may be loaded by a process running as *euid*.

    Only the process's own user and root qualify: without root, nobody can create a file another
    user owns, so a ``.env`` planted in a shared directory such as ``/tmp`` always fails this.

    Examples:
        >>> _owner_is_trusted(1000, euid=1000), _owner_is_trusted(0, euid=1000), _owner_is_trusted(1001, euid=1000)
        (True, True, False)
    """
    return owner_uid in {euid, 0}


def _foreign_owner(path: Path) -> int | None:
    """Return the owner uid of a searched *path* when neither the current user nor root owns it.

    The check is the trust boundary of the upward search: every parent directory up to ``/`` is
    searched, and a ``.env`` another user put in one of them (``/tmp/.env``) would otherwise outrank
    the app, host and user files. Only ownership is checked, not the mode: files created under the
    usual ``umask 0002`` are group-writable and many working trees are world-writable, and a mode
    rule skipped those legitimate files too (user decision 2026-11-03). Windows has no POSIX owner
    to compare, so nothing is skipped there.

    A symlink is judged by its own owner AND its target's: judged by the target alone, another
    user could plant a link in a directory they control pointing at any file the reader owns, and
    the search would read that file as the ``.env``.

    Returns:
        The first untrusted owner's uid (the link's, then the target's), or ``None`` when the file
        may be loaded. A path that cannot be stat'ed here is ``None`` too: reading it then raises
        the usual unreadable-file error.
    """
    if sys.platform == "win32":
        return None
    try:
        owners = (path.lstat().st_uid, path.stat().st_uid)
    except OSError:
        return None
    euid = os.geteuid()
    return next((owner for owner in owners if not _owner_is_trusted(owner, euid=euid)), None)


def _log_dotenv_skipped(path: Path, owner_uid: int) -> None:
    """Warn that a searched dotenv file was passed over because another user owns it."""
    log_warn("dotenv_skipped_foreign_owner", layer=DOTENV_LAYER, path=str(path), owner_uid=owner_uid)


def _link_count_if_shared(path: Path) -> int | None:
    """Return the hard-link count of a searched *path* when it is above one, else ``None``.

    A hard link keeps its file's owner, so the owner check cannot see one: another user who can write
    some file the reader owns (a group- or world-writable one, on the same filesystem) can link it as
    ``.env`` into a directory on the search path and then write settings into it. The second link is
    the one trace that leaves. A legitimate ``.env`` with two links (a ``cp -al`` backup tree on the
    search path) is skipped too and must be named with ``dotenv_path`` (user decision 2026-11-17,
    rs-R4-F1). The count is read through a symlink, from the file the search would read.

    Returns:
        The link count when it is above one, or ``None`` when the file may be loaded. A path that
        cannot be stat'ed here is ``None`` too: reading it then raises the usual unreadable-file error.
    """
    try:
        count = path.stat().st_nlink
    except OSError:
        return None
    return count if count > 1 else None


def _log_dotenv_skipped_hard_link(path: Path, link_count: int) -> None:
    """Warn that a searched dotenv file was passed over because it has more than one hard link."""
    log_warn("dotenv_skipped_hard_link", layer=DOTENV_LAYER, path=str(path), link_count=link_count)


def _parse_dotenv(path: Path, *, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE) -> Mapping[str, object]:
    """Parse dotenv file into nested dict.

    Args:
        path: The file to read.
        not_sensitive: Paths the application declared not sensitive.

    Raises:
        InvalidFormatError: On malformed lines or bytes, or when the file is larger than
            :data:`~lib_layered_config.adapters.file_loaders.structured.MAX_CONFIG_FILE_BYTES`
            (a regular file is sized before it is read, a FIFO or device is read to one byte past
            the cap; the same cap and refusal shape structured configuration files use), when
            it cannot be read, or when one line sets a value and another a key below it
            (``DB`` and ``DB__PORT``), in either order.
    """
    entries: list[NestedEntry] = []
    try:
        raw = read_capped_bytes(path)
    except OSError as error:
        raise config_path_unreadable(path, error) from error
    # A leading BOM (Notepad's "UTF-8 with BOM", PowerShell 5 Out-File) would otherwise become part
    # of the first key's name, which no lookup can reach.
    text = decode_utf8(raw, path=path).removeprefix(UTF8_BOM_CHAR)
    # StringIO with newline=None keeps the universal-newline line splitting the text-mode open() had.
    for line_number, raw_line in enumerate(io.StringIO(text, newline=None), start=1):
        entry = _split_line(raw_line, line_number, path)
        if entry is None:
            continue
        value = _dotenv_value(entry.key, entry.raw_value, not_sensitive=not_sensitive)
        entries.append(NestedEntry(entry.key, value, f"{entry.key} (line {line_number})"))
    return build_nested(entries, error_cls=InvalidFormatError, where=f"{path}: ")


def _is_ignorable(line: str) -> bool:
    """Return True if line is empty or a comment."""
    return not line or line.startswith(_COMMENT_CHAR)


class _DotenvEntry(NamedTuple):
    """One ``KEY=value`` line: the stripped key and the stripped, not yet converted value."""

    key: str
    raw_value: str


def _split_line(raw_line: str, line_number: int, path: Path) -> _DotenvEntry | None:
    """Return a dotenv line's key and raw value, or None for a blank or comment line.

    Raises:
        InvalidFormatError: The line has no ``=``, or its key or value holds a NUL.
    """
    line = raw_line.strip()
    if _is_ignorable(line):
        return None
    if _KEY_VALUE_DELIMITER not in line:
        _log_dotenv_error(path, line_number)
        raise InvalidFormatError(f"Malformed line {line_number} in {path}")
    key, value = line.split(_KEY_VALUE_DELIMITER, 1)
    if "\x00" in line:
        # tomllib refuses a raw NUL in a string too; the message leaves the value out.
        _log_dotenv_error(path, line_number)
        raise InvalidFormatError(f"NUL character in the key or value of line {line_number} in {path}")
    return _DotenvEntry(key=key.strip(), raw_value=value.strip())


def _dotenv_value(key: str, raw: str, *, not_sensitive: NotSensitiveKeys = NotSensitiveKeys.NONE) -> object:
    """Return a dotenv value: quoted stays the literal text; unquoted is converted like the environment.

    Quoting is the only way to keep a literal string such as ``"5432"`` or ``"true"`` in .env, so a
    quoted value is never parsed further.

    Examples:
        >>> _dotenv_value("PORT", "5432"), _dotenv_value("PORT", "'5432'"), _dotenv_value("NAME", "plain # note")
        (5432, '5432', 'plain')
        >>> _dotenv_value("HOSTS", "[1, 2]"), _dotenv_value("SMTP_PASSWORD", "none")
        ([1, 2], 'none')
    """
    if _is_quoted(raw):
        return raw[1:-1]
    # The unquoted branch: comment handling, then conversion.
    return coerce_value(key, _strip_quotes(raw), not_sensitive=not_sensitive)


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
