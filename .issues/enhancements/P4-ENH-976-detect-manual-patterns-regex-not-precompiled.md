---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-976: `detect_manual_patterns` recompiles regex patterns on each call

## Summary

`_MANUAL_PATTERNS` in `quality.py` stores raw pattern strings in its nested `"patterns"` lists. Inside `detect_manual_patterns`, these strings are passed to `re.findall(pattern, content, re.IGNORECASE)` on every call, triggering a compile step (or LRU cache lookup) for each `(issue, pattern)` combination. Pre-compiling the patterns at module load time as `re.Pattern` objects eliminates this overhead entirely.

## Location

- **File**: `scripts/little_loops/issue_history/quality.py`
- **Line(s)**: 224–268 (`_MANUAL_PATTERNS` definition), 299–316 (`detect_manual_patterns` usage) (at scan commit: 96d74cda)
- **Anchor**: `_MANUAL_PATTERNS` module constant and `in function detect_manual_patterns`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_history/quality.py#L224)
- **Code**:
```python
# _MANUAL_PATTERNS stores raw strings:
_MANUAL_PATTERNS = {
    "direct_implementation": {
        "patterns": [r"direct implementation", r"implemented directly"],
        ...
    },
    ...
}

# detect_manual_patterns — compile step per call per pattern:
for pattern in config["patterns"]:
    matches = re.findall(pattern, content, re.IGNORECASE)
```

## Current Behavior

With 5 pattern types and 2–3 patterns each, every `detect_manual_patterns(issues)` call triggers 10–15 `re.findall` calls with string patterns per issue. Python's `re` module caches up to 512 compiled patterns, so these are LRU lookups rather than full recompiles on repeated calls — but the cache lookup + flag combination overhead is still unnecessary when the patterns are fixed at module load time.

## Expected Behavior

Pattern objects are compiled once at module import with `re.compile(pattern, re.IGNORECASE)`. Each `detect_manual_patterns` call uses `pattern_obj.findall(content)` directly.

## Motivation

`detect_manual_patterns` is called during `ll-history analyze` on all completed issues. Pre-compiling patterns is the idiomatic Python approach for module-level constants and makes the intent explicit: these patterns are fixed, not dynamic.

## Proposed Solution

Change `_MANUAL_PATTERNS` to store compiled patterns:

```python
import re

_MANUAL_PATTERNS = {
    "direct_implementation": {
        "patterns": [
            re.compile(r"direct implementation", re.IGNORECASE),
            re.compile(r"implemented directly", re.IGNORECASE),
        ],
        ...
    },
    ...
}

# In detect_manual_patterns:
for pattern in config["patterns"]:
    matches = pattern.findall(content)  # no flags needed — compiled in
```

## Scope Boundaries

- Only change how patterns are stored and called; do not change pattern strings or detection logic

## Success Metrics

- `_MANUAL_PATTERNS["*"]["patterns"]` contains `re.Pattern` objects, not strings

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/quality.py` — `_MANUAL_PATTERNS` and `detect_manual_patterns`

### Dependent Files (Callers/Importers)
- `analyze_quality` in the same file — calls `detect_manual_patterns`

### Similar Patterns
- `session_log.py` — `_SESSION_LOG_SECTION_RE = re.compile(...)` module-level compiled pattern (reference)

### Tests
- `scripts/tests/test_issue_history_advanced_analytics.py` — existing tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Wrap each pattern string in `_MANUAL_PATTERNS` with `re.compile(..., re.IGNORECASE)`
2. Update the `re.findall(pattern, content, re.IGNORECASE)` call to `pattern.findall(content)`
3. Run existing tests

## Impact

- **Priority**: P4 — Idiomatic improvement; micro-optimization and code clarity
- **Effort**: Small — Change string literals to `re.compile()` calls, update one call site
- **Risk**: Low — Identical behavior; only the compilation timing changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
