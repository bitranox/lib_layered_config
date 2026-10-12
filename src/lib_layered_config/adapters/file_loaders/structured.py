"""Structured configuration file loaders.

Convert on-disk artifacts into Python mappings that the merge layer understands.
Adapters are small wrappers around ``rtoml``/``json``/``yaml.safe_load`` so
error handling, observability, and immutability policies live in one place.

Contents:
    - ``BaseFileLoader``: shared primitives for reading files and asserting
      mapping outputs.
    - ``TOMLFileLoader`` / ``JSONFileLoader`` / ``YAMLFileLoader``: thin
      adapters that delegate to parser-specific helpers.
    - ``_log_file_read`` / ``_log_file_loaded`` / ``_log_file_invalid``:
      structured logging helpers reused across loaders.
    - ``_ensure_yaml_available``: guard ensuring YAML support is present before
      attempting to parse.

Invoked by :func:`lib_layered_config.core._load_files` to parse structured files
before passing the results to the merge policy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import orjson
import rtoml

from ...domain.errors import InvalidFormatError, NotFoundError
from ...observability import log_debug, log_error
from .._path_probe import PathKind, checked_kind, config_path_unreadable
from .._text_decoding import decode_utf8, decode_yaml_text
from ._yaml_facade import as_yaml_module

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._yaml_facade import YAMLModule

#: Maximum size of a single configuration file. A config file is normally a few KB; this
#: generous 10 MiB ceiling bounds memory so an oversized or adversarial file (including
#: one dropped into a ``.d`` directory) cannot exhaust memory during a read.
MAX_CONFIG_FILE_BYTES: Final[int] = 10 * 1024 * 1024

yaml: YAMLModule | None = None


FILE_LAYER = "file"
"""Layer label used in structured logging for file-oriented events.

Tag observability events originating from file loaders with a consistent name.

