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

import json
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import rtoml

from ...domain.errors import InvalidFormatError, NotFoundError
from ...observability import log_debug, log_error

yaml: ModuleType | None = None


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


def _log_file_invalid(path: str, format_name: str, exc: Exception) -> None:
    """Capture parser failures for diagnostics.

    Surface parse errors with enough context (path, format, message) for quick
    troubleshooting.

    Args:
        path: File path that failed to parse.
        format_name: Parser identifier.
        exc: Exception raised by the parser.
    """
    log_error(
        "config_file_invalid",
        layer=FILE_LAYER,
        path=path,
        format=format_name,
        error=str(exc),
    )


def _raise_invalid_format(path: str, format_name: str, exc: Exception) -> NoReturn:
    """Log and raise :class:`InvalidFormatError` for parser errors.

    Reuse logging side-effects while presenting callers with a uniform
    exception type.

    Args:
        path: File path being parsed.
        format_name: Parser identifier.
        exc: Original exception raised by the parser.
    """
    _log_file_invalid(path, format_name, exc)
    raise InvalidFormatError(f"Invalid {format_name.upper()} in {path}: {exc}") from exc


def _ensure_yaml_available() -> None:
    """Announce clearly whether PyYAML can be reached.

    YAML support is optional; the loader must fail fast with guidance when the
    dependency is absent so callers can install the expected extra.

    Raises:
        NotFoundError: When the PyYAML package cannot be imported.
    """
    _require_yaml_module()


def _require_yaml_module() -> ModuleType:
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


def _load_yaml_module() -> ModuleType | None:
    """Import PyYAML on demand, caching the result for future readers.

    Avoid importing optional dependencies unless they are genuinely needed,
    while still ensuring subsequent calls reuse the same module object.

    Returns:
        The PyYAML module when available; otherwise ``None``.
    """
    global yaml
    if yaml is not None:
        return yaml
    try:
        yaml = import_module("yaml")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        yaml = None
    return yaml


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
        if not file_path.is_file():
            raise NotFoundError(f"Configuration file not found: {path}")
        payload = file_path.read_bytes()
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
        return data  # type: ignore[return-value]


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
        try:
            raw_bytes = self._read(path)
            decoded = raw_bytes.decode("utf-8")
            parsed = rtoml.loads(decoded)
        except (UnicodeDecodeError, rtoml.TomlParsingError) as exc:
            _raise_invalid_format(path, "toml", exc)
        result = self._ensure_mapping(parsed, path=path)
        _log_file_loaded(path, "toml")
        return result


class JSONFileLoader(BaseFileLoader):
    """Load JSON documents.

    Provide a drop-in parser for JSON configuration files.

    Uses :mod:`json` to parse files and delegates validation/logging to the base class.
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
        try:
            payload: Any = json.loads(self._read(path))
        except json.JSONDecodeError as exc:
            _raise_invalid_format(path, "json", exc)
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
        parsed = _parse_yaml_bytes(raw_bytes, yaml_module, path)
        mapping = self._ensure_mapping(parsed, path=path)
        _log_file_loaded(path, "yaml")
        return mapping


def _parse_yaml_bytes(payload: bytes, module: ModuleType, path: str) -> object:
    """Turn YAML bytes into a Python shape that mirrors the file.

    Normalise the PyYAML parsing contract so callers always receive a mapping,
    raising a domain-specific error when the parser signals invalid syntax.

    Args:
        payload: Raw YAML document supplied as bytes.
        module: PyYAML module providing ::func:`safe_load` and the ``YAMLError`` base class.
        path: Source identifier used to enrich error messages.

    Returns:
        Parsed document; an empty dict when the YAML payload evaluates to ``None``.

    Raises:
        InvalidFormatError: When PyYAML raises ``YAMLError`` while parsing the payload.

    Examples:
        >>> from types import SimpleNamespace
        >>> fake = SimpleNamespace(safe_load=lambda data: {"key": data.decode("utf-8")}, YAMLError=Exception)
        >>> _parse_yaml_bytes(b"value", fake, "memory.yaml")  # doctest: +ELLIPSIS
        {'key': 'value'}
    """
    try:
        document = module.safe_load(payload)
    except module.YAMLError as exc:  # type: ignore[attr-defined]
        _raise_invalid_format(path, "yaml", exc)
    return {} if document is None else document
