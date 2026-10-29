"""Structured configuration file loaders.

Convert on-disk artifacts into Python mappings that the merge layer understands.
Adapters are small wrappers around the TOML parser, the JSON codec and ``yaml.safe_load`` so
error handling, observability, and immutability policies live in one place.

Contents:
    - ``FileFormat``: the structured formats the loaders parse, as logs and messages name them.
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

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from ...domain.errors import InvalidFormatError, NotFoundError
from ...domain.json_codec import (
    CODEC,
    CONFIG_MAX_DEPTH,
    JSON_INT_MAX,
    JSON_INT_MIN,
    JsonCodec,
    JsonLoadError,
    duplicate_keys,
    nesting_depth,
)
from ...domain.source_position import SourcePosition
from ...observability import log_debug, log_error
from .._path_probe import PathKind, checked_kind, config_path_unreadable
from .._text_decoding import decode_utf8, decode_yaml_text
from ._toml_backend import PARSER, TomlLoadError, TomlParser
from ._yaml_facade import as_yaml_module, compose_document

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._yaml_facade import YAMLModule, YAMLNode

__all__ = [
    "FILE_LAYER",
    "MAX_CONFIG_FILE_BYTES",
    "BaseFileLoader",
    "FileFormat",
    "JSONFileLoader",
    "TOMLFileLoader",
    "YAMLFileLoader",
    "directory_not_config_file",
    "ensure_within_size_cap",
    "read_capped_bytes",
    "special_file_not_config_file",
    "unsupported_config_format",
]


#: Maximum size of a single configuration file. A config file is normally a few KB; this
#: generous 10 MiB ceiling bounds memory so an oversized or adversarial file (including
#: one dropped into a ``.d`` directory) cannot exhaust memory during a read.
MAX_CONFIG_FILE_BYTES: Final[int] = 10 * 1024 * 1024

#: The tag PyYAML resolves ``<<`` to; such a key merges a mapping in rather than naming a setting.
_YAML_MERGE_TAG: Final[str] = "tag:yaml.org,2002:merge"

yaml: YAMLModule | None = None


FILE_LAYER = "file"
"""Layer label used in structured logging for file-oriented events.

Tag observability events originating from file loaders with a consistent name.

