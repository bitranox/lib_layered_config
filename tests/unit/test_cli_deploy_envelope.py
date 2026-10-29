"""The deploy command's JSON envelope: its keys, their order and each list's order stay fixed."""

from __future__ import annotations

import json
from pathlib import Path

from lib_layered_config.cli.deploy import _format_results
from lib_layered_config.examples.deploy import DeployAction, DeployResult
from tests.support.os_markers import os_agnostic

_ROOT = Path("/opt/acme")


def _result(
    name: str,
    action: DeployAction,
    *,
    backup: str | None = None,
    ucf: str | None = None,
    dot_d: list[DeployResult] | None = None,
) -> DeployResult:
    return DeployResult(
        destination=_ROOT / name,
        action=action,
        backup_path=None if backup is None else _ROOT / backup,
        ucf_path=None if ucf is None else _ROOT / ucf,
        dot_d_results=[] if dot_d is None else dot_d,
    )


def _quoted(name: str) -> str:
    """The JSON string for a path under the root, as this platform spells the path."""
    return json.dumps(str(_ROOT / name))


def _render(template: str) -> str:
    """Replace each ``@name@`` in *template* with that path's JSON string."""
    pieces = template.split("@")
    return "".join(_quoted(piece) if index % 2 else piece for index, piece in enumerate(pieces))


#: Captured from the envelope as it was built before the section records (one dict filled under
#: prefixed keys): the main lists first, then the ``.d`` lists, each in deploy order across every
#: destination, and an empty list left out.
_FULL_ENVELOPE = """{
  "created": [
    @new.toml@,
    @second.toml@
  ],
  "overwritten": [
    @over.toml@
  ],
  "kept": [
    @ucf.toml@
  ],
  "skipped": [
    @skip.toml@
  ],
  "backups": [
    @over.toml.bak@
  ],
  "ucf_files": [
    @ucf.toml.ucf@
  ],
  "dot_d_created": [
    @a.d/10.toml@,
    @b.d/10.toml@
  ],
  "dot_d_overwritten": [
    @a.d/20.toml@,
    @b.d/20.toml@
  ],
  "dot_d_kept": [
    @a.d/30.toml@
  ],
  "dot_d_skipped": [
    @b.d/40.toml@
  ],
  "dot_d_backups": [
    @a.d/20.toml.bak@,
    @b.d/20.toml.bak@
  ],
  "dot_d_ucf_files": [
    @a.d/30.toml.ucf@
  ]
}"""


def _results_with_every_list_filled() -> list[DeployResult]:
    first_dot_d = [
        _result("a.d/10.toml", DeployAction.CREATED),
        _result("a.d/20.toml", DeployAction.OVERWRITTEN, backup="a.d/20.toml.bak"),
        _result("a.d/30.toml", DeployAction.KEPT, ucf="a.d/30.toml.ucf"),
    ]
    second_dot_d = [
        _result("b.d/40.toml", DeployAction.SKIPPED),
        _result("b.d/10.toml", DeployAction.CREATED),
        _result("b.d/20.toml", DeployAction.OVERWRITTEN, backup="b.d/20.toml.bak"),
    ]
    return [
        _result("ucf.toml", DeployAction.KEPT, ucf="ucf.toml.ucf", dot_d=first_dot_d),
        _result("new.toml", DeployAction.CREATED),
        _result("over.toml", DeployAction.OVERWRITTEN, backup="over.toml.bak", dot_d=second_dot_d),
        _result("skip.toml", DeployAction.SKIPPED),
        _result("second.toml", DeployAction.CREATED),
    ]


@os_agnostic
def test_envelope_with_every_list_filled_keeps_its_keys_and_order() -> None:
    assert _format_results(_results_with_every_list_filled()) == _render(_FULL_ENVELOPE)


@os_agnostic
def test_envelope_leaves_out_every_empty_list() -> None:
    expected = _render('{\n  "created": [\n    @only.toml@\n  ]\n}')

    assert _format_results([_result("only.toml", DeployAction.CREATED)]) == expected


@os_agnostic
def test_envelope_of_no_results_is_an_empty_object() -> None:
    assert _format_results([]) == "{}"


@os_agnostic
def test_envelope_with_only_dot_d_results_has_only_prefixed_keys() -> None:
    results = [
        _result(
            "same.toml",
            DeployAction.SKIPPED,
            dot_d=[_result("c.d/10.toml", DeployAction.KEPT, ucf="c.d/10.toml.ucf")],
        )
    ]
    expected = _render(
        '{\n  "skipped": [\n    @same.toml@\n  ],\n'
        '  "dot_d_kept": [\n    @c.d/10.toml@\n  ],\n'
        '  "dot_d_ucf_files": [\n    @c.d/10.toml.ucf@\n  ]\n}'
    )

    assert _format_results(results) == expected
