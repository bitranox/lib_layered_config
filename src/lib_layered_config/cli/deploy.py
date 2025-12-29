"""CLI command for deploying configuration files into layer directories."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import rich_click as click

from ..examples import DeployAction, DeployResult
from ..examples import deploy_config as deploy_config_impl
from .common import normalise_platform_option, normalise_targets
from .constants import CLICK_CONTEXT_SETTINGS, TARGET_CHOICES


def _prompt_for_action(destination: Path) -> DeployAction:
    """Prompt user for action when destination file exists."""
    click.echo(f"\nFile exists: {destination}")
    choice = click.prompt(
        "  [K]eep existing (save new as .ucf)\n  [O]verwrite (backup existing to .bak)\nChoose",
        type=click.Choice(["k", "o"], case_sensitive=False),
        default="k",
        show_choices=False,
    )
    if choice.lower() == "o":
        return DeployAction.OVERWRITTEN
    return DeployAction.KEPT


_ACTION_TO_KEY: dict[DeployAction, str] = {
    DeployAction.CREATED: "created",
    DeployAction.OVERWRITTEN: "overwritten",
    DeployAction.KEPT: "kept",
    DeployAction.SKIPPED: "skipped",
}


def _append_result_to_output(
    r: DeployResult,
    output: dict[str, list[str]],
    prefix: str = "",
) -> None:
    """Append a single deployment result to the output dictionary.

    Args:
        r: The deployment result to process.
        output: Dictionary to append results to.
        prefix: Key prefix for .d directory results (e.g., "dot_d_").
    """
    key = _ACTION_TO_KEY.get(r.action)
    if key:
        output[f"{prefix}{key}"].append(str(r.destination))
    if r.backup_path:
        output[f"{prefix}backups"].append(str(r.backup_path))
    if r.ucf_path:
        output[f"{prefix}ucf_files"].append(str(r.ucf_path))


def _format_results(results: list[DeployResult]) -> str:
    """Format deployment results as JSON, including .d directory results."""
    output: dict[str, list[str]] = {
        "created": [],
        "overwritten": [],
        "kept": [],
        "skipped": [],
        "backups": [],
        "ucf_files": [],
        "dot_d_created": [],
        "dot_d_overwritten": [],
        "dot_d_kept": [],
        "dot_d_skipped": [],
        "dot_d_backups": [],
        "dot_d_ucf_files": [],
    }
    for r in results:
        _append_result_to_output(r, output)
        for dot_d_r in r.dot_d_results:
            _append_result_to_output(dot_d_r, output, prefix="dot_d_")
    return json.dumps({k: v for k, v in output.items() if v}, indent=2)


@click.command("deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--source",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    required=True,
    help="Path to the configuration file to deploy (companion .d directory is auto-detected)",
)
@click.option("--vendor", required=True, help="Vendor namespace")
@click.option("--app", required=True, help="Application name")
@click.option("--slug", required=True, help="Slug identifying the configuration set")
@click.option("--profile", default=None, help="Configuration profile name (e.g., 'test', 'production')")
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
    help="Overwrite existing files (with .bak backup)",
)
@click.option(
    "--batch",
    is_flag=True,
    default=False,
    help="Non-interactive mode: keep existing and write new as .ucf (for CI/scripts)",
)
def deploy_command(
    source: Path,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    targets: Sequence[str],
    platform: str | None,
    force: bool,
    batch: bool,
) -> None:
    """Copy a source file into the requested layered directories.

    When a destination file already exists:

    \b
    - With --force: backs up to .bak and overwrites
    - With --batch: keeps existing and writes new as .ucf (for CI/scripts)
    - Otherwise: prompts to keep (save as .ucf) or overwrite (backup to .bak)
    """
    # Determine conflict resolver
    conflict_resolver = None if (force or batch) else _prompt_for_action

    results = deploy_config_impl(
        source,
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,
        targets=normalise_targets(targets),
        platform=normalise_platform_option(platform),
        force=force,
        batch=batch,
        conflict_resolver=conflict_resolver,
    )
    click.echo(_format_results(results))


def register(cli_group: click.Group) -> None:
    """Register the deploy command with the root CLI group."""
    cli_group.add_command(deploy_command)
