---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# ENH-428: Missing caching in config.resolve_variable()

## Summary

`resolve_variable()` calls `self.to_dict()` on every invocation, constructing a large nested dictionary each time. When called in a loop (e.g., during template interpolation), this creates unnecessary allocations and repeated work.

## Current Behavior

Each call to `resolve_variable()` reconstructs the full config dict via `to_dict()`, even though the config doesn't change between calls.

## Expected Behavior

The config dict should be cached and only regenerated when config is reloaded.

## Motivation

Template interpolation resolves multiple variables per issue file. Caching eliminates redundant dictionary construction, reducing allocations and improving throughput for batch operations like `scan-codebase`.

## Scope Boundaries

- **In scope**: Caching `to_dict()` result, invalidating on config reload
- **Out of scope**: Redesigning the config system

## Proposed Solution

Use `functools.cached_property` for the dict representation:

```python
@cached_property
def _cached_dict(self) -> dict[str, Any]:
    return self.to_dict()

def resolve_variable(self, var_path: str) -> str | None:
    parts = var_path.split(".")
    value: Any = self._cached_dict
    # ...
```

Or add a simple `_dict_cache` attribute that is set to `None` on reload and lazily populated.

## Integration Map

### Files to Modify
- `scripts/little_loops/config.py`

### Dependent Files (Callers/Importers)
- Any module that calls `resolve_variable()` benefits automatically

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_config.py` — verify caching works and invalidation is correct

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `cached_property` or manual cache to `to_dict()`
2. Ensure cache is invalidated on config reload
3. Add test verifying cache behavior

## Impact

- **Priority**: P4 - Performance improvement for batch operations, not critical
- **Effort**: Small - Simple caching addition
- **Risk**: Low - Must ensure invalidation on reload
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `config`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Closed (Duplicate)** | Created: 2026-02-15 | Closed: 2026-02-14 | Priority: P4

## Closure Note

**Closed by**: Architectural audit (2026-02-14)
**Reason**: Duplicate of completed ENH-247 (cache-resolve-variable-config-dict). The scanner re-discovered the same unfixed code pattern. ENH-247 has been reopened since the fix was never applied.
