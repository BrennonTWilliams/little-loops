---
discovered_date: 2026-03-06
discovered_by: capture-issue
confidence_score: 80
outcome_confidence: 72
---

# BUG-616: `ready-issue` returns `CORRECTED` instead of `BLOCKED` when open blockers exist

## Summary

When `ready-issue` validates an issue that has an open blocker in its `## Blocked By` section, it returns verdict `CORRECTED` (if it also made line-drift fixes) instead of a dedicated `BLOCKED` verdict. Downstream automation (sprint runner, `ll-auto`) interprets `CORRECTED` as "ready to implement" and proceeds with implementation, ignoring the blocker.

## Steps to Reproduce

1. Have an issue (e.g. ENH-552) with an active blocker (FEAT-555) listed in `## Blocked By`
2. Run `/ll:ready-issue ENH-552` (or trigger it via `ll-sprint run`)
3. Observe: verdict is `CORRECTED` because line numbers were also updated
4. Sprint runner sees `CORRECTED` → proceeds to Phase 2 implementation
5. Implementation runs on the same files as the open blocker → potential merge conflict

## Current Behavior

`ready-issue` returns `CORRECTED` (or `PASS`) even when the issue has an unresolved blocking dependency. The `READY_FOR` section may contain a caveat like "Implementation: Yes (after FEAT-555 lands)" but the top-level verdict does not reflect the blocked state.

Observed in `ll-sprint-cli-polish.log` at lines 380–416:
- Blocker check row: `WARN | **FEAT-555 is still open**`
- READY_FOR: `Implementation: Yes (after FEAT-555 lands)`
- Verdict: `CORRECTED` ← should be `BLOCKED`

## Expected Behavior

When any issue listed in `## Blocked By` is still active (exists in `.issues/` outside `completed/` or `deferred/`), `ready-issue` should return verdict `BLOCKED` regardless of other corrections made. The `BLOCKED` verdict must be the top-level signal so that all callers (sprint runner, `ll-auto`) can detect it without parsing the prose body.

The existing `CORRECTIONS_MADE` content should still be recorded in the output but the verdict must be `BLOCKED`.

## Motivation

This bug causes incorrect automation behavior:
- Blocked issues get implemented prematurely, risking merge conflicts with in-progress blocker work
- Sprint runner (`ll-sprint run`) and `ll-auto` both trust the `ready-issue` verdict — a wrong verdict cascades through all automation paths
- Manual intervention is required to catch and revert premature implementations, negating automation's time savings

## Root Cause

- **File**: `commands/ready-issue.md`
- **Anchor**: Verdict taxonomy at `### 4. Determine Verdict` (line ~183) and blocker check at `#### Dependency Status` (line ~148)
- **Cause**: The blocker check at lines 148-154 validates `## Blocked By` entries and flags open blockers as `WARNING`, but line 156 explicitly states: _"Open blockers are a WARNING, not a failure. The issue can still be marked READY."_ The verdict taxonomy (lines 183-190) only contains `READY`, `CORRECTED`, `NOT_READY`, `CLOSE`, `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION` — no `BLOCKED` verdict exists.

Additionally, `scripts/little_loops/output_parsing.py:23` defines `VALID_VERDICTS = ("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW", "CLOSE")` — the parsing layer also has no awareness of a `BLOCKED` verdict, and `_extract_verdict_from_text()` at line 70 only searches for those 5 values.

## Proposed Solution

1. Add `BLOCKED` to the verdict taxonomy in `ready-issue`
2. After validating blocker references: if any `## Blocked By` entry resolves to an active issue file, set verdict `BLOCKED` (overrides `CORRECTED`)
3. Document the new verdict in `ready-issue` output format docs

## Implementation Steps

1. **Modify `commands/ready-issue.md`**:
   - Add `BLOCKED` to the verdict taxonomy table at `### 4. Determine Verdict` (line ~183): `| BLOCKED | Issue has unresolved blocking dependencies | Any Blocked By entry resolves to an active issue |`
   - Change line 156 from "Open blockers are a WARNING, not a failure" to specify that open blockers force `BLOCKED` verdict
   - Add `BLOCKED` to the verdict priority order: blockers override all other verdicts (check before READY/CORRECTED)
   - Add `BLOCKED` to the output format at `### 6. Output Format` (line ~241): `[READY|CORRECTED|NOT_READY|CLOSE|BLOCKED|REGRESSION_LIKELY|POSSIBLE_REGRESSION]`
   - Add `## BLOCKED_BY` output section template listing the open blockers

2. **Modify `scripts/little_loops/output_parsing.py`**:
   - Add `"BLOCKED"` to `VALID_VERDICTS` tuple (line 23)
   - Add `"BLOCKED"` to the verdict search order in `_extract_verdict_from_text()` (line 70)
   - Update `parse_ready_issue_output()` return: set `is_ready = False` when verdict is `BLOCKED` (line 369: change to `is_ready = verdict in ("READY", "CORRECTED")` — already excludes BLOCKED, but verify)

