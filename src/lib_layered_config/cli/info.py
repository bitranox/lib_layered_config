"""Metadata-related CLI commands."""

from __future__ import annotations

import re

import rich_click as click

from ..core import default_env_prefix
from ..domain.errors import ValidationError
from .common import describe_distribution, package_metadata
from .constants import CLICK_CONTEXT_SETTINGS
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope
from .output import emit_text
from .typed_click import argument

__all__ = [
    "env_prefix_command",
    "info_command",
    "register",
]

#: A name ``export NAME=value`` accepts in a POSIX shell.
_SHELL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@click.command("info", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@json_envelope_option
def info_command(*, json_envelope: bool) -> None:
    """Print package metadata in friendly lines."""
    if json_envelope:
        run_in_envelope("info", _metadata_fields)
        return
    for line in describe_distribution():
        emit_text(line)


def _slug_argument(_ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Refuse a slug ``default_env_prefix`` refuses, as a usage error rather than a crash."""
    try:
        default_env_prefix(value)
    except ValidationError as exc:
        raise click.BadParameter(str(exc), param=param) from exc
    return value


@click.command("env-prefix", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@argument("slug", callback=_slug_argument)
@json_envelope_option
def env_prefix_command(slug: str, *, json_envelope: bool) -> None:
    """Echo the canonical environment variable prefix for a slug."""
    _note_unexportable(default_env_prefix(slug))
    if json_envelope:
        run_in_envelope("env-prefix", lambda: {"slug": slug, "prefix": default_env_prefix(slug)})
        return
    emit_text(default_env_prefix(slug))


def _note_unexportable(prefix: str) -> None:
    """Say on stderr when *prefix* is not a name a POSIX shell can ``export``.

    A dot in the slug stays in the prefix, and so does a leading digit. Such a variable is still read,
    so the prefix is not rewritten, but the reader has to set it some other way than ``export``. The
    remedy names the first character as well: a slug must start with a letter or digit, and only a
    letter gives a name a shell accepts.
    """
    if _SHELL_NAME.fullmatch(prefix):
        return
    emit_text(
        f"note: {prefix} is not a name a POSIX shell can export (a name holds only letters, digits and _ "
        "and does not start with a digit); set such variables with env(1) or a container's or service's "
        "environment, or use a slug that starts with a letter and holds only letters, digits, - and _",
        err=True,
    )


def _metadata_fields() -> dict[str, str]:
    """The package metadata ``info`` prints, as a mapping."""
    return {
        "name": package_metadata.name,
        "title": package_metadata.title,
        "version": package_metadata.version,
        "homepage": package_metadata.homepage,
        "author": package_metadata.author,
        "author_email": package_metadata.author_email,
        "shell_command": package_metadata.shell_command,
    }


def register(cli_group: click.Group) -> None:
    """Register metadata commands with the root CLI group."""
    cli_group.add_command(info_command)
    cli_group.add_command(env_prefix_command)
