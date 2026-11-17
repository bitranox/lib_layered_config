"""Runtime-checkable protocols stating the adapter contracts.

Each protocol states what one kind of adapter provides. The read and deploy functions build the
concrete adapters directly (``DefaultPathResolver``, ``DefaultDotEnvLoader``, ``DefaultEnvLoader``
and the TOML, JSON and YAML file loaders) and are typed with them, not with these protocols; the
contract tests (``tests/adapters/test_port_contracts.py``) check with ``isinstance`` that each
adapter satisfies its protocol.

Contents:
    - ``OutputFormat``: enum for CLI/adapter output format selection.
    - ``SourceInfoPayload``: another name for domain ``SourceInfo``, kept for importers.
    - Type aliases (``ConfigData``, ``ProvenanceData``) for consistent signatures.
    - Protocols for each adapter type (path resolver, file loader, dotenv loader,
      environment loader), each checked by the contract tests.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Protocol, runtime_checkable

from ..domain.config import SourceInfo


class OutputFormat(str, Enum):
    """Output format options for CLI commands and display adapters.

    Provides type-safe selection between human-readable and machine-readable output.
    Placed in the application layer so both CLI and adapters can import it.
    """

    HUMAN = "human"
    JSON = "json"


SourceInfoPayload = SourceInfo
"""Another name for :class:`~lib_layered_config.domain.config.SourceInfo`, kept for code that imports it.

The library itself names ``SourceInfo``; this alias is removed in 9.0.0.
"""

# Type aliases for clarity in function signatures
ConfigData = Mapping[str, object]
"""Type alias for merged configuration data."""

ProvenanceData = Mapping[str, SourceInfo]
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

    def load(self, start_dir: str | None = None, *, dotenv_path: str | None = None) -> ConfigData:
        """Load *dotenv_path* when given, else discover and parse a `.env` file upward from *start_dir*."""
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


__all__ = [
    "ConfigData",
    "DotEnvLoader",
    "EnvLoader",
    "FileLoader",
    "OutputFormat",
    "PathResolver",
    "ProvenanceData",
    "SourceInfoPayload",
]
