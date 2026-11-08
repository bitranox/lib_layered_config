"""Deprecated alias of :mod:`lib_layered_config.deploy`; importing it warns (see the package docstring)."""

from __future__ import annotations

from ..deploy import (
    ConflictResolver,
    DeployAction,
    DeploymentStrategy,
    DeployResult,
    LinuxDeployment,
    MacDeployment,
    WindowsDeployment,
    deploy_config,
    deploy_config_paths,
    read_deploy_config,
)

__all__ = [
    "ConflictResolver",
    "DeployAction",
    "DeployResult",
    "DeploymentStrategy",
    "LinuxDeployment",
    "MacDeployment",
    "WindowsDeployment",
    "deploy_config",
    "deploy_config_paths",
    "read_deploy_config",
]
