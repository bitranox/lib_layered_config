"""CLI command for deploying configuration files into layer directories."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import rich_click as click

from ..domain import json_codec
from ..domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from ..domain.deploy_permissions import DeployPermissionsError
from ..examples import DeployAction, DeployResult
from ..examples import deploy_config as deploy_config_impl
from .common import normalise_platform_option, normalise_targets
from .constants import CLICK_CONTEXT_SETTINGS, TARGET_CHOICES
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


__all__ = [
    "deploy_command",
    "register",
]


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


def _mode_option(kind: ModeKind) -> Callable[[click.Context, click.Parameter, str | None], int | None]:
    """Build a click callback that parses an octal mode for *kind* and refuses an unsafe one."""

    def parse(_ctx: click.Context, param: click.Parameter, value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return DeployMode.from_text(value, kind).value
        except DeployModeError as exc:
            raise click.BadParameter(str(exc), param=param) from exc

    return parse


#: The library's hint names Python keywords; a CLI user needs the options. Both modes come first,
#: because --no-permissions leaves a secrets file to the umask.
_CLI_DEPLOY_ANYWAY_HINT = (
    "to deploy anyway, give both --dir-mode and --file-mode (the built-in modes are 700 and 600 for user, "
    "755 and 644 for app and host); --no-permissions also deploys, but leaves every mode to the umask, which "
    "can make a user file that holds secrets readable by other accounts"
)


#: The JSON envelope names the ``.d`` section's lists like the main ones, with this in front.
_DOT_D_KEY_PREFIX = "dot_d_"


class _SectionReport(NamedTuple):
    """What one section of a deploy did (the main files or their ``.d`` copies), as path strings."""

    created: list[str]
    overwritten: list[str]
    kept: list[str]
    skipped: list[str]
    backups: list[str]
    ucf_files: list[str]

    @classmethod
    def of(cls, results: Sequence[DeployResult]) -> _SectionReport:
        """Sort *results* into the section's lists, each in deploy order."""

        def destinations(action: DeployAction) -> list[str]:
            return [str(r.destination) for r in results if r.action == action]

        return cls(
            created=destinations(DeployAction.CREATED),
            overwritten=destinations(DeployAction.OVERWRITTEN),
            kept=destinations(DeployAction.KEPT),
            skipped=destinations(DeployAction.SKIPPED),
            backups=[str(r.backup_path) for r in results if r.backup_path is not None],
            ucf_files=[str(r.ucf_path) for r in results if r.ucf_path is not None],
        )

    def json_fields(self) -> tuple[tuple[str, list[str]], ...]:
        """The section's lists under their envelope names, in the envelope's order."""
        return (
            ("created", self.created),
            ("overwritten", self.overwritten),
            ("kept", self.kept),
            ("skipped", self.skipped),
            ("backups", self.backups),
            ("ucf_files", self.ucf_files),
        )


def _format_results(results: list[DeployResult]) -> str:
    """Format deployment results as JSON, including .d directory results; an empty list is left out."""
    main = _SectionReport.of(results)
    dot_d = _SectionReport.of([dot_d_result for r in results for dot_d_result in r.dot_d_results])
    envelope = {name: values for name, values in main.json_fields() if values}
    envelope.update({_DOT_D_KEY_PREFIX + name: values for name, values in dot_d.json_fields() if values})
    return json_codec.dumps(envelope, indent=True)


@click.command("deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--source",
    type=click.Path(path_type=Path, exists=True, file_okay=True, dir_okay=False, readable=True),
    required=True,
    help="Path to the configuration file to deploy (companion .d directory is auto-detected)",
)
@option("--vendor", required=True, help="Vendor namespace")
@option("--app", required=True, help="Application name")
@option("--slug", required=True, help="Slug identifying the configuration set")
@option("--profile", default=None, help="Configuration profile name (e.g., 'test', 'production')")
@option(
    "--target",
    "targets",
    multiple=True,
    required=True,
    type=click.Choice(TARGET_CHOICES, case_sensitive=False),
    help="Layer targets to deploy to (repeatable)",
)
@option(
    "--platform",
    default=None,
    help="Override auto-detected platform (linux, darwin, windows)",
)
@option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Overwrite existing files (with .bak backup)",
)
@option(
    "--batch",
    is_flag=True,
    default=False,
    help="Non-interactive mode: keep existing and write new as .ucf (for CI/scripts)",
)
@option(
    "--permissions/--no-permissions",
    default=None,
    help="Set Unix permissions (default: the configured default_permissions.enabled, else on)",
)
@option(
    "--dir-mode",
    default=None,
    callback=_mode_option(ModeKind.DIRECTORY),
    help="Directory mode for every target, octal (e.g. 750 or 0o750); overrides the configured one",
)
@option(
    "--file-mode",
    default=None,
    callback=_mode_option(ModeKind.FILE),
    help="File mode for every target, octal (e.g. 640 or 0o640); overrides the configured one",
)
def deploy_command(
    *,
    source: Path,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,
    targets: Sequence[str],
    platform: str | None,
    force: bool,
    batch: bool,
    permissions: bool | None,
    dir_mode: int | None,
    file_mode: int | None,
) -> None:
    """Copy a source file into the requested layered directories.

    When a destination file already exists:

    \b
    - With --force: backs up to .bak and overwrites
    - With --batch: keeps existing and writes new as .ucf (for CI/scripts)
    - Otherwise: prompts to keep (save as .ucf) or overwrite (backup to .bak)

    \b
    Modes: --dir-mode/--file-mode win, then [lib_layered_config.default_permissions] from the
    source, the target files this command does not write and the environment (never .env), then
    755/644 (app, host) and 700/600 (user). An unsafe mode is refused.
    """
    if permissions is False and (dir_mode is not None or file_mode is not None):
        raise click.UsageError("--no-permissions cannot be combined with --dir-mode or --file-mode")

    # Determine conflict resolver
    conflict_resolver = None if (force or batch) else _prompt_for_action

    try:
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
            set_permissions=permissions,
            dir_mode=dir_mode,
            file_mode=file_mode,
        )
    except DeployPermissionsError as exc:
        # Same type and problems; only the way through is respelled for the command line.
        raise DeployPermissionsError(exc.problems, hint=_CLI_DEPLOY_ANYWAY_HINT) from None
    click.echo(_format_results(results))


def register(cli_group: click.Group) -> None:
    """Register the deploy command with the root CLI group."""
    cli_group.add_command(deploy_command)
