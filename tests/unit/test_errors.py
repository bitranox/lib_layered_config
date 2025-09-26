from __future__ import annotations

from lib_layered_config.domain.errors import ConfigError, InvalidFormat, NotFound, ValidationError


def test_error_hierarchy() -> None:
    assert issubclass(InvalidFormat, ConfigError)
    assert issubclass(ValidationError, ConfigError)
    assert issubclass(NotFound, ConfigError)
    for exception in (InvalidFormat(""), ValidationError(""), NotFound("")):
        assert isinstance(exception, ConfigError)
