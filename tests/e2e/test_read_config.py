"""Composition root stories that prove precedence, provenance, and defaults."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import socket
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from lib_layered_config import ConfigError, read_config, read_config_json, read_config_raw
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.core import LayerLoadError
from tests.adapters.test_loader_errors import _chain
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic, posix_only

if TYPE_CHECKING:
    from pathlib import Path

VENDOR = "Acme"
APP = "ConfigKit"
SLUG = "config-kit"

# See tests/adapters/test_file_loaders.py for why find_spec, not a lazily-populated module global.
_YAML_INSTALLED = importlib.util.find_spec("yaml") is not None


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


def arrange_precedence_story(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
):
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [service]
            timeout = 5
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/01-extra.toml",
        content=dedent(
            """
            [service]
            retries = 1
            """
        ),
    )
    sandbox.write(
        "host",
        "test-host.toml",
        content=dedent(
            """
            [service]
            timeout = 10
            """
        ),
    )
    sandbox.write(
        "user",
        "config.toml",
        content=dedent(
            """
            [service]
            endpoint = 'https://api'
            """
        ),
    )
    sandbox.write(
        "user",
        ".env",
        content="SERVICE__TIMEOUT=15\n",
    )
    monkeypatch.setenv("CONFIG_KIT___SERVICE__TIMEOUT", "20")
    monkeypatch.setenv("CONFIG_KIT___SERVICE__MODE", "debug")
    result = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    return result


@os_agnostic
def test_read_config_returns_highest_precedence_value(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    timeout = result.data["service"]["timeout"]  # type: ignore[index]
    assert int(timeout) == 20


@os_agnostic
def test_read_config_preserves_lower_precedence_scalars(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.data["service"]["retries"] == 1  # type: ignore[index]


@os_agnostic
def test_read_config_provenance_records_env_layer(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.provenance["service.timeout"]["layer"] == "env"


@os_agnostic
def test_read_config_provenance_records_app_layer(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    result = arrange_precedence_story(monkeypatch, sandbox)
    assert result.provenance["service.retries"]["layer"] == "app"


@pytest.mark.skipif(not _YAML_INSTALLED, reason="PyYAML not available")
@os_agnostic
def test_read_config_reports_a_yaml_construction_error_as_layer_load_error(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox, caplog: pytest.LogCaptureFixture
) -> None:
    """PyYAML's timestamp constructor raises a bare ``ValueError`` for an out-of-range calendar
    date, never its own ``YAMLError``; ``read_config`` must still refuse it as ``LayerLoadError``
    naming the file, not leak the parser's own ``ValueError`` or its message text."""
    sandbox.apply_env(monkeypatch)
    written = sandbox.write("app", "config.d/01-broken.yaml", content="a: 2020-13-01\n")

    with caplog.at_level(logging.DEBUG, logger="lib_layered_config"), pytest.raises(LayerLoadError) as captured:
        read_config_raw(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir))

    assert isinstance(captured.value, ConfigError)
    message = str(captured.value)
    assert str(written) in message
    assert "is not valid YAML" in message
    # pytest's own tmp_path can legitimately contain "13" (e.g. "pytest-13"), so check
    # leak-freedom on the message with the path removed, not on the raw message.
    without_path = message.replace(str(written), "")
    assert "month" not in without_path
    assert "13" not in without_path
    for link in _chain(captured.value):
        link_text = str(link).replace(str(written), "")
        assert "month" not in link_text
        assert "13" not in link_text
    # Liveness: the capture sees the event, so an absent leak means the event is clean, not unseen.
    assert any(record.getMessage() == "config_file_invalid" for record in caplog.records)
    assert not any("month" in repr(vars(record)) for record in caplog.records)


@os_agnostic
def test_read_config_json_contains_config_and_provenance(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content="""[feature]\nflag = true\n""",
    )
    payload = read_config_json(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )
    data = json.loads(payload)
    assert data["config"]["feature"]["flag"] is True
    assert data["provenance"]["feature.flag"]["layer"] == "app"