Constant referenced by logging helpers within this module.
"""


def _log_file_read(path: str, size: int) -> None:
    """Record that *path* was read with *size* bytes.

    Provide insight into which files were accessed and their size for
    troubleshooting.

    Args:
        path: Absolute path read from disk.
        size: Number of bytes read.
    """
    log_debug("config_file_read", layer=FILE_LAYER, path=path, size=size)


def _log_file_loaded(path: str, format_name: str) -> None:
    """Record a successful parse for *path* and *format_name*.

    Trace successful parsing events and note which parser handled the file.

    Args:
        path: Absolute file path.
        format_name: Parser identifier (e.g., ``"toml"``).
    """
    log_debug("config_file_loaded", layer=FILE_LAYER, path=path, format=format_name)


#: rtoml's message is read only for the numbers in it; "line 1 column 4" (toml 0.5) and
#: "line 1, column 4" (newer renderers, which also print a source snippet) both match.
_TOML_POSITION: Final[re.Pattern[str]] = re.compile(r"line (\d+),? column (\d+)")

#: rtoml's two depth refusals: "cannot recurse further; max recursion depth met at ..." for an
#: array or inline table, "recursion limit" for a table header or dotted key. Fixed wording that
#: carries no file content.
_TOML_TOO_DEEP: Final[re.Pattern[str]] = re.compile(r"recursion")

#: orjson's depth refusal: "depth limit exceeded: line 1 column 1026 (char 1025)".
_JSON_TOO_DEEP: Final[str] = "depth limit exceeded"


@dataclass(frozen=True)
class _ParseFailure:
    """What a parser's refusal says about the document, read without keeping its text.

    Attributes:
        position: 1-based (line, column), or ``None`` when the parser reported none.
        too_deep: The parser stopped at its nesting limit; the document may be well formed.
    """

    position: tuple[int, int] | None
    too_deep: bool = False


def _log_file_invalid(path: str, format_name: str, message: str) -> None:
    """Log a parse failure with the content-free message the caller will see.

    Args:
        path: File path that failed to parse.
        format_name: Parser identifier.
        message: The content-free message the caller will also see.
    """
    log_error("config_file_invalid", layer=FILE_LAYER, path=path, format=format_name, error=message)


def directory_not_config_file(path: Path) -> InvalidFormatError:
    """Log and build the refusal for a configured file path that is a directory on disk.

    Without it the layer's file would be dropped without a trace and the configuration would
    fall back to lower layers. Shared by the file layers and an explicit ``dotenv_path``.

    Args:
        path: The configured path that resolved to a directory.

    Returns:
        The error to raise.

    Examples:
        >>> str(directory_not_config_file(Path("config.toml")))
        'config.toml is a directory, not a configuration file'
    """
    message = f"{path} is a directory, not a configuration file"
    log_error("config_path_is_directory", layer=FILE_LAYER, path=str(path), error=message)
    return InvalidFormatError(message)


def _build_invalid_format_message(path: str, format_name: str, failure: _ParseFailure | None) -> str:
    """Build the caller-facing message: path, format, why and, when known, line and column.

    A refusal at the parser's nesting limit says so rather than calling a well-formed file
    invalid. Kept separate from logging and error construction so the text itself stays pinned
    by a plain doctest.

    Args:
        path: File path being parsed.
        format_name: Parser identifier (e.g. ``"toml"``).
        failure: What the parser's refusal said, or ``None`` when nothing is known.

    Returns:
        The message text.

    Examples:
        >>> print(_build_invalid_format_message("a.toml", "toml", _ParseFailure((2, 5))))
        a.toml is not valid TOML (line 2, column 5)
        >>> print(_build_invalid_format_message("a.yaml", "yaml", None))
        a.yaml is not valid YAML
        >>> print(_build_invalid_format_message("a.toml", "toml", _ParseFailure((1, 85), too_deep=True)))
        a.toml nests deeper than the TOML parser allows (line 1, column 85)
    """
    position = failure.position if failure is not None else None
    where = f" (line {position[0]}, column {position[1]})" if position is not None else ""
    if failure is not None and failure.too_deep:
        return f"{path} nests deeper than the {format_name.upper()} parser allows{where}"
    return f"{path} is not valid {format_name.upper()}{where}"


def _log_and_build_invalid_format(path: str, format_name: str, failure: _ParseFailure | None) -> InvalidFormatError:
    """Log the parse failure, then build the error for it: path, format and, when known, line/column.

    The caller raises it OUTSIDE its ``except`` block, so the parser's exception, whose message or
    mark can hold file content, is not reachable through ``__context__``.

    Args:
        path: File path being parsed.
        format_name: Parser identifier (e.g. ``"toml"``).
        failure: What the parser's refusal said, or ``None`` when nothing is known.

    Returns:
        The error to raise.
    """
    message = _build_invalid_format_message(path, format_name, failure)
    _log_file_invalid(path, format_name, message)
    return InvalidFormatError(message)


def _toml_position(message: str) -> tuple[int, int] | None:
    """Return the 1-based line and column rtoml reports, or None.

    Args:
        message: The text of the ``rtoml.TomlParsingError``.

    Returns:
        The (line, column) pair, or ``None`` when the message carries no position.

    Examples:
        >>> _toml_position("expected an equals, found eof at line 1 column 4")
        (1, 4)
        >>> _toml_position("TOML parse error at line 3, column 7")
        (3, 7)
        >>> _toml_position("boom") is None
        True
    """
    found = _TOML_POSITION.search(message)
    return (int(found.group(1)), int(found.group(2))) if found else None


def _yaml_position(exc: BaseException) -> tuple[int, int] | None:
    """Return the 1-based line and column of a PyYAML ``MarkedYAMLError``, or None.

    Args:
        exc: The exception PyYAML raised.

    Returns:
        The (line, column) pair, or ``None`` when the exception carries no mark.

    Examples:
        >>> from types import SimpleNamespace
        >>> error = Exception()
        >>> error.problem_mark = SimpleNamespace(line=1, column=9)
        >>> _yaml_position(error)
        (2, 10)
        >>> _yaml_position(Exception()) is None
        True
    """
    mark: object = getattr(exc, "problem_mark", None)
    line: object = getattr(mark, "line", None)
    column: object = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        return line + 1, column + 1
    return None


def _json_position(exc: BaseException) -> tuple[int, int] | None:
    """Return the 1-based line and column an ``orjson.JSONDecodeError`` reports, or None.

    Args:
        exc: The exception caught while parsing; only ``orjson.JSONDecodeError`` carries a
            position, so any other exception type yields ``None``.

    Returns:
        The (line, column) pair, or ``None``.
    """
    return (exc.lineno, exc.colno) if isinstance(exc, orjson.JSONDecodeError) else None


def _toml_failure(exc: BaseException) -> _ParseFailure:
    """Read an ``rtoml.TomlParsingError`` into its position and whether it is rtoml's depth limit.

    Examples:
        >>> _toml_failure(ValueError("cannot recurse further; max recursion depth met at line 1 column 85"))
        _ParseFailure(position=(1, 85), too_deep=True)
        >>> _toml_failure(ValueError("extra `=`, expected nothing at line 1 column 5"))
        _ParseFailure(position=(1, 5), too_deep=False)
    """
    message = str(exc)
    return _ParseFailure(_toml_position(message), too_deep=_TOML_TOO_DEEP.search(message) is not None)


def _json_failure(exc: BaseException) -> _ParseFailure:
    """Read an ``orjson.JSONDecodeError`` into its position and whether it is orjson's depth limit.

    Examples:
        >>> import orjson
        >>> try:
        ...     orjson.loads("[" * 1100 + "]" * 1100)
        ... except orjson.JSONDecodeError as error:
        ...     _json_failure(error).too_deep
        True
    """
    return _ParseFailure(_json_position(exc), too_deep=str(exc).startswith(_JSON_TOO_DEEP))


#: Sentinel returned by :func:`_run_parser` in place of a value when the parse failed. A real
#: parsed value (including ``None`` from an empty JSON/YAML document) is never mistaken for a
#: failure because this identity, not ``None``, marks it.
_PARSE_FAILED: Final[object] = object()


def _run_parser(
    parse: Callable[[], object],
    exceptions: type[BaseException] | tuple[type[BaseException], ...],
    describe: Callable[[BaseException], _ParseFailure],
) -> tuple[object, _ParseFailure | None]:
    """Run *parse*, collapsing its try/except into one reusable call per format.

    Args:
        parse: Zero-argument callable performing the parse attempt.
        exceptions: Exception type(s) that signal a parse failure rather than propagating.
        describe: Callable reading the caught exception into a :class:`_ParseFailure`.

    Returns:
        ``(value, None)`` on success. ``(_PARSE_FAILED, failure)`` when *parse* raised one of
        *exceptions*; *failure* says where and whether the parser stopped at its nesting limit.

    Examples:
        >>> _run_parser(lambda: 42, ValueError, lambda exc: _ParseFailure(None))
        (42, None)
        >>> def boom() -> int:
        ...     raise ValueError("bad line 2 column 4")
        >>> value, failure = _run_parser(boom, ValueError, lambda exc: _ParseFailure((2, 4)))
        >>> value is _PARSE_FAILED, failure.position
        (True, (2, 4))
    """
    try:
        return parse(), None
    except exceptions as exc:
        return _PARSE_FAILED, describe(exc)


def _ensure_yaml_available() -> None:
    """Announce clearly whether PyYAML can be reached.

    YAML support is optional; the loader must fail fast with guidance when the
    dependency is absent so callers can install the expected extra.

    Raises:
        NotFoundError: When the PyYAML package cannot be imported.
    """
    _require_yaml_module()


def _require_yaml_module() -> YAMLModule:
    """Fetch the PyYAML module or explain its absence.

    Downstream helpers need the module object for access to both ``safe_load``
    and the package-specific ``YAMLError`` type.

    Returns:
        The imported PyYAML module.

    Raises:
        NotFoundError: When PyYAML is not installed.
    """
    module = _load_yaml_module()
    if module is None:
        raise NotFoundError("PyYAML is required for YAML configuration support")
    return module


def _load_yaml_module() -> YAMLModule | None:
    """Import PyYAML on demand, caching the result for future readers.

    Avoid importing optional dependencies unless they are genuinely needed,
    while still ensuring subsequent calls reuse the same module object.

    Returns:
        The PyYAML module when available; otherwise ``None``.
    """
    global yaml  # noqa: PLW0603 - module-level cache for an optional dependency, populated once
    if yaml is not None:
        return yaml
    try:
        yaml = as_yaml_module(import_module("yaml"))
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        yaml = None
    return yaml


def ensure_within_size_cap(path: str, size: int) -> None:
    """Raise :class:`InvalidFormatError` when *size* exceeds :data:`MAX_CONFIG_FILE_BYTES`.

    Shared by every adapter that reads a whole configuration file into memory (the
    structured file loaders below, and the dotenv adapter) so the cap, its check order
    (called before the file content is read), and the refusal message stay in one place.

    Args:
        path: File path being sized, used only for the error message.
        size: The file's size in bytes, as reported by ``stat()`` before any read.

    Raises:
        InvalidFormatError: When *size* is greater than :data:`MAX_CONFIG_FILE_BYTES`.
    """
    if size > MAX_CONFIG_FILE_BYTES:
        raise InvalidFormatError(
            f"Configuration file {path} is {size} bytes, exceeding the {MAX_CONFIG_FILE_BYTES}-byte limit"
        )


class BaseFileLoader:
    """Common utilities shared by the structured file loaders.

    Avoid duplicating file I/O, error handling, and mapping validation across
    individual loaders.

    Provides reusable helpers for reading files and asserting parser outputs.
    """

    def _read(self, path: str) -> bytes:
        """Read *path* as bytes, raising :class:`NotFoundError` when the file is missing.

        Centralise file existence checks and logging so all loaders behave
        consistently.

        Args:
            path: Absolute file path expected to exist.

        Returns:
            Raw file contents.

        Raises:
            NotFoundError: *path* is not a file.
            InvalidFormatError: *path* cannot be checked or read, or exceeds the size cap.

        Side Effects:
            Emits ``config_file_read`` debug events.

        Examples:
            >>> from tempfile import NamedTemporaryFile
            >>> tmp = NamedTemporaryFile(delete=False)
            >>> _ = tmp.write(b"key = 'value'")
            >>> tmp.close()
            >>> BaseFileLoader()._read(tmp.name)[:3]
            b'key'
            >>> Path(tmp.name).unlink()
        """
        file_path = Path(path)
        if checked_kind(file_path) is not PathKind.FILE:
            raise NotFoundError(f"Configuration file not found: {path}")
        try:
            ensure_within_size_cap(path, file_path.stat().st_size)
            payload = file_path.read_bytes()
        except OSError as error:
            raise config_path_unreadable(file_path, error) from error
        _log_file_read(path, len(payload))
        return payload

    @staticmethod
    def _ensure_mapping(data: object, *, path: str) -> Mapping[str, object]:
        """Ensure *data* behaves like a mapping, otherwise raise ``InvalidFormatError``.

        Merging logic expects mapping-like structures; other types indicate a
        malformed configuration file.

        Args:
            data: Object produced by the parser.
            path: Originating file path used for error messaging.

        Returns:
            The validated mapping.

        Examples:
            >>> BaseFileLoader._ensure_mapping({"key": 1}, path="demo")
            {'key': 1}
            >>> BaseFileLoader._ensure_mapping(42, path="demo")
            Traceback (most recent call last):
            ...
            lib_layered_config.domain.errors.InvalidFormatError: File demo did not produce a mapping
        """
        if not isinstance(data, Mapping):
            raise InvalidFormatError(f"File {path} did not produce a mapping")
        # The isinstance check proves a Mapping and nothing about its keys. TOML and JSON keys are
        # always strings; YAML can produce int or bool keys (`1:`, `true:`), which pass through as
        # they are - YAMLFileLoader warns about each one. The cast states the declared type, not a
        # checked one.
        return cast("Mapping[str, object]", data)


class TOMLFileLoader(BaseFileLoader):
    """Load TOML documents using the rtoml (Rust-based) parser for 5x faster parsing."""

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from TOML file at *path*.

        TOML is the primary structured format in the documentation; this loader
        provides friendly error messages and structured logging.

        Args:
            path: Absolute path to a TOML document.

        Returns:
            Parsed configuration data.

        Side Effects:
            Emits ``config_file_loaded`` debug events.

        Examples:
            >>> from tempfile import NamedTemporaryFile
            >>> tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
            >>> _ = tmp.write('key = "value"')
            >>> tmp.close()
            >>> TOMLFileLoader().load(tmp.name)["key"]
            'value'
            >>> Path(tmp.name).unlink()
        """
        raw_bytes = self._read(path)
        try:
            decoded = decode_utf8(raw_bytes, path=path)
        except InvalidFormatError as exc:
            _log_file_invalid(path, "toml", str(exc))
            raise
        parsed, failure = _run_parser(lambda: rtoml.loads(decoded), rtoml.TomlParsingError, _toml_failure)
        if parsed is _PARSE_FAILED:
            raise _log_and_build_invalid_format(path, "toml", failure)
        result = self._ensure_mapping(parsed, path=path)
        _log_file_loaded(path, "toml")
        return result


