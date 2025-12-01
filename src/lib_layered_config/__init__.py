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
from .domain.identifiers import Layer
from .examples import deploy_config, generate_examples
from .observability import bind_trace_id, get_logger
from .testing import i_should_fail

__all__ = [
    "Config",
    "ConfigError",
    "InvalidFormatError",
    "ValidationError",
    "NotFoundError",
    "LayerLoadError",
    "Layer",
    "read_config",
    "read_config_json",
    "read_config_raw",
    "deploy_config",
    "generate_examples",
    "default_env_prefix",
    "i_should_fail",
    "bind_trace_id",
    "get_logger",
]
