---
discovered_commit: 5d6419bad2fa3174b9f2c4062ef912bba5205e1a
discovered_branch: main
discovered_date: 2026-02-25
discovered_by: audit-architecture
focus_area: organization
confidence_score: 85
outcome_confidence: 56
---

# ENH-507: Add `__all__` exports to 19 public root-level modules

## Summary

Architectural issue found by `/ll:audit-architecture`. 19 of the 24 root-level modules in `scripts/little_loops/` are missing `__all__` definitions, leaving their public API implicit and undeclared.

## Location

- **Files**: `scripts/little_loops/*.py` (19 modules)
- **Module**: `little_loops.*`

## Finding

### Current State

Only 5 of 24 root-level modules define `__all__`:
- `config.py` ✓
- `cli_args.py` ✓
- `user_messages.py` ✓
- `workflow_sequence_analyzer.py` ✓
- `text_utils.py` ✓

**Missing `__all__`** (19 modules):

```
dependency_graph.py
dependency_mapper.py
doc_counts.py
frontmatter.py
git_operations.py
goals_parser.py
issue_lifecycle.py
issue_manager.py
issue_parser.py
link_checker.py
logger.py
logo.py
session_log.py
sprint.py
state.py
subprocess_utils.py
sync.py
work_verification.py
```

Without `__all__`, `from little_loops.module import *` (used in some test helpers and `__init__.py` re-exports) imports every name including private helpers and imported names from other modules. IDE auto-complete and type checkers also produce less accurate results.

### Impact

- **IDE tooling**: Auto-complete shows private helpers alongside public API
- **Type checking**: `mypy` and `pyright` report less precise public API boundaries
- **`import *` semantics**: Without `__all__`, star imports leak internal names
- **Documentation**: No machine-readable signal for what's intended as public API

## Proposed Solution

Add `__all__` to each module listing only its intended public exports.

### Suggested Approach

1. For each of the 19 modules, identify public functions, classes, and constants (those not prefixed with `_`)
2. Add `__all__ = [...]` after the module docstring and imports
3. Exclude:
   - Private helpers (`_prefixed`)
   - Names imported from other modules (unless intentionally re-exported)
   - Implementation-only dataclasses used only internally

### Example

```python
# git_operations.py - before
# (no __all__)

# git_operations.py - after
__all__ = [
    "commit_all",
    "get_current_branch",
    "stage_files",
    "GitOperationError",
]
```

## Impact Assessment

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low (additive change, no behavior change)
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `auto-generated`

---

---

## Tradeoff Review Note

**Reviewed**: 2026-02-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | LOW |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Clean hygiene improvement but LOW utility for a CLI/plugin project where star imports and IDE auto-complete accuracy are not pressing concerns. Blocked by FEAT-488. Consider batching with other cleanup work when the blocker resolves rather than tracking as a standalone priority.

## Session Log
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is comprehensive with full list of 19 modules needing __all__; no knowledge gaps identified

## Status

**Open** | Created: 2026-02-25 | Priority: P5

## Blocked By

- FEAT-488
