"""Domain error taxonomy shared across layers.

Codifies the error classes referenced throughout ``docs/systemdesign`` so the
application and adapter layers can communicate failures without depending on
concrete implementations.

Contents:
    - ``ConfigError``: base class for every library-specific exception.
    - ``InvalidFormatError``: raised when structured configuration cannot be parsed.
    - ``ValidationError``: an identifier, platform or deploy argument was refused.
    - ``DeployDestinationError``: a deploy destination is a symbolic link or not a regular file.
    - ``GenerateDestinationError``: an example path generation would write through is a link or not a file.
    - ``NotFoundError``: indicates optional configuration sources were absent.

System Role:
    Adapters raise these exceptions; the composition root and CLI translate them
    into operator-facing messages without leaking implementation details.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "DeployDestinationError",
    "GenerateDestinationError",
    "InvalidFormatError",
    "LayerRootNotAbsoluteError",
    "NotFoundError",
    "ValidationError",
]


class ConfigError(Exception):
    """Base class for all configuration-related errors in the library.

    Centralises exception handling so callers can catch a single type when
    operating at library boundaries.
    """


class InvalidFormatError(ConfigError):
    """Raised when a configuration source cannot be parsed.

    Typical sources include malformed TOML, JSON, YAML, or dotenv files. The
    message should reference the offending path for operator debugging.
    """


class ValidationError(ConfigError, ValueError):
    """Raised when an identifier or platform value fails validation.

    Subclasses both :class:`ConfigError` (so a caller can catch every library error
    with a single ``except ConfigError``) and the stdlib :class:`ValueError` (so the
    long-standing ``except ValueError`` contract documented for the validation helpers
    keeps working). Raising this instead of a bare ``ValueError`` is backward compatible.
    """


class LayerRootNotAbsoluteError(ValidationError):
    """Raised when a layer root is not an absolute path.

    A Windows root (ProgramData, APPDATA, LOCALAPPDATA), or an empty or relative
    ``LIB_LAYERED_CONFIG_ETC``, ``LIB_LAYERED_CONFIG_MAC_APP_ROOT`` or ``LIB_LAYERED_CONFIG_MAC_HOME_ROOT``.

    Its own type because a deploy's permission read treats exactly this case as an absent layer:
    no file can sit under a root that has no absolute path on this machine, so there are no modes
    to read from it. Every write keeps the refusal. A :class:`ValidationError`, so existing
    ``except ValidationError`` / ``except ValueError`` handlers still catch it.
    """


class DeployDestinationError(ValidationError):
    """Raised when a file deploy would write is a symbolic link (dangling or not) or not a regular file.

    Deploy neither writes through a link (which would change the file it points at) nor replaces
    it, and it writes only regular files (reading a FIFO there would block), so every such
    destination is refused, one line each, before anything is written. A
    :class:`ValidationError`, so ``except ValidationError`` still catches every deploy refusal.
    """


class GenerateDestinationError(ValidationError):
    """Raised when an example path generation would write is a symbolic link or not a regular file.

    With ``force`` every such path is refused, one line each, before anything is written: writing
    through a link changes the file it points at, a FIFO would block the write, and a directory,
    device or socket cannot be an example. Without ``force`` an existing path is kept, so only a link
    that resolves to nothing, which a plain create would write through, is refused. A
    :class:`ValidationError`, so ``except ValidationError`` still catches it.
    """


class NotFoundError(ConfigError):
    """Indicates an optional configuration source was not discovered.

    Used when files, directory entries, or environment variable namespaces are
    genuinely missing; callers generally treat this as informational rather than
    fatal.
    """