class JSONFileLoader(BaseFileLoader):
    """Load JSON documents.

    Provide a drop-in parser for JSON configuration files.

    Uses :mod:`orjson` to parse files and delegates validation/logging to the base class.
    """

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from JSON file at *path*.

        Provide parity with TOML for teams that prefer JSON configuration.

        Args:
            path: Absolute path to a JSON document.

        Returns:
            Parsed configuration mapping.

        Side Effects:
            Emits ``config_file_loaded`` debug events.

        Examples:
            >>> from tempfile import NamedTemporaryFile
            >>> tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
            >>> _ = tmp.write('{"enabled": true}')
            >>> tmp.close()
            >>> JSONFileLoader().load(tmp.name)["enabled"]
            True
            >>> Path(tmp.name).unlink()
        """
        raw_bytes = self._read(path)
        try:
            decoded = decode_utf8(raw_bytes, path=path)
        except InvalidFormatError as exc:
            _log_file_invalid(path, "json", str(exc))
            raise
        payload, failure = _run_parser(lambda: orjson.loads(decoded), orjson.JSONDecodeError, _json_failure)
        if payload is _PARSE_FAILED:
            raise _log_and_build_invalid_format(path, "json", failure)
        result = self._ensure_mapping(payload, path=path)
        _log_file_loaded(path, "json")
        return result


class YAMLFileLoader(BaseFileLoader):
    """Load YAML documents when PyYAML is available.

    Support teams that rely on YAML without imposing a mandatory dependency.

    Guards on PyYAML availability before delegating to :func:`yaml.safe_load`.
    """

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from YAML file at *path*.

        Some teams rely on YAML for configuration; this loader keeps behaviour
        consistent with TOML/JSON while remaining optional.

        Args:
            path: Absolute path to a YAML document.

        Returns:
            Parsed configuration mapping.

        Raises:
            NotFoundError: When PyYAML is not installed.

        Side Effects:
            Emits ``config_file_loaded`` debug events.

        Examples:
            >>> if _load_yaml_module() is not None:  # doctest: +SKIP
            ...     from tempfile import NamedTemporaryFile
            ...     tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
            ...     _ = tmp.write('key: 1')
            ...     tmp.close()
            ...     YAMLFileLoader().load(tmp.name)["key"]
            ...     Path(tmp.name).unlink()
        """
        _ensure_yaml_available()
        yaml_module = _require_yaml_module()
        raw_bytes = self._read(path)
        try:
            decoded = decode_yaml_text(raw_bytes, path=path)
        except InvalidFormatError as exc:
            _log_file_invalid(path, "yaml", str(exc))
            raise
        parsed = _parse_yaml_text(decoded, yaml_module, path)
        mapping = self._ensure_mapping(parsed, path=path)
        _refuse_non_string_keys(mapping, path=path)
        _refuse_ordered_map_tags(mapping, path=path)
        _refuse_values_json_cannot_carry(mapping, path=path)
        _log_file_loaded(path, "yaml")
        return mapping


