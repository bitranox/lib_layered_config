"""Print the library's warnings on stderr while a CLI command runs.

The ``lib_layered_config`` logger carries only a ``NullHandler``, the right default for a library: an
application decides where its logs go. A CLI user has no logging set up, so without this module a
warning the docs promise (a ``.env`` another user owns passed over, an ignored ``app_*`` setting in a
user file) never reaches anyone. stderr keeps stdout, and with it a ``--json`` envelope, unchanged.

Every warning's fields are key names, paths, types and owners, never configuration values, so a line
cannot print a secret.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ..domain.printable import escape_controls
from .output import emit_text

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["attach_stderr_warnings", "format_warning"]

_LOGGER_NAME = "lib_layered_config"
#: Correlates log entries inside one process; it means nothing to a person reading a terminal.
_HIDDEN_FIELDS = frozenset({"trace_id"})


def format_warning(record: logging.LogRecord) -> str:
    """Render one warning as ``warning: <event> key=value ...``.

    Fields holding ``None`` are left out, as is the trace identifier. A control character in a value
    is written as ``\\uXXXX``, so the warning stays one line.

    Examples:
        >>> record = logging.LogRecord("lib_layered_config", logging.WARNING, "x", 1, "type_conflict", None, None)
        >>> record.context = {"trace_id": None, "key": "a", "layer": "app", "path": None}
        >>> format_warning(record)
        'warning: type_conflict key=a layer=app'
    """
    context: object = getattr(record, "context", None)
    fields = cast("dict[str, object]", context) if isinstance(context, dict) else {}
    shown = [
        f"{name}={escape_controls(str(value))}"
        for name, value in fields.items()
        if name not in _HIDDEN_FIELDS and value is not None
    ]
    return " ".join(["warning:", record.getMessage(), *shown])


class _StderrWarningHandler(logging.Handler):
    """Write each warning record to stderr as one line."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            emit_text(format_warning(record), err=True)
        except Exception:
            self.handleError(record)


def attach_stderr_warnings() -> Callable[[], None]:
    """Attach the stderr handler to the package logger and return the call that removes it.

    The caller removes it when the command ends, so a later library call in the same process (a test
    suite, an application that also ran a CLI command) stays silent again.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    handler = _StderrWarningHandler(level=logging.WARNING)
    logger.addHandler(handler)

    def detach() -> None:
        logger.removeHandler(handler)

    return detach