@os_agnostic
def test_read_config_default_file_serves_as_lowest_precedence(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    default_file = tmp_path / "defaults.toml"
    default_file.write_text(
        dedent(
            """
            [service]
            timeout = 3
            mode = "defaults"
            region = "eu-central"
            """
        ),
        encoding="utf-8",
    )
    sandbox.write(
        "app",
        "config.toml",
        content="""[service]\nmode = \"app\"\n""",
    )
    sandbox.write(
        "user",
        "config.toml",
        content="""[service]\ntimeout = 10\n""",
    )
    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        default_file=default_file,
    )
    assert config.get("service.timeout") == 10
    assert config.get("service.region") == "eu-central"


@os_agnostic
def test_read_config_dotenv_path_overrides_discovery(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    # Write a .env in start_dir that should be ignored
    sandbox.write("user", ".env", content="SERVICE__MODE=discovered\n")
    # Write an explicit dotenv file elsewhere
    explicit_env = tmp_path / "explicit.env"
    explicit_env.write_text("SERVICE__MODE=explicit\n", encoding="utf-8")

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        dotenv_path=explicit_env,
    )
    assert config.get("service.mode") == "explicit"


@os_agnostic
def test_read_config_dotenv_path_provenance_records_explicit_file(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    sandbox.apply_env(monkeypatch)
    explicit_env = tmp_path / "custom.env"
    explicit_env.write_text("SERVICE__REGION=us-east\n", encoding="utf-8")

    result = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        dotenv_path=str(explicit_env),
    )
    assert result.data["service"]["region"] == "us-east"  # type: ignore[index]
    assert result.provenance["service.region"]["layer"] == "dotenv"
    assert result.provenance["service.region"]["path"] == str(explicit_env)


@posix_only
def test_read_config_refuses_a_fifo_given_as_default_file(tmp_path: Path) -> None:
    """A FIFO at `default_file` (a shell's `<(...)` is one) refuses the load naming its kind. It
    used to be passed over as if absent, so the defaults layer vanished without a word. The FIFO
    has no writer: a refusal that opened it first would hang here, not pass."""
    fifo = tmp_path / "defaults.toml"
    os.mkfifo(fifo)

    with pytest.raises(LayerLoadError, match="is a FIFO, not a configuration file") as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=fifo)

    assert str(fifo) in str(caught.value)


@posix_only
def test_read_config_refuses_a_device_given_as_default_file(tmp_path: Path) -> None:
    """A device at `default_file` refuses the load naming its kind, rather than reading as no defaults."""
    with pytest.raises(LayerLoadError, match="/dev/null is a character device, not a configuration file"):
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file="/dev/null")


