# ENH-816 Implementation Plan: Analyze-loop with name arg scopes to most recent execution

**Issue**: ENH-816
**Date**: 2026-03-19
**Action**: improve
**Effort**: Small — two changes to `skills/analyze-loop/SKILL.md`

---

## Summary

When `/ll:analyze-loop <loop-name>` is invoked with a loop name, it currently calls `ll-loop history <loop_name> --json` with no `run_id`, returning run summary metadata for all archived runs — not the event stream for a single execution. The fix resolves the most recent `run_id` first, then calls history with that `run_id` to get the proper event stream.

---

## Phase 1: Modify Step 1 (add run_id resolution)

**File**: `skills/analyze-loop/SKILL.md:32`

**Before**: "If `loop_name` argument is provided, skip to Step 2."

**After**: Replace with a sub-step that:
1. Calls `ll-loop history <loop_name> --json` (no run_id → returns run summary list)
2. Parses the JSON array (newest-first order per `_list_archived_runs`)
3. Extracts `runs[0]["run_id"]` as `LATEST_RUN_ID`
4. If empty array → report "No archived runs found for `<loop_name>`." and stop

## Phase 2: Modify Step 2 (use LATEST_RUN_ID)

**File**: `skills/analyze-loop/SKILL.md:67`

**Before**: `ll-loop history <loop_name> --json --tail <tail_arg_or_200>`

**After**: `ll-loop history <loop_name> <LATEST_RUN_ID> --json --tail <tail_arg_or_200>`

---

## Success Criteria

- [x] Step 1 includes run_id resolution sub-step when loop_name is provided
- [x] Step 2 uses `<LATEST_RUN_ID>` in the history command
- [x] Auto-selection path (no loop_name) is unchanged
- [x] Empty history case is handled gracefully

---

## Notes

- No Python code changes required
- CLI already supports optional `run_id` positional arg in `ll-loop history`
- `_list_archived_runs` returns newest-first (lexicographic sort reversed), so `runs[0]` is always the most recent
