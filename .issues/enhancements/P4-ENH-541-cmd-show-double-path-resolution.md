---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# ENH-541: `cmd_show` Resolves Loop File Path Twice (Double Disk I/O)

## Summary

`cmd_show` in `info.py` calls `load_loop_with_spec()` (which internally calls `resolve_loop_path()` and reads the YAML file), then calls `resolve_loop_path()` again on the next line to obtain the path string for display. The path resolution walk (checking `.fsm.yaml`, `.yaml`, built-in names) runs twice per `ll-loop show` invocation.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 993–994 (at scan commit: 47c81c8; current HEAD)
- **Anchor**: `in function cmd_show()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/info.py#L507-L509) _(line 993–994 at current HEAD)_
- **Code**:
```python
fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)   # resolves path internally
path = resolve_loop_path(loop_name, loops_dir)                   # resolves path again
```

`load_loop_with_spec` in `_helpers.py:71-98` calls `resolve_loop_path` at line 87.

## Current Behavior

`resolve_loop_path` (filesystem stat/open sequence checking multiple path candidates) runs twice for every `ll-loop show` call.

## Expected Behavior

`resolve_loop_path` runs once; the resolved path is reused for display.

## Motivation

Minor performance improvement and code clarity. The double-resolution is the kind of inconsistency that can mask bugs (e.g., if the loop file is renamed between the two calls, they could return different paths). Small fix that also improves legibility.

## Proposed Solution

Option A — Call `resolve_loop_path` once before `load_loop_with_spec`:
```python
path = resolve_loop_path(loop_name, loops_dir)
fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)
# use path for display — resolved once
```

Option B — Modify `load_loop_with_spec` to return a 3-tuple `(fsm, spec, path)`:
```python
fsm, spec, path = load_loop_with_spec(loop_name, loops_dir, logger)
```

Option A is simpler and doesn't change function signatures.

## API/Interface

No new API; the change is internal to `cmd_show()`:
```python
# Before (double resolution):
fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)
path = resolve_loop_path(loop_name, loops_dir)

# After (single resolution):
path = resolve_loop_path(loop_name, loops_dir)
fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)
```

## Success Metrics

- [ ] `ll-loop show` command completes successfully with identical output
- [ ] `resolve_loop_path` is called exactly once in `cmd_show()`
- [ ] Existing tests in `scripts/tests/test_ll_loop_execution.py` pass unchanged
- [ ] No functional behavior change — paths resolved and loop data loaded identically

## Scope Boundaries

**In scope:**
- Reorder function calls in `cmd_show()` to call `resolve_loop_path()` once
- Remove duplicate call to `resolve_loop_path()`

**Out of scope:**
- Does not change `load_loop_with_spec` or `resolve_loop_path` behavior
- Does not affect other `cmd_*` functions in `info.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()`, reorder the two calls

### Dependent Files (Callers/Importers)
- N/A — local change in `cmd_show`

### Similar Patterns
- Other `cmd_*` functions in `info.py` for reference

### Tests
- No new tests needed; existing `cmd_show` tests cover functionality

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Move `resolve_loop_path` call to before `load_loop_with_spec` in `cmd_show()`
2. Remove the duplicate `resolve_loop_path` call
3. Confirm `ll-loop show` output is identical

## Impact

- **Priority**: P4 — Micro-optimization; primarily code clarity
- **Effort**: Small — 2-line reorder
- **Risk**: Low — No semantic change; same path resolution logic
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | CLI interface — `ll-loop show` subcommand (line 1381), FSM diagram rendering |
| `docs/guides/LOOPS_GUIDE.md` | Inspect workflow (line 191) |

## Labels

`enhancement`, `ll-loop`, `performance`, `scan-codebase`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: double calls at info.py:993-994
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: double `resolve_loop_path()` call confirmed at `info.py:1053-1054` (lines shifted from 993-994)

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `info.py:507` double `resolve_loop_path()` call
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: `cmd_show` at `info.py:985`; double `resolve_loop_path()` call confirmed at lines 993–994; line numbers updated
- `/ll:format-issue` - 2026-03-06T08:42:00Z - Agent task — Formatted to v2.0 template; added API/Interface, Success Metrics, restructured Scope Boundaries
- `/ll:confidence-check` - 2026-03-06T08:42:49Z - Agent task — Readiness: 100/100 PROCEED; Outcome: 100/100 HIGH CONFIDENCE
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — DEP_ISSUES: removed completed ENH-668 from Blocked By; double resolve confirmed at lines 378-379 (shifted from 1053-1054)

---


## Blocked By
## Blocks
- FEAT-543

---

## Status

**Open** | Created: 2026-03-03 | Priority: P4