@posix_only
def test_read_config_refuses_a_socket_given_as_default_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Unix socket at `default_file` refuses the load naming its kind. Bound by a relative name
    from inside tmp_path: macOS caps a socket path near 104 bytes and its tmp_path is longer."""
    monkeypatch.chdir(tmp_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind("defaults.toml")

        with pytest.raises(LayerLoadError, match="is a socket, not a configuration file"):
            read_config(
                vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=tmp_path / "defaults.toml"
            )


@os_agnostic
@pytest.mark.parametrize("name", ["defaults.conf", "defaults"])
def test_read_config_refuses_a_default_file_without_a_supported_suffix(tmp_path: Path, name: str) -> None:
    """A `default_file` whose suffix no loader reads refuses the load naming the supported ones.
    It used to load nothing and raise nothing, so the defaults layer vanished without a word."""
    default_file = tmp_path / name
    default_file.write_text("a = 1\n", encoding="utf-8")

    with pytest.raises(LayerLoadError, match=r"has no supported format \(\.toml, \.json, \.yaml, \.yml\)") as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)

    assert str(default_file) in str(caught.value)


@os_agnostic
def test_read_config_reads_a_default_file_suffix_in_any_case(tmp_path: Path) -> None:
    """The suffix is matched without regard to case, so an upper-case `.TOML` is a supported one."""
    default_file = tmp_path / "DEFAULTS.TOML"
    default_file.write_text("a = 1\n", encoding="utf-8")

    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=default_file)

    assert config.as_dict() == {"a": 1}


@os_agnostic
@pytest.mark.parametrize("name", ["absent.toml", "absent.conf"])
def test_read_config_treats_a_missing_default_file_as_no_defaults(tmp_path: Path, name: str) -> None:
    """A `default_file` that does not exist stays optional, whatever its suffix: only a path that
    exists as something other than a readable configuration file is refused."""
    config = read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(tmp_path), default_file=tmp_path / name)

    assert config.as_dict() == {}


@os_agnostic
@pytest.mark.parametrize(("layer", "relative"), [("app", "config.toml"), ("host", None), ("user", "config.toml")])
def test_read_config_refuses_a_discovered_config_path_that_is_a_directory(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox, layer: str, relative: str | None
) -> None:
    """A directory where a layer's config file belongs refuses the load, as one at `default_file`
    does. The resolver used to pass a discovered path on only when it was a file, so the directory
    was skipped in silence and the configuration fell back to the layers below it."""
    sandbox.apply_env(monkeypatch)
    # The host file is named after the machine the resolver runs on, not a fixed test name.
    if relative is None:
        relative = f"{DefaultPathResolver(vendor=VENDOR, app=APP, slug=SLUG).hostname}.toml"
    placed = sandbox.write(layer, relative, content="")
    placed.unlink()
    placed.mkdir()

    with pytest.raises(LayerLoadError, match="is a directory, not a configuration file") as caught:
        read_config(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir))

    assert str(placed) in str(caught.value)


@os_agnostic
def test_a_table_declared_empty_and_filled_by_dotenv_reports_no_origin_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
    sandbox: LayeredSandbox,
    tmp_path: Path,
) -> None:
    """The defaults file declares the table empty and the .env fills it, so every value in it came
    from the .env. The table key used to keep the empty declaration's origin (defaults), while a
    table that was never empty has no origin of its own: the values carry it."""
    sandbox.apply_env(monkeypatch)
    default_file = tmp_path / "defaults.toml"
    default_file.write_text("[logging]\nconsole_styles = {}\n", encoding="utf-8")
    explicit_env = tmp_path / "custom.env"
    explicit_env.write_text('LOGGING__CONSOLE_STYLES={"DEBUG":"dim","ERROR":"bold red"}\n', encoding="utf-8")

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        default_file=default_file,
        dotenv_path=explicit_env,
    )

    assert config.get("logging.console_styles") == {"DEBUG": "dim", "ERROR": "bold red"}
    assert config.origin("logging.console_styles") is None
    debug = config.origin("logging.console_styles.DEBUG")
    assert debug is not None and debug["layer"] == "dotenv"


@os_agnostic
def test_env_var_overrides_one_array_element_end_to_end(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    """A prefixed env var with a numeric segment overrides one element of a file-defined array."""
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [[dataset]]
            name = "primary"
            dsn = "postgres://old"

            [[dataset]]
            name = "secondary"
            """
        ),
    )
    monkeypatch.setenv("CONFIG_KIT___DATASET__0__DSN", "postgres://new")

    result = read_config_raw(vendor=VENDOR, app=APP, slug=SLUG, start_dir=str(sandbox.start_dir))

    dataset = result.data["dataset"]  # type: ignore[index]
    assert isinstance(dataset, list)
    assert dataset[0]["dsn"] == "postgres://new"
    assert dataset[0]["name"] == "primary"
    assert dataset[1]["name"] == "secondary"
    assert result.provenance["dataset.0.dsn"]["layer"] == "env"
