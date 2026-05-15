---
id: BUG-1484
type: BUG
priority: P2
status: open
captured_at: "2026-05-15T20:48:07Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
relates_to: FEAT-1479
---

# BUG-1484: `config/__init__.py` Imports `OrchestrationConfig` and `CLConfig` Before They Exist in `core.py`

## Summary

`scripts/little_loops/config/__init__.py` line 32 imports `OrchestrationConfig` and `CLConfig` from `little_loops.config.core`, but neither class is defined there. This causes an `ImportError` on package import, breaking every `ll-*` CLI tool (`ll-issues`, `ll-auto`, `ll-sprint`, etc.).

## Motivation

All `ll-*` CLI tools are completely broken — `ll-issues`, `ll-auto`, `ll-sprint`, `ll-parallel`, `ll-action`, and `ll-loop` all fail at import time. This blocks any `little_loops`-dependent workflow until the import is fixed.

- **Blocks**: All development workflows that use `ll-*` tools
- **Cause**: Partial apply of FEAT-1479 — `__init__.py` was updated to export new classes before they were added to `core.py`
- **Resolution cost**: Low — either add two dataclass stubs or revert one import line

## Root Cause

**File**: `scripts/little_loops/config/__init__.py:32`
**Function/anchor**: module-level import

```python
from little_loops.config.core import BRConfig, CLConfig, OrchestrationConfig, ProjectConfig
```

`BRConfig` and `ProjectConfig` exist in `core.py`; `CLConfig` and `OrchestrationConfig` do not. This appears to be a partial apply of FEAT-1479 (Pi adapter config candidate work) — `__init__.py` was updated to export the new classes before they were added to `core.py`.

**Error observed**:
```
ImportError: cannot import name 'OrchestrationConfig' from 'little_loops.config.core'
```

## Steps to Reproduce

```bash
ll-issues next-id
# or any ll-* CLI tool
```

## Expected Behavior

`ll-issues next-id` (and all other `ll-*` tools) run without import errors.

## Current Behavior

```
Traceback (most recent call last):
  File ".../bin/ll-issues", line 5, in <module>
    from little_loops.cli import main_issues
  File ".../little_loops/__init__.py", line 7, in <module>
    from little_loops.config import BRConfig
  File ".../little_loops/config/__init__.py", line 32, in <module>
    from little_loops.config.core import BRConfig, CLConfig, OrchestrationConfig, ProjectConfig
ImportError: cannot import name 'OrchestrationConfig' from 'little_loops.config.core'
```

## Proposed Solution

**Option A** (preferred if FEAT-1479 is in-flight): Add `CLConfig` and `OrchestrationConfig` dataclasses to `scripts/little_loops/config/core.py` per the FEAT-1479 spec.

**Option B** (quick unblock): Revert the `__init__.py` import line to only import what currently exists (`BRConfig`, `ProjectConfig`) until FEAT-1479 is complete.

## Implementation Steps

1. Choose fix approach (Option A: add `CLConfig`/`OrchestrationConfig` to `core.py`; Option B: revert `__init__.py` import)
2. Implement in `scripts/little_loops/config/core.py` (Option A) or `scripts/little_loops/config/__init__.py` (Option B)
3. Verify all `ll-*` CLI tools import without errors
4. Run test suite (`python -m pytest scripts/tests/`) to confirm no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/config/__init__.py` — fix the broken import (line 32)
- `scripts/little_loops/config/core.py` — add `CLConfig` and `OrchestrationConfig` (Option A)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/__init__.py` — imports `BRConfig` from `little_loops.config`
- All `ll-*` CLI entry points transitively import from `little_loops`

### Similar Patterns
- TBD — check for other partial-apply exports in `config/__init__.py`

### Tests
- `scripts/tests/test_config.py` — may need new tests for added config classes
- `scripts/tests/test_config_schema.py` — may need schema validation for new classes

### Documentation
- N/A

### Configuration
- `config-schema.json` — may need additions for `CLConfig`/`OrchestrationConfig` per FEAT-1479 spec

## Impact

- **Priority**: P2 — All `ll-*` CLI tools broken; unblocks all `little_loops`-dependent workflows
- **Effort**: Small — Add two dataclasses (Option A) or revert one import line (Option B)
- **Risk**: Low — Targeted import fix; no behavior change
- **Breaking Change**: No — Restores existing behavior
- **Blast Radius**: All `ll-*` CLI tools (`ll-issues`, `ll-auto`, `ll-sprint`, `ll-parallel`, `ll-action`, `ll-loop`) and any tool that imports from `little_loops`; automation runs fail immediately on import

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/config/__init__.py:32` | The broken import line |
| `scripts/little_loops/config/core.py` | Missing `CLConfig` and `OrchestrationConfig` definitions |
| `.issues/features/P5-FEAT-1479-pi-adapter-config-candidate-schema-and-config-tests.md` | In-progress work that likely introduced this partial apply |

## Labels

config, import-error, broken, pi-adapter

## Status

**Open** | Created: 2026-05-15 | Priority: P2

---

## Session Log
- `/ll:capture-issue` - 2026-05-15T20:48:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
- `/ll:format-issue` - 2026-05-15T00:00:00Z
