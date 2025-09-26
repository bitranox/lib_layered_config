"""Domain-level exception hierarchy.

Purpose
-------
Expose the stable error taxonomy shared by adapters, the composition root, and
consuming applications. The hierarchy lives in the domain layer to respect the
Clean Architecture dependency rule (outer layers may depend on inner layers, not
vice versa).

Contents
--------
* :class:`ConfigError` – umbrella base class for all configuration-related
  issues.
* :class:`InvalidFormat` – parsing problems while reading files or env sources.
* :class:`ValidationError` – reserved for semantic validation failures.
* :class:`NotFound` – raised when an expected configuration resource is missing.

System Role
-----------
Adapters raise these exceptions to signal recoverable errors (e.g., missing
files) while the composition root wraps unexpected failures in
:class:`LayerLoadError`. Callers catch :class:`ConfigError` to handle all library
failures uniformly.
"""

from __future__ import annotations


class ConfigError(Exception):
    """Base type for all exceptions emitted by ``lib_layered_config``.

    Why
    ----
    Provide a single catch-all type for consumers that do not need fine-grained
    handling.

    What
    ----
    Subclasses :class:`Exception` without modification so it can be used in
    ``except ConfigError`` blocks.
    """


class InvalidFormat(ConfigError):
    """Raised when an input artifact cannot be parsed into structured data.

    Why
    ----
    Distinguish between missing files and malformed content.

    Typical Sources
    ---------------
    Structured file loaders (:mod:`tomllib`, :mod:`json`, :mod:`yaml`) and dotenv
    parsing helpers.
    """


class ValidationError(ConfigError):
    """Signifies that a syntactically valid configuration failed semantic checks.

    Why
    ----
    Reserve a bucket for future schema validation without breaking the error
    hierarchy.

    Current Usage
    -------------
    Not actively raised yet; maintained for roadmap compatibility.
    """


class NotFound(ConfigError):
    """Represents missing-but-optional resources (files, directories, etc.).

    Why
    ----
    Allow adapters to signal absence without aborting the entire configuration
    load. The composition root treats this as a non-fatal condition.
    """
