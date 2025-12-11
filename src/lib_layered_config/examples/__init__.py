"""Expose example-generation and deployment helpers as a tidy façade.

Purpose
    Provide a single import point for notebooks and docs that showcase layered
    configuration scenarios. Keeps consumers away from internal module layout.

Contents
    - :func:`deploy_config`: copy template files into etc/xdg directories.
    - :class:`DeployAction`: enum of actions taken during deployment.
    - :class:`DeployResult`: result of a single file deployment.
    - :class:`ExampleSpec`: describes example assets to generate.
    - :data:`DEFAULT_HOST_PLACEHOLDER`: default hostname marker for templates.
    - :func:`generate_examples`: materialise example configs on disk.

System Integration
    Re-exports live in the ``examples`` namespace so tutorials can call
    ``lib_layered_config.examples.generate_examples`` without traversing the
    package internals.
"""

from __future__ import annotations

from .deploy import ConflictResolver, DeployAction, DeployResult, deploy_config
from .generate import DEFAULT_HOST_PLACEHOLDER, ExampleSpec, generate_examples

__all__ = (
    "ConflictResolver",
    "deploy_config",
    "DeployAction",
    "DeployResult",
    "ExampleSpec",
    "DEFAULT_HOST_PLACEHOLDER",
    "generate_examples",
)
