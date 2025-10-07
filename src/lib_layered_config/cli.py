"""A compact CLI that reads like instructions rather than code."""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence, cast

import lib_cli_exit_tools
import rich_click as click

from .application.ports import SourceInfoPayload
from .core import default_env_prefix as _default_env_prefix
from .core import read_config, read_config_json, read_config_raw
from .examples import deploy_config as _deploy_config
from .examples import generate_examples as _generate_examples
from .testing import i_should_fail

CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
TRACEBACK_SUMMARY = 500
TRACEBACK_VERBOSE = 10_000
TARGET_CHOICES = ("app", "host", "user")
EXAMPLE_PLATFORM_CHOICES = ("posix", "windows")


def _toggle_traceback(show: bool) -> None:
    """Synchronise ``lib_cli_exit_tools`` traceback flags with *show*.

    Why
    ----
    Keeps CLI command handlers agnostic of configuration details while allowing
    the root command to flip traceback rendering globally.
    """

    lib_cli_exit_tools.config.traceback = show
    lib_cli_exit_tools.config.traceback_force_color = show


def _version_string() -> str:
    """Return the installed distribution version or a fallback placeholder."""

    try:
        return metadata.version("lib_layered_config")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _describe_distribution() -> Iterable[str]:
    """Yield human-readable metadata lines about the installed distribution.

    Why
    ----
    CLI ``info`` command prints these lines verbatim for operators.
    """

    meta = _load_distribution_metadata()
    if meta is None:
        yield "lib_layered_config (metadata unavailable)"
        return
    yield f"Info for {meta.get('Name', 'lib_layered_config')}:"
    yield f"  Version         : {meta.get('Version', _version_string())}"
    yield f"  Requires-Python : {meta.get('Requires-Python', '>=3.13')}"
    summary = meta.get("Summary")
    if summary:
        yield f"  Summary         : {summary}"
    for entry in meta.get_all("Project-URL") or []:
        yield f"  {entry}"


def _load_distribution_metadata() -> metadata.PackageMetadata | None:
    """Return importlib metadata when the package is installed locally."""

    try:
        return metadata.metadata("lib_layered_config")
    except metadata.PackageNotFoundError:
        return None


@click.group(
    help="Immutable layered configuration reader",
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.version_option(
    version=_version_string(),
    prog_name="lib_layered_config",
    message="lib_layered_config version %(version)s",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
def cli(traceback: bool) -> None:
    """Root command that remembers whether tracebacks should flow."""

    _toggle_traceback(traceback)


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print package metadata in friendly lines."""

    for line in _describe_distribution():
        click.echo(line)


@cli.command("env-prefix", context_settings=CLICK_CONTEXT_SETTINGS)
@click.argument("slug")
def cli_env_prefix(slug: str) -> None:
    """Echo the canonical environment variable prefix for a slug."""

    click.echo(_default_env_prefix(slug))


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Intentionally raise a runtime error for test harnesses."""

    i_should_fail()


@cli.command("deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--source",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    required=True,
    help="Path to the configuration file that should be copied",
)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option(
    "--target",
    "targets",
    multiple=True,
    required=True,
    type=click.Choice(TARGET_CHOICES, case_sensitive=False),
    help="Layer targets to deploy to (repeatable)",
)
@click.option(
    "--platform",
    default=None,
    help="Override auto-detected platform (linux, darwin, windows)",
)
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing files at the destination",
)
def cli_deploy_config(
    source: Path,
    vendor: str,
    app: str,
    slug: str,
    targets: Sequence[str],
    platform: Optional[str],
    force: bool,
) -> None:
    """Copy a source file into the requested layered directories."""

    created = _deploy_config(
        source,
        vendor=vendor,
        app=app,
        targets=_normalise_targets(targets),
        slug=slug,
        platform=_normalise_platform(platform),
        force=force,
    )
    click.echo(_json_paths(created))


@cli.command("generate-examples", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--destination",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, resolve_path=True),
    required=True,
    help="Directory that will receive the example tree",
)
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option(
    "--platform",
    default=None,
    help="Override platform layout (posix/windows)",
)
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing example files",
)
def cli_generate_examples(
    destination: Path,
    slug: str,
    vendor: str,
    app: str,
    platform: Optional[str],
    force: bool,
) -> None:
    """Create reference example trees for documentation or onboarding."""

    created = _generate_examples(
        destination,
        slug=slug,
        vendor=vendor,
        app=app,
        force=force,
        platform=_normalise_examples_platform(platform),
    )
    click.echo(_json_paths(created))


