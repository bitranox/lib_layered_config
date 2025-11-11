# Performance Benchmarks

This directory contains performance analysis and benchmarking scripts for `lib_layered_config`.

## Purpose

These files are excluded from:
- Testing (`pytest`)
- Linting (`ruff`)
- Coverage reporting
- Type checking

They are **not** part of the production codebase but serve as documentation and analysis tools.

## Files

### Analysis Documents

- **`PERFORMANCE_SUMMARY.md`** - Executive summary with visual breakdown
- **`CACHE_ANALYSIS.md`** - Detailed technical analysis

### Benchmark Scripts

- **`benchmark_cache.py`** - Synthetic benchmarks testing lru_cache performance
- **`benchmark_realistic.py`** - Real-world usage simulation
- **`profile_actual_usage.py`** - cProfile-based analysis

## Running Benchmarks

```bash
# Run synthetic benchmarks
python tests/benchmark/benchmark_cache.py

# Run realistic usage benchmarks
python tests/benchmark/benchmark_realistic.py

# Profile actual usage
python tests/benchmark/profile_actual_usage.py
```

## Key Findings

**Question:** Should we use `@lru_cache` to speed up the codebase?

**Answer:** **NO** - Functions are called once per operation, making cache overhead exceed any benefits.

See `PERFORMANCE_SUMMARY.md` for details.

## Configuration

This directory is excluded via `pyproject.toml`:

```toml
[tool.ruff]
extend-exclude = ["tests/benchmark"]

[tool.pytest.ini_options]
addopts = ["--ignore=tests/benchmark"]

[tool.coverage.report]
omit = ["tests/benchmark/*"]
```