def _parse_yaml_text(document: str, module: YAMLModule, path: str) -> object:
    """Turn a decoded YAML document into a Python shape that mirrors the file.

    Normalise the PyYAML parsing contract so callers always receive a mapping,
    raising a domain-specific error when the parser signals invalid syntax.

    Args:
        document: Decoded YAML document.
        module: PyYAML module providing ::func:`safe_load` and the ``YAMLError`` base class.
        path: Source identifier used to enrich error messages.

    Returns:
        Parsed document; an empty dict when the YAML payload evaluates to ``None``.

    Raises:
        InvalidFormatError: When PyYAML raises ``YAMLError`` while parsing the document, or when a
            constructor it calls raises a bare ``ValueError`` (e.g. an out-of-range calendar date
            such as ``2020-13-01``) or ``RecursionError`` (a deeply nested document, reported as
            nesting deeper than the YAML parser allows); neither is a ``YAMLError`` subclass, so both
            are caught separately, with no reported position.

    Examples:
        >>> from types import SimpleNamespace
        >>> fake = SimpleNamespace(safe_load=lambda data: {"key": data}, YAMLError=Exception)
        >>> _parse_yaml_text("value", fake, "memory.yaml")  # doctest: +ELLIPSIS
        {'key': 'value'}
    """

    def _describe(exc: BaseException) -> _ParseFailure:
        position = _yaml_position(exc) if isinstance(exc, module.YAMLError) else None
        return _ParseFailure(position, too_deep=isinstance(exc, RecursionError))

    parsed, failure = _run_parser(
        lambda: module.safe_load(document), (module.YAMLError, ValueError, RecursionError), _describe
    )
    if parsed is _PARSE_FAILED:
        raise _log_and_build_invalid_format(path, "yaml", failure)
    return {} if parsed is None else parsed


