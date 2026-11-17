"""Deprecated alias of :mod:`lib_layered_config.generate`; importing it warns (see the package docstring)."""

from __future__ import annotations

from ..generate import (
    DEFAULT_HOST_PLACEHOLDER,
    ExamplePlan,
    ExampleSpec,
    ExamplesReport,
    generate_examples,
    generate_examples_report,
    generated_before_failure,
)

__all__ = [
    "DEFAULT_HOST_PLACEHOLDER",
    "ExamplePlan",
    "ExampleSpec",
    "ExamplesReport",
    "generate_examples",
    "generate_examples_report",
    "generated_before_failure",
]
