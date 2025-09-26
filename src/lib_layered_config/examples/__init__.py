"""Example and deployment helper utilities for ``lib_layered_config``."""

from .deploy import deploy_config
from .generate import ExampleSpec, DEFAULT_HOST_PLACEHOLDER, generate_examples

__all__ = [
    "deploy_config",
    "ExampleSpec",
    "DEFAULT_HOST_PLACEHOLDER",
    "generate_examples",
]
