"""DeployMode: the one rule for a permission mode the deploy path may apply."""

from __future__ import annotations

import ast
import inspect
import sys

import pytest

from lib_layered_config.domain import deploy_mode as module
from lib_layered_config.domain.deploy_mode import DeployMode, DeployModeError, ModeKind, parse_mode_text
from lib_layered_config.domain.errors import ConfigError
from lib_layered_config.domain.permissions import LAYER_PERMISSIONS
from tests.support.os_markers import os_agnostic

D = ModeKind.DIRECTORY
F = ModeKind.FILE


@os_agnostic
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0o750", 0o750),
        ("750", 0o750),
        ("0", 0),
        ("000640", 0o640),
        ("7777", 0o7777),
        ("0000750", 0o750),
        ("0o0000000750", 0o750),
    ],
)
def test_parse_mode_text_reads_a_plain_octal_literal(text: str, expected: int) -> None:
    assert parse_mode_text(text) == expected


@os_agnostic
@pytest.mark.parametrize(
    "text",
    ["-1", "7_5_0", " 750", "750 ", "0O750", "0x1ed", "", "0o", "8", "\u0667\u0665\u0660", "750\n"],
)
def test_parse_mode_text_refuses_anything_but_a_plain_octal_literal(text: str) -> None:
    with pytest.raises(DeployModeError, match="is not a plain octal literal"):
        parse_mode_text(text)


@os_agnostic
@pytest.mark.parametrize("text", ["10000", "0o10000", "00010000"])
def test_parse_mode_text_refuses_a_value_above_0o7777(text: str) -> None:
    with pytest.raises(DeployModeError, match=r"is outside 0\.\.0o7777$"):
        parse_mode_text(text)


@os_agnostic
def test_a_long_refused_text_is_shortened_in_the_message() -> None:
    with pytest.raises(DeployModeError) as caught:
        parse_mode_text("7" * 10_000)
    assert len(str(caught.value)) < 200


@os_agnostic
@pytest.mark.parametrize(
    ("value", "kind"),
    [(0o755, D), (0o750, D), (0o700, D), (0o644, F), (0o640, F), (0o600, F)],
)
def test_safe_modes_are_accepted(value: int, kind: ModeKind) -> None:
    assert DeployMode(value, kind).value == value


@os_agnostic
@pytest.mark.parametrize(
    ("value", "kind", "fragments"),
    [
        (-1, D, ["mode -1 is outside 0..0o7777"]),
        (0o10000, F, ["mode 4096 is outside 0..0o7777"]),
        (
            0o7777,
            D,
            [
                "unsafe directory mode 0o7777",
                "the setuid bit (0o4000)",
                "the setgid bit (0o2000)",
                "the sticky bit (0o1000)",
                "group write (0o020)",
                "world write (0o002)",
            ],
        ),
        (0o770, D, ["group write (0o020)"]),
        (0o757, D, ["world write (0o002)"]),
        (0o500, D, ["no owner rwx (0o700 is required)"]),
        (444, F, ["unsafe file mode 0o674", "group write (0o020)", "an execute bit on a file (0o10)"]),
        (0o755, F, ["an execute bit on a file (0o111)"]),
        (0o400, F, ["no owner rw (0o600 is required)"]),
    ],
)
def test_unsafe_modes_are_refused_naming_every_bit(value: int, kind: ModeKind, fragments: list[str]) -> None:
    with pytest.raises(DeployModeError) as caught:
        DeployMode(value, kind)
    for fragment in fragments:
        assert fragment in str(caught.value)


@os_agnostic
@pytest.mark.parametrize(("value", "type_name"), [(True, "bool"), (False, "bool"), (1.0, "float"), ("0o640", "str")])
def test_a_mode_must_be_an_int(value: object, type_name: str) -> None:
    with pytest.raises(DeployModeError, match=f"a mode must be an int, got {type_name}$"):
        DeployMode(value, F)  # pyright excludes tests/; the wrong type is the point


@os_agnostic
@pytest.mark.parametrize(("value", "reading"), [(444, "444 = 0o674"), (416, "416 = 0o640"), (-1, "-1 = -0o1")])
def test_a_config_integer_is_refused_with_its_decimal_reading(value: int, reading: str) -> None:
    with pytest.raises(DeployModeError) as caught:
        DeployMode.from_config_value(value, F)
    message = str(caught.value)
    assert f"a bare integer is read as decimal ({reading})" in message
    # The quotes belong to a file; a shell strips them, so the environment spelling is named too (re-review m5),
    # and a runtime override such as an application's --set (m-a). Controller ruling on review finding M-3: the
    # library has no --set option of its own, so the hint must not name one as if it did.
    assert message.endswith(
        'write the mode as an octal string: "0o640" (quoted) in a file, 0o640 in the environment '
        "or a runtime override (such as an application's --set)"
    )


