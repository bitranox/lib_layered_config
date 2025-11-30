"""CLI helper tests retold as crisp verses."""

from __future__ import annotations

import importlib
import json
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from lib_layered_config import __init__conf__ as metadata_module
from lib_layered_config import cli as cli_module
from lib_layered_config.cli import common as common_module
from tests.support.os_markers import os_agnostic


@os_agnostic
def test_version_string_reflects_static_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common_module.package_metadata, "version", "9.9.9", raising=False)
    assert common_module.version_string() == "9.9.9"


@os_agnostic
def test_common_describe_distribution_returns_info_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = importlib.reload(metadata_module)
    expected = list(_expected_info_lines(metadata))
    assert list(common_module.describe_distribution()) == expected


@os_agnostic
def test_cli_describe_distribution_matches_common(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = importlib.reload(metadata_module)
    expected = _expected_info_lines(metadata)
    assert tuple(common_module.describe_distribution()) == expected


@os_agnostic
def test_session_overrides_detect_traceback_flag() -> None:
    overrides = cli_module._session_overrides(["--traceback"])
    assert overrides == {"traceback": True}


@os_agnostic
def test_session_overrides_default_to_empty_when_flag_absent() -> None:
    assert cli_module._session_overrides(["read", "--vendor", "Acme"]) == {}


@os_agnostic
def test_session_overrides_return_empty_for_none() -> None:
    assert cli_module._session_overrides(None) == {}


@os_agnostic
def test_session_overrides_swallow_click_parse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module.cli,
        "make_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(cli_module.click.ClickException("boom")),
        raising=False,
    )

    assert cli_module._session_overrides(["--traceback"]) == {}


@os_agnostic
@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        (None, None),
        ("linux", "linux"),
        ("posix", "linux"),
        ("macos", "darwin"),
        ("darwin", "darwin"),
        ("windows", "win32"),
        ("win", "win32"),
    ],
)
def test_normalise_platform_maps_aliases(alias: str | None, expected: str | None) -> None:
    assert common_module.normalise_platform_option(alias) == expected


@os_agnostic
def test_normalise_platform_raises_on_unknown_words() -> None:
    with pytest.raises(cli_module.click.BadParameter):
        common_module.normalise_platform_option(" ")


@os_agnostic
def test_normalise_examples_platform_maps_aliases() -> None:
    assert common_module.normalise_examples_platform_option("macos") == "posix"


@os_agnostic
def test_normalise_examples_platform_raises_on_unknown_words() -> None:
    with pytest.raises(cli_module.click.BadParameter):
        common_module.normalise_examples_platform_option("amiga")


@os_agnostic
def test_main_delegates_through_cli_session(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    @contextmanager
    def fake_session(*, summary_limit, verbose_limit, overrides, restore):
        captured["summary_limit"] = summary_limit
        captured["verbose_limit"] = verbose_limit
        captured["overrides"] = overrides
        captured["restore"] = restore

        def runner(command, *, argv=None, prog_name=None, **kwargs):
            captured["command"] = command
            captured["argv"] = argv
            captured["prog_name"] = prog_name
            captured["kwargs"] = kwargs
            return 123

        yield runner

    monkeypatch.setattr(cli_module, "cli_session", fake_session, raising=False)

    exit_code = cli_module.main(["--traceback"], restore_traceback=False)

    assert exit_code == 123
    assert captured["summary_limit"] == cli_module.TRACEBACK_SUMMARY
    assert captured["verbose_limit"] == cli_module.TRACEBACK_VERBOSE
    assert captured["overrides"] == {"traceback": True}
    assert captured["restore"] is False
    assert captured["argv"] == ["--traceback"]
    assert captured["prog_name"] == "lib_layered_config"


@os_agnostic
def test_json_paths_renders_stringified_paths(tmp_path) -> None:
    sample = [tmp_path / "one", tmp_path / "two"]
    assert common_module.json_paths(sample) == json.dumps([str(path) for path in sample], indent=2)


@os_agnostic
def test_run_module_delegates_arguments_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from lib_layered_config import __main__ as entry

    captured: dict[str, object] = {}

    def fake_main(arguments, restore_traceback):
        captured["arguments"] = arguments
        captured["restore_traceback"] = restore_traceback
        return 7

    monkeypatch.setattr(entry, "main", fake_main)

    exit_code = entry.run_module(["--demo"])

    assert exit_code == 7
    assert captured == {"arguments": ["--demo"], "restore_traceback": True}


@os_agnostic
def test_render_human_declares_empty_configuration() -> None:
    message = common_module.render_human({}, {})
    assert message == "No configuration values were found."


@os_agnostic
def test_render_human_includes_value_and_provenance() -> None:
    data = {"service": {"port": 8080}}
    provenance = {"service.port": {"layer": "app", "path": "/tmp/config.toml"}}

    message = common_module.render_human(data, provenance)

    expected = "\n".join(
        [
            "service.port: 8080",
            "  provenance: layer=app, path=/tmp/config.toml",
        ]
    )
    assert message == expected


@os_agnostic
def test_render_human_skips_provenance_when_absent() -> None:
    data = {"service": {"port": 8080}}
    message = common_module.render_human(data, {})
    assert message == "service.port: 8080"


@os_agnostic
def test_format_scalar_translates_true_to_lowercase() -> None:
    assert common_module.format_scalar(True) == "true"


@os_agnostic
def test_format_scalar_translates_none_to_null() -> None:
    assert common_module.format_scalar(None) == "null"


@os_agnostic
def test_format_scalar_converts_other_values_to_string() -> None:
    assert common_module.format_scalar(42) == "42"


@os_agnostic
def test_normalise_prefer_returns_none_for_empty_input() -> None:
    assert common_module.normalise_prefer(()) is None


@os_agnostic
def test_normalise_prefer_lowercases_suffixes() -> None:
    result = common_module.normalise_prefer(["YAML", ".Toml"])
    assert result == ("yaml", "toml")


@os_agnostic
def test_cli_read_config_json_emits_combined_payload(tmp_path) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("[service]\nport = 8080\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        cli_module.cli_read_config_json,
        [
            "--vendor",
            "Acme",
            "--app",
            "Demo",
            "--slug",
            "demo",
            "--default-file",
            str(defaults),
            "--indent",
        ],
    )

    assert result.exit_code == 0 and '"config"' in result.stdout


def _expected_info_lines(metadata: object) -> tuple[str, ...]:
    """Compose the info lines from metadata constants."""

    fields = (
        ("name", metadata.name),
        ("title", metadata.title),
        ("version", metadata.version),
        ("homepage", metadata.homepage),
        ("author", metadata.author),
        ("author_email", metadata.author_email),
        ("shell_command", metadata.shell_command),
    )
    pad = max(len(label) for label, _ in fields)
    lines = [f"Info for {metadata.name}:", ""]
    lines.extend(f"    {label.ljust(pad)} = {value}" for label, value in fields)
    return tuple(lines)