def _refuse_non_string_keys(data: object, *, path: str) -> None:
    """Refuse a document holding a mapping key that is not a string.

    YAML reads ``1:`` as an int key and ``true:`` as a bool key, while everything downstream
    treats keys as strings: the merge and :class:`Config` would treat a mapping holding such a key
    as ONE value, none of its keys reachable by dotted lookup or carrying its own provenance. The
    error names the file, the dotted position of each key's parent and the key itself; it never
    carries a value, which may be a secret.

    Args:
        data: Parsed document, already known to be a mapping at the top.
        path: File the document came from, named in the error.

    Raises:
        InvalidFormatError: When any mapping in *data* has a key that is not a string.

    Examples:
        >>> _refuse_non_string_keys({"service": {"timeout": 5}}, path="demo.yaml")
        >>> _refuse_non_string_keys({"db": {5: "x"}}, path="demo.yaml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: demo.yaml has keys ... db: 5 (int)
    """
    found = _non_string_keys(data)
    if not found:
        return
    message = f"{path} has keys that are not strings (quote them): {'; '.join(found)}"
    _log_file_invalid(path, "yaml", message)
    raise InvalidFormatError(message)


def _non_string_keys(data: object) -> list[str]:
    """Describe every mapping key in *data* that is not a string, as ``"<parent>: <key> (<type>)"``.

    The walk uses an explicit stack rather than recursion: the parser accepted the document's
    depth, and the walk must not fail on a depth the parser accepted.

    Examples:
        >>> _non_string_keys({"items": [{"name": "a"}, {7: "y"}], True: 1})
        ['<top>: True (bool)', 'items.1: 7 (int)']
    """
    found: list[str] = []
    pending: list[tuple[object, str]] = [(data, "")]
    while pending:
        node, parent = pending.pop()
        if isinstance(node, Mapping):
            mapping = cast("Mapping[object, object]", node)
            found.extend(
                f"{parent or '<top>'}: {key!r} ({type(key).__name__})" for key in mapping if not isinstance(key, str)
            )
            pending.extend((value, _join_position(parent, str(key))) for key, value in mapping.items())
        elif isinstance(node, list):
            items = cast("list[object]", node)
            pending.extend((item, _join_position(parent, str(index))) for index, item in enumerate(items))
    return sorted(found)


