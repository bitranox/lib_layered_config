"""Runtime-checkable protocols defining adapter contracts.

Purpose
-------
Ensure the composition root depends on abstractions instead of concrete
implementations, mirroring the Clean Architecture layering in the system design.

Contents
--------
- ``SourceInfoPayload``: typed dictionary describing provenance for merged keys.
- Protocols for each adapter type (path resolver, file loader, dotenv loader,
  environment loader) plus the merge interface consumed by tests and tooling.

System Role
-----------
Adapters must implement these protocols; tests (`tests/adapters/test_port_contracts.py`)
use ``isinstance`` checks to enforce compliance at runtime.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol, Tuple, TypedDict, runtime_checkable


class SourceInfoPayload(TypedDict):
    """Structured provenance emitted by the merge policy.

    Why
    ----
    Downstream consumers (CLI JSON output, deploy helpers) rely on consistent
    keys when rendering provenance information.

    Fields
    ------
    layer:
        Logical layer name contributing the value.
    path:
        Optional filesystem path associated with the entry.
    key:
        Fully-qualified dotted key.
    """

    layer: str
    path: str | None
    key: str


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

    def load(self, path: str) -> Mapping[str, object]: ...  # pragma: no cover - protocol


@runtime_checkable
class DotEnvLoader(Protocol):
    """Convert `.env` files into nested mappings respecting prefix semantics."""

    def load(self, start_dir: str | None = None) -> Mapping[str, object]: ...  # pragma: no cover - protocol

    @property
    def last_loaded_path(self) -> str | None:  # pragma: no cover - attribute contract
        ...


@runtime_checkable
class EnvLoader(Protocol):
    """Translate prefixed environment variables into nested mappings."""

    def load(self, prefix: str) -> Mapping[str, object]: ...  # pragma: no cover - protocol


@runtime_checkable
class Merger(Protocol):
    """Combine ordered layers into merged data and provenance structures."""

    def merge(
        self, layers: Iterable[Tuple[str, Mapping[str, object], str | None]]
    ) -> Tuple[
        Mapping[str, object],
        Mapping[str, SourceInfoPayload],
    ]: ...  # pragma: no cover - protocol


__all__ = [
    "SourceInfoPayload",
    "PathResolver",
    "FileLoader",
    "DotEnvLoader",
    "EnvLoader",
    "Merger",
]
