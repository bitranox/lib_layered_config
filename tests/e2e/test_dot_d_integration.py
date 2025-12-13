"""End-to-end tests for .d directory expansion integration.

Verify that .d directories are correctly discovered, loaded, and merged
at all configuration layers (defaults, app, host, user).

Naming convention: config.toml → config.d (not config.toml.d)
This allows mixed formats (TOML, YAML, JSON) in the same .d directory.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from lib_layered_config import read_config, read_config_raw
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

VENDOR = "Acme"
APP = "DotDTest"
SLUG = "dot-d-test"


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


@os_agnostic
def test_read_config_merges_dot_d_directory(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """Files from config.d are merged into the configuration."""
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [database]
            host = "localhost"
            port = 5432
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/10-override.toml",
        content=dedent(
            """
            [database]
            host = "db.example.com"
            """
        ),
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("database.host") == "db.example.com"
    assert config.get("database.port") == 5432


@os_agnostic
def test_read_config_dot_d_override_precedence(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """Later .d files override earlier ones (lexicographic order)."""
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
        "config.d/10-first.toml",
        content=dedent(
            """
            [service]
            timeout = 10
            retries = 3
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/20-second.toml",
        content=dedent(
            """
            [service]
            timeout = 15
            """
        ),
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("service.timeout") == 15
    assert config.get("service.retries") == 3


@os_agnostic
def test_read_config_dot_d_provenance_tracks_individual_files(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    """Provenance tracks which .d file provided each value."""
    sandbox.apply_env(monkeypatch)
    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [app]
            name = "base"
            """
        ),
    )
    dot_d_file = sandbox.write(
        "app",
        "config.d/10-extra.toml",
        content=dedent(
            """
            [app]
            version = "1.0"
            """
        ),
    )

    result = read_config_raw(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert result.provenance["app.version"]["path"] == str(dot_d_file)
    assert result.provenance["app.version"]["layer"] == "app"


@os_agnostic
def test_read_config_dot_d_works_for_default_file(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox, tmp_path: Path
) -> None:
    """The default_file parameter also supports .d expansion."""
    sandbox.apply_env(monkeypatch)

    defaults = tmp_path / "defaults.toml"
    defaults.write_text(
        dedent(
            """
            [defaults]
            base = true
            """
        ),
        encoding="utf-8",
    )

    defaults_d = tmp_path / "defaults.d"  # defaults.toml → defaults.d
    defaults_d.mkdir()
    (defaults_d / "10-extra.toml").write_text(
        dedent(
            """
            [defaults]
            extra = "from-dot-d"
            """
        ),
        encoding="utf-8",
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
        default_file=defaults,
    )

    assert config.get("defaults.base") is True
    assert config.get("defaults.extra") == "from-dot-d"


@os_agnostic
def test_read_config_dot_d_only_without_base_file(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """Config loads from .d directory even when base file is missing."""
    sandbox.apply_env(monkeypatch)

    (sandbox.roots["app"] / "config.d").mkdir(parents=True)
    sandbox.write(
        "app",
        "config.d/10-only.toml",
        content=dedent(
            """
            [orphan]
            key = "value"
            """
        ),
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("orphan.key") == "value"


@os_agnostic
def test_read_config_dot_d_mixed_formats(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """The .d directory can contain mixed TOML, YAML, and JSON files."""
    sandbox.apply_env(monkeypatch)

    sandbox.write(
        "app",
        "config.toml",
        content=dedent(
            """
            [base]
            format = "toml"
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/10-yaml.yaml",
        content=dedent(
            """
            yaml:
              enabled: true
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/20-json.json",
        content='{"json": {"count": 42}}\n',
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("base.format") == "toml"
    assert config.get("yaml.enabled") is True
    assert config.get("json.count") == 42


@os_agnostic
def test_read_config_dot_d_user_layer_overrides_app_layer(
    monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox
) -> None:
    """User layer .d files override app layer .d files."""
    sandbox.apply_env(monkeypatch)

    sandbox.write(
        "app",
        "config.d/10-db.toml",
        content=dedent(
            """
            [database]
            host = "app-db"
            port = 5432
            """
        ),
    )
    sandbox.write(
        "user",
        "config.d/10-db.toml",
        content=dedent(
            """
            [database]
            host = "user-db"
            """
        ),
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("database.host") == "user-db"
    assert config.get("database.port") == 5432


@os_agnostic
def test_read_config_dot_d_ignores_non_config_files(monkeypatch: pytest.MonkeyPatch, sandbox: LayeredSandbox) -> None:
    """Non-config files in .d directory are ignored."""
    sandbox.apply_env(monkeypatch)

    sandbox.write(
        "app",
        "config.d/10-valid.toml",
        content=dedent(
            """
            [valid]
            key = "value"
            """
        ),
    )
    sandbox.write(
        "app",
        "config.d/README.md",
        content="# This should be ignored\n",
    )
    sandbox.write(
        "app",
        "config.d/notes.txt",
        content="This should also be ignored\n",
    )

    config = read_config(
        vendor=VENDOR,
        app=APP,
        slug=SLUG,
        start_dir=str(sandbox.start_dir),
    )

    assert config.get("valid.key") == "value"
    assert config.as_dict() == {"valid": {"key": "value"}}
