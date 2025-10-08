"""CLI helper tests retold as crisp verses."""

from __future__ import annotations

import json
from typing import Iterable

import lib_cli_exit_tools
import pytest
from click.testing import CliRunner

from lib_layered_config import cli as cli_module
from lib_layered_config.cli import common as common_module

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_toggle_traceback_sets_flags_when_enabled() -> None:
    cli_module._toggle_traceback(True)
    pairing = (lib_cli_exit_tools.config.traceback, lib_cli_exit_tools.config.traceback_force_color)
    cli_module._toggle_traceback(False)
    assert pairing == (True, True)


@os_agnostic
def test_toggle_traceback_clears_flags_when_disabled() -> None:
    cli_module._toggle_traceback(True)
    cli_module._toggle_traceback(False)
    pairing = (lib_cli_exit_tools.config.traceback, lib_cli_exit_tools.config.traceback_force_color)
    assert pairing == (False, False)


@os_agnostic
def test_version_string_falls_back_when_distribution_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module.metadata, "version", lambda _: (_ for _ in ()).throw(cli_module.metadata.PackageNotFoundError)
    )
    assert cli_module._version_string() == "0.0.0"


@os_agnostic
def test_describe_distribution_yields_metadata_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyMeta(dict):
        def get_all(self, key: str) -> Iterable[str] | None:  # pragma: no cover - interface contract
            return ["Homepage, https://example.invalid"] if key == "Project-URL" else None

    meta = DummyMeta(Name="Example", Version="1.2.3", Summary="Helpful")
    monkeypatch.setattr(cli_module, "_load_distribution_metadata", lambda: meta)

    result = list(cli_module._describe_distribution())

    assert result == [
        "Info for Example:",
        "  Version         : 1.2.3",
        "  Requires-Python : >=3.13",
        "  Summary         : Helpful",
        "  Homepage, https://example.invalid",
    ]


@os_agnostic
def test_describe_distribution_handles_missing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_load_distribution_metadata", lambda: None)
    assert list(cli_module._describe_distribution()) == ["lib_layered_config (metadata unavailable)"]


@os_agnostic
def test_describe_distribution_omits_blank_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyMeta(dict):
        def get_all(self, key: str):  # pragma: no cover - interface contract
            return None

    meta = DummyMeta(Name="Example", Version="1.2.3", Summary="")
    monkeypatch.setattr(cli_module, "_load_distribution_metadata", lambda: meta)

    result = list(cli_module._describe_distribution())

    assert "Summary" not in "".join(result)


@os_agnostic
def test_describe_distribution_handles_metadata_without_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    class PlainMeta(dict):
        pass

    meta = PlainMeta(Name="Example", Version="1.2.3")
    monkeypatch.setattr(cli_module, "_load_distribution_metadata", lambda: meta)

    result = list(cli_module._describe_distribution())

    assert result == [
        "Info for Example:",
        "  Version         : 1.2.3",
        "  Requires-Python : >=3.13",
    ]


@os_agnostic
def test_load_distribution_metadata_delegates_to_common(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(cli_module, "load_distribution_metadata", lambda: sentinel)

    assert cli_module._load_distribution_metadata() is sentinel


@os_agnostic
def test_common_describe_distribution_emits_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyMeta(dict):
        def get_all(self, key: str) -> Iterable[str] | None:  # pragma: no cover - protocol tidy
            return ["Docs, https://example.invalid"] if key == "Project-URL" else None

    meta = DummyMeta(Name="Example", Version="3.4.5", Summary="Shiny")
    monkeypatch.setattr(common_module, "load_distribution_metadata", lambda: meta)

    result = list(common_module.describe_distribution())

    assert result[-1] == "  Docs, https://example.invalid"


@os_agnostic
def test_common_describe_distribution_skips_blank_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    class PlainMeta(dict):
        def get_all(self, key: str) -> Iterable[str] | None:  # pragma: no cover - protocol tidy
            return None

    meta = PlainMeta(Name="Example", Version="3.4.5", Summary="")
    monkeypatch.setattr(common_module, "load_distribution_metadata", lambda: meta)

    lines = list(common_module.describe_distribution())

    assert "Summary" not in "".join(lines)


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
    assert cli_module._normalise_platform(alias) == expected


@os_agnostic
def test_normalise_platform_raises_on_unknown_words() -> None:
    with pytest.raises(cli_module.click.BadParameter):
        cli_module._normalise_platform(" ")


@os_agnostic
def test_normalise_examples_platform_maps_aliases() -> None:
    assert cli_module._normalise_examples_platform("macos") == "posix"


@os_agnostic
def test_normalise_examples_platform_raises_on_unknown_words() -> None:
    with pytest.raises(cli_module.click.BadParameter):
        cli_module._normalise_examples_platform("amiga")


@os_agnostic
def test_main_restores_traceback_flags_even_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyError(RuntimeError):
        pass

    def explode(*_: object, **__: object) -> None:
        raise DummyError("boom")

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", explode)
    monkeypatch.setattr(lib_cli_exit_tools, "get_system_exit_code", lambda exc: 42)
    monkeypatch.setattr(lib_cli_exit_tools, "print_exception_message", lambda **__: None)
    lib_cli_exit_tools.config.traceback = True
    lib_cli_exit_tools.config.traceback_force_color = True

    exit_code = cli_module.main(["read", "--vendor", "Acme", "--app", "Demo", "--slug", "demo"])

    assert exit_code == 42


@os_agnostic
def test_main_puts_traceback_flags_back_after_runner_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    def mutate_and_return_zero(*_: object, **__: object) -> int:
        lib_cli_exit_tools.config.traceback = True
        lib_cli_exit_tools.config.traceback_force_color = True
        return 0

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", mutate_and_return_zero)
    lib_cli_exit_tools.config.traceback = False
    lib_cli_exit_tools.config.traceback_force_color = False

    cli_module.main(["read", "--vendor", "Acme", "--app", "Demo", "--slug", "demo"])

    assert (lib_cli_exit_tools.config.traceback, lib_cli_exit_tools.config.traceback_force_color) == (False, False)


@os_agnostic
def test_json_paths_renders_stringified_paths(tmp_path) -> None:
    sample = [tmp_path / "one", tmp_path / "two"]
    assert cli_module._json_paths(sample) == json.dumps([str(path) for path in sample], indent=2)


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
    message = cli_module._render_human({}, {})
    assert message == "No configuration values were found."


@os_agnostic
def test_render_human_includes_value_and_provenance() -> None:
    data = {"service": {"port": 8080}}
    provenance = {"service.port": {"layer": "app", "path": "/tmp/config.toml"}}

    message = cli_module._render_human(data, provenance)

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
    message = cli_module._render_human(data, {})
    assert message == "service.port: 8080"


@os_agnostic
def test_format_scalar_translates_true_to_lowercase() -> None:
    assert cli_module._format_scalar(True) == "true"


@os_agnostic
def test_format_scalar_translates_none_to_null() -> None:
    assert cli_module._format_scalar(None) == "null"


@os_agnostic
def test_format_scalar_converts_other_values_to_string() -> None:
    assert cli_module._format_scalar(42) == "42"


@os_agnostic
def test_normalise_prefer_returns_none_for_empty_input() -> None:
    assert cli_module._normalise_prefer(()) is None


@os_agnostic
def test_normalise_prefer_lowercases_suffixes() -> None:
    result = cli_module._normalise_prefer(["YAML", ".Toml"])
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
