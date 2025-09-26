"""Application-layer ports describing adapter responsibilities.

Purpose
-------
Define the structural contracts that adapters must satisfy so the composition
root can orchestrate behaviour without depending on concrete implementations.
The ports mirror the responsibilities documented in
``docs/systemdesign/module_reference.md``.

Contents
--------
* :class:`PathResolver` – yields candidate paths for each configuration layer.
* :class:`FileLoader` – parses structured configuration artifacts.
* :class:`DotEnvLoader` – loads ``.env`` files for layered precedence.
* :class:`EnvLoader` – materialises process environment variables.
* :class:`Merger` – combines layer payloads and produces provenance metadata.

System Role
-----------
These protocols enforce Dependency Inversion (DIP). Each adapter implements one
protocol so the application layer can request behaviour via abstraction.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol, Tuple


class PathResolver(Protocol):
    """Discover configuration artifacts for each logical layer.

    Why
    ----
    Encapsulate OS-specific discovery rules while keeping the composition root
    agnostic of filesystem conventions.

    Methods
    -------
    :meth:`app`
        System-wide defaults (e.g., ``/etc/<slug>/config.toml``).
    :meth:`host`
        Host-specific overrides (``hosts/<hostname>.toml``).
    :meth:`user`
        Per-user configuration (XDG, Application Support, etc.).
    :meth:`dotenv`
        Candidate ``.env`` files discovered via upward search and OS conventions.
    """

    def app(self) -> Iterable[str]:
        """Yield candidate system-wide configuration paths."""

    def host(self) -> Iterable[str]:
        """Yield host-specific overrides."""

    def user(self) -> Iterable[str]:
        """Yield user-level configuration locations."""

    def dotenv(self) -> Iterable[str]:
        """Yield ``.env`` candidates discovered during path resolution."""


class FileLoader(Protocol):
    """Parse a structured configuration file into a mapping.

    Why
    ----
    Segregate parsing concerns (TOML/JSON/YAML) from orchestration logic.
    """

    def load(self, path: str) -> Mapping[str, object]:
        """Read *path* and return a mapping representation or raise ``InvalidFormat``."""


class DotEnvLoader(Protocol):
    """Materialise a ``.env`` file into nested dictionaries.

    Why
    ----
    Provide deterministic precedence for secret and local overrides.
    """

    def load(self, start_dir: str | None = None) -> Mapping[str, object]:
        """Search from *start_dir* upwards (plus extras) and return the first parsed file."""


class EnvLoader(Protocol):
    """Translate process environment variables into nested configuration dictionaries.

    Why
    ----
    Allow environment configuration to join the merge process with predictable
    namespacing.
    """

    def load(self, prefix: str) -> Mapping[str, object]:
        """Return variables that match *prefix* (case-insensitive, ``__`` for nesting)."""


class Merger(Protocol):
    """Combine layers and produce both merged data and provenance metadata.

    Why
    ----
    Make the merge strategy replaceable (e.g., deterministic vs. optimistic)
    without rewriting adapters.
    """

    def merge(
        self, layers: Iterable[tuple[str, Mapping[str, object], str | None]]
    ) -> Tuple[Mapping[str, object], Mapping[str, dict[str, object]]]:
        """Deterministically merge *layers* preserving precedence order."""
