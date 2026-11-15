"""CLI command for generating example configuration trees."""

from __future__ import annotations

from pathlib import Path

import rich_click as click

from ..generate import ExamplesReport, generate_examples_report
from .common import json_paths, normalise_examples_platform_option
from .constants import CLICK_CONTEXT_SETTINGS
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope
from .output import emit_json
from .typed_click import option

__all__ = [
    "generate_examples_command",
    "register",
]


@click.command("generate-examples", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--destination",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, resolve_path=True),
    required=True,
    help="Directory that will receive the example tree",
)
@option("--slug", required=True, help="Slug identifying the configuration set")
@option("--vendor", required=True, help="Vendor namespace")
@option("--app", required=True, help="Application name")
@option(
    "--platform",
    default=None,
    help="Override platform layout (posix/windows)",
)
@option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing example files",
)
@json_envelope_option
def generate_examples_command(
    *,
    destination: Path,
    slug: str,
    vendor: str,
    app: str,
    platform: str | None,
    force: bool,
    json_envelope: bool,
) -> None:
    """Create reference example trees for documentation or onboarding."""

    def generate() -> ExamplesReport:
        return generate_examples_report(
            destination,
            slug=slug,
            vendor=vendor,
            app=app,
            force=force,
            platform=normalise_examples_platform_option(platform),
        )

    if json_envelope:
        run_in_envelope("generate-examples", lambda: _envelope_data(generate()), skipped=_skipped_in)
        return
    emit_json(json_paths(generate().created))


def _envelope_data(report: ExamplesReport) -> dict[str, list[str]]:
    """The ``--json`` data: the files written, and the existing ones kept (as ``deploy`` names them)."""
    return {"created": [str(path) for path in report.created], "skipped": [str(path) for path in report.kept]}


def _skipped_in(data: dict[str, list[str]]) -> list[str]:
    """The kept files in :func:`_envelope_data`, for the envelope's ``skipped``."""
    return data["skipped"]


def register(cli_group: click.Group) -> None:
    """Register the generate-examples command."""
    cli_group.add_command(generate_examples_command)
