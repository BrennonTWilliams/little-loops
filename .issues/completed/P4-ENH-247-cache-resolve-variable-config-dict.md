---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-247: Cache resolve_variable config dict rebuilds

## Summary

Every call to `BRConfig.resolve_variable()` invokes `self.to_dict()`, which constructs a full nested dictionary of all configuration values. When resolving multiple template variables, the config dict is rebuilt from scratch each time.

## Location

- **File**: `scripts/little_loops/config.py`
- **Line(s)**: 657-679 (at scan commit: a8f4144)
- **Anchor**: `in method BRConfig.resolve_variable`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/config.py#L657-L679)
- **Code**:
```python
def resolve_variable(self, var_path: str) -> str | None:
    parts = var_path.split(".")
    value: Any = self.to_dict()  # rebuilds entire dict every time
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
```

## Current Behavior

Full nested dict is constructed on every call.

## Expected Behavior

Cache the dict or navigate dataclass attributes directly via `getattr()`.

## Proposed Solution

Either cache `to_dict()` result with invalidation, or use `getattr()` to navigate the config's dataclass attributes directly.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (Won't Fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4

**Closure reason**: Premature optimization. Config resolution happens a handful of times per run. Caching adds invalidation complexity for zero perceived speedup.
