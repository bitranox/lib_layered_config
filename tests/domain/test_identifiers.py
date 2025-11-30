"""Tests for identifier validation and Layer enum."""

from __future__ import annotations

import pytest

from lib_layered_config.domain.identifiers import (
    Layer,
    validate_hostname,
    validate_identifier,
)


class TestValidateIdentifier:
    """Tests for validate_identifier function."""

    def test_accepts_simple_identifier(self) -> None:
        assert validate_identifier("myapp", "slug") == "myapp"

    def test_accepts_hyphenated_identifier(self) -> None:
        assert validate_identifier("my-app", "slug") == "my-app"

    def test_accepts_underscored_identifier(self) -> None:
        assert validate_identifier("my_app", "slug") == "my_app"

    def test_accepts_numeric_suffix(self) -> None:
        assert validate_identifier("app123", "slug") == "app123"

    def test_rejects_forward_slash(self) -> None:
        with pytest.raises(ValueError, match="slug contains invalid path characters"):
            validate_identifier("../etc", "slug")

    def test_rejects_backslash(self) -> None:
        with pytest.raises(ValueError, match="vendor contains invalid path characters"):
            validate_identifier("..\\windows", "vendor")

    def test_rejects_dot_prefix(self) -> None:
        with pytest.raises(ValueError, match="app cannot start with a dot"):
            validate_identifier(".hidden", "app")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="slug cannot be empty"):
            validate_identifier("", "slug")

    def test_error_message_includes_param_name(self) -> None:
        with pytest.raises(ValueError, match="vendor"):
            validate_identifier("/bad", "vendor")


class TestValidateHostname:
    """Tests for validate_hostname function."""

    def test_accepts_simple_hostname(self) -> None:
        assert validate_hostname("webserver") == "webserver"

    def test_accepts_hyphenated_hostname(self) -> None:
        assert validate_hostname("web-server-01") == "web-server-01"

    def test_accepts_fqdn(self) -> None:
        assert validate_hostname("server.example.com") == "server.example.com"

    def test_rejects_forward_slash(self) -> None:
        with pytest.raises(ValueError, match="hostname contains invalid path characters"):
            validate_hostname("../etc")

    def test_rejects_backslash(self) -> None:
        with pytest.raises(ValueError, match="hostname contains invalid path characters"):
            validate_hostname("..\\windows")


class TestLayerEnum:
    """Tests for Layer enumeration."""

    def test_layer_values_are_strings(self) -> None:
        assert Layer.APP == "app"
        assert Layer.HOST == "host"
        assert Layer.USER == "user"
        assert Layer.DOTENV == "dotenv"
        assert Layer.ENV == "env"
        assert Layer.DEFAULTS == "defaults"

    def test_layer_is_string_subclass(self) -> None:
        assert isinstance(Layer.APP, str)

    def test_layer_can_be_used_as_dict_key(self) -> None:
        data = {Layer.APP: "value"}
        assert data[Layer.APP] == "value"
        assert data["app"] == "value"

    def test_all_layers_defined(self) -> None:
        expected = {"defaults", "app", "host", "user", "dotenv", "env"}
        actual = {layer.value for layer in Layer}
        assert actual == expected
