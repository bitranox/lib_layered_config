from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path

import click

project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
for entry in (src_path, project_root):
    candidate = str(entry)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
from scripts._utils import get_project_metadata  # noqa: E402

PROJECT = get_project_metadata()
PACKAGE = PROJECT.import_package


@click.command(
    help=f"Run {PROJECT.name} CLI (passes additional args)",
    context_settings={"ignore_unknown_options": True},
)
@click.option(
    "--use-dotenv/--no-use-dotenv",
    default=False,
    help="Load environment variables from a nearby .env before running commands.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def main(ctx: click.Context, use_dotenv: bool, args: tuple[str, ...]) -> None:
    config_module = import_module(f"{PACKAGE}.config")
    explicit: bool | None = None
    if ctx.get_parameter_source("use_dotenv") is not click.core.ParameterSource.DEFAULT:
        explicit = use_dotenv

    env_toggle = os.getenv(config_module.DOTENV_ENV_VAR)
    if config_module.should_use_dotenv(explicit=explicit, env_value=env_toggle):
        config_module.enable_dotenv()

    import_module(f"{PACKAGE}.__main__")
    cli_main = import_module(f"{PACKAGE}.cli").main

    forwarded = list(args) if args else ["--help"]
    if explicit is True and "--use-dotenv" not in forwarded:
        forwarded.insert(0, "--use-dotenv")
    elif explicit is False and "--no-use-dotenv" not in forwarded:
        forwarded.insert(0, "--no-use-dotenv")

    code = cli_main(forwarded)  # returns int
    raise SystemExit(int(code))


if __name__ == "__main__":
    main()
