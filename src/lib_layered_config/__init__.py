"""Public API surface for ``lib_layered_config``.

Expose the curated, stable symbols that consumers need to interact with the
library: reader functions, value object, error taxonomy, and observability
helpers.

Contents:
    * :func:`lib_layered_config.core.read_config`
    * :func:`lib_layered_config.core.read_config_raw`
    * :func:`lib_layered_config.examples.deploy.deploy_config`
    * :class:`lib_layered_config.domain.config.Config`
    * Error hierarchy (:class:`ConfigError`, :class:`InvalidFormatError`, etc.)
    * Diagnostics helpers (:func:`lib_layered_config.testing.i_should_fail`)
    * Observability bindings (:func:`bind_trace_id`, :func:`get_logger`)

System Role:
    Acts as the frontline module imported by applications, keeping the public
    surface area deliberate and well-documented (see
    ``docs/systemdesign/module_reference.md``).
"""

from __future__ import annotations

from .adapters.display import display_config
from .application.ports import OutputFormat
from .core import (
    Config,
    ConfigError,
    InvalidFormatError,
    LayerLoadError,
    NotFoundError,
    ValidationError,
    default_env_prefix,
    read_config,
    read_config_json,
    read_config_raw,
)
from .domain.identifiers import (
    DEFAULT_MAX_PROFILE_LENGTH,
    Layer,
    is_valid_profile_name,
    validate_profile_name,
)
from .domain.permissions import (
    DEFAULT_APP_DIR_MODE,
    DEFAULT_APP_FILE_MODE,
    DEFAULT_USER_DIR_MODE,
    DEFAULT_USER_FILE_MODE,
)
from .domain.redaction import REDACTED_PLACEHOLDER, is_sensitive, redact_mapping
from .examples import deploy_config, generate_examples
from .observability import bind_trace_id, get_logger
from .testing import i_should_fail

__all__ = [
    "Config",
    "ConfigError",
    "DEFAULT_APP_DIR_MODE",
    "DEFAULT_APP_FILE_MODE",
    "DEFAULT_MAX_PROFILE_LENGTH",
    "DEFAULT_USER_DIR_MODE",
    "DEFAULT_USER_FILE_MODE",
    "InvalidFormatError",
    "Layer",
    "LayerLoadError",
    "NotFoundError",
    "OutputFormat",
    "REDACTED_PLACEHOLDER",
    "ValidationError",
    "bind_trace_id",
    "default_env_prefix",
    "deploy_config",
    "display_config",
    "generate_examples",
    "get_logger",
    "i_should_fail",
    "is_sensitive",
    "is_valid_profile_name",
    "read_config",
    "read_config_json",
    "read_config_raw",
    "redact_mapping",
    "validate_profile_name",
]
