"""CLI command for deploying configuration files into layer directories."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import rich_click as click
from lib_cli_exit_tools import CliSignalError

from ..deploy import DeployAction, DeployResult, deployed_before_failure
from ..deploy import deploy_config as deploy_config_impl
from ..domain import json_codec
from ..domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from ..domain.deploy_permissions import DeployPermissionsError
from ..domain.printable import escape_controls
from .common import normalise_platform_option, normalise_targets
from .constants import CLICK_CONTEXT_SETTINGS, TARGET_CHOICES
from .envelope import EnvelopeCommand, json_envelope_option, run_in_envelope
from .output import emit_json, emit_text
from .typed_click import option

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


__all__ = [
    "deploy_command",
    "register",
]


def _prompt_for_action(destination: Path) -> DeployAction:
    """Ask on stderr whether to keep or overwrite an existing *destination*.

    stdout is reserved for the JSON result. An answer may come from a pipe; when none can be read
    the refusal names the flags that make the command unattended.

    Raises:
        click.UsageError: stdin reached end of file before an answer.
    """
    emit_text(f"\nFile exists: {destination}", err=True)
    try:
        choice = click.prompt(
            "  [K]eep existing (save new as .ucf)\n  [O]verwrite (backup existing to .bak)\nChoose",
            type=click.Choice(["k", "o"], case_sensitive=False),
            default="k",
            show_choices=False,
            err=True,
        )
    except click.Abort as exc:
        # click raises Abort for both Ctrl-C and end of input; only the second is a usage problem.
        # It raises "from None", which hides the cause but still records it as the context.
        if not isinstance(exc.__context__, EOFError):
            raise
        raise click.UsageError(
            f"{destination} exists and no answer could be read: pass --batch (keep it, write .ucf) "
            "or --force (overwrite it, keep .bak)"
        ) from None
    if choice.lower() == "o":
        return DeployAction.OVERWRITTEN
    return DeployAction.KEPT


def _mode_option(kind: ModeKind) -> Callable[[click.Context, click.Parameter, str | None], DeployMode | None]:
    """Build a click callback that parses an octal mode for *kind* and refuses an unsafe one."""

    def parse(_ctx: click.Context, param: click.Parameter, value: str | None) -> DeployMode | None:
        if value is None:
            return None
        try:
            return DeployMode.from_text(value, kind)
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


def _full_report(results: list[DeployResult]) -> dict[str, list[str]]:
    """Every section of the deployment report, .d directory results included, empty ones too."""
    main = _SectionReport.of(results)
    dot_d = _SectionReport.of([dot_d_result for r in results for dot_d_result in r.dot_d_results])
    report = dict(main.json_fields())
    report.update({_DOT_D_KEY_PREFIX + name: values for name, values in dot_d.json_fields()})
    return report


def _format_results(results: list[DeployResult]) -> str:
    """Format deployment results as JSON, including .d directory results; an empty list is left out."""
    return json_codec.dumps({name: values for name, values in _full_report(results).items() if values}, indent=True)


def _written_paths(results: Sequence[DeployResult]) -> list[str]:
    """Every file *results* wrote, in the order written: backup, destination or .ucf, then the .d copies."""
    paths: list[str] = []
    for result in results:
        paths.extend(_paths_written_by(result))
        for dot_d_result in result.dot_d_results:
            paths.extend(_paths_written_by(dot_d_result))
    return paths


def _paths_written_by(result: DeployResult) -> list[str]:
    """The files one result wrote: a skipped file wrote nothing, a kept one only its .ucf."""
    written = [result.backup_path, result.ucf_path]
    if result.action in (DeployAction.CREATED, DeployAction.OVERWRITTEN):
        written.append(result.destination)
    return [str(path) for path in written if path is not None]


def _written_detail(error: Exception) -> dict[str, object]:
    """The failure envelope's ``written`` list, present only when the deploy wrote something first."""
    written = _written_paths(deployed_before_failure(error))
    return {"written": written} if written else {}


def _report_written(error: BaseException) -> None:
    """Name on stderr the files a failed deploy had already written, before the error itself prints.

    User decision 2026-11-16 (R2-F2): the failure leaves them written, and the error alone does not say so.
    """
    written = _written_paths(deployed_before_failure(error))
    if written:
        emit_text(
            "deploy stopped after writing:\n" + "\n".join(f"  {escape_controls(path)}" for path in written), err=True
        )


def _skipped_in(report: dict[str, list[str]]) -> list[str]:
    """The skipped destinations in a :func:`_full_report`, the .d directory's included."""
    return report["skipped"] + report[_DOT_D_KEY_PREFIX + "skipped"]


@click.command("deploy", cls=EnvelopeCommand, context_settings=CLICK_CONTEXT_SETTINGS)
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
@json_envelope_option
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
    dir_mode: DeployMode | None,
    file_mode: DeployMode | None,
    json_envelope: bool,
) -> None:
    """Copy a source file into the requested layered directories.

    When a destination file already exists:

    \b
    - With --force: backs up to .bak and overwrites
    - With --batch: keeps existing and writes new as .ucf (for CI/scripts)
    - With both: a usage error, since one overwrites and the other keeps
    - Otherwise: prompts on stderr to keep (save as .ucf) or overwrite (backup to .bak);
      with no answer to read, a usage error names --batch and --force

    \b
    Modes: --dir-mode/--file-mode win, then [lib_layered_config.default_permissions] from the
    source, the target files this command does not write and the environment (never .env), then
    755/644 (app, host) and 700/600 (user). An unsafe mode is refused.
    """

    def deploy() -> list[DeployResult]:
        if permissions is False and (dir_mode is not None or file_mode is not None):
            raise click.UsageError("--no-permissions cannot be combined with --dir-mode or --file-mode")
        if force and batch:
            raise click.UsageError("--force overwrites an existing file and --batch keeps it; pass one")
        # Prompt only when neither --force nor --batch decides the conflict.
        conflict_resolver = None if (force or batch) else _prompt_for_action
        try:
            return deploy_config_impl(
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

    if json_envelope:
        try:
            run_in_envelope("deploy", lambda: _full_report(deploy()), skipped=_skipped_in, detail=_written_detail)
        except (click.Abort, CliSignalError) as interrupt:
            # The envelope passes an interrupt through unprinted, so this is the only place it can still
            # say what the deploy wrote; a failure envelope already carries that as error.written.
            _report_written(interrupt)
            raise
        return
    try:
        results = deploy()
    except BaseException as error:
        _report_written(error)
        raise
    emit_json(_format_results(results))


def register(cli_group: click.Group) -> None:
    """Register the deploy command with the root CLI group."""
    cli_group.add_command(deploy_command)
