"""An unquoted ``null``/``none`` from the environment or ``.env``, still to be judged.

A sensitive key keeps ``null``/``none`` as text, so a secret is never cleared to None by accident.
Environment and ``.env`` key names arrive in lowercase, and a lowercase name can hide the word
boundary the sensitivity rule needs: ``dbpassword`` looks harmless where the file spells
``dbPassword``. So the loader hands such a value on as a :class:`NullLiteral`, and the merge, once
it has matched the key to the spelling a lower layer stored, settles it with
:func:`settle_null_literal`.

Contents:
    - ``NullLiteral``: the written text of a ``null``/``none`` whose key the loader could not judge.
    - ``settle_null_literal``: the text for a sensitive key at a path, None for any other key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .redaction import is_sensitive_at

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["NullLiteral", "settle_null_literal"]


@dataclass(frozen=True, slots=True)
class NullLiteral:
    """An unquoted ``null`` or ``none`` as it was written, waiting for its key's final spelling.

    Attributes:
        text: The value as written (``null``, ``None``, ``NULL``), kept for a sensitive key.
    """

    text: str


def settle_null_literal(value: object, path: Sequence[str]) -> object:
    """Return *value*, or for a :class:`NullLiteral` its text when the key at *path* is sensitive, else None.

    Args:
        value: A merged value; anything but a :class:`NullLiteral` comes back unchanged.
        path: The key's segments from the root, in the spelling the merge stores, its own name last.

    Returns:
        The value to store.

    Examples:
        >>> settle_null_literal(NullLiteral("null"), ("a", "dbPassword"))
        'null'
        >>> settle_null_literal(NullLiteral("null"), ("a", "dbpassword")) is None
        True
        >>> settle_null_literal(5, ("a", "dbPassword"))
        5
    """
    if not isinstance(value, NullLiteral):
        return value
    return value.text if is_sensitive_at(tuple(path)) else None