def _refuse_ordered_map_tags(data: object, *, path: str) -> None:
    """Refuse a document holding a ``!!omap`` or ``!!pairs`` value.

    PyYAML's safe loader builds both tags as a list of ``(key, value)`` tuples, and it builds a
    tuple from no other tag, so a tuple in the document marks one exactly. Inside such a list a key
    is a tuple element rather than a mapping key: redaction never sees ``password`` there, and every
    redacted view would print its value. A plain mapping keeps its order, so the error points the
    user at one. It names the file and each such value's dotted position (the mapping keys above it),
    never a key or value from inside it.

    Args:
        data: Parsed document, already known to be a mapping at the top.
        path: File the document came from, named in the error.

    Raises:
        InvalidFormatError: When any value in *data* came from ``!!omap`` or ``!!pairs``.

    Examples:
        >>> _refuse_ordered_map_tags({"items": [{"a": 1}]}, path="demo.yaml")
        >>> _refuse_ordered_map_tags({"creds": [("password", "x")]}, path="demo.yaml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: demo.yaml uses !!omap or !!pairs ...: creds
    """
    found = _ordered_map_positions(data)
    if not found:
        return
    message = (
        f"{path} uses !!omap or !!pairs, whose keys redaction cannot see; "
        f"write a plain mapping instead: {'; '.join(found)}"
    )
    _log_file_invalid(path, "yaml", message)
    raise InvalidFormatError(message)


