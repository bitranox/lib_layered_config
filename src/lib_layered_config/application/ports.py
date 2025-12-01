"""Runtime-checkable protocols defining adapter contracts.

Ensure the composition root depends on abstractions instead of concrete
implementations, mirroring the Clean Architecture layering in the system design.

Contents:
    - ``SourceInfoPayload``: type alias for domain ``SourceInfo`` TypedDict.
    - Type aliases (``ConfigData``, ``ProvenanceData``) for consistent signatures.
    - Protocols for each adapter type (path resolver, file loader, dotenv loader,
      environment loader) plus the merge interface consumed by tests and tooling.

System Role:
    Adapters must implement these protocols; tests (`tests/adapters/test_port_contracts.py`)
    use ``isinstance`` checks to enforce compliance at runtime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, runtime_checkable

from ..domain.config import SourceInfo

# Re-export domain SourceInfo as SourceInfoPayload for adapter contracts
SourceInfoPayload = SourceInfo
"""Alias for :class:`~lib_layered_config.domain.config.SourceInfo`.

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

    def app(self) -> Iterable[str]:
        """Return paths for application-level configuration."""
        ...  # pragma: no cover - protocol

    def host(self) -> Iterable[str]:
        """Return paths for host-specific configuration."""
        ...  # pragma: no cover - protocol

    def user(self) -> Iterable[str]:
        """Return paths for user-level configuration."""
        ...  # pragma: no cover - protocol

    def dotenv(self) -> Iterable[str]:
        """Return candidate paths for `.env` file discovery."""
        ...  # pragma: no cover - protocol


@runtime_checkable
class FileLoader(Protocol):
    """Parse a structured configuration file into a mapping."""

    def load(self, path: str) -> ConfigData:
        """Load and parse the file at *path* into a configuration mapping."""
        ...  # pragma: no cover - protocol


@runtime_checkable
class DotEnvLoader(Protocol):
    """Convert `.env` files into nested mappings respecting prefix semantics."""

    def load(self, start_dir: str | None = None) -> ConfigData:
        """Discover and parse a `.env` file starting from *start_dir*."""
        ...  # pragma: no cover - protocol

    @property
    def last_loaded_path(self) -> str | None:
        """Return the path of the most recently loaded `.env` file."""
        ...  # pragma: no cover - attribute contract


@runtime_checkable
class EnvLoader(Protocol):
    """Translate prefixed environment variables into nested mappings."""

    def load(self, prefix: str) -> ConfigData:
        """Load environment variables matching *prefix* into a nested mapping."""
        ...  # pragma: no cover - protocol


@runtime_checkable
class Merger(Protocol):
    """Combine ordered layers into merged data and provenance structures."""

    def merge(self, layers: Iterable[tuple[str, ConfigData, str | None]]) -> tuple[ConfigData, ProvenanceData]:
        """Merge *layers* into unified configuration data with provenance."""
        ...  # pragma: no cover - protocol


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
