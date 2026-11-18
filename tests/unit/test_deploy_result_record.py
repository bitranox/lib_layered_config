"""``DeployResult`` is a frozen record whose invalid states cannot be built.

``backup_path`` belongs to an ``OVERWRITTEN`` result only and ``ucf_path`` to a ``KEPT`` one;
``action`` is a ``DeployAction``; ``dot_d_results`` is stored as a tuple whatever sequence a caller
passes. Until 9.0.0 the record was mutable, so ``r.action = "created"`` made it compare unequal to
``DeployAction.CREATED`` (DATA-PERF-REVIEW.md finding 8).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, cast

import pytest

from lib_layered_config import DeployAction, DeployResult, ValidationError, deploy_config, deployed_before_failure
from tests.support import create_layered_sandbox
from tests.support.os_markers import os_agnostic

_DESTINATION = Path("/opt/acme/config.toml")


@os_agnostic
def test_a_result_cannot_be_changed() -> None:
    result = DeployResult(destination=_DESTINATION, action=DeployAction.CREATED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast("Any", result).action = DeployAction.SKIPPED


@os_agnostic
@pytest.mark.parametrize("action", [a for a in DeployAction if a is not DeployAction.OVERWRITTEN])
def test_a_backup_path_belongs_to_an_overwritten_result_only(action: DeployAction) -> None:
    with pytest.raises(ValidationError, match=r"backup_path is set only for an OVERWRITTEN result"):
        DeployResult(destination=_DESTINATION, action=action, backup_path=Path("/opt/acme/config.toml.bak"))


@os_agnostic
@pytest.mark.parametrize("action", [a for a in DeployAction if a is not DeployAction.KEPT])
def test_a_ucf_path_belongs_to_a_kept_result_only(action: DeployAction) -> None:
    with pytest.raises(ValidationError, match=r"ucf_path is set only for a KEPT result"):
        DeployResult(destination=_DESTINATION, action=action, ucf_path=Path("/opt/acme/config.toml.ucf"))


@os_agnostic
def test_the_action_must_be_a_deploy_action() -> None:
    with pytest.raises(ValidationError, match=r"action must be a DeployAction, got str"):
        DeployResult(destination=_DESTINATION, action=cast("Any", "created"))


@os_agnostic
def test_dot_d_results_are_stored_as_a_tuple() -> None:
    inner = DeployResult(destination=Path("/opt/acme/config.d/10-a.toml"), action=DeployAction.CREATED)
    result = DeployResult(destination=_DESTINATION, action=DeployAction.CREATED, dot_d_results=[inner])
    assert result.dot_d_results == (inner,)
    assert DeployResult(destination=_DESTINATION, action=DeployAction.CREATED).dot_d_results == ()


def _source_with_dot_d(tmp_path: Path, names: list[str]) -> Path:
    source = tmp_path / "src" / "config.toml"
    (source.parent / "config.d").mkdir(parents=True)
    source.write_text("a = 1\n", encoding="utf-8")
    for name in names:
        (source.parent / "config.d" / name).write_text("b = 2\n", encoding="utf-8")
    return source


@os_agnostic
def test_a_deploy_returns_frozen_results_with_their_dot_d_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_layered_sandbox(tmp_path / "layers", vendor="Acme", app="Demo", slug="demo").apply_env(monkeypatch)
    source = _source_with_dot_d(tmp_path, ["10-a.toml", "20-b.toml"])

    (result,) = deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"])

    assert isinstance(result.dot_d_results, tuple)
    assert [r.destination.name for r in result.dot_d_results] == ["10-a.toml", "20-b.toml"]


class _DeclinedError(Exception):
    """What the test's conflict resolver raises: a prompt the user declined."""


def _decline(path: Path) -> DeployAction:
    raise _DeclinedError(str(path))


@os_agnostic
def test_a_failure_in_the_dot_d_copies_still_reports_the_copies_written_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = create_layered_sandbox(tmp_path / "layers", vendor="Acme", app="Demo", slug="demo")
    sandbox.apply_env(monkeypatch)
    source = _source_with_dot_d(tmp_path, ["10-a.toml", "20-b.toml"])
    user_dot_d = sandbox.roots["user"] / "config.d"
    user_dot_d.mkdir(parents=True)
    (user_dot_d / "20-b.toml").write_text("other = 3\n", encoding="utf-8")  # differs: the resolver is asked

    with pytest.raises(_DeclinedError) as caught:
        deploy_config(source, vendor="Acme", app="Demo", slug="demo", targets=["user"], conflict_resolver=_decline)

    (written,) = deployed_before_failure(caught.value)
    assert written.action is DeployAction.CREATED
    assert isinstance(written.dot_d_results, tuple)
    assert [r.destination.name for r in written.dot_d_results] == ["10-a.toml"]