def _ordered_map_positions(data: object) -> list[str]:
    """Return the dotted position of every list in *data* that holds a ``(key, value)`` tuple.

    Walks with an explicit stack for the reason :func:`_non_string_keys` gives.

    Examples:
        >>> _ordered_map_positions({"a": [{"b": [("k", 1)]}], "c": [("k", 2)], "d": [1]})
        ['a.0.b', 'c']
    """
    found: list[str] = []
    pending: list[tuple[object, str]] = [(data, "")]
    while pending:
        node, position = pending.pop()
        if isinstance(node, Mapping):
            mapping = cast("Mapping[object, object]", node)
            pending.extend((value, _join_position(position, str(key))) for key, value in mapping.items())
        elif isinstance(node, list):
            items = cast("list[object]", node)
            if any(isinstance(item, tuple) for item in items):
                found.append(position)
                continue
            pending.extend((item, _join_position(position, str(index))) for index, item in enumerate(items))
    return sorted(found)


#: The tag a YAML author wrote for each Python type PyYAML's safe loader builds with no JSON form.
_TAG_OF_UNSERIALISABLE: dict[type, str] = {set: "!!set", bytes: "!!binary"}


def _refuse_values_json_cannot_carry(data: object, *, path: str) -> None:
    """Refuse a document holding a ``!!set`` or ``!!binary`` value.

    PyYAML's safe loader builds them as ``set`` and ``bytes``, and neither has a JSON form: such a
    config loaded, then crashed every JSON view (``Config.to_json``, ``read_config_json``,
    ``display_config`` in JSON) with an uncaught ``TypeError``. Refusing at load names the problem
    where the file is known. The error names the file, the tags, and each value's dotted position
    with its Python type, never the value.

    Args:
        data: Parsed document, already known to be a mapping at the top.
        path: File the document came from, named in the error.

    Raises:
        InvalidFormatError: When any value in *data* came from ``!!set`` or ``!!binary``.

    Examples:
        >>> _refuse_values_json_cannot_carry({"tags": ["x"]}, path="demo.yaml")
        >>> _refuse_values_json_cannot_carry({"tags": {"x"}}, path="demo.yaml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: demo.yaml uses !!set or !!binary, ...: tags (set)
    """
    found = _unserialisable_positions(data)
    if not found:
        return
    message = (
        f"{path} uses !!set or !!binary, which have no JSON form; "
        f"write a list or a base64 string instead: {'; '.join(found)}"
    )
    _log_file_invalid(path, "yaml", message)
    raise InvalidFormatError(message)


def _unserialisable_positions(data: object) -> list[str]:
    """Describe every ``set`` or ``bytes`` value in *data* as ``"<position> (<type>)"``.

    Walks with an explicit stack for the reason :func:`_non_string_keys` gives.

    Examples:
        >>> _unserialisable_positions({"a": [{"b": {1}}], "c": b"x", "d": [1]})
        ['a.0.b (set)', 'c (bytes)']
    """
    found: list[str] = []
    pending: list[tuple[object, str]] = [(data, "")]
    while pending:
        node, position = pending.pop()
        if type(node) in _TAG_OF_UNSERIALISABLE:
            found.append(f"{position or '<top>'} ({type(node).__name__})")
        elif isinstance(node, Mapping):
            mapping = cast("Mapping[object, object]", node)
            pending.extend((value, _join_position(position, str(key))) for key, value in mapping.items())
        elif isinstance(node, list):
            items = cast("list[object]", node)
            pending.extend((item, _join_position(position, str(index))) for index, item in enumerate(items))
    return sorted(found)


def _join_position(parent: str, segment: str) -> str:
    """Append *segment* to the dotted *parent* position.

    Examples:
        >>> _join_position("", "db"), _join_position("db", "port")
        ('db', 'db.port')
    """
    return f"{parent}.{segment}" if parent else segment
