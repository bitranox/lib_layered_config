"""Structured configuration file loaders.

Purpose
-------
Convert on-disk artifacts into Python mappings that the merge layer understands.
Adapters are small wrappers around ``tomllib``/``json``/``yaml.safe_load`` so
error handling, observability, and immutability policies live in one place.

Contents
    - ``BaseFileLoader``: shared primitives for reading files and asserting
      mapping outputs.
    - ``TOMLFileLoader`` / ``JSONFileLoader`` / ``YAMLFileLoader``: thin
      adapters that delegate to parser-specific helpers.
    - ``_log_file_read`` / ``_log_file_loaded`` / ``_log_file_invalid``:
      structured logging helpers reused across loaders.
    - ``_ensure_yaml_available``: guard ensuring YAML support is present before
      attempting to parse.

System Role
-----------
Invoked by :func:`lib_layered_config.core._load_files` to parse structured files
before passing the results to the merge policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore[assignment]

from ...domain.errors import InvalidFormat, NotFound
from ...observability import log_debug, log_error

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]


FILE_LAYER = "file"
"""Layer label used in structured logging for file-oriented events."""


def _log_file_read(path: str, size: int) -> None:
    """Record that *path* was read with *size* bytes."""

    log_debug("config_file_read", layer=FILE_LAYER, path=path, size=size)


def _log_file_loaded(path: str, format_name: str) -> None:
    """Record a successful parse for *path* and *format_name*."""

    log_debug("config_file_loaded", layer=FILE_LAYER, path=path, format=format_name)


def _log_file_invalid(path: str, format_name: str, exc: Exception) -> None:
    """Capture parser failures for diagnostics."""

    log_error(
        "config_file_invalid",
        layer=FILE_LAYER,
        path=path,
        format=format_name,
        error=str(exc),
    )


def _raise_invalid_format(path: str, format_name: str, exc: Exception) -> None:
    """Log and raise :class:`InvalidFormat` for parser errors."""

    _log_file_invalid(path, format_name, exc)
    raise InvalidFormat(f"Invalid {format_name.upper()} in {path}: {exc}") from exc


def _ensure_yaml_available() -> None:
    """Raise :class:`NotFound` when optional YAML support is missing."""

    if yaml is None:
        raise NotFound("PyYAML is required for YAML configuration support")


class BaseFileLoader:
    """Common utilities shared by the structured file loaders."""

    def _read(self, path: str) -> bytes:
        """Read *path* as bytes, raising :class:`NotFound` when the file is missing.

        Why
        ----
        Centralise file existence checks and logging so all loaders behave
        consistently.

        Parameters
        ----------
        path:
            Absolute file path expected to exist.

        Returns
        -------
        bytes
            Raw file contents.

        Side Effects
        ------------
        Emits ``config_file_read`` debug events.

        Examples
        --------
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
            raise NotFound(f"Configuration file not found: {path}")
        payload = file_path.read_bytes()
        _log_file_read(path, len(payload))
        return payload

    @staticmethod
    def _ensure_mapping(data: object, *, path: str) -> Mapping[str, object]:
        """Ensure *data* behaves like a mapping, otherwise raise ``InvalidFormat``.

        Why
        ----
        Merging logic expects mapping-like structures; other types indicate a
        malformed configuration file.

        Parameters
        ----------
        data:
            Object produced by the parser.
        path:
            Originating file path used for error messaging.

        Returns
        -------
        Mapping[str, object]
            The validated mapping.

        Examples
        --------
        >>> BaseFileLoader._ensure_mapping({"key": 1}, path="demo")
        {'key': 1}
        >>> BaseFileLoader._ensure_mapping(42, path="demo")
        Traceback (most recent call last):
        ...
        lib_layered_config.domain.errors.InvalidFormat: File demo did not produce a mapping
        """

        if not isinstance(data, Mapping):
            raise InvalidFormat(f"File {path} did not produce a mapping")
        return data  # type: ignore[return-value]


class TOMLFileLoader(BaseFileLoader):
    """Load TOML documents using the standard library parser."""

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from TOML file at *path*.

        Why
        ----
        TOML is the primary structured format in the documentation; this loader
        provides friendly error messages and structured logging.

        Parameters
        ----------
        path:
            Absolute path to a TOML document.

        Returns
        -------
        Mapping[str, object]
            Parsed configuration data.

        Side Effects
        ------------
        Emits ``config_file_loaded`` debug events.

        Examples
        --------
        >>> from tempfile import NamedTemporaryFile
        >>> tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
        >>> _ = tmp.write('key = "value"')
        >>> tmp.close()
        >>> TOMLFileLoader().load(tmp.name)["key"]
        'value'
        >>> Path(tmp.name).unlink()
        """

        try:
            decoded = self._read(path).decode("utf-8")
            data = tomllib.loads(decoded)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:  # type: ignore[attr-defined]
            _raise_invalid_format(path, "toml", exc)
        result = self._ensure_mapping(data, path=path)
        _log_file_loaded(path, "toml")
        return result


class JSONFileLoader(BaseFileLoader):
    """Load JSON documents."""

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from JSON file at *path*.

        Why
        ----
        Provide parity with TOML for teams that prefer JSON configuration.

        Parameters
        ----------
        path:
            Absolute path to a JSON document.

        Examples
        --------
        >>> from tempfile import NamedTemporaryFile
        >>> tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
        >>> _ = tmp.write('{"enabled": true}')
        >>> tmp.close()
        >>> JSONFileLoader().load(tmp.name)["enabled"]
        True
        >>> Path(tmp.name).unlink()
        """

        try:
            data = json.loads(self._read(path))
        except json.JSONDecodeError as exc:
            _raise_invalid_format(path, "json", exc)
        result = self._ensure_mapping(data, path=path)
        _log_file_loaded(path, "json")
        return result


class YAMLFileLoader(BaseFileLoader):
    """Load YAML documents when PyYAML is available."""

    def load(self, path: str) -> Mapping[str, object]:
        """Return mapping extracted from YAML file at *path*.

        Why
        ----
        Some teams rely on YAML for configuration; this loader keeps behaviour
        consistent with TOML/JSON while remaining optional.

        Parameters
        ----------
        path:
            Absolute path to a YAML document.

        Raises
        ------
        NotFound
            When PyYAML is not installed.

        Examples
        --------
        >>> if yaml is not None:  # doctest: +SKIP
        ...     from tempfile import NamedTemporaryFile
        ...     tmp = NamedTemporaryFile('w', delete=False, encoding='utf-8')
        ...     _ = tmp.write('key: 1')
        ...     tmp.close()
        ...     YAMLFileLoader().load(tmp.name)["key"]
        ...     Path(tmp.name).unlink()
        """

        _ensure_yaml_available()
        try:
            parsed = yaml.safe_load(self._read(path))  # type: ignore[operator]
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            _raise_invalid_format(path, "yaml", exc)
        data = {} if parsed is None else parsed
        result = self._ensure_mapping(data, path=path)
        _log_file_loaded(path, "yaml")
        return result
