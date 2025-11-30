"""Runtime-checkable protocols defining adapter contracts.

Purpose
-------
Ensure the composition root depends on abstractions instead of concrete
implementations, mirroring the Clean Architecture layering in the system design.

Contents
--------
- ``SourceInfoPayload``: type alias for domain ``SourceInfo`` TypedDict.
- Type aliases (``ConfigData``, ``ProvenanceData``) for consistent signatures.
- Protocols for each adapter type (path resolver, file loader, dotenv loader,
  environment loader) plus the merge interface consumed by tests and tooling.

System Role
-----------
Adapters must implement these protocols; tests (`tests/adapters/test_port_contracts.py`)
use ``isinstance`` checks to enforce compliance at runtime.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol, Tuple, runtime_checkable

from ..domain.config import SourceInfo

# Re-export domain SourceInfo as SourceInfoPayload for adapter contracts
SourceInfoPayload = SourceInfo
"""Alias for :class:`~lib_layered_config.domain.config.SourceInfo`.

Why
----
Provides a stable name for the provenance payload used across adapter and
application boundaries without duplicating the TypedDict definition.
"""

# Type aliases for clarity in function signatures
ConfigData = Mapping[str, object]
"""Type alias for merged configuration data."""

ProvenanceData = Mapping[str, SourceInfoPayload]
"""Type alias for provenance metadata keyed by dotted path."""


@runtime_checkable
class PathResolver(Protocol):
    """Provide ordered path iterables for each configuration layer.

    Methods mirror the precedence hierarchy documented in
    ``docs/systemdesign/concept.md``.
    """

    def app(self) -> Iterable[str]: ...  # pragma: no cover - protocol

    def host(self) -> Iterable[str]: ...  # pragma: no cover - protocol

    def user(self) -> Iterable[str]: ...  # pragma: no cover - protocol

    def dotenv(self) -> Iterable[str]: ...  # pragma: no cover - protocol


@runtime_checkable
class FileLoader(Protocol):
    """Parse a structured configuration file into a mapping."""

    def load(self, path: str) -> ConfigData: ...  # pragma: no cover - protocol


@runtime_checkable
class DotEnvLoader(Protocol):
    """Convert `.env` files into nested mappings respecting prefix semantics."""

    def load(self, start_dir: str | None = None) -> ConfigData: ...  # pragma: no cover - protocol

    @property
    def last_loaded_path(self) -> str | None:  # pragma: no cover - attribute contract
        ...


@runtime_checkable
class EnvLoader(Protocol):
    """Translate prefixed environment variables into nested mappings."""

    def load(self, prefix: str) -> ConfigData: ...  # pragma: no cover - protocol


@runtime_checkable
class Merger(Protocol):
    """Combine ordered layers into merged data and provenance structures."""

    def merge(
        self, layers: Iterable[Tuple[str, ConfigData, str | None]]
    ) -> Tuple[ConfigData, ProvenanceData]: ...  # pragma: no cover - protocol


__all__ = [
    "SourceInfoPayload",
    "ConfigData",
    "ProvenanceData",
    "PathResolver",
    "FileLoader",
    "DotEnvLoader",
    "EnvLoader",
    "Merger",
]