Constant referenced by logging helpers within this module.
"""


class FileFormat(str, Enum):
    """A structured format a file loader parses.

    The value is the name the ``format`` field of a log event carries; messages name the format
    upper-cased (``TOML``). Both are built from ``.value``, never from the member itself, whose
    ``str()`` differs between Python 3.10 and 3.11+.

    Examples:
        >>> FileFormat.TOML.value, FileFormat("yaml") is FileFormat.YAML
        ('toml', True)
    """

    TOML = "toml"
    JSON = "json"
    YAML = "yaml"


def _log_file_read(path: str, size: int) -> None:
    """Record that *path* was read with *size* bytes.

    Provide insight into which files were accessed and their size for
    troubleshooting.

    Args:
        path: Absolute path read from disk.
        size: Number of bytes read.
    """
    log_debug("config_file_read", layer=FILE_LAYER, path=path, size=size)


def _log_file_loaded(path: str, file_format: FileFormat) -> None:
    """Record a successful parse for *path* and *file_format*.

    Trace successful parsing events and note which parser handled the file.

    Args:
        path: Absolute file path.
        file_format: The format the file was parsed as; logged by its value (``"toml"``).
    """
    log_debug("config_file_loaded", layer=FILE_LAYER, path=path, format=file_format.value)


@dataclass(frozen=True)
class _ParseFailure:
    """What a parser's refusal says about the document, read without keeping its text.

    Attributes:
        position: 1-based line and column, or ``None`` when the parser reported none.
        too_deep: The parser stopped at its nesting limit; the document may be well formed.
    """

    position: SourcePosition | None
    too_deep: bool = False


def _log_file_invalid(path: str, file_format: FileFormat, message: str) -> None:
    """Log a parse failure with the content-free message the caller will see.

    Args:
        path: File path that failed to parse.
        file_format: The format the file was parsed as; logged by its value.
        message: The content-free message the caller will also see.
    """
    log_error("config_file_invalid", layer=FILE_LAYER, path=path, format=file_format.value, error=message)


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


_SPECIAL_FILE_KINDS: Final = (
    (stat.S_ISFIFO, "FIFO"),
    (stat.S_ISCHR, "character device"),
    (stat.S_ISBLK, "block device"),
    (stat.S_ISSOCK, "socket"),
)


def special_file_not_config_file(path: Path) -> InvalidFormatError:
    """Log and build the refusal for a configured file path that is a FIFO, device or socket.

    A defaults file comes with a ``.d`` companion named after it, which has no meaning for a
    stream such as ``/dev/fd/63``, so a stream is refused rather than read; passed over as absent,
    the layer vanished without a word. Naming the kind tells the caller why an existing path did
    not load.

    Args:
        path: The configured path that exists as something other than a file or directory.

    Returns:
        The error to raise.

    Examples:
        >>> str(special_file_not_config_file(Path("nonexistent-lib-layered-config-probe")))
        'nonexistent-lib-layered-config-probe is a special file, not a configuration file'
    """
    try:
        mode = path.stat().st_mode
    except (OSError, ValueError):
        # Gone or changed between the caller's check and this one: name no kind rather than guess.
        mode = 0
    kind = next((name for is_kind, name in _SPECIAL_FILE_KINDS if is_kind(mode)), "special file")
    message = f"{path} is a {kind}, not a configuration file"
    log_error("config_path_is_special_file", layer=FILE_LAYER, path=str(path), error=message)
    return InvalidFormatError(message)


def unsupported_config_format(path: Path, suffixes: tuple[str, ...]) -> InvalidFormatError:
    """Log and build the refusal for a configured file whose suffix no loader reads.

    Args:
        path: The configured file.
        suffixes: The suffixes a loader reads, in the order the message lists them.

    Returns:
        The error to raise.

    Examples:
        >>> str(unsupported_config_format(Path("defaults.conf"), (".toml", ".json")))
        'defaults.conf has no supported format (.toml, .json)'
    """
    message = f"{path} has no supported format ({', '.join(suffixes)})"
    log_error("config_path_unsupported_format", layer=FILE_LAYER, path=str(path), error=message)
    return InvalidFormatError(message)


def _build_invalid_format_message(path: str, file_format: FileFormat, failure: _ParseFailure | None) -> str:
    """Build the caller-facing message: path, format, why and, when known, line and column.

    A refusal at the parser's nesting limit says so rather than calling a well-formed file
    invalid. Kept separate from logging and error construction so the text itself stays pinned
    by a plain doctest.

    Args:
        path: File path being parsed.
        file_format: The format the file was parsed as, named upper-cased.
        failure: What the parser's refusal said, or ``None`` when nothing is known.

    Returns:
        The message text.

    Examples:
        >>> print(_build_invalid_format_message("a.toml", FileFormat.TOML, _ParseFailure(SourcePosition(2, 5))))
        a.toml is not valid TOML (line 2, column 5)
        >>> print(_build_invalid_format_message("a.yaml", FileFormat.YAML, None))
        a.yaml is not valid YAML
        >>> too_deep = _ParseFailure(SourcePosition(1, 85), too_deep=True)
        >>> print(_build_invalid_format_message("a.toml", FileFormat.TOML, too_deep))
        a.toml nests deeper than the TOML parser allows (line 1, column 85)
    """
    position = failure.position if failure is not None else None
    where = f" (line {position.line}, column {position.column})" if position is not None else ""
    display_name = file_format.value.upper()
    if failure is not None and failure.too_deep:
        return f"{path} nests deeper than the {display_name} parser allows{where}"
    return f"{path} is not valid {display_name}{where}"


def _log_and_build_invalid_format(
    path: str, file_format: FileFormat, failure: _ParseFailure | None
) -> InvalidFormatError:
    """Log the parse failure, then build the error for it: path, format and, when known, line/column.

    The caller raises it OUTSIDE its ``except`` block, so the parser's exception, whose message or
    mark can hold file content, is not reachable through ``__context__``.

    Args:
        path: File path being parsed.
        file_format: The format the file was parsed as.
        failure: What the parser's refusal said, or ``None`` when nothing is known.

    Returns:
        The error to raise.
    """
    message = _build_invalid_format_message(path, file_format, failure)
    _log_file_invalid(path, file_format, message)
    return InvalidFormatError(message)


def _yaml_position(exc: BaseException) -> SourcePosition | None:
    """Return the 1-based line and column of a PyYAML ``MarkedYAMLError``, or None.

    Args:
        exc: The exception PyYAML raised.

    Returns:
        The position, or ``None`` when the exception carries no mark.

    Examples:
        >>> from types import SimpleNamespace
        >>> error = Exception()
        >>> error.problem_mark = SimpleNamespace(line=1, column=9)
        >>> _yaml_position(error)
        SourcePosition(line=2, column=10)
        >>> _yaml_position(Exception()) is None
        True
    """
    mark: object = getattr(exc, "problem_mark", None)
    line: object = getattr(mark, "line", None)
    column: object = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        return SourcePosition(line + 1, column + 1)
    return None


def _backend_failure(exc: BaseException) -> _ParseFailure:
    """Read a TOML or JSON backend's refusal into its position and whether the document nests too deep.

    Examples:
        >>> _backend_failure(JsonLoadError("deep", too_deep=True))
        _ParseFailure(position=None, too_deep=True)
        >>> _backend_failure(TomlLoadError("bad", position=SourcePosition(2, 8)))
        _ParseFailure(position=SourcePosition(line=2, column=8), too_deep=False)
    """
    if not isinstance(exc, (JsonLoadError, TomlLoadError)):
        return _ParseFailure(None)
    return _ParseFailure(exc.position, too_deep=exc.too_deep)


class _ParseOutcome(NamedTuple):
    """What one parse attempt produced.

    The failure, not the value, tells the two apart: a real parsed value can be ``None`` (an
    empty JSON or YAML document).

    Attributes:
        value: The parsed value; ``None`` when the parse failed.
        failure: What the parser's refusal said, or ``None`` when the parse succeeded.
    """

    value: object
    failure: _ParseFailure | None


def _run_parser(
    parse: Callable[[], object],
    exceptions: type[BaseException] | tuple[type[BaseException], ...],
    describe: Callable[[BaseException], _ParseFailure],
) -> _ParseOutcome:
    """Run *parse*, collapsing its try/except into one reusable call per format.

    Args:
        parse: Zero-argument callable performing the parse attempt.
        exceptions: Exception type(s) that signal a parse failure rather than propagating.
        describe: Callable reading the caught exception into a :class:`_ParseFailure`.

    Returns:
        The parsed value with no failure on success. When *parse* raised one of *exceptions*, no
        value and the failure, which says where and whether the parser stopped at its nesting limit.

    Examples:
        >>> _run_parser(lambda: 42, ValueError, lambda exc: _ParseFailure(None))
        _ParseOutcome(value=42, failure=None)
        >>> def boom() -> int:
        ...     raise ValueError("bad line 2 column 4")
        >>> outcome = _run_parser(boom, ValueError, lambda exc: _ParseFailure(SourcePosition(2, 4)))
        >>> outcome.failure is not None, outcome.failure.position
        (True, SourcePosition(line=2, column=4))
    """
    try:
        return _ParseOutcome(parse(), None)
    except exceptions as exc:
        return _ParseOutcome(None, describe(exc))


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


def read_capped_bytes(path: Path) -> bytes:
    """Read *path* whole, refusing it once it holds more than :data:`MAX_CONFIG_FILE_BYTES`.

    A regular file is sized with ``stat()`` first, so an oversized one is refused unread. A stream
    (a FIFO such as a shell's ``<(...)``, or a device) has no size to ask, so at most one byte past
    the cap is read: an endless source like ``/dev/zero`` is refused instead of read forever. A
    refused stream reports the cap plus one as its size, the most that was read.

    Args:
        path: The file or stream to read.

    Returns:
        The content.

    Raises:
        InvalidFormatError: When the content exceeds the cap.
        OSError: When *path* cannot be opened or read.

    Examples:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     target = Path(tmp) / "a.env"
        ...     _ = target.write_bytes(b"A=1")
        ...     read_capped_bytes(target)
        b'A=1'
    """
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        ensure_within_size_cap(str(path), opened.st_size if stat.S_ISREG(opened.st_mode) else 0)
        payload = stream.read(MAX_CONFIG_FILE_BYTES + 1)
    ensure_within_size_cap(str(path), len(payload))
    return payload


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
    """Load TOML documents with the interpreter's TOML parser (rtoml, or tomllib with the same answers)."""

    def __init__(self, parser: TomlParser = PARSER) -> None:
        """Parse with *parser*; the default is the parser this interpreter chose at import."""
        self._parser = parser

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
            _log_file_invalid(path, FileFormat.TOML, str(exc))
            raise
        outcome = _run_parser(lambda: self._parser.loads(decoded), TomlLoadError, _backend_failure)
        if outcome.failure is not None:
            raise _log_and_build_invalid_format(path, FileFormat.TOML, outcome.failure)
        result = self._ensure_mapping(outcome.value, path=path)
        _refuse_integers_json_cannot_carry(result, path=path, file_format=FileFormat.TOML)
        _refuse_nesting_json_cannot_write(result, path=path, file_format=FileFormat.TOML)
        _log_file_loaded(path, FileFormat.TOML)
        return result


class JSONFileLoader(BaseFileLoader):
    """Load JSON documents.

    Provide a drop-in parser for JSON configuration files.

    Parses with the interpreter's JSON codec (orjson, or stdlib json with the same answers) and
    delegates validation/logging to the base class.
    """

    def __init__(self, codec: JsonCodec = CODEC) -> None:
        """Parse with *codec*; the default is the codec this interpreter chose at import."""
        self._codec = codec

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
            _log_file_invalid(path, FileFormat.JSON, str(exc))
            raise
        outcome = _run_parser(lambda: self._codec.loads(decoded), JsonLoadError, _backend_failure)
        if outcome.failure is not None:
            raise _log_and_build_invalid_format(path, FileFormat.JSON, outcome.failure)
        result = self._ensure_mapping(outcome.value, path=path)
        _refuse_nesting_json_cannot_write(result, path=path, file_format=FileFormat.JSON)
        _refuse_repeated_keys(duplicate_keys(decoded), path=path, file_format=FileFormat.JSON)
        _log_file_loaded(path, FileFormat.JSON)
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
            _log_file_invalid(path, FileFormat.YAML, str(exc))
            raise
        parsed = _parse_yaml_text(decoded, yaml_module, path)
        mapping = self._ensure_mapping(parsed, path=path)
        _refuse_non_string_keys(mapping, path=path)
        _refuse_ordered_map_tags(mapping, path=path)
        _refuse_values_json_cannot_carry(mapping, path=path)
        _refuse_integers_json_cannot_carry(mapping, path=path, file_format=FileFormat.YAML)
        _refuse_nesting_json_cannot_write(mapping, path=path, file_format=FileFormat.YAML)
        _refuse_repeated_keys(_yaml_repeated_keys(decoded, yaml_module), path=path, file_format=FileFormat.YAML)
        _log_file_loaded(path, FileFormat.YAML)
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

    outcome = _run_parser(lambda: module.safe_load(document), (module.YAMLError, ValueError, RecursionError), _describe)
    if outcome.failure is not None:
        raise _log_and_build_invalid_format(path, FileFormat.YAML, outcome.failure)
    return {} if outcome.value is None else outcome.value


def _refuse_repeated_keys(positions: list[str], *, path: str, file_format: FileFormat) -> None:
    """Refuse a file that repeats a key within one table, naming every repeat's position.

    JSON and YAML parsers keep the last value of a repeated key without a word, so a copy-pasted
    block silently replaces the setting above it; TOML refuses the same file as invalid. The
    message names positions only, never a value, which may be a secret.

    Examples:
        >>> _refuse_repeated_keys([], path="demo.json", file_format=FileFormat.JSON)
        >>> _refuse_repeated_keys(["db.host"], path="demo.json", file_format=FileFormat.JSON)  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: demo.json repeats a key, ...: db.host
    """
    if not positions:
        return
    message = f"{path} repeats a key, and only its last value would load: {'; '.join(positions)}"
    _log_file_invalid(path, file_format, message)
    raise InvalidFormatError(message)


def _yaml_repeated_keys(document: str, module: YAMLModule) -> list[str]:
    """Return ``"<position> (line L, column C)"`` for every key *document* repeats in one mapping.

    ``safe_load`` keeps only the last of two equal keys, so the check reads the composed node
    graph, where both are still there. Two keys are equal when their resolved tag and text are, so
    ``a`` and ``"a"`` are one key. A merge key (``<<``) is not a setting and may appear more than once
    in a mapping, so it is skipped as a key; its value is still checked. Every node is visited once: an alias is
    the same node as its anchor, and a document may alias a node into itself.

    Examples:
        >>> module = _load_yaml_module()
        >>> module is None or _yaml_repeated_keys("a: 1\\nb: {c: 1, c: 2}\\n", module) == ["b.c (line 2, column 11)"]
        True
    """
    root = compose_document(module, document)
    found: list[tuple[int, int, str]] = []
    visited: set[int] = set()
    pending: list[tuple[YAMLNode, str]] = [] if root is None else [(root, "")]
    while pending:
        node, position = pending.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        if node.id == "mapping":
            found.extend(_repeats_in_mapping(node, position, pending))
        elif node.id == "sequence":
            items = cast("list[YAMLNode]", node.value)
            pending.extend((item, _join_position(position, str(index))) for index, item in enumerate(items))
    return [f"{where} (line {line + 1}, column {column + 1})" for line, column, where in sorted(found)]


def _repeats_in_mapping(
    node: YAMLNode, position: str, pending: list[tuple[YAMLNode, str]]
) -> list[tuple[int, int, str]]:
    """Return ``(line, column, position)`` of each repeated key in one mapping node; queue its values."""
    repeats: list[tuple[int, int, str]] = []
    seen: set[tuple[str, str]] = set()
    for key_node, value_node in cast("list[tuple[YAMLNode, YAMLNode]]", node.value):
        if key_node.tag == _YAML_MERGE_TAG or key_node.id != "scalar":
            # A non-scalar key is refused afterwards, as a key that is not a string.
            pending.append((value_node, position))
            continue
        key = (key_node.tag, cast("str", key_node.value))
        child = _join_position(position, key[1])
        if key in seen:
            repeats.append((key_node.start_mark.line, key_node.start_mark.column, child))
        seen.add(key)
        pending.append((value_node, child))
    return repeats


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
    _log_file_invalid(path, FileFormat.YAML, message)
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
    _log_file_invalid(path, FileFormat.YAML, message)
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
    _log_file_invalid(path, FileFormat.YAML, message)
    raise InvalidFormatError(message)


def _unserialisable_positions(data: object) -> list[str]:
    """Describe every ``set`` or ``bytes`` value in *data* as ``"<position> (<type>)"``.

    Examples:
        >>> _unserialisable_positions({"a": [{"b": {1}}], "c": b"x", "d": [1]})
        ['a.0.b (set)', 'c (bytes)']
    """
    return _positions_of(data, lambda node: type(node).__name__ if type(node) in _TAG_OF_UNSERIALISABLE else None)


def _refuse_integers_json_cannot_carry(data: object, *, path: str, file_format: FileFormat) -> None:
    """Refuse a document holding an integer outside ``-2**63 .. 2**64-1``.

    orjson writes no integer outside that range, and rtoml reads up to 128 bits while PyYAML reads
    a hex literal of any width: such a config loaded, then crashed every JSON view with an uncaught
    ``TypeError``. The error names the file and each integer's dotted position with its width, never
    its digits, which may be a secret and may run to thousands of characters.

    Args:
        data: Parsed document, already known to be a mapping at the top.
        path: File the document came from, named in the error.
        file_format: Format logged with the refusal (TOML or YAML).

    Raises:
        InvalidFormatError: When any integer in *data* is outside the range.

    Examples:
        >>> _refuse_integers_json_cannot_carry({"port": 2**64 - 1}, path="a.toml", file_format=FileFormat.TOML)
        >>> toml = FileFormat.TOML
        >>> _refuse_integers_json_cannot_carry({"port": 2**64}, path="a.toml", file_format=toml)  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: a.toml holds an integer JSON ...: port (int, 65 bits)
    """
    found = _positions_of(data, _describe_wide_int)
    if not found:
        return
    message = (
        f"{path} holds an integer JSON cannot write (it takes -2**63 to 2**64-1); "
        f"write it as a string instead: {'; '.join(found)}"
    )
    _log_file_invalid(path, file_format, message)
    raise InvalidFormatError(message)


def _refuse_nesting_json_cannot_write(data: Mapping[str, object], *, path: str, file_format: FileFormat) -> None:
    """Refuse a document nesting deeper than JSON output can write.

    orjson writes at most 254 levels and ``read_config_json`` wraps the config in one more, so a
    config may nest :data:`CONFIG_MAX_DEPTH` levels counted from its top-level table. A deeper
    document loaded, then crashed every JSON view with ``TypeError: Recursion limit reached``.

    Args:
        data: Parsed document, already known to be a mapping at the top.
        path: File the document came from, named in the error.
        file_format: Format logged with the refusal (TOML, JSON or YAML).

    Raises:
        InvalidFormatError: When *data* nests past :data:`CONFIG_MAX_DEPTH`.

    Examples:
        >>> def nested(depth):
        ...     value = 1
        ...     for _ in range(depth):
        ...         value = [value]
        ...     return value
        >>> _refuse_nesting_json_cannot_write({"deep": nested(252)}, path="a.json", file_format=FileFormat.JSON)
        >>> _refuse_nesting_json_cannot_write({"deep": nested(253)}, path="a.json", file_format=FileFormat.JSON)
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormatError: a.json nests deep 254 levels deep; JSON ... 253, ...
    """
    position = _first_position_past_the_json_depth(data)
    if position is None:
        return
    message = (
        f"{path} nests {position} {nesting_depth(data)} levels deep; JSON output takes "
        f"{CONFIG_MAX_DEPTH}, counted from the top-level table: flatten it, or write it as a string"
    )
    _log_file_invalid(path, file_format, message)
    raise InvalidFormatError(message)


def _first_position_past_the_json_depth(data: Mapping[str, object]) -> str | None:
    """Return the key position under which *data* first nests past :data:`CONFIG_MAX_DEPTH`.

    The position names mapping keys only, down to the first list: an index path through a list
    nested 250 levels deep would make the message the size of the document. Walks with an explicit
    stack for the reason :func:`_non_string_keys` gives.

    Examples:
        >>> deep = [1]
        >>> for _ in range(CONFIG_MAX_DEPTH):
        ...     deep = [deep]
        >>> _first_position_past_the_json_depth({"a": {"b": [{"c": deep}]}, "d": 1})
        'a.b'
        >>> _first_position_past_the_json_depth({"a": [[1]]}) is None
        True
    """
    pending: list[tuple[object, str, int, bool]] = [(data, "", 1, False)]
    while pending:
        node, position, depth, in_list = pending.pop()
        if depth > CONFIG_MAX_DEPTH:
            return position or "<top>"
        if isinstance(node, Mapping):
            mapping = cast("Mapping[object, object]", node)
            pending.extend(
                (value, position if in_list else _join_position(position, str(key)), depth + 1, in_list)
                for key, value in mapping.items()
                if _is_container(value)
            )
        elif isinstance(node, list):
            items = cast("list[object]", node)
            pending.extend((item, position, depth + 1, True) for item in items if _is_container(item))
    return None


def _is_container(node: object) -> bool:
    """Return whether *node* adds a nesting level (a mapping or a list).

    A plain ``bool``, not a ``TypeGuard``: narrowing to ``Mapping`` would type the walk's items
    as ``Mapping[Unknown, Unknown]``.

    Examples:
        >>> _is_container({}), _is_container([]), _is_container("[]")
        (True, True, False)
    """
    return isinstance(node, (Mapping, list))


def _describe_wide_int(node: object) -> str | None:
    """Return ``"int, N bits"`` for an integer outside JSON's range, else ``None``.

    Examples:
        >>> _describe_wide_int(2**64), _describe_wide_int(-(2**63)), _describe_wide_int(True)
        ('int, 65 bits', None, None)
    """
    if type(node) is not int or JSON_INT_MIN <= node <= JSON_INT_MAX:
        return None
    return f"int, {node.bit_length()} bits"


def _positions_of(data: object, describe: Callable[[object], str | None]) -> list[str]:
    """Return ``"<position> (<description>)"`` for every node *describe* names, sorted.

    Walks with an explicit stack for the reason :func:`_non_string_keys` gives.

    Examples:
        >>> _positions_of({"a": [1, "x"], "b": "y"}, lambda node: "str" if isinstance(node, str) else None)
        ['a.1 (str)', 'b (str)']
    """
    found: list[str] = []
    pending: list[tuple[object, str]] = [(data, "")]
    while pending:
        node, position = pending.pop()
        description = describe(node)
        if description is not None:
            found.append(f"{position or '<top>'} ({description})")
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
