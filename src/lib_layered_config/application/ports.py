"""Runtime-checkable protocols stating the adapter contracts.

Each protocol states what one kind of adapter provides. The read and deploy functions build the
concrete adapters directly (``DefaultPathResolver``, ``DefaultDotEnvLoader``, ``DefaultEnvLoader``
and the TOML, JSON and YAML file loaders) and are typed with them, not with these protocols; the
contract tests (``tests/adapters/test_port_contracts.py``) check with ``isinstance`` that each
adapter satisfies its protocol.

Contents:
    - ``OutputFormat``: enum for CLI/adapter output format selection.
    - ``DotEnvLoad``: what a dotenv load found: the parsed data and the file it came from.
    - Type aliases (``ConfigData``, ``ProvenanceData``) for consistent signatures.
    - Protocols for each adapter type (path resolver, file loader, dotenv loader,
      environment loader), each checked by the contract tests.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..domain.config import SourceInfo

if TYPE_CHECKING:
    from pathlib import Path


class OutputFormat(str, Enum):
    """Output format options for CLI commands and display adapters.

    Provides type-safe selection between human-readable and machine-readable output.
    Placed in the application layer so both CLI and adapters can import it.
    """

    HUMAN = "human"
    JSON = "json"


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

    def app(self) -> Iterable[Path]:
        """Return paths for application-level configuration."""
        ...  # pragma: no cover - protocol

    def host(self) -> Iterable[Path]:
        """Return paths for host-specific configuration."""
        ...  # pragma: no cover - protocol

    def user(self) -> Iterable[Path]:
        """Return paths for user-level configuration."""
        ...  # pragma: no cover - protocol

    def dotenv(self) -> Iterable[Path]:
        """Return candidate paths for `.env` file discovery."""
        ...  # pragma: no cover - protocol


@runtime_checkable
class FileLoader(Protocol):
    """Parse a structured configuration file into a mapping."""

    def load(self, path: Path) -> ConfigData:
        """Load and parse the file at *path* into a configuration mapping."""
        ...  # pragma: no cover - protocol


@dataclass(frozen=True)
class DotEnvLoad:
    """What one dotenv load found.

    Attributes:
        data: The parsed file as a nested mapping; empty when no file was loaded.
        path: The file the data came from, or ``None`` when no file was loaded.
    """

    data: ConfigData
    path: Path | None


@runtime_checkable
class DotEnvLoader(Protocol):
    """Convert `.env` files into nested mappings respecting prefix semantics."""

    def load(self, start_dir: Path | None = None, *, dotenv_path: Path | None = None) -> DotEnvLoad:
        """Load *dotenv_path* when given, else discover and parse a `.env` file upward from *start_dir*.

        The result names the file it read, so no loader state outlives the call: a load that
        raises reports nothing. A ``null``/``none`` value is delivered as for :meth:`EnvLoader.load`.
        """
        ...  # pragma: no cover - protocol


@runtime_checkable
class EnvLoader(Protocol):
    """Translate prefixed environment variables into nested mappings."""

    def load(self, prefix: str) -> ConfigData:
        """Load environment variables matching *prefix* into a nested mapping.

        A ``null``/``none`` whose key the lowercase name cannot judge arrives as a
        :class:`~lib_layered_config.domain.null_literal.NullLiteral`, which ``merge_layers`` settles.
        """
        ...  # pragma: no cover - protocol


__all__ = [
    "ConfigData",
    "DotEnvLoad",
    "DotEnvLoader",
    "EnvLoader",
    "FileLoader",
    "OutputFormat",
    "PathResolver",
    "ProvenanceData",
]
