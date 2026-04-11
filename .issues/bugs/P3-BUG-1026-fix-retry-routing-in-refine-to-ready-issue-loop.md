---
id: BUG-1026
type: bug
priority: P3
title: "fix retry routing in refine-to-ready-issue loop"
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-1026: Fix retry routing in refine-to-ready-issue loop

## Summary

In the `refine-to-ready-issue` FSM loop, when confidence thresholds are not met after a refinement pass, the retry path routes back through `check_lifetime_limit` before reaching `refine_issue`. This is one step too far back — `format_issue` only needs to run once per run, and `check_lifetime_limit` is unnecessary indirection on intra-run retries. Worse, the lifetime cap may have already incremented from the just-completed refinement, which can falsely trip the cap mid-run. The `on_yes` transition from `check_refine_limit` should route directly to `refine_issue`.

## Current Behavior

When scores don't meet thresholds after a refinement pass:

```
check_scores (no) → check_refine_limit (yes) → check_lifetime_limit → refine_issue
```

`check_lifetime_limit` re-checks `ll-issues refine-status`, but the count may have just incremented from the completed refinement — potentially causing a false lifetime-cap trip that aborts the run prematurely.

## Expected Behavior

The retry path should skip `check_lifetime_limit` and go directly to `refine_issue`:

```
check_scores (no) → check_refine_limit (yes) → refine_issue
```

The lifetime cap is already enforced at the beginning of each run before the first refinement. Skipping it on the intra-run retry is correct.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue` on an issue that needs two refinement passes
2. Observe that after the first pass fails the confidence check, the loop visits `check_lifetime_limit` before attempting the second pass
3. If the lifetime refine count is near its cap, the second pass may be incorrectly aborted

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `check_refine_limit` state (line 158)
- **Cause**: `on_yes` is set to `check_lifetime_limit` instead of `refine_issue`. The lifetime cap check belongs only at the start of a run, not between intra-run retry attempts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The false-trip mechanism is concrete: `refine_count` (read by `check_lifetime_limit`) is sourced from the issue's `## Session Log` section on disk (`scripts/little_loops/cli/issues/refine_status.py:301` → `session_log.py:42-59`). That log entry is written **during** `refine_issue` state execution — `commands/refine-issue.md` Step 7 calls `ll-issues append-log`, which writes to disk at `scripts/little_loops/session_log.py:128` (via `append_log.py:13`). By the time the FSM transitions through `check_wire_done` → `confidence_check` → `check_scores` → `check_refine_limit` → `check_lifetime_limit`, the session log has already been updated. On the retry path, `TOTAL_REFINES` is one higher than when `check_lifetime_limit` was first visited after `format_issue`. The FSM executor re-runs `check_lifetime_limit`'s shell action fresh each entry (`executor.py:427`) with no caching, so it always reads the current on-disk count.

## Motivation

Intra-run retries are governed by `check_refine_limit` (per-run cap). The lifetime cap (`check_lifetime_limit`) was designed as a pre-run guard against over-refining issues across sessions. Re-checking it mid-run can prematurely abort a run that is still within its per-run budget, especially when the lifetime count increments right after the first refinement.

## Proposed Solution

In `scripts/little_loops/loops/refine-to-ready-issue.yaml`, line 158:

Change:
```yaml
on_yes: check_lifetime_limit
```

To:
```yaml
on_yes: refine_issue
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — change `check_refine_limit.on_yes`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:713-758` — `_route()` method resolves `on_yes`/`on_no`; no changes needed
- `scripts/little_loops/cli/issues/refine_status.py:301` — where `refine_count` in `ll-issues refine-status --json` is sourced (`session_command_counts.get("/ll:refine-issue", 0)`)
- `scripts/little_loops/session_log.py:42-59` — `count_session_commands()` reads session log to produce the count
- `scripts/little_loops/session_log.py:85-129` — `append_session_log_entry()` writes to disk at line 128 (increments the count during `refine_issue` execution)
- `scripts/little_loops/cli/issues/append_log.py:13` — `cmd_append_log()` entry point called by Step 7 of `commands/refine-issue.md:374`
- `scripts/little_loops/loops/issue-refinement.yaml` — delegates to `refine-to-ready-issue` as a sub-loop; inherits the fix automatically

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml` — also invokes `refine-to-ready-issue` as a sub-loop via `run_refine` state; inherits the fix automatically, no changes needed [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml:22-37` — `retry_counter` fragment is the canonical pattern: `on_yes` routes to the action state (caller supplies), never through another cap check
- Research confirmed: `refine-to-ready-issue.yaml:158` is the **only** state across all 30+ loop YAMLs where a per-run counter's `on_yes` routes through a second limit-check state rather than directly to the action state
- `scripts/little_loops/loops/issue-refinement.yaml:42-56` — `check_commit` counter: `on_yes: commit` directly (correct pattern)

