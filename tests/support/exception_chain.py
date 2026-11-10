"""Walk an exception's ``__cause__`` and ``__context__`` links for assertions.

A refusal that keeps the operating system's error lets a caller tell "permission denied" from
"malformed file", and a refusal that must not echo a file's content has to be clean in every link.
Both questions need EVERY reachable exception: a raise site that sets ``__cause__`` (``raise ...
from exc``) can still leave a different exception in ``__context__``, so a walk following only
``__cause__ or __context__`` skips whichever link the raise site did not choose.
"""

from __future__ import annotations

__all__ = ["carries", "chain"]


def chain(exc: BaseException) -> list[BaseException]:
    """Return *exc* and every exception reachable from it over ``__cause__`` and ``__context__``.

    Breadth-first, each exception once (by identity), *exc* first.

    Args:
        exc: The exception a test caught.

    Returns:
        The reachable exceptions, nearest first.

    Examples:
        >>> try:
        ...     try:
        ...         raise KeyError("inner")
        ...     except KeyError:
        ...         raise ValueError("outer") from OSError("cause")
        ... except ValueError as caught:
        ...     [type(link).__name__ for link in chain(caught)]
        ['ValueError', 'OSError', 'KeyError']
    """
    seen: list[BaseException] = []
    queue: list[BaseException] = [exc]
    while queue:
        current = queue.pop(0)
        if any(current is known for known in seen):
            continue
        seen.append(current)
        queue.extend(link for link in (current.__cause__, current.__context__) if link is not None)
    return seen


def carries(exc: BaseException, kind: type[BaseException]) -> bool:
    """Return whether an instance of *kind* is reachable from *exc* (see :func:`chain`).

    Args:
        exc: The exception a test caught.
        kind: The exception type to look for, such as ``PermissionError``.

    Returns:
        ``True`` when *exc* or any linked exception is an instance of *kind*.

    Examples:
        >>> carries(ValueError("x"), ValueError), carries(ValueError("x"), OSError)
        (True, False)
    """
    return any(isinstance(link, kind) for link in chain(exc))
