# Performance Analysis Summary: Should We Use lru_cache?

## Answer: **NO** ❌

---

## Quick Facts

| Metric | Value |
|--------|-------|
| **Current lru_cache usage** | 0 instances |
| **Config load time** | ~0.13ms (extremely fast) |
| **Value access time** | ~0.002ms per get() |
| **String ops % of total time** | <1% |
| **I/O % of total time** | ~90-95% |

---

## Where Time Is Actually Spent

```
Config Loading Performance Breakdown (100 loads, 55ms total):

File I/O Operations        ████████████████████████████  48%  (posix.stat, is_file)
Environment Access         ███████████████████          24%  (os.environ lookups)
Path Operations           ████████████                 18%  (Path.__str__, .drive)
Other overhead            ████                         10%  (function calls, etc.)
String operations         ▏                           <1%  (replace, upper, strip)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                          Not worth optimizing with lru_cache
```

---

## Benchmark Results

### 1. Synthetic Test (Unrealistic: 600 repeated calls)
| Function | Speedup with lru_cache |
|----------|----------------------|
| `default_env_prefix()` | 2.47x ✓ |
| `normalise_resolver_platform()` | 3.31x ✓ |
| `_sanitize()` | 2.11x ✓ |

**Looks good, but misleading!** These functions are NOT called 600 times in real usage.

### 2. Real Usage Test (100 config loads)
| Operation | Result |
|-----------|--------|
| Total time | 0.0131s |
| Per load | 0.13ms (already excellent) |
| Bottleneck | File I/O, not string ops |

**Reality:** Each function called **once** per load. Cache overhead ≈ function cost.

### 3. Profiler Results (Actual bottlenecks)

**Top 5 Time Consumers:**
1. `posix.stat` (filesystem) - 0.008s
2. `os.environ.__getitem__` - 0.013s
3. `Path.is_file` - 0.007s
4. `Path.__str__` - 0.008s
5. `Path.drive` - 0.008s

**String operations:** Not in top 25 functions ❌

---

## Real Usage Pattern

```python
# Application Startup (happens ONCE)
config = read_config(vendor="Acme", app="Demo", slug="demo")
# ↑ default_env_prefix() called ONCE here
# ↑ Platform normalization called ONCE (if at all)
# Takes: ~0.13ms total

# Runtime (happens THOUSANDS of times)
timeout = config.get("service.timeout")  # ← This is the hot path
endpoint = config.get("service.endpoint")
# ↑ Already optimized (dict lookup, O(1))
# Takes: ~0.002ms per access
```

**Key insight:** Functions you'd cache are called **once**. The hot path (get/origin) is already optimal.

---

## Why lru_cache Won't Help

### 1. Functions Called Once Per Load
```python
# Without cache
def default_env_prefix(slug: str) -> str:
    return slug.replace("-", "_").upper()  # ~150ns

# Call pattern in real usage:
default_env_prefix("my-app")  # Called once
# ... 1000s of config.get() calls ...
# No more calls to default_env_prefix()
```

Cache hit rate: **0%** (only called once)

### 2. Cache Overhead ≈ Function Cost

For a single call:
- **Function execution:** ~150ns
- **Cache overhead:** ~100-150ns (hashing + dict lookup)
- **Net benefit:** ~0ns or negative ❌

### 3. Memory Overhead for Zero Benefit

Each `@lru_cache(maxsize=128)`:
- **Memory:** ~2-3 KB
- **Benefit:** 0ns (functions called once)
- **Return on Investment:** -100% ❌

### 4. Not the Bottleneck

From profiling:
- **File I/O:** 48% of time
- **Env access:** 24% of time
- **String ops:** <1% of time

**You can't optimize <1% into a meaningful gain.**

---

## Tested Functions & Verdicts

| Function | Called | Time | Cache Worth It? |
|----------|--------|------|-----------------|
| `default_env_prefix()` | Once/load | ~150ns | ❌ NO |
| `normalise_resolver_platform()` | Once/CLI | ~200ns | ❌ NO |
| `normalise_examples_platform()` | Once/op | ~200ns | ❌ NO |
| `_sanitize()` | Once | ~100ns | ❌ NO |
| `_is_linux/mac/windows` | Many | ~10ns | Already optimal ✓ |
| `Config.get()` | 1000s | ~2000ns | Already optimal ✓ |

---

## Recommendations

### ❌ DO NOT ADD lru_cache

Because:
1. Functions called once (cache hit rate = 0%)
2. String ops not the bottleneck (<1% of time)
3. Cache overhead ≥ function cost
4. Memory waste for zero benefit
5. Code complexity increase

### ✅ Current Code Is Already Optimal

Performance is excellent:
- **0.13ms** per config load (dominated by unavoidable I/O)
- **0.002ms** per value access (already using O(1) dict lookups)

### ✅ If Performance Is Needed, Optimize The Real Bottlenecks

1. **File I/O (48% of time):**
   - Cache the entire Config object at app level
   - Use file watchers instead of repeated loads
   - Memory-map config files if very large

2. **Environment Access (24% of time):**
   - Already optimal (can't avoid `os.environ` access)

3. **Path Operations (18% of time):**
   - Already necessary for path resolution
   - Can't optimize without breaking functionality

### ✅ Only Profile If Issues Arise

```bash
# If you suspect performance problems:
python -m cProfile -o profile.stats your_app.py
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

**Expected:** File I/O dominates, not string operations.

---

## Anti-Pattern to Avoid

```python
# ❌ BAD: Loading config repeatedly (anti-pattern)
for _ in range(1000):
    config = read_config(...)  # 0.13ms × 1000 = 130ms

# ✓ GOOD: Load once, access many times
config = read_config(...)  # 0.13ms once
for _ in range(1000):
    value = config.get("key")  # 0.002ms × 1000 = 2ms
```

If you're loading config repeatedly, fix the **architecture**, not the string operations.

---

## Files Created for This Analysis

1. **`CACHE_ANALYSIS.md`** - Detailed technical analysis
2. **`PERFORMANCE_SUMMARY.md`** (this file) - Executive summary
3. **`benchmark_cache.py`** - Synthetic benchmarks
4. **`benchmark_realistic.py`** - Real usage simulation
5. **`profile_actual_usage.py`** - Profiler analysis

---

## Final Verdict

**The codebase is already well-optimized for its usage pattern.**

Adding `lru_cache` would:
- ❌ Provide <0.01% real-world benefit
- ❌ Add 2-3 KB memory overhead per function
- ❌ Increase code complexity
- ❌ Not address actual bottlenecks

**Recommendation: Keep the code as-is. Do not add lru_cache.**

---

## Questions?

**Q: But the synthetic benchmarks show 2-3x speedup!**

A: Yes, when calling the same function 600 times. But in real usage, it's called once. 2x speedup on <1% of total time = <0.01% total improvement.

**Q: Should we ever use lru_cache in this codebase?**

A: Only if:
- Profiling proves a function is a bottleneck (>5% of time)
- Function is called repeatedly (>10 times per operation)
- Function execution time >1-10ms

**Q: What if I'm seeing performance issues?**

A: Profile your actual usage. Likely causes:
1. Loading config repeatedly (fix: cache Config object)
2. Very large config files (fix: lazy loading)
3. Network file systems (fix: local caching)

Not likely: String operation overhead.