### Tests
- `scripts/tests/test_builtin_loops.py:547` — `test_check_lifetime_limit_routes_to_breakdown_issue` tests `check_lifetime_limit.on_no`; no equivalent test exists for `check_refine_limit.on_yes` routing — a test should be added after the fix following this pattern
- Verify manually with `ll-loop run refine-to-ready-issue` on an issue that needs two refinement passes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:646` — add `test_check_refine_limit_routes_to_refine_issue` to `TestRefineToReadyIssueSubLoop` after line 646, following the exact pattern of `test_check_lifetime_limit_routes_to_breakdown_issue:547`; no existing test currently pins the old `on_yes: check_lifetime_limit` routing so nothing breaks [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:273` — "Before each refinement, the `check_lifetime_limit` state reads..." describes the current (buggy) timing; after the fix, `check_lifetime_limit` only runs once per run (at start), not before each intra-run retry — update to "At the start of each run" [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/refine-to-ready-issue.yaml`
2. In the `check_refine_limit` state (line 158), change `on_yes: check_lifetime_limit` to `on_yes: refine_issue`
3. Trace the full FSM happy path and retry path to confirm no dead ends
4. Add a test to `scripts/tests/test_builtin_loops.py` following the pattern of `test_check_lifetime_limit_routes_to_breakdown_issue` (line 547): assert `check_refine_limit.on_yes == "refine_issue"`
5. Run `python -m pytest scripts/tests/test_builtin_loops.py -v -k "refine_to_ready"` to verify
6. Run a manual smoke test: `ll-loop run refine-to-ready-issue <issue-id>` and verify the retry goes directly to `refine_issue`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `test_check_refine_limit_routes_to_refine_issue` to `scripts/tests/test_builtin_loops.py` in `TestRefineToReadyIssueSubLoop` after line 646, using this pattern:
   ```python
   def test_check_refine_limit_routes_to_refine_issue(self, data: dict) -> None:
       """check_refine_limit.on_yes must route directly to refine_issue (not check_lifetime_limit)."""
       state = data["states"].get("check_refine_limit", {})
       assert state.get("on_yes") == "refine_issue", (
           f"check_refine_limit.on_yes should be 'refine_issue', got {state.get('on_yes')!r}"
       )
   ```
8. Update `docs/guides/LOOPS_GUIDE.md:273` — change "Before each refinement, the `check_lifetime_limit` state reads..." to "At the start of each run, the `check_lifetime_limit` state reads..." to reflect that it only runs once per run after the fix

## Impact

- **Priority**: P3 - Logic error that can prematurely abort intra-run retries; affects only multi-pass refinement scenarios near the lifetime cap
- **Effort**: Small - Single line change in one YAML file
- **Risk**: Low - No Python code changes; FSM routing is declarative
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM loop execution model |
| `.claude/CLAUDE.md` | CLI tools reference for `ll-loop` |

## Labels

`bug`, `fsm`, `loops`, `refine-to-ready-issue`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd761c4f-1d5d-4463-b0ee-835538892eea.jsonl`
- `/ll:wire-issue` - 2026-04-11T04:26:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3be8bdda-d42f-491e-8a93-0f32e4fd87aa.jsonl`
- `/ll:refine-issue` - 2026-04-11T04:21:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c66e6a84-cf7b-484b-806d-2eb53f8dbabb.jsonl`
- `/ll:format-issue` - 2026-04-11T04:16:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11232320-22e5-4553-9a97-2031c0377954.jsonl`

- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4254e7c6-6671-4edc-8250-54edc6b02c61.jsonl`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3
