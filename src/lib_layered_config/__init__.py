"""Public API surface for ``lib_layered_config``.

Expose the curated, stable symbols that consumers need to interact with the
library: reader functions, value object, error taxonomy, and observability
helpers.

Contents:
    * :func:`lib_layered_config.core.read_config`
    * :func:`lib_layered_config.core.read_config_raw`, returning a
      :class:`~lib_layered_config.application.merge.MergeResult`
    * :func:`lib_layered_config.deploy.deploy_config`, with
      :func:`~lib_layered_config.deploy.deploy_config_paths` and
      :func:`~lib_layered_config.deploy.read_deploy_config`; ``deploy_config`` returns
      :class:`~lib_layered_config.deploy.DeployResult` items naming a
      :class:`~lib_layered_config.deploy.DeployAction`
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

import importlib
from typing import TYPE_CHECKING

from .application.merge import MergeResult
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
from .deploy import (
    DeployAction,
    DeployResult,
    deploy_config,
    deploy_config_paths,
    deployed_before_failure,
    read_deploy_config,
)
from .domain.config import OVERRIDE_LAYER, SourceInfo
from .domain.deploy_mode import DeployMode, DeployModeError, ModeKind
from .domain.deploy_permissions import (
    DeployPermissions,
    DeployPermissionsError,
    LayerModes,
    PermissionProblem,
    deploy_permissions_from_config,
)
from .domain.errors import (
    DeployDestinationError,
    GenerateDestinationError,
    HomeDirectoryUnknownError,
    LayerRootNotAbsoluteError,
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
from .domain.redaction import REDACTED_PLACEHOLDER, NotSensitiveKeys, is_sensitive, is_sensitive_at, redact_mapping
from .generate import generate_examples, generated_before_failure
from .observability import bind_trace_id, get_logger
from .testing import i_should_fail

if TYPE_CHECKING:
    from .adapters.display import display_config

#: Names exported on first access, each from the module named here. ``display_config`` needs Rich and
#: rich-click, which a program that only reads configuration never uses: importing them eagerly cost
#: about a third of ``import lib_layered_config``.
_LAZY_EXPORTS = {"display_config": ".adapters.display"}


def __getattr__(name: str) -> object:
    """Import a lazily exported name on first access and keep it in the module namespace.

    Raises:
        AttributeError: *name* is not a name this package exports.
    """
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module, __name__), name)
    globals()[name] = value
    return value


__all__ = [
    "DEFAULT_APP_DIR_MODE",
    "DEFAULT_APP_FILE_MODE",
    "DEFAULT_MAX_PROFILE_LENGTH",
    "DEFAULT_USER_DIR_MODE",
    "DEFAULT_USER_FILE_MODE",
    "OVERRIDE_LAYER",
    "REDACTED_PLACEHOLDER",
    "Config",
    "ConfigError",
    "DeployAction",
    "DeployDestinationError",
    "DeployMode",
    "DeployModeError",
    "DeployPermissions",
    "DeployPermissionsError",
    "DeployResult",
    "GenerateDestinationError",
    "HomeDirectoryUnknownError",
    "InvalidFormatError",
    "Layer",
    "LayerLoadError",
    "LayerModes",
    "LayerRootNotAbsoluteError",
    "MergeResult",
    "ModeKind",
    "NotFoundError",
    "NotSensitiveKeys",
    "OutputFormat",
    "PermissionProblem",
    "SourceInfo",
    "ValidationError",
    "bind_trace_id",
    "default_env_prefix",
    "deploy_config",
    "deploy_config_paths",
    "deploy_permissions_from_config",
    "deployed_before_failure",
    "display_config",
    "generate_examples",
    "generated_before_failure",
    "get_logger",
    "i_should_fail",
    "is_sensitive",
    "is_sensitive_at",
    "is_valid_profile_name",
    "read_config",
    "read_config_json",
    "read_config_raw",
    "read_deploy_config",
    "redact_mapping",
    "validate_profile_name",
]
