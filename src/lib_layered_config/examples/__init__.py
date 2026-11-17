"""Deprecated: the old home of :mod:`lib_layered_config.deploy` and :mod:`lib_layered_config.generate`.

Every name here is re-exported from those modules, and importing this package warns. Import from
the package root (``from lib_layered_config import deploy_config, DeployAction``) or from
``lib_layered_config.deploy`` / ``lib_layered_config.generate`` instead. This shim is removed in
9.0.0.
"""

from __future__ import annotations

import warnings

from ..deploy import (
    ConflictResolver,
    DeployAction,
    DeployResult,
    deploy_config,
    deploy_config_paths,
    read_deploy_config,
)
from ..generate import DEFAULT_HOST_PLACEHOLDER, ExampleSpec, generate_examples

warnings.warn(
    "lib_layered_config.examples is deprecated and will be removed in 9.0.0; import from "
    "lib_layered_config, lib_layered_config.deploy or lib_layered_config.generate instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = (
    "DEFAULT_HOST_PLACEHOLDER",
    "ConflictResolver",
    "DeployAction",
    "DeployResult",
    "ExampleSpec",
    "deploy_config",
    "deploy_config_paths",
    "generate_examples",
    "read_deploy_config",
)
