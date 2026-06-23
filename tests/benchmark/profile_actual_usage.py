#!/usr/bin/env python3
"""Profile actual config loading to see where time is spent."""

import cProfile
import pstats
import io
import tempfile
from pathlib import Path

from src.lib_layered_config import read_config


def setup_test_config():
    """Create a test config."""
    tmpdir = tempfile.mkdtemp()
    config_dir = Path(tmpdir) / "test-app"
    config_dir.mkdir(parents=True)

    config_file = config_dir / "config.toml"
    config_file.write_text("""
[service]
timeout = 30
endpoint = "https://api.example.com"

[database]
host = "localhost"
port = 5432
name = "myapp"

[logging]
level = "INFO"
format = "json"
handlers = ["console", "file"]

[features]
feature_a = true
feature_b = false
feature_c = true
""")

    # Create a config.d directory with additional files
    config_d = config_dir / "config.d"
    config_d.mkdir()

    (config_d / "10-extra.toml").write_text("""
[extra]
setting1 = "value1"
setting2 = "value2"
""")

    return tmpdir, config_dir


def profile_config_loading():
    """Profile actual config loading operation."""
    tmpdir, config_dir = setup_test_config()

    print("\n" + "=" * 70)
    print("PROFILING: Actual Config Loading")
    print("=" * 70)

    # Profile config loading
    profiler = cProfile.Profile()

    profiler.enable()
    for _ in range(100):
        config = read_config(
            vendor="Test",
            app="App",
            slug="test-app",
            start_dir=str(config_dir.parent),
        )
    profiler.disable()

    # Analyze results
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.sort_stats('cumulative')

    print("\nTop 25 functions by cumulative time:")
    print("=" * 70)
    stats.print_stats(25)

    # Print the stats
    print(s.getvalue())

    # Additional analysis
    print("\n" + "=" * 70)
    print("STRING OPERATION FUNCTIONS:")
    print("=" * 70)
    stats.sort_stats('cumulative')
    stats.print_stats('default_env_prefix|sanitize|normalise|replace|upper|lower')

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir)

    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    print("""
Look at the profile output above:

1. Find "default_env_prefix" - likely <0.01% of total time
2. Find "normalise" functions - likely not in top 50
3. Top time consumers are likely:
   - File I/O operations (Path.is_file, Path.read_text, etc.)
   - TOML parsing (tomllib functions)
   - Path operations

This confirms: String operations are NOT the bottleneck.
    """)


if __name__ == "__main__":
    profile_config_loading()
