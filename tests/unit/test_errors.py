from __future__ import annotations

from lib_layered_config.domain.errors import ConfigError, InvalidFormatError, NotFoundError, ValidationError

from tests.support.os_markers import os_agnostic


@os_agnostic
def test_invalid_format_descends_from_config_error() -> None:
    assert issubclass(InvalidFormatError, ConfigError)


@os_agnostic
def test_validation_error_descends_from_config_error() -> None:
    assert issubclass(ValidationError, ConfigError)


@os_agnostic
def test_not_found_descends_from_config_error() -> None:
    assert issubclass(NotFoundError, ConfigError)


@os_agnostic
def test_error_instances_remain_config_error_instances() -> None:
    bouquet = (InvalidFormatError(""), ValidationError(""), NotFoundError(""))
    assert all(isinstance(exception, ConfigError) for exception in bouquet)