@cli.command("read", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option("--prefer", multiple=True, help="Preferred file suffix ordering (repeatable)")
@click.option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
    help="Starting directory for .env upward search",
)
@click.option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
    help="Optional lowest-precedence defaults file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    show_default=True,
    help="Choose between human prose or JSON",
)
@click.option("--indent", type=int, default=None, help="Pretty-print JSON output")
@click.option(
    "--provenance/--no-provenance",
    default=True,
    show_default=True,
    help="Include provenance metadata in JSON output",
)
def cli_read_config(
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str],
    start_dir: Optional[Path],
    default_file: Optional[Path],
    output_format: str,
    indent: Optional[int],
    provenance: bool,
) -> None:
    """Read configuration and print either human prose or JSON."""

    prefer_order = _normalise_prefer(prefer)
    start_dir_str = _stringify(start_dir)
    default_file_str = _stringify(default_file)

    if output_format.lower() == "json":
        click.echo(
            _render_json(
                vendor=vendor,
                app=app,
                slug=slug,
                prefer=prefer_order,
                start_dir=start_dir_str,
                default_file=default_file_str,
                indent=indent,
                provenance=provenance,
            )
        )
        return

    data, meta = read_config_raw(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=prefer_order,
        start_dir=start_dir_str,
        default_file=default_file_str,
    )
    click.echo(_render_human(data, meta))


@cli.command("read-json", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option("--vendor", required=True)
@click.option("--app", required=True)
@click.option("--slug", required=True)
@click.option("--prefer", multiple=True)
@click.option(
    "--start-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
    default=None,
)
@click.option(
    "--default-file",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    default=None,
)
@click.option("--indent", type=int, default=None)
def cli_read_config_json(
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str],
    start_dir: Optional[Path],
    default_file: Optional[Path],
    indent: Optional[int],
) -> None:
    """Always emit combined JSON (config + provenance)."""

    payload = read_config_json(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=_normalise_prefer(prefer),
        start_dir=_stringify(start_dir),
        default_file=_stringify(default_file),
        indent=indent,
    )
    click.echo(payload)


def main(argv: Optional[Sequence[str]] = None, *, restore_traceback: bool = True) -> int:
    """Entry point that restores traceback preferences on exit."""

    previous_traceback = getattr(lib_cli_exit_tools.config, "traceback", False)
    previous_force_color = getattr(lib_cli_exit_tools.config, "traceback_force_color", False)
    try:
        try:
            run_cli = cast(Callable[..., int], lib_cli_exit_tools.run_cli)  # pyright: ignore[reportUnknownMemberType]
            return run_cli(cli, argv=list(argv) if argv is not None else None, prog_name="lib_layered_config")
        except BaseException as exc:  # noqa: BLE001
            print_exception = cast(Callable[..., None], lib_cli_exit_tools.print_exception_message)  # pyright: ignore[reportUnknownMemberType]
            print_exception(
                trace_back=lib_cli_exit_tools.config.traceback,
                length_limit=TRACEBACK_VERBOSE if lib_cli_exit_tools.config.traceback else TRACEBACK_SUMMARY,
            )
            exit_code_fn = cast(Callable[[BaseException], int], lib_cli_exit_tools.get_system_exit_code)  # pyright: ignore[reportUnknownMemberType]
            return exit_code_fn(exc)
    finally:
        if restore_traceback:
            lib_cli_exit_tools.config.traceback = previous_traceback
            lib_cli_exit_tools.config.traceback_force_color = previous_force_color


