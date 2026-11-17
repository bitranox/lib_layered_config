"""Domain error taxonomy shared across layers.

Codifies the error classes referenced throughout ``docs/systemdesign`` so the
application and adapter layers can communicate failures without depending on
concrete implementations.

Contents:
    - ``ConfigError``: base class for every library-specific exception.
    - ``InvalidFormatError``: raised when structured configuration cannot be parsed.
    - ``ValidationError``: an identifier, platform or deploy argument was refused.
    - ``DeployDestinationError``: a deploy destination is a symbolic link, not a regular file, or cannot be created.
    - ``GenerateDestinationError``: an example path generation would write is a link, not a file, or cannot be created.
    - ``NotFoundError``: indicates optional configuration sources were absent.
    - ``HomeDirectoryUnknownError``: the home directory the user layer lives under cannot be determined.

System Role:
    Adapters raise these exceptions; the composition root and CLI translate them
    into operator-facing messages without leaking implementation details.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "DeployDestinationError",
    "GenerateDestinationError",
    "HomeDirectoryUnknownError",
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

    A Windows root (ProgramData, APPDATA, LOCALAPPDATA), an empty or relative home directory (``HOME`` on
    Linux and macOS, ``USERPROFILE`` on Windows), or an empty or relative ``LIB_LAYERED_CONFIG_ETC``,
    ``LIB_LAYERED_CONFIG_MAC_APP_ROOT`` or ``LIB_LAYERED_CONFIG_MAC_HOME_ROOT``.

    Its own type because a deploy's permission read treats exactly this case as an absent layer:
    no file can sit under a root that has no absolute path on this machine, so there are no modes
    to read from it. Every write keeps the refusal. A :class:`ValidationError`, so existing
    ``except ValidationError`` / ``except ValueError`` handlers still catch it.
    """


class DeployDestinationError(ValidationError):
    """Raised when a file deploy would write is a link (dangling or not), not a regular file, or cannot be created.

    Deploy neither writes through a link (which would change the file it points at) nor replaces
    it, and it writes only regular files (reading a FIFO there would block). A destination that does
    not exist yet cannot be created when its nearest existing ancestor is not a directory (a regular
    file, FIFO or dangling link where the layer or ``.d`` directory belongs): ``<path> cannot be
    created: <ancestor> is not a directory``; nor when no ancestor exists at all (a Windows drive or
    share that is not there): ``<path> cannot be created: no directory above it exists``. Every such
    destination is refused, one line each, before anything is written. A :class:`ValidationError`, so
    ``except ValidationError`` still catches every deploy refusal.
    """


class GenerateDestinationError(ValidationError):
    """Raised when an example path generation would write is a symbolic link, not a regular file, or cannot be created.

    With ``force`` every such path is refused, one line each, before anything is written: writing
    through a link changes the file it points at, a FIFO would block the write, and a directory,
    device or socket cannot be an example. Without ``force`` an existing path is kept, so only a link
    that resolves to nothing, which a plain create would write through, is refused. In both modes a
    missing example path is refused when it cannot be created, with the same wording as
    :class:`DeployDestinationError`: a regular file, FIFO or dangling link where the destination or an
    example's directory belongs, or no directory above it at all. A :class:`ValidationError`, so
    ``except ValidationError`` still catches it.
    """


class NotFoundError(ConfigError):
    """Indicates an optional configuration source was not discovered.

    Used when files, directory entries, or environment variable namespaces are
    genuinely missing; callers generally treat this as informational rather than
    fatal.
    """


class HomeDirectoryUnknownError(ConfigError, RuntimeError):
    """The home directory the user layer lives under cannot be determined.

    Also a ``RuntimeError``, as ``Path.home()`` raises, so an existing ``except RuntimeError`` still
    catches it. Its own type because a read skips the user layer on exactly this error and on no other
    RuntimeError: ``Path.resolve()`` raises one for a symlink loop below Python 3.13.
    """
