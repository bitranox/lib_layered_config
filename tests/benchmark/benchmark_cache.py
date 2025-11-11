#!/usr/bin/env python3
"""Benchmark script to test if lru_cache would improve performance."""

from __future__ import annotations

import timeit
from functools import lru_cache
from pathlib import Path

# Import functions to test
from src.lib_layered_config.adapters.env.default import default_env_prefix
from src.lib_layered_config._platform import (
    normalise_resolver_platform,
    normalise_examples_platform,
    _sanitize,
)
from src.lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver


# Cached versions for comparison
@lru_cache(maxsize=128)
def cached_default_env_prefix(slug: str) -> str:
    """Cached version of default_env_prefix."""
    return slug.replace("-", "_").upper()


@lru_cache(maxsize=128)
def cached_sanitize(alias: str | None) -> str | None:
    """Cached version of _sanitize."""
    if alias is None:
        return None
    stripped = alias.strip().lower()
    if not stripped:
        raise ValueError("Platform alias cannot be empty.")
    return stripped


@lru_cache(maxsize=128)
def cached_normalise_resolver_platform(alias: str | None) -> str | None:
    """Cached version - just for testing."""
    return normalise_resolver_platform(alias)


def benchmark_env_prefix():
    """Benchmark default_env_prefix with and without cache."""
    test_slugs = [
        "lib-layered-config",
        "my-app",
        "config-kit",
        "demo-service",
        "lib-layered-config",  # repeated
        "my-app",  # repeated
    ] * 100

    print("\n" + "=" * 70)
    print("BENCHMARK: default_env_prefix")
    print("=" * 70)

    # Without cache
    time_no_cache = timeit.timeit(
        lambda: [default_env_prefix(slug) for slug in test_slugs],
        number=1000
    )
    print(f"Without cache: {time_no_cache:.4f} seconds")

    # With cache
    time_with_cache = timeit.timeit(
        lambda: [cached_default_env_prefix(slug) for slug in test_slugs],
        number=1000
    )
    print(f"With cache:    {time_with_cache:.4f} seconds")

    speedup = time_no_cache / time_with_cache if time_with_cache > 0 else 0
    print(f"Speedup:       {speedup:.2f}x")

    if speedup > 1.2:
        print("✓ Caching provides meaningful benefit (>20% improvement)")
    elif speedup > 1.05:
        print("~ Caching provides marginal benefit (5-20% improvement)")
    else:
        print("✗ Caching provides negligible benefit (<5% improvement)")


def benchmark_platform_normalization():
    """Benchmark platform normalization functions."""
    test_platforms = [
        "linux", "darwin", "windows", "mac", "win32",
        "linux", "darwin", "windows",  # repeated
    ] * 100

    print("\n" + "=" * 70)
    print("BENCHMARK: normalise_resolver_platform")
    print("=" * 70)

    # Without cache
    time_no_cache = timeit.timeit(
        lambda: [normalise_resolver_platform(p) for p in test_platforms],
        number=1000
    )
    print(f"Without cache: {time_no_cache:.4f} seconds")

    # With cache
    time_with_cache = timeit.timeit(
        lambda: [cached_normalise_resolver_platform(p) for p in test_platforms],
        number=1000
    )
    print(f"With cache:    {time_with_cache:.4f} seconds")

    speedup = time_no_cache / time_with_cache if time_with_cache > 0 else 0
    print(f"Speedup:       {speedup:.2f}x")

    if speedup > 1.2:
        print("✓ Caching provides meaningful benefit (>20% improvement)")
    elif speedup > 1.05:
        print("~ Caching provides marginal benefit (5-20% improvement)")
    else:
        print("✗ Caching provides negligible benefit (<5% improvement)")


def benchmark_path_resolver():
    """Benchmark path resolver instantiation and calls."""
    print("\n" + "=" * 70)
    print("BENCHMARK: DefaultPathResolver operations")
    print("=" * 70)

    # Test repeated resolver creation
    time_resolver_creation = timeit.timeit(
        lambda: DefaultPathResolver(
            vendor="Acme",
            app="Demo",
            slug="demo-app",
        ),
        number=10000
    )
    print(f"Resolver creation (10k times): {time_resolver_creation:.4f} seconds")

    # Test repeated method calls
    resolver = DefaultPathResolver(
        vendor="Acme",
        app="Demo",
        slug="demo-app",
    )

    time_platform_checks = timeit.timeit(
        lambda: (resolver._is_linux, resolver._is_macos, resolver._is_windows),
        number=100000
    )
    print(f"Platform checks (100k times):  {time_platform_checks:.4f} seconds")
    print("Note: Platform checks are already properties and very fast")


def benchmark_sanitize():
    """Benchmark _sanitize function."""
    test_inputs = [
        "  MacOS  ", "linux", "WINDOWS", "  darwin  ",
        "  MacOS  ", "linux",  # repeated
    ] * 100

    print("\n" + "=" * 70)
    print("BENCHMARK: _sanitize")
    print("=" * 70)

    # Without cache
    time_no_cache = timeit.timeit(
        lambda: [_sanitize(inp) for inp in test_inputs],
        number=1000
    )
    print(f"Without cache: {time_no_cache:.4f} seconds")

    # With cache
    time_with_cache = timeit.timeit(
        lambda: [cached_sanitize(inp) for inp in test_inputs],
        number=1000
    )
    print(f"With cache:    {time_with_cache:.4f} seconds")

    speedup = time_no_cache / time_with_cache if time_with_cache > 0 else 0
    print(f"Speedup:       {speedup:.2f}x")

    if speedup > 1.2:
        print("✓ Caching provides meaningful benefit (>20% improvement)")
    elif speedup > 1.05:
        print("~ Caching provides marginal benefit (5-20% improvement)")
    else:
        print("✗ Caching provides negligible benefit (<5% improvement)")


def main():
    """Run all benchmarks."""
    print("\n" + "=" * 70)
    print("LRU_CACHE PERFORMANCE ANALYSIS")
    print("=" * 70)
    print("\nTesting whether adding @lru_cache would improve performance")
    print("in lib_layered_config codebase...")

    benchmark_env_prefix()
    benchmark_platform_normalization()
    benchmark_sanitize()
    benchmark_path_resolver()

    print("\n" + "=" * 70)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 70)
    print("""
The benchmarks test whether caching would help for:
1. default_env_prefix: Simple string operations (replace + upper)
2. Platform normalization: String sanitization + dict lookups
3. Path resolver: Object creation and platform detection

Key considerations:
- lru_cache adds overhead (memory + function call wrapper)
- Only beneficial when:
  * Function is called repeatedly with same inputs
  * Function computation is expensive
  * Cache hit rate is high

For this library:
- Most functions are called once per config load
- String operations are extremely fast in Python
- Dictionary lookups are already O(1)
- Cache memory overhead may exceed benefits

Recommendation: Only add caching if profiling shows these
functions are actual bottlenecks in real usage.
    """)


if __name__ == "__main__":
    main()
