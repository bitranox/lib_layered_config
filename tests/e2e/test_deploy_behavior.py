"""End-to-end behavior tests for deploy command conflict handling.

These tests verify the complete behavior of the deploy command when handling
file conflicts, including backup creation, UCF file generation, and JSON output
formatting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from lib_layered_config import cli
from tests.support import LayeredSandbox, create_layered_sandbox
from tests.support.os_markers import os_agnostic

VENDOR = "Acme"
APP = "Demo"
SLUG = "demo"


@pytest.fixture()
def sandbox(tmp_path: Path) -> LayeredSandbox:
    return create_layered_sandbox(tmp_path, vendor=VENDOR, app=APP, slug=SLUG)


def make_runner() -> CliRunner:
    return CliRunner()


def make_deploy_command(
    source: Path,
    *,
    targets: list[str] | None = None,
    force: bool = False,
    batch: bool = False,
) -> list[str]:
    """Build a deploy command with common options."""
    cmd = [
        "deploy",
        "--source",
        str(source),
        "--vendor",
        VENDOR,
        "--app",
        APP,
        "--slug",
        SLUG,
    ]
    for target in targets or ["app"]:
        cmd.extend(["--target", target])
    if force:
        cmd.append("--force")
    if batch:
        cmd.append("--batch")
    return cmd


# ---------------------------------------------------------------------------
# Behavior: First deploy creates files
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_first_run_creates_files_and_reports_created(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """When deploying to empty directories, files are created and reported."""
    source = tmp_path / "config.toml"
    source.write_text('[service]\nname = "test"\n', encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source, targets=["app"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "created" in output
    assert len(output["created"]) == 1
    # Verify file was actually created
    created_path = Path(output["created"][0])
    assert created_path.exists()
    assert "test" in created_path.read_text(encoding="utf-8")


@os_agnostic
def test_deploy_first_run_multiple_targets_creates_all(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Deploying to multiple targets creates files for each."""
    source = tmp_path / "config.toml"
    source.write_text("[settings]\nvalue = 1\n", encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source, targets=["app", "user"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert len(output.get("created", [])) == 2


# ---------------------------------------------------------------------------
# Behavior: Batch mode keeps existing and writes UCF
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_batch_mode_creates_ucf_for_different_content(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """With --batch and different content, existing files kept and UCF created."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[new]\nkey = 1\n", encoding="utf-8")
    source2.write_text("[new]\nkey = 2\n", encoding="utf-8")

    # First deploy
    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)

    # Second deploy with --batch and different content should create UCF
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, batch=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "kept" in output
    assert "ucf_files" in output
    assert len(output["kept"]) == 1
    assert len(output["ucf_files"]) == 1
    assert "created" not in output
    # Verify UCF file contains new content
    ucf_path = Path(output["ucf_files"][0])
    assert ucf_path.exists()
    assert "key = 2" in ucf_path.read_text(encoding="utf-8")


@os_agnostic
def test_deploy_batch_mode_preserves_original_content(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Batch mode does not modify the existing file content, but creates UCF."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[version]\nv = 1\n", encoding="utf-8")
    source2.write_text("[version]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    # Deploy v1
    first = runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    output1 = json.loads(first.output)
    target_path = Path(output1["created"][0])

    # Deploy v2 with --batch (should keep original, create UCF)
    result = runner.invoke(cli.cli, make_deploy_command(source2, batch=True), env=sandbox.env)
    output2 = json.loads(result.output)

    # Original content should still be v1
    assert "v = 1" in target_path.read_text(encoding="utf-8")
    # UCF file should contain v2
    ucf_path = Path(output2["ucf_files"][0])
    assert "v = 2" in ucf_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Behavior: Force mode creates backups and overwrites
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_force_mode_creates_backup_and_overwrites(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """With --force, existing files are backed up to .bak and overwritten."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[version]\nv = 1\n", encoding="utf-8")
    source2.write_text("[version]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    # Deploy v1
    first = runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    output1 = json.loads(first.output)
    target_path = Path(output1["created"][0])

    # Force deploy v2
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "overwritten" in output
    assert "backups" in output
    assert len(output["backups"]) == 1
    # Verify backup contains old content
    backup_path = Path(output["backups"][0])
    assert backup_path.exists()
    assert "v = 1" in backup_path.read_text(encoding="utf-8")
    # Verify target has new content
    assert "v = 2" in target_path.read_text(encoding="utf-8")


@os_agnostic
def test_deploy_force_mode_backup_has_bak_extension(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Backup files use the .bak extension."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nversion = 1\n", encoding="utf-8")
    source2.write_text("[test]\nversion = 2\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    backup_path = Path(output["backups"][0])
    assert backup_path.name.endswith(".bak")


# ---------------------------------------------------------------------------
# Behavior: Numbered suffixes for multiple operations
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_multiple_force_creates_numbered_backups(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Multiple force deploys create numbered backup files."""
    sources = [tmp_path / f"v{i}.toml" for i in range(4)]
    for i, src in enumerate(sources):
        src.write_text(f"[version]\nv = {i}\n", encoding="utf-8")

    runner = make_runner()
    # Initial deploy
    runner.invoke(cli.cli, make_deploy_command(sources[0]), env=sandbox.env)

    # Three force deploys
    backup_names = []
    for src in sources[1:]:
        result = runner.invoke(
            cli.cli,
            make_deploy_command(src, force=True),
            env=sandbox.env,
        )
        output = json.loads(result.output)
        backup_names.append(Path(output["backups"][0]).name)

    # Verify numbered suffixes
    assert backup_names[0] == "config.toml.bak"
    assert backup_names[1] == "config.toml.bak.1"
    assert backup_names[2] == "config.toml.bak.2"


# ---------------------------------------------------------------------------
# Behavior: JSON output format validation
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_json_output_structure_on_create(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """JSON output contains only 'created' key for new files."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\n", encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    # Only non-empty keys should be present
    assert "created" in output
    assert "overwritten" not in output
    assert "skipped" not in output
    assert "backups" not in output
    assert "ucf_files" not in output
    assert "kept" not in output


@os_agnostic
def test_deploy_json_output_structure_on_skip(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """JSON output contains only 'skipped' key when skipping."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source, batch=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    assert "skipped" in output
    assert "created" not in output


@os_agnostic
def test_deploy_json_output_structure_on_overwrite(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """JSON output contains 'overwritten' and 'backups' keys when forcing."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nv = 1\n", encoding="utf-8")
    source2.write_text("[test]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    assert "overwritten" in output
    assert "backups" in output
    assert len(output["overwritten"]) == len(output["backups"])


@os_agnostic
def test_deploy_json_output_structure_on_batch_keep(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """JSON output contains 'kept' and 'ucf_files' keys in batch mode with different content."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nv = 1\n", encoding="utf-8")
    source2.write_text("[test]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, batch=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    assert "kept" in output
    assert "ucf_files" in output
    assert len(output["kept"]) == len(output["ucf_files"])
    assert "created" not in output
    assert "overwritten" not in output
    assert "skipped" not in output


# ---------------------------------------------------------------------------
# Behavior: Force takes precedence over batch
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_force_overrides_batch_flag(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """When both --force and --batch are specified, force takes precedence."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nv = 1\n", encoding="utf-8")
    source2.write_text("[test]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True, batch=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    # Force should win - file should be overwritten, not skipped
    assert "overwritten" in output
    assert "skipped" not in output


# ---------------------------------------------------------------------------
# Behavior: Empty output when source equals destination
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_skips_when_source_equals_destination(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Deployment is skipped when source and destination are the same file."""
    # Create a file in the app layer location
    target = sandbox.roots["app"] / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[test]\n", encoding="utf-8")

    # Try to deploy the same file to the same location
    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(target, targets=["app"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    # Should have no results (empty JSON or only empty keys filtered out)
    output = json.loads(result.output) if result.output.strip() else {}
    # The file should not appear in any action category
    all_paths = output.get("created", []) + output.get("overwritten", []) + output.get("skipped", [])
    assert str(target) not in all_paths or len(all_paths) == 0


# ---------------------------------------------------------------------------
# Behavior: Smart skipping when content is identical
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_force_skips_when_content_identical(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """With --force, identical content is skipped without backup creation."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\nvalue = 42\n", encoding="utf-8")

    runner = make_runner()
    # First deploy creates the file
    runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)

    # Second deploy with --force but same content should skip
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source, force=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    # Should be skipped, not overwritten (no backup needed)
    assert "skipped" in output
    assert "overwritten" not in output
    assert "backups" not in output


@os_agnostic
def test_deploy_batch_skips_when_content_identical(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """With --batch, identical content is skipped."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\nvalue = 42\n", encoding="utf-8")

    runner = make_runner()
    # First deploy creates the file
    runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)

    # Second deploy with --batch and same content should skip
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source, batch=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "skipped" in output


@os_agnostic
def test_deploy_force_creates_backup_when_content_differs(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """With --force and different content, backup is created and file overwritten."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nvalue = 1\n", encoding="utf-8")
    source2.write_text("[test]\nvalue = 2\n", encoding="utf-8")

    runner = make_runner()
    # First deploy creates the file
    first = runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)
    output1 = json.loads(first.output)
    target_path = Path(output1["created"][0])

    # Second deploy with --force and different content should create backup
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "overwritten" in output
    assert "backups" in output
    # Verify backup contains old content
    backup_path = Path(output["backups"][0])
    assert "value = 1" in backup_path.read_text(encoding="utf-8")
    # Verify target has new content
    assert "value = 2" in target_path.read_text(encoding="utf-8")


@os_agnostic
def test_smart_skip_preserves_original_file_unchanged(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Smart skipping does not modify the original file in any way."""
    source = tmp_path / "config.toml"
    content = "[settings]\nkey = 'original'\n"
    source.write_text(content, encoding="utf-8")

    runner = make_runner()
    # First deploy
    first = runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)
    output1 = json.loads(first.output)
    target_path = Path(output1["created"][0])
    original_mtime = target_path.stat().st_mtime

    # Wait a tiny bit to ensure mtime would change if file was touched
    import time

    time.sleep(0.01)

    # Second deploy with same content (smart skip)
    runner.invoke(cli.cli, make_deploy_command(source, force=True), env=sandbox.env)

    # File should be completely untouched
    assert target_path.read_text(encoding="utf-8") == content
    assert target_path.stat().st_mtime == original_mtime


@os_agnostic
def test_smart_skip_detects_whitespace_differences(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Whitespace differences are detected and result in overwrite, not skip."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nvalue = 1\n", encoding="utf-8")
    source2.write_text("[test]\nvalue = 1\n\n", encoding="utf-8")  # Extra newline

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)

    # Deploy with whitespace difference should NOT be skipped
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    assert "overwritten" in output
    assert "skipped" not in output


@os_agnostic
def test_smart_skip_with_mixed_targets(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Smart skipping handles mixed scenarios: some targets skip, others create."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nv = 1\n", encoding="utf-8")
    source2.write_text("[test]\nv = 2\n", encoding="utf-8")

    runner = make_runner()
    # Deploy v1 to app target only
    runner.invoke(cli.cli, make_deploy_command(source1, targets=["app"]), env=sandbox.env)

    # Deploy v1 to both app and user - app should skip, user should create
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source1, targets=["app", "user"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    # App target should be skipped (identical content)
    assert "skipped" in output
    # User target should be created (new file)
    assert "created" in output


@os_agnostic
def test_smart_skip_no_backup_or_ucf_files_created(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Smart skipping does not create any .bak or .ucf files."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\ndata = 123\n", encoding="utf-8")

    runner = make_runner()
    first = runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)
    output1 = json.loads(first.output)
    target_path = Path(output1["created"][0])
    target_dir = target_path.parent

    # Count files before smart skip
    files_before = set(target_dir.iterdir())

    # Multiple force deploys with identical content
    for _ in range(3):
        runner.invoke(
            cli.cli,
            make_deploy_command(source, force=True),
            env=sandbox.env,
        )

    # No new files should be created
    files_after = set(target_dir.iterdir())
    assert files_before == files_after


@os_agnostic
def test_smart_skip_consecutive_deploys_all_skip(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Multiple consecutive deploys with identical content all report skipped."""
    source = tmp_path / "config.toml"
    source.write_text("[test]\nkey = 'value'\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)

    # Run 5 consecutive deploys
    for i in range(5):
        result = runner.invoke(
            cli.cli,
            make_deploy_command(source, force=True),
            env=sandbox.env,
        )
        output = json.loads(result.output)
        assert "skipped" in output, f"Deploy {i + 1} should have skipped"
        assert "overwritten" not in output
        assert "backups" not in output


@os_agnostic
def test_smart_skip_then_change_then_skip(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Smart skip, then actual change, then smart skip again."""
    source1 = tmp_path / "v1.toml"
    source2 = tmp_path / "v2.toml"
    source1.write_text("[test]\nversion = 1\n", encoding="utf-8")
    source2.write_text("[test]\nversion = 2\n", encoding="utf-8")

    runner = make_runner()
    # Initial deploy
    runner.invoke(cli.cli, make_deploy_command(source1), env=sandbox.env)

    # Smart skip (same content)
    result1 = runner.invoke(
        cli.cli,
        make_deploy_command(source1, force=True),
        env=sandbox.env,
    )
    assert "skipped" in json.loads(result1.output)

    # Actual change (different content)
    result2 = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )
    output2 = json.loads(result2.output)
    assert "overwritten" in output2
    assert "backups" in output2

    # Smart skip again (same as current content)
    result3 = runner.invoke(
        cli.cli,
        make_deploy_command(source2, force=True),
        env=sandbox.env,
    )
    assert "skipped" in json.loads(result3.output)


@os_agnostic
def test_smart_skip_json_output_only_contains_skipped(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """JSON output for smart skip contains only 'skipped' key, no empty arrays."""
    source = tmp_path / "config.toml"
    source.write_text("[data]\nx = 1\n", encoding="utf-8")

    runner = make_runner()
    runner.invoke(cli.cli, make_deploy_command(source), env=sandbox.env)

    result = runner.invoke(
        cli.cli,
        make_deploy_command(source, force=True),
        env=sandbox.env,
    )

    output = json.loads(result.output)
    # Only skipped should be present
    assert "skipped" in output
    assert len(output["skipped"]) == 1
    # Other keys should not be present at all
    assert "created" not in output
    assert "overwritten" not in output
    assert "backups" not in output
    assert "ucf_files" not in output
    assert "kept" not in output


# ---------------------------------------------------------------------------
# Behavior: .d directory deployment
# ---------------------------------------------------------------------------


@os_agnostic
def test_deploy_with_dot_d_directory_copies_both_base_and_dot_d_files(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Deploying a config with .d directory copies both base file and .d contents."""
    # Create source with .d directory
    source = tmp_path / "config.toml"
    source.write_text('[base]\nkey = "value"\n', encoding="utf-8")
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()
    (dot_d / "10-db.toml").write_text('[db]\nhost = "localhost"\n', encoding="utf-8")
    (dot_d / "20-cache.toml").write_text("[cache]\nenabled = true\n", encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source, targets=["app"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)

    # Base file should be created
    assert "created" in output
    assert len(output["created"]) == 1
    base_dest = Path(output["created"][0])
    assert base_dest.exists()
    assert 'key = "value"' in base_dest.read_text(encoding="utf-8")

    # .d files should also be created
    assert "dot_d_created" in output
    assert len(output["dot_d_created"]) == 2

    # Verify .d files exist at destination
    dest_dot_d = base_dest.with_suffix(".d")
    assert dest_dot_d.is_dir()
    assert (dest_dot_d / "10-db.toml").exists()
    assert (dest_dot_d / "20-cache.toml").exists()
    assert 'host = "localhost"' in (dest_dot_d / "10-db.toml").read_text(encoding="utf-8")


@os_agnostic
def test_deploy_dot_d_force_mode_creates_backups(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Force mode creates backups for .d files with different content."""
    # Create source with .d directory
    source1 = tmp_path / "v1" / "config.toml"
    source1.parent.mkdir()
    source1.write_text("[base]\nv = 1\n", encoding="utf-8")
    dot_d1 = tmp_path / "v1" / "config.d"
    dot_d1.mkdir()
    (dot_d1 / "10-extra.toml").write_text("[extra]\nv = 1\n", encoding="utf-8")

    source2 = tmp_path / "v2" / "config.toml"
    source2.parent.mkdir()
    source2.write_text("[base]\nv = 2\n", encoding="utf-8")
    dot_d2 = tmp_path / "v2" / "config.d"
    dot_d2.mkdir()
    (dot_d2 / "10-extra.toml").write_text("[extra]\nv = 2\n", encoding="utf-8")

    runner = make_runner()

    # First deploy
    runner.invoke(cli.cli, make_deploy_command(source1, targets=["app"]), env=sandbox.env)

    # Second deploy with --force
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source2, targets=["app"], force=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)

    # Both base and .d files should be overwritten with backups
    assert "overwritten" in output
    assert "backups" in output
    assert "dot_d_overwritten" in output
    assert "dot_d_backups" in output


@os_agnostic
def test_deploy_dot_d_smart_skip_identical_content(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Smart skip works for .d files with identical content."""
    source = tmp_path / "config.toml"
    source.write_text("[base]\nkey = 1\n", encoding="utf-8")
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()
    (dot_d / "10-extra.toml").write_text("[extra]\nkey = 1\n", encoding="utf-8")

    runner = make_runner()

    # First deploy
    runner.invoke(cli.cli, make_deploy_command(source, targets=["app"]), env=sandbox.env)

    # Second deploy with same content - should skip
    result = runner.invoke(
        cli.cli,
        make_deploy_command(source, targets=["app"], force=True),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)

    # Both base and .d files should be skipped
    assert "skipped" in output
    assert "dot_d_skipped" in output


@os_agnostic
def test_deploy_dot_d_includes_non_config_files(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """All files in .d directory are deployed, including non-config files."""
    source = tmp_path / "config.toml"
    source.write_text("[base]\n", encoding="utf-8")
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()
    (dot_d / "10-valid.toml").write_text("[valid]\n", encoding="utf-8")
    (dot_d / "README.md").write_text("# Configuration docs\n", encoding="utf-8")
    (dot_d / "notes.txt").write_text("Notes about config\n", encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source, targets=["app"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)

    # All 3 .d files should be created (config + non-config files)
    assert len(output.get("dot_d_created", [])) == 3

    # Verify ALL files were copied (deployment preserves non-config files)
    base_dest = Path(output["created"][0])
    dest_dot_d = base_dest.with_suffix(".d")
    assert (dest_dot_d / "10-valid.toml").exists()
    assert (dest_dot_d / "README.md").exists()
    assert (dest_dot_d / "notes.txt").exists()
    assert "Configuration docs" in (dest_dot_d / "README.md").read_text(encoding="utf-8")


@os_agnostic
def test_deploy_dot_d_mixed_formats(
    tmp_path: Path,
    sandbox: LayeredSandbox,
) -> None:
    """Deploying .d directory with mixed formats (TOML, YAML, JSON) works."""
    source = tmp_path / "config.toml"
    source.write_text("[base]\n", encoding="utf-8")
    dot_d = tmp_path / "config.d"
    dot_d.mkdir()
    (dot_d / "10-toml.toml").write_text("[toml]\nx = 1\n", encoding="utf-8")
    (dot_d / "20-yaml.yaml").write_text("yaml:\n  y: 2\n", encoding="utf-8")
    (dot_d / "30-json.json").write_text('{"json": {"z": 3}}\n', encoding="utf-8")

    result = make_runner().invoke(
        cli.cli,
        make_deploy_command(source, targets=["app"]),
        env=sandbox.env,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)

    # All 3 .d files should be created
    assert len(output.get("dot_d_created", [])) == 3

    # Verify all formats exist at destination
    base_dest = Path(output["created"][0])
    dest_dot_d = base_dest.with_suffix(".d")
    assert (dest_dot_d / "10-toml.toml").exists()
    assert (dest_dot_d / "20-yaml.yaml").exists()
    assert (dest_dot_d / "30-json.json").exists()
