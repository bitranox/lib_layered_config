"""Safe Unix permission modes for deployed configuration.

Contents:
    - ``ModeKind``: whether a mode is meant for a directory or a file.
    - ``DeployMode``: an immutable, validated mode; an unsafe one cannot be constructed.
    - ``DeployModeError``: the refusal, naming the reason or every offending bit.
    - ``parse_mode_text``: the one rule for a textual mode (``"750"``, ``"0o750"``).

System Role:
    Every ``chmod`` on the deploy path takes a ``DeployMode``, so a mode that widens access to a
    file that can hold credentials never reaches the filesystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from .errors import ValidationError

__all__ = ["MAX_MODE", "DeployMode", "DeployModeError", "ModeKind", "brief_repr", "parse_mode_text"]

#: chmod(2) defines only the low 12 bits: setuid, setgid, sticky and rwxrwxrwx.
MAX_MODE: Final[int] = 0o7777

#: An optional lowercase ``0o`` and octal digits, nothing else. ``int(text, 8)`` alone would also
#: accept whitespace, ``_`` separators and a sign. ``fullmatch`` also refuses a trailing newline,
#: which ``$`` would let through.
_TEXT_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:0o)?[0-7]+")
#: 0o7777 has four octal digits. Leading zeros are dropped first, so "0000750" is 0o750, and a
#: longer remainder is refused before ``int()`` sees it, however long the text is.
_MAX_SIGNIFICANT_DIGITS: Final[int] = 4

_SPECIAL_BITS: Final[tuple[tuple[int, str], ...]] = (
    (0o4000, "the setuid bit (0o4000)"),
    (0o2000, "the setgid bit (0o2000)"),
    (0o1000, "the sticky bit (0o1000)"),
)
#: Group write counts like world write: a group can be every local account (``staff`` on macOS).
_GROUP_WRITE: Final[int] = 0o020
_WORLD_WRITE: Final[int] = 0o002
#: A configuration file is never run, so an execute bit on one is the typical sign of a mistyped mode.
_ANY_EXECUTE: Final[int] = 0o111
_OWNER_DIRECTORY: Final[int] = 0o700
_OWNER_FILE: Final[int] = 0o600
#: A safe mode fits in a handful of octal digits; 64 bits (about 20 decimal digits) is generous
#: headroom while staying far below any CPython int-to-str conversion limit, so the decision does
#: not depend on `sys.get_int_max_str_digits` or `PYTHONINTMAXSTRDIGITS` at all.
_MAX_SAFE_BITS: Final[int] = 64


class ModeKind(Enum):
    """Whether a mode applies to the configuration directory or to a configuration file."""

    DIRECTORY = "directory"
    FILE = "file"


class DeployModeError(ValidationError):
    """A permission setting was refused; the message names the reason or every offending bit.

    Raised for an unsafe or malformed mode itself, and also for a caller-built ``LayerModes`` or
    ``DeployPermissions`` whose field does not match its declared type (a non-``DeployMode``
    directory/file, a non-``LayerModes`` layer, or a non-``bool`` ``enabled``), or whose
    ``LayerModes`` swaps a directory mode and a file mode (``LayerModes`` needs a directory mode
    and a file mode, in that order). ``deploy_config`` also raises it for a ``dir_mode`` or
    ``file_mode`` given together with ``set_permissions=False``, since a mode cannot be applied
    while permission setting is off.
    """


def _int_is_safe_to_stringify(value: int) -> bool:
    """Return whether *value* is small enough to format as decimal/octal text.

    This is decided purely from ``bit_length()``, which never converts the value to a string, so
    it cannot raise: a huge int is never handed to ``str()``/``repr()``/``oct()`` to find out.
    Deciding by size also keeps the bound independent of the interpreter's own int-to-str
    conversion limit (`sys.get_int_max_str_digits` / `PYTHONINTMAXSTRDIGITS`, 4300 digits by
    default) - that limit only prevents a crash, not a multi-thousand-character message.
    """
    return value.bit_length() <= _MAX_SAFE_BITS


def brief_repr(value: object, limit: int = 40) -> str:
    """Return ``repr(value)``, shortened to *limit* characters so a hostile value cannot flood a message.

    An ``int`` wider than ``_MAX_SAFE_BITS`` (64 bits) is never passed to ``repr()``: its bit length
    is reported instead. This is not only to dodge the interpreter's int-to-str digit limit - the
    64-bit threshold is far below that limit and rejects plenty of ints ``repr()`` could format
    without raising; it also keeps the message itself short and independent of interpreter settings.

    Examples:
        >>> brief_repr("abc")
        "'abc'"
        >>> len(brief_repr("x" * 500))
        40
        >>> brief_repr(2**64)
        '<int, 65 bits>'
        >>> brief_repr(10**5000)
        '<int, 16610 bits>'
    """
    if isinstance(value, int) and not isinstance(value, bool) and not _int_is_safe_to_stringify(value):
        text = f"<int, {value.bit_length()} bits>"
        return text if len(text) <= limit else f"{text[: limit - 3]}..."
    text = repr(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def parse_mode_text(text: str) -> int:
    """Parse a plain octal literal (``"750"`` or ``"0o750"``) into a mode in 0..0o7777.

    Args:
        text: The candidate literal.

    Returns:
        The parsed mode. Safety is not checked here; construct a :class:`DeployMode` for that.

    Raises:
        DeployModeError: *text* is not a plain octal literal, or lies above 0o7777.

    Examples:
        >>> oct(parse_mode_text("0o750"))
        '0o750'
        >>> try:
        ...     parse_mode_text("-1")
        ... except DeployModeError as exc:
        ...     print(exc)
        '-1' is not a plain octal literal; write it like "0o640" or "640"
    """
    if not _TEXT_PATTERN.fullmatch(text):
        raise DeployModeError(f'{brief_repr(text)} is not a plain octal literal; write it like "0o640" or "640"')
    significant = text.removeprefix("0o").lstrip("0") or "0"
    if len(significant) > _MAX_SIGNIFICANT_DIGITS:
        raise DeployModeError(f"{brief_repr(text)} is outside 0..{oct(MAX_MODE)}")
    return int(significant, 8)


def _unsafe_bits(mode: int, kind: ModeKind) -> list[str]:
    """Return one label per rule *mode* breaks for *kind*; empty when the mode is safe."""
    problems = [label for bit, label in _SPECIAL_BITS if mode & bit]
    if mode & _GROUP_WRITE:
        problems.append("group write (0o020)")
    if mode & _WORLD_WRITE:
        problems.append("world write (0o002)")
    if kind is ModeKind.FILE and mode & _ANY_EXECUTE:
        problems.append(f"an execute bit on a file ({oct(mode & _ANY_EXECUTE)})")
    owner = _OWNER_DIRECTORY if kind is ModeKind.DIRECTORY else _OWNER_FILE
    if mode & owner != owner:
        needed = "rwx" if kind is ModeKind.DIRECTORY else "rw"
        problems.append(f"no owner {needed} ({oct(owner)} is required)")
    return problems


@dataclass(frozen=True, slots=True)
class DeployMode:
    """A permission mode that is safe for configuration that can hold credentials.

    Widening READ access beyond the layer defaults is allowed; a special bit, group or world
    write, an execute bit on a file, or locking the owner out is not.

    Examples:
        >>> str(DeployMode(0o750, ModeKind.DIRECTORY))
        '0o750'
        >>> try:
        ...     DeployMode(0o4750, ModeKind.DIRECTORY)
        ... except DeployModeError as exc:
        ...     print(exc)
        unsafe directory mode 0o4750: the setuid bit (0o4000)
    """

    value: int
    kind: ModeKind

    def __post_init__(self) -> None:
        """Refuse a value that is not an int, is out of range, or breaks a safety rule."""
        # A caller outside the type checker can pass anything, and bool is an int subclass.
        if type(self.value) is not int:
            raise DeployModeError(f"a mode must be an int, got {type(self.value).__name__}")
        if not 0 <= self.value <= MAX_MODE:
            raise DeployModeError(f"mode {brief_repr(self.value)} is outside 0..{oct(MAX_MODE)}")
        problems = _unsafe_bits(self.value, self.kind)
        if problems:
            raise DeployModeError(f"unsafe {self.kind.value} mode {oct(self.value)}: {'; '.join(problems)}")

    @classmethod
    def from_text(cls, text: str, kind: ModeKind) -> DeployMode:
        """Parse *text* with :func:`parse_mode_text` and validate it for *kind*."""
        return cls(parse_mode_text(text), kind)

    @classmethod
    def from_config_value(cls, value: object, kind: ModeKind) -> DeployMode:
        """Validate a mode read from a configuration source.

        Only a string is accepted. A TOML ``user_file = 400``, a runtime override
        ``...=400`` and an environment value ``400`` all arrive as the DECIMAL integer
        400 (0o620), and the TOML literal ``0o640`` arrives as the integer 416; after
        parsing nobody can tell which was meant, so an integer is refused with its
        decimal reading and the form to use instead: quoted in a file, and with the
        ``0o`` prefix in the environment or a runtime override (a shell strips the
        quotes, and ``0o640`` is not a JSON number, so it arrives as the string).

        Raises:
            DeployModeError: *value* is not a string, or the string is refused.
        """
        if isinstance(value, str):
            return cls.from_text(value, kind)
        if isinstance(value, int) and not isinstance(value, bool):
            reading = f"{value} = {oct(value)}" if _int_is_safe_to_stringify(value) else brief_repr(value)
            raise DeployModeError(
                f"a bare integer is read as decimal ({reading}); "
                'write the mode as an octal string: "0o640" (quoted) in a file, 0o640 in the environment '
                "or a runtime override (such as an application's --set)"
            )
        raise DeployModeError(f'expected a quoted octal string such as "0o640", got {type(value).__name__}')

    def __str__(self) -> str:
        """Return the mode as an octal literal, e.g. ``0o750``."""
        return oct(self.value)
