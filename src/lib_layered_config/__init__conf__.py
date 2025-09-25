"""Runtime metadata facade kept in sync with the installed distribution.

Purpose
-------
Expose key package metadata (name, version, homepage, author) as simple module
attributes so that CLI commands and documentation can present authoritative
information without parsing project files at runtime.

Contents
--------
* Private helpers (``_meta``, ``_version``, etc.) encapsulate the
  :mod:`importlib.metadata` lookups and their fallbacks.
* Module-level constants mirror the fields enumerated in
  ``docs/systemdesign/module_reference.md`` and stay aligned with
  ``pyproject.toml``.
* :func:`print_info` provides a single place to render the metadata in a human
  readable form for the CLI ``info`` command.

System Role
-----------
Lives in the adapters/platform layer: domain code does not depend on these
details, but transports and tooling reference them to keep messages and release
automation consistent with the published package.
"""

from __future__ import annotations

from importlib import metadata as _im
from typing import Any, Iterable, Protocol, runtime_checkable

# ``pyproject.toml`` defines the package name; we mirror it here so the metadata
# lookups and fallbacks stay in lockstep with the published distribution.
_DIST_NAME = "lib_layered_config"


@runtime_checkable
class _MetaMapping(Protocol):
    """Minimal protocol for package metadata across Python versions.

    On Python < 3.12, `importlib.metadata.metadata()` returns an
    `email.message.Message` which supports `.get(key, default)`.
    On Python >= 3.12, it returns `PackageMetadata`, which also supports `.get`.
    We type to this protocol to keep Pyright happy on 3.10.
    """

    def get(self, __key: str, __default: object = ...) -> object: ...


def _get_str(m: _MetaMapping, key: str, default: str = "") -> str:
    """Return a string metadata value or fall back when the key is absent.

    Why
        Metadata objects behave like mappings but may return non-string values;
        this helper enforces the string contract expected by downstream
        consumers.

    Parameters
    ----------
    m:
        Metadata mapping implementing ``.get``.
    key:
        Field name to fetch (e.g., ``"Author"``).
    default:
        Fallback returned when the key is missing or not a ``str``.

    Returns
    -------
    str
        The resolved string or ``default`` when the value is missing/invalid.

    Examples
    --------
    >>> sample = {"Author": "bitranox", "Author-email": 42}
    >>> _get_str(sample, "Author")
    'bitranox'
    >>> _get_str(sample, "Author-email", "fallback@example.com")
    'fallback@example.com'
    """

    v = m.get(key, default)
    return v if isinstance(v, str) else default


def _meta(dist_name: str = _DIST_NAME) -> Any | None:
    """Load distribution metadata if the package is installed.

    Why
        Running from a working tree (without an editable install) should not
        raise; returning ``None`` lets callers pick sensible fallbacks.

    Parameters
    ----------
    dist_name:
        Distribution name to query; defaults to the project distribution.

    Returns
    -------
    Any | None
        Metadata object when available, otherwise ``None``.

    Examples
    --------
    >>> import importlib.metadata as _md
    >>> original = _md.metadata
    >>> try:
    ...     _md.metadata = lambda _: {"Summary": "Demo"}
    ...     _meta("demo-package")
    ... finally:
    ...     _md.metadata = original
    {'Summary': 'Demo'}
    """

    try:
        return _im.metadata(dist_name)
    except _im.PackageNotFoundError:
        return None


def _version(dist_name: str = _DIST_NAME) -> str:
    """Fetch the installed version or return the development fallback.

    Why
        Version numbers must remain a single source of truth; when the package
        is not installed yet, returning a predictable dev version keeps tooling
        deterministic.

    Parameters
    ----------
    dist_name:
        Distribution name to query.

    Returns
    -------
    str
        The installed version or ``"0.0.0.dev0"`` when missing.

    Examples
    --------
    >>> import importlib.metadata as _md
    >>> original = _md.version
    >>> try:
    ...     _md.version = lambda _: "1.2.3"
    ...     _version("demo-package")
    ... finally:
    ...     _md.version = original
    '1.2.3'
    >>> _version("non-existent-demo") == "0.0.0.dev0"
    True
    """

    try:
        return _im.version(dist_name)
    except _im.PackageNotFoundError:
        return "0.0.0.dev0"