3. **Verify downstream callers handle BLOCKED correctly** (companion BUG-617):
   - `scripts/little_loops/issue_manager.py:474` — `not parsed["is_ready"]` will catch BLOCKED since `is_ready` will be False
   - `scripts/little_loops/parallel/worker_pool.py:321` — same `not ready_parsed["is_ready"]` check
   - Sprint runner delegates to issue_manager, so covered transitively

4. **Add test** in `scripts/tests/test_output_parsing.py`: test that BLOCKED verdict is parsed correctly and sets `is_ready=False`, `should_close=False`

## Integration Map

### Files to Modify
- `commands/ready-issue.md` — verdict taxonomy (line ~183), blocker-check policy (line ~156), output format (line ~241)
- `scripts/little_loops/output_parsing.py` — `VALID_VERDICTS` (line 23), `_extract_verdict_from_text()` (line 70)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:474` — `not parsed["is_ready"]` already handles non-ready verdicts; BLOCKED will be caught since `is_ready` stays False (verify only, no code change needed)
- `scripts/little_loops/parallel/worker_pool.py:321` — same `not ready_parsed["is_ready"]` check (verify only)
- `scripts/little_loops/cli/sprint/run.py` — sequential retry verdict dispatch (companion fix in BUG-617 for explicit BLOCKED branch + `skipped_blocked` state)

### Similar Patterns
- `commands/ready-issue.md:148-154` — existing blocker validation logic that already checks `## Blocked By` entries against active issue directories; currently emits WARNING only, needs to force BLOCKED verdict
- `scripts/little_loops/dependency_graph.py:112-134` — `get_ready_issues()` / `get_blocking_issues()` already implement blocker-aware scheduling at the graph level; the ready-issue verdict should mirror this at the validation level

### Tests
- `scripts/tests/test_output_parsing.py` — add test for BLOCKED verdict parsing (existing file has comprehensive verdict parsing tests)
- `scripts/tests/test_issue_manager.py:524-566` — existing blocker scheduling tests; add test verifying `_process_issue()` handles BLOCKED verdict from ready-issue

### Documentation
- `commands/ready-issue.md` — verdict taxonomy docs within the command itself (self-documenting)

### Configuration
- N/A

## Impact

- **Priority**: P2 — causes incorrect automation behavior; blocked issues get implemented prematurely
- **Effort**: Low — verdict taxonomy change + one new check in ready-issue logic
- **Risk**: Low — additive change; no existing callers handle `BLOCKED` yet (see BUG-617 for the companion fix)
- **Breaking Change**: No (new verdict; callers that don't handle `BLOCKED` will treat it as unknown, which is a safe no-op if BUG-617 is also fixed)

## Labels

`bug`, `ready-issue`, `sprint`, `automation`

## Status

Completed

## Resolution

- **Fix Date**: 2026-03-06
- **Fix Commit**: (see commit)
- **Files Changed**:
  - `commands/ready-issue.md` — added `BLOCKED` verdict to taxonomy, changed blocker check policy from WARNING to BLOCKED override, updated output format and integration table
  - `scripts/little_loops/output_parsing.py` — added `"BLOCKED"` to `VALID_VERDICTS`, added to `_extract_verdict_from_text()` search order, updated old-format regex
  - `scripts/tests/test_output_parsing.py` — added `test_blocked_verdict` and `test_blocked_verdict_with_corrections` tests
- **Summary**: Added `BLOCKED` as a first-class verdict in `ready-issue`. Open blockers now force `BLOCKED` verdict (overriding `CORRECTED`/`READY`). Automation callers already handle non-ready verdicts via `is_ready=False`, so no caller changes were needed.

## Related

- BUG-617 should be fixed in the same release (companion fix — sprint runner must handle `BLOCKED` verdict)

## Blocks

- BUG-617

## Session Log
- `/ll:manage-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:capture-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec3d1ef8-aeec-4ccb-bd08-ffea1f74e5ef.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID, DEP_ISSUES: circular dep with BUG-617 fixed (changed Blocked By to Related, added Blocks)
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bc080c9-9927-4928-8886-2faf81c31f92.jsonl`
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bc080c9-9927-4928-8886-2faf81c31f92.jsonl`
- `/ll:refine-issue` - 2026-03-07T03:44:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84d93c18-f729-4cd9-b9c3-7999ecffeae1.jsonl`
- `/ll:ready-issue` - 2026-03-07T04:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7e9630a-0d1b-4f88-880b-9943a12c5c71.jsonl`
- `/ll:ready-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4b5caf30-71a2-4fbb-ab07-56d5862b8a76.jsonl`
- `/ll:ready-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5086416e-eec9-4168-aeef-1b6ab9549a6d.jsonl`