def _render_json(
    *,
    vendor: str,
    app: str,
    slug: str,
    prefer: Sequence[str] | None,
    start_dir: str | None,
    default_file: str | None,
    indent: int | None,
    provenance: bool,
) -> str:
    """Render configuration as JSON with optional provenance inclusion."""
    if provenance:
        return read_config_json(
            vendor=vendor,
            app=app,
            slug=slug,
            prefer=prefer,
            start_dir=start_dir,
            default_file=default_file,
            indent=indent,
        )

    config = read_config(
        vendor=vendor,
        app=app,
        slug=slug,
        prefer=prefer,
        start_dir=start_dir,
        default_file=default_file,
    )
    return config.to_json(indent=indent)


def _render_human(data: Mapping[str, object], provenance: Mapping[str, SourceInfoPayload]) -> str:
    """Return a human-readable description of config values and provenance."""

    entries = list(_iter_leaf_items(data))
    if not entries:
        return "No configuration values were found."

    lines: list[str] = []
    for dotted, value in entries:
        lines.append(f"{dotted}: {_format_scalar(value)}")
        info = provenance.get(dotted)
        if info:
            path = info["path"] or "(memory)"
            lines.append(f"  provenance: layer={info['layer']}, path={path}")
    return "\n".join(lines)


def _iter_leaf_items(mapping: Mapping[str, object], prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, object]]:
    """Yield dotted paths and values for every leaf entry in *mapping*."""

    for key, value in mapping.items():
        dotted = ".".join((*prefix, key))
        if isinstance(value, Mapping):
            nested = cast(Mapping[str, object], value)
            yield from _iter_leaf_items(nested, (*prefix, key))
        else:
            yield dotted, value


def _format_scalar(value: object) -> str:
    """Return string representation used in human output for *value*."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _normalise_prefer(values: Sequence[str]) -> Sequence[str] | None:
    """Lowercase supplied extensions and strip leading dots."""

    if not values:
        return None
    return tuple(value.lower().lstrip(".") for value in values)


def _normalise_targets(values: Sequence[str]) -> tuple[str, ...]:
    """Normalise deployment targets to lowercase for resolver routing."""

    return tuple(value.lower() for value in values)


def _normalise_platform(platform: Optional[str]) -> Optional[str]:
    """Map user-friendly platform aliases to canonical resolver identifiers."""

    if platform is None:
        return None
    alias = platform.strip().lower()
    mapping = {
        "linux": "linux",
        "posix": "linux",
        "darwin": "darwin",
        "mac": "darwin",
        "macos": "darwin",
        "windows": "win32",
        "win": "win32",
        "win32": "win32",
        "wine": "win32",
    }
    try:
        return mapping[alias]
    except KeyError as exc:
        raise click.BadParameter(
            "Platform must be one of: linux, posix, darwin, mac, macos, windows, win, win32, wine.",
            param_hint="--platform",
        ) from exc


def _normalise_examples_platform(platform: Optional[str]) -> Optional[str]:
    """Map example-generation platform aliases to canonical values."""

    if platform is None:
        return None
    alias = platform.strip().lower()
    mapping = {
        "posix": "posix",
        "linux": "posix",
        "darwin": "posix",
        "mac": "posix",
        "macos": "posix",
        "windows": "windows",
        "win": "windows",
        "win32": "windows",
        "wine": "windows",
    }
    try:
        return mapping[alias]
    except KeyError as exc:
        raise click.BadParameter(
            "Platform must be one of: posix, linux, darwin, mac, macos, windows, win, win32, wine.",
            param_hint="--platform",
        ) from exc


def _stringify(path: Optional[Path]) -> Optional[str]:
    """Return stringified path or ``None`` when *path* is ``None``."""

    return None if path is None else str(path)


def _json_paths(paths: Iterable[Path]) -> str:
    """Return JSON array of stringified paths written by helper commands."""

    return json.dumps([str(path) for path in paths], indent=2)


if __name__ == "__main__":  # pragma: no cover - exercised via console script
    raise SystemExit(main(sys.argv[1:]))
