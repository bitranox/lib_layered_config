"""Test support utilities for `lib_layered_config` suites.

This package hosts reusable fixtures and builders that keep test modules
focused on behaviour instead of re-implementing cross-platform scaffolding.
"""

from __future__ import annotations

__all__ = [
    "create_layered_sandbox",
    "LayeredSandbox",
]

from .layered import LayeredSandbox, create_layered_sandbox
