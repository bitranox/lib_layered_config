"""App-declared not-sensitive keys: the value object and the masking it governs."""

from __future__ import annotations

import re
from typing import cast

import pytest

from lib_layered_config.domain.redaction import (
    REDACTED_PLACEHOLDER,
    NotSensitiveKeys,
    is_sensitive_at,
    redact_mapping,
)
from tests.support.os_markers import os_agnostic


@os_agnostic
def test_a_declared_path_is_shown_while_an_undeclared_secret_stays_masked() -> None:
    data = {"performance": {"max_token_bytes": 4096}, "db": {"password": "s3cret"}}

    redacted = redact_mapping(data, not_sensitive=["performance.max_token_bytes"])

    assert redacted == {"performance": {"max_token_bytes": 4096}, "db": {"password": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_without_a_declaration_masking_is_unchanged() -> None:
    redacted = redact_mapping({"performance": {"max_token_bytes": 4096}})

    assert redacted == {"performance": {"max_token_bytes": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_a_declaration_covers_only_its_own_path() -> None:
    data = {"performance": {"max_token_bytes": 1}, "limits": {"max_token_bytes": 2}}

    redacted = redact_mapping(data, not_sensitive=["performance.max_token_bytes"])

    assert redacted == {"performance": {"max_token_bytes": 1}, "limits": {"max_token_bytes": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_paths_match_case_insensitively() -> None:
    redacted = redact_mapping({"Performance": {"MAX_TOKEN_BYTES": 1}}, not_sensitive=["performance.max_token_bytes"])

    assert redacted == {"Performance": {"MAX_TOKEN_BYTES": 1}}


@os_agnostic
def test_a_list_item_is_addressed_by_the_list_path_without_an_index() -> None:
    data = {"servers": [{"api_token": "t1", "auth_token_ttl": 60}, {"auth_token_ttl": 30}]}

    redacted = redact_mapping(data, not_sensitive=["servers.auth_token_ttl"])

    assert redacted == {"servers": [{"api_token": REDACTED_PLACEHOLDER, "auth_token_ttl": 60}, {"auth_token_ttl": 30}]}


@os_agnostic
def test_declaring_a_child_does_not_unmask_a_masked_ancestor() -> None:
    redacted = redact_mapping({"credentials": {"user": "alice"}}, not_sensitive=["credentials.user"])

    assert redacted == {"credentials": REDACTED_PLACEHOLDER}


@os_agnostic
def test_declaring_a_section_unmasks_it_while_its_own_secrets_stay_masked() -> None:
    data = {"credentials": {"user": "alice", "password": "s3cret"}}

    redacted = redact_mapping(data, not_sensitive=["credentials"])

    assert redacted == {"credentials": {"user": "alice", "password": REDACTED_PLACEHOLDER}}


@os_agnostic
def test_a_path_that_matches_nothing_changes_nothing() -> None:
    redacted = redact_mapping({"api_token": "t"}, not_sensitive=["no.such.key"])

    assert redacted == {"api_token": REDACTED_PLACEHOLDER}


@os_agnostic
def test_a_bare_string_is_refused_because_it_would_declare_its_characters() -> None:
    with pytest.raises(TypeError, match="not a single str"):
        NotSensitiveKeys.of("performance.max_token_bytes")


@os_agnostic
def test_a_non_string_entry_is_refused() -> None:
    with pytest.raises(TypeError, match="got int"):
        NotSensitiveKeys.of(cast("list[str]", [42]))


@os_agnostic
@pytest.mark.parametrize("entry", ["", "a..b", ".a", "a."])
def test_an_empty_path_or_segment_is_refused_naming_the_entry(entry: str) -> None:
    with pytest.raises(ValueError, match=re.escape(repr(entry))):
        NotSensitiveKeys.of([entry])


@os_agnostic
def test_of_passes_an_instance_through_and_maps_none_to_none() -> None:
    keys = NotSensitiveKeys.of(["a.b"])

    assert NotSensitiveKeys.of(keys) is keys
    assert NotSensitiveKeys.of(None) is NotSensitiveKeys.NONE


@os_agnostic
def test_a_generator_is_read_once_and_kept() -> None:
    keys = NotSensitiveKeys.of(path for path in ["A.B_Token"])

    assert keys.covers(("a", "b_token"))
    assert list(keys) == ["a.b_token"]


@os_agnostic
def test_is_sensitive_at_needs_a_sensitive_leaf_and_no_covering_declaration() -> None:
    declared = NotSensitiveKeys.of(["performance.max_token_bytes"])

    assert is_sensitive_at(("db", "password"), not_sensitive=declared)
    assert not is_sensitive_at(("performance", "max_token_bytes"), not_sensitive=declared)
    assert is_sensitive_at(("performance", "max_token_bytes"))
    assert not is_sensitive_at(("db", "host"))
    assert not is_sensitive_at(())


@os_agnostic
def test_is_sensitive_at_refuses_a_dotted_str_instead_of_reading_its_characters() -> None:
    with pytest.raises(TypeError, match=re.escape("tuple('db.password'.split('.'))")):
        is_sensitive_at(cast("tuple[str, ...]", "db.password"))


@os_agnostic
def test_covers_refuses_a_dotted_str_instead_of_reading_its_characters() -> None:
    with pytest.raises(TypeError, match="not a dotted str"):
        NotSensitiveKeys.of(["a.b"]).covers(cast("tuple[str, ...]", "a.b"))


@os_agnostic
def test_a_directly_built_declaration_refuses_a_paths_value_that_is_not_a_frozenset_of_tuples() -> None:
    with pytest.raises(TypeError, match="frozenset"):
        NotSensitiveKeys(cast("frozenset[tuple[str, ...]]", {("a", "b")}))
    with pytest.raises(TypeError, match="tuple of str"):
        NotSensitiveKeys(cast("frozenset[tuple[str, ...]]", frozenset({"a.b"})))
    with pytest.raises(TypeError, match="tuple of str"):
        NotSensitiveKeys(cast("frozenset[tuple[str, ...]]", frozenset({("a", 1)})))


@os_agnostic
def test_a_directly_built_declaration_refuses_an_empty_or_uppercase_segment() -> None:
    with pytest.raises(ValueError, match="empty segment"):
        NotSensitiveKeys(frozenset({("a", "")}))
    with pytest.raises(ValueError, match="empty segment"):
        NotSensitiveKeys(frozenset({()}))
    with pytest.raises(ValueError, match="lowercase"):
        NotSensitiveKeys(frozenset({("A", "b")}))


@os_agnostic
def test_a_directly_built_valid_declaration_works() -> None:
    assert NotSensitiveKeys(frozenset({("a", "b")})).covers(("A", "B"))