def _home_page(m: Any | None) -> str:
    """Resolve the project homepage URL with sensible fallbacks.

    Why
        Packaging metadata may omit the homepage. Providing a default ensures
        CLI commands and docs always have a stable link.

    Parameters
    ----------
    m:
        Metadata mapping or ``None`` when the package is not installed.

    Returns
    -------
    str
        Homepage URL, defaulting to the GitHub repository when missing.

    Examples
    --------
    >>> _home_page(None)
    'https://github.com/bitranox/lib_layered_config'
    >>> _home_page({"Homepage": "https://example.test"})
    'https://example.test'
    """

    if not m:
        return "https://github.com/bitranox/lib_layered_config"
    # cast to protocol for typing purposes
    mm: _MetaMapping = m  # type: ignore[assignment]
    hp = _get_str(mm, "Home-page") or _get_str(mm, "Homepage")
    return hp or "https://github.com/bitranox/lib_layered_config"


def _author(m: Any | None) -> tuple[str, str]:
    """Return author metadata as a ``(name, email)`` tuple.

    Why
        Several commands print attribution; falling back to project defaults
        keeps the message friendly even before packaging metadata exists.

    Parameters
    ----------
    m:
        Metadata mapping or ``None`` when the package is absent.

    Returns
    -------
    tuple[str, str]
        Author name and email, empty strings when not provided.

    Examples
    --------
    >>> _author(None)
    ('bitranox', 'bitranox@gmail.com')
    >>> _author({"Author": "Alice", "Author-email": "alice@example"})
    ('Alice', 'alice@example')
    """

    if not m:
        return ("bitranox", "bitranox@gmail.com")
    mm: _MetaMapping = m  # type: ignore[assignment]
    return (_get_str(mm, "Author", ""), _get_str(mm, "Author-email", ""))


def _summary(m: Any | None) -> str:
    """Return the short project description used for titles.

    Why
        The CLI help text pulls from this value; providing a default keeps the
        scaffold informative before packaging metadata is present.

    Parameters
    ----------
    m:
        Metadata mapping or ``None`` when metadata is unavailable.

    Returns
    -------
    str
        Summary string describing the project.

    Examples
    --------
    >>> _summary(None)
    'Rich-powered logging helpers for colorful terminal output'
    >>> _summary({"Summary": "Demo"})
    'Demo'
    """

    if not m:
        return "Rich-powered logging helpers for colorful terminal output"
    mm: _MetaMapping = m  # type: ignore[assignment]
    return _get_str(mm, "Summary", "Rich-powered logging helpers for colorful terminal output")


def _shell_command(entry_points: Iterable[Any] | None = None) -> str:
    """Derive the console-script name registered for the CLI entry point.

    Why
        Documentation should reflect the executable name actually published by
        the distribution—even when users override it via entry-points.

    Parameters
    ----------
    entry_points:
        Iterable of entry point objects with ``.value`` and ``.name`` attributes.
        Defaults to querying :mod:`importlib.metadata`.

    Returns
    -------
    str
        Console script name or the distribution name when not registered.

    Examples
    --------
    >>> class Ep:
    ...     def __init__(self, name, value):
    ...         self.name = name
    ...         self.value = value
    >>> fake_eps = [Ep("bt-cli", "lib_layered_config.cli:main")]
    >>> _shell_command(fake_eps)
    'bt-cli'
    """

    eps = entry_points if entry_points is not None else _im.entry_points(group="console_scripts")
    target = "lib_layered_config.cli:main"
    for ep in list(eps):
        if getattr(ep, "value", None) == target:
            return getattr(ep, "name")
    return _DIST_NAME


# Public values (resolve metadata once)
_m = _meta()
# Exported metadata mirrors the distribution so CLI output stays authoritative.
name = _DIST_NAME
title = _summary(_m)
version = _version()
homepage = _home_page(_m)
author, author_email = _author(_m)
shell_command = _shell_command()


def print_info() -> None:
    """Print the summarised metadata block used by the CLI ``info`` command.

    Why
        Provides a single, auditable rendering function so documentation and
        CLI output always match the system design reference.

    What
        Formats the key metadata fields with aligned labels and writes them to
        ``stdout``.

    Side Effects
        Writes to ``stdout``.

    Examples
    --------
    >>> print_info()  # doctest: +ELLIPSIS
    Info for lib_layered_config:
    ...
    """

    fields = [
        ("name", name),
        ("title", title),
        ("version", version),
        ("homepage", homepage),
        ("author", author),
        ("author_email", author_email),
        ("shell_command", shell_command),
    ]
    pad = max(len(k) for k, _ in fields)
    lines = [f"Info for {name}:", ""]
    lines += [f"    {k.ljust(pad)} = {v}" for k, v in fields]
    print("\n".join(lines))