@os_agnostic
@pytest.mark.parametrize(
    ("value", "type_name"), [(6.4, "float"), (True, "bool"), (None, "NoneType"), (["0o640"], "list")]
)
def test_a_config_value_of_another_type_is_refused(value: object, type_name: str) -> None:
    with pytest.raises(DeployModeError, match=f"got {type_name}$"):
        DeployMode.from_config_value(value, F)


@os_agnostic
def test_a_config_string_goes_through_the_text_rule() -> None:
    assert DeployMode.from_config_value("0o640", F).value == 0o640
    with pytest.raises(DeployModeError, match="not a plain octal literal"):
        DeployMode.from_config_value("7_5_0", D)


@os_agnostic
def test_str_is_the_octal_literal() -> None:
    assert str(DeployMode(0o750, D)) == "0o750"


@os_agnostic
def test_the_refusal_is_a_config_error_and_a_value_error() -> None:
    assert issubclass(DeployModeError, ConfigError)
    assert issubclass(DeployModeError, ValueError)


@os_agnostic
@pytest.mark.parametrize("layer", sorted(LAYER_PERMISSIONS))
def test_every_built_in_layer_default_passes_the_rule(layer: str) -> None:
    assert DeployMode(LAYER_PERMISSIONS[layer]["dir"], D).kind is D
    assert DeployMode(LAYER_PERMISSIONS[layer]["file"], F).kind is F


@os_agnostic
def test_a_huge_out_of_range_int_is_refused_as_a_deploy_mode_error_not_a_bare_value_error() -> None:
    """A 5000-digit int trips CPython's int-to-str conversion limit; the message must still be
    a DeployModeError of bounded length, never a bare ValueError from the f-string itself."""
    huge = 10**5000
    with pytest.raises(DeployModeError) as caught:
        DeployMode(huge, D)
    message = str(caught.value)
    assert len(message) < 200
    assert "outside 0.." in message


@os_agnostic
def test_a_huge_config_integer_is_refused_as_a_deploy_mode_error_not_a_bare_value_error() -> None:
    huge = 10**5000
    with pytest.raises(DeployModeError) as caught:
        DeployMode.from_config_value(huge, F)
    message = str(caught.value)
    assert len(message) < 200
    assert "a bare integer is read as decimal" in message


@os_agnostic
def test_a_4000_digit_out_of_range_int_is_refused_with_a_bounded_message() -> None:
    """4000 decimal digits sits under CPython's default 4300-digit int-to-str conversion limit, so
    the old sys.get_int_max_str_digits()-based decision treated it as "safe" and stringified it in
    full, producing a multi-thousand-character message. The bit_length()-based decision must bound
    it the same way as a 5000-digit value."""
    huge = 10**4000
    with pytest.raises(DeployModeError) as caught:
        DeployMode(huge, D)
    message = str(caught.value)
    assert len(message) < 200
    assert "outside 0.." in message


@os_agnostic
def test_a_4000_digit_config_integer_is_refused_with_a_bounded_message() -> None:
    huge = 10**4000
    with pytest.raises(DeployModeError) as caught:
        DeployMode.from_config_value(huge, F)
    message = str(caught.value)
    assert len(message) < 200
    assert "a bare integer is read as decimal" in message


@os_agnostic
def test_deploy_mode_module_does_not_import_sys() -> None:
    """G1: the digit-limit decision must not depend on the interpreter's int-to-str conversion
    limit at all, so the module must not even import sys."""
    tree = ast.parse(inspect.getsource(module))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "sys" not in imported_names


@os_agnostic
def test_a_huge_int_is_still_bounded_with_get_int_max_str_digits_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the behaviour does not depend on sys.get_int_max_str_digits by removing it outright
    (a legitimate external-edge patch: the attribute itself, not this module's internals)."""
    monkeypatch.delattr(sys, "get_int_max_str_digits", raising=True)
    huge = 10**5000
    with pytest.raises(DeployModeError) as caught:
        DeployMode(huge, D)
    message = str(caught.value)
    assert len(message) < 200
    assert "outside 0.." in message


@os_agnostic
def test_messages_stay_bounded_with_the_digit_limit_disabled() -> None:
    """PYTHONINTMAXSTRDIGITS=0 semantics: with the conversion limit disabled, the old
    sys-based decision treated every int as "safe" and stringified it in full. The
    bit_length()-based decision must still bound the message."""
    original_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        for huge in (10**5000, 10**4000):
            with pytest.raises(DeployModeError) as caught:
                DeployMode(huge, D)
            assert len(str(caught.value)) < 200
            with pytest.raises(DeployModeError) as caught_config:
                DeployMode.from_config_value(huge, F)
            assert len(str(caught_config.value)) < 200
    finally:
        sys.set_int_max_str_digits(original_limit)
