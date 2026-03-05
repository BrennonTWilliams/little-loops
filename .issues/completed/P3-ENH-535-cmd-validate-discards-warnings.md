---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-535: `cmd_validate` Silently Discards Validation Warnings to the User

## Summary

`validate_fsm()` returns both `ERROR` (blocks execution) and `WARNING` severity results (e.g., unreachable states, conflicting shorthand-plus-route routing). `load_and_validate()` passes warnings to Python's `logging.warning()` only. `cmd_validate` prints a success line but never surfaces warnings to stdout. Users validating loop configs see no indication of non-fatal issues.

## Location

- **File**: `scripts/little_loops/cli/loop/config_cmds.py`
- **Line(s)**: 66–101 (at scan commit: 47c81c8)
- **Anchor**: `in function cmd_validate()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/config_cmds.py#L66-L101)
- **Code**:
```python
# validation.py:339-342
warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
for warning in warnings:
    logger.warning(str(warning))   # Python logging only — not printed to stdout

# config_cmds.py:91-95
logger.success(f"{loop_name} is valid")
print(f"  States: {', '.join(fsm.states.keys())}")
# Warnings never appear in terminal output
```

## Current Behavior

`ll-loop validate my-loop` prints `✓ my-loop is valid` even when warnings exist (e.g., unreachable state `cleanup` detected). Warnings go to Python logging (invisible unless `--debug` is set).

## Expected Behavior

After the "is valid" line, any warnings are printed to stdout with a `⚠` prefix so users can address them before running the loop.

## Motivation

Validation warnings indicate real problems: an unreachable state means dead configuration; conflicting routing is a logic error that may cause unexpected behavior. Users who run `ll-loop validate` before deploying a loop expect to see all issues, not just fatal ones.

## Proposed Solution

Return warnings from `load_and_validate()` and print them in `cmd_validate`:

Option A — Return warnings alongside the FSMLoop:
```python
# In validation.py: load_and_validate() returns (FSMLoop, list[ValidationError])
# In config_cmds.py:
fsm, warnings = load_and_validate(...)
if warnings:
    for w in warnings:
        print(f"  ⚠ {w}")
```

Option B — Re-run `validate_fsm()` in `cmd_validate` after `load_and_validate`:
```python
fsm = load_and_validate(...)
_, all_errors = validate_fsm(fsm)
warnings = [e for e in all_errors if e.severity == ValidationSeverity.WARNING]
for w in warnings:
    print(f"  ⚠ {w}")
```

Option A requires a signature change to `load_and_validate`; Option B is simpler but does double validation.

## Scope Boundaries

- Only `cmd_validate` output; does not change `load_and_validate` behavior during `run`
- Does not change exit code (exit 0 on warnings-only)
- Does not affect `cmd_compile` or `cmd_test`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()`
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` (if Option A)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — routes `validate` subcommand; no changes
- `scripts/little_loops/fsm/executor.py` — calls `load_and_validate`; not affected by Option A signature change if it doesn't use the warnings

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_ll_loop_commands.py:18` (`TestCmdValidate` class) — add: validate with unreachable state prints warning to stdout
- YAML fixture: `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml` already exists — use directly

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Choose Option A or B for exposing warnings from `load_and_validate`
2. Print warnings in `cmd_validate` with `⚠` prefix after "is valid" line
3. Add test: loop with unreachable state validates successfully but prints a warning

## Impact

- **Priority**: P3 — UX issue; users miss non-fatal config problems
- **Effort**: Small — Output addition in `cmd_validate` + optional return type change
- **Risk**: Low — Additive only; does not change validation logic or exit codes
- **Breaking Change**: No (unless Option A changes `load_and_validate` signature — callers need updating)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | FSM schema validation (line 357), CLI interface — `ll-loop validate` (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | Validation walkthrough (line 191) |

## Labels

`enhancement`, `ll-loop`, `validation`, `ux`, `scan-codebase`

## Resolution

Implemented Option B: call `validate_fsm(fsm)` in `cmd_validate` after `load_and_validate`, filter for `WARNING`-severity results, and print each with `⚠` prefix. No signature changes to `load_and_validate`; `cmd_run` behavior is unaffected.

**Files changed:**
- `scripts/little_loops/cli/loop/config_cmds.py` — imported `validate_fsm` and `ValidationSeverity`; added warning-print loop after success line
- `scripts/tests/test_ll_loop_commands.py` — added `test_validate_with_unreachable_state_prints_warning` to `TestCmdValidate`

All 3207 tests pass.

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; updated test ref to `test_ll_loop_commands.py:18` (TestCmdValidate) + noted `fixtures/fsm/loop-with-unreachable-state.yaml` fixture
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:manage-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/worker-enh-535-session.jsonl`

---

## Blocks

- BUG-532

---

**Completed** | Created: 2026-03-03 | Priority: P3
