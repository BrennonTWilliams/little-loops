---
id: BUG-2026
title: goal-cluster silently routes every EPIC to propose_new_loop (invalid --format flag + input/goal key mismatch)
type: BUG
priority: P2
status: done
captured_at: '2026-06-08T00:00:00Z'
discovered_date: '2026-06-08'
discovered_by: audit-loop-run
completed_date: '2026-06-08'
relates_to:
- FEAT-2024
labels:
- bug
- loops
- goal-cluster
- loop-router
- dispatch
decision_needed: false
size: Small
---

# BUG-2026: goal-cluster → loop-router dispatch silently aborts with zero implementation work

## Summary

Two coupled defects in `scripts/little_loops/loops/goal-cluster.yaml` caused
`goal-cluster` to silently route every EPIC to `propose_new_loop` and abort
without doing any implementation work. Discovered via
`/ll:audit-loop-run rn-build` (run `2026-06-08T204657`).

The two bugs compound: the first feeds the dispatcher a garbage goal list, and
the second drops even that into a context key the sub-loop ignores. Either one
alone produces an empty/incorrect dispatch; together they guarantee a no-op run.

## Bug 1 — `load_goals` used invalid `--format json` flag (EPIC child enumeration silently skipped)

`load_goals` enumerated EPIC children with
`ll-issues list --parent <epic_id> --format json`, but `--format` is not a
valid `ll-issues list` flag (the valid flag is `--json` / `-j`). The subprocess
failed silently, the JSON parse fell back to `'[]'`, and execution fell through
to the raw-text fallback — yielding `goal_text: "EPIC-001"` as a literal string
instead of the 12 child feature issues.

**Observed:** `goals.json` contained
`[{"goal_id": "g01", "goal_text": "EPIC-001", "hints": ""}]` instead of the
child issues.

A second instance of the same invalid flag lived in a `rn-build.yaml` prompt
instruction (`Run \`ll-issues list --format json\``), which would have failed
the same way when an LLM followed it literally.

## Bug 2 — `dispatch_cluster` passed context key `input`, but sub-loops expect `goal`

`dispatch_cluster` handed the batch goal to sub-loops via
`with: {input: "..."}`. But `loop-router` (and the other dispatch targets)
declare `input_key: goal` and read `${context.goal}` throughout. The key
mismatch left `context.goal` empty, so `classify_goal` saw `GOAL: ` (empty
string), concluded "no goal provided," and unconditionally routed to
`propose_new_loop`.

**Observed:** `classify_goal` action preview showed `"GOAL: \n\n"`; LLM output:
"No goal was provided — the GOAL field is empty. BRANCH:propose_new".

## Root Cause

- `goal-cluster.yaml` `load_goals` shell action: `'--format', 'json'` instead of `'--json'`, with the failure swallowed by `except Exception: pass`.
- `goal-cluster.yaml` `dispatch_cluster` `with:` block: key `input:` instead of `goal:`.
- No documented protocol contract pinned the goal variable name across the two loops, so the mismatch was invisible at authoring time.

## Fix

**`scripts/little_loops/loops/goal-cluster.yaml`**
- `load_goals`: `['ll-issues', 'list', '--parent', epic_id, '--format', 'json']` → `[..., '--json']`.
- `load_goals`: added an empty-EPIC guard — a named EPIC that enumerates zero
  children now exits 1 with a clear warning instead of falling through to the
  raw-text fallback (which would re-add the EPIC id as a literal goal and route
  the wrong work).
- `dispatch_cluster`: `with: {input: ...}` → `with: {goal: ...}`.

**`scripts/little_loops/loops/rn-build.yaml`**
- Prompt instruction: `ll-issues list --format json` → `ll-issues list --json`.

**`scripts/tests/test_goal_cluster.py`** — added regression coverage:
- `test_load_goals_epic_enumeration_uses_valid_json_flag` — asserts `--format` is never used and EPIC enumeration uses `--parent <id> --json`.
- `test_load_goals_fails_loudly_on_empty_epic` — asserts the empty-EPIC guard exits 1 with a warning.
- `TestGoalClusterDispatch::test_dispatch_cluster_passes_goal_key_not_input` — pins the `goal:` hand-off contract and forbids `input:`.

## Acceptance Criteria

- [x] `goal-cluster` invoked with `goals=EPIC-NNN` enumerates child issues into `goals.json` (each entry has `goal_id` = child id, `goal_text` = child title).
- [x] Empty child list (new EPIC) is handled gracefully with a warning, not a silent fallback.
- [x] `loop-router` receives a non-empty `${context.goal}` when dispatched from `goal-cluster`.
- [x] `classify_goal` routes to a scoring branch (not `propose_new_loop`) for a valid EPIC goal.
- [x] Regression tests pin both the `--json` flag and the `goal:` dispatch key.

## Verification

- `ll-loop validate goal-cluster` — valid (remaining warnings pre-existing, unrelated).
- `ll-loop validate rn-build` — valid.
- `python -m pytest scripts/tests/test_goal_cluster.py` — 36 passed (4 new).
- `python -m pytest scripts/tests/test_rn_build.py` — 66 passed, 1 skipped.

_Discovered by `/ll:audit-loop-run rn-build` — run `2026-06-08T204657`. Source findings: `goal-cluster-dispatch-bugs.md` (BUG-015 / BUG-016)._


## Session Log
- `hook:posttooluse-status-done` - 2026-06-08T21:22:57 - `ce3e9086-9f94-4f00-bfdb-74fcb4403247.jsonl`
