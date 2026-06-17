---
id: BUG-2202
title: 'rn-implement: re_enqueue_unblocked spuriously re-enqueues stalled issues'
type: BUG
priority: P2
status: done
discovered_date: 2026-06-17
discovered_by: audit-loop-run
captured_at: '2026-06-17T02:40:00Z'
completed_at: '2026-06-17T16:31:25Z'
relates_to:
- ENH-2195
labels:
- rn-implement
- orchestration
- queue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2202: rn-implement — re_enqueue_unblocked spuriously re-enqueues stalled issues

## Summary

`re_enqueue_unblocked` (added by ENH-2195) checks whether all `blocked_by` deps are done and
re-enqueues if so — but it does not check *why the issue was deferred*. An issue deferred for
"remediation stalled" gets re-enqueued if its `blocked_by` deps happen to be done, triggering a
wasteful second remediation pass that reaches the same stall.

## Current Behavior

`re_enqueue_unblocked` in `loops/rn-implement.yaml` scans `deferred.txt` and re-enqueues any
issue whose `blocked_by` dependencies are resolved — regardless of *why* the issue was originally
deferred. Issues deferred due to "remediation stalled" are re-enqueued even though their deferral
is not dependency-driven, causing redundant passes that always reach the same stall.

## Expected Behavior

`re_enqueue_unblocked` should only re-enqueue entries whose deferral reason explicitly contains
`blocked_by`. Issues deferred for other reasons (stall, depth-capped, skipped, etc.) should
remain in `deferred.txt` unchanged after the re-enqueue pass runs.

## Steps to Reproduce

1. FEAT-1156 is deferred in pass 1 — reason: `"remediation stalled (scores did not converge
   across passes)"`. Deferral line in `deferred.txt`:
   ```
   FEAT-1156  remediation stalled (...) and decomposition declined to split; ...
   ```
2. FEAT-1262 is implemented.
3. `re_enqueue_unblocked` runs. It reads FEAT-1156's `blocked_by: FEAT-1112` frontmatter, sees
   FEAT-1112 is `done` → no unmet deps → re-enqueues FEAT-1156.
4. FEAT-1156 enters a second remediation pass (13 more iterations) → same stall → deferred again.
   **Wasted: ~13 loop iterations and ~10 minutes of wall-clock time.**

## Root Cause

`re_enqueue_unblocked` action in `loops/rn-implement.yaml` (`re_enqueue_unblocked` state):

```bash
# Current logic (simplified):
for each line in deferred.txt:
    ID = line[0]
    UNMET = check_blocked_by_deps(ID)
    if UNMET is empty:
        re-enqueue ID   # <-- re-enqueues regardless of deferral reason
```

The `deferred.txt` format already encodes the reason:
- `FEAT-1156  remediation stalled ...` — deferred for stall, NOT for blocked deps
- `FEAT-1157  blocked_by FEAT-1156 (not done)` — deferred for unmet dep (correct to re-enqueue)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed in `scripts/little_loops/loops/rn-implement.yaml`, state `re_enqueue_unblocked` at line 552
- The `while IFS= read -r line` loop starts at line 574; `ID=$(echo "$line" | awk '{print $1}')` is at line 576 — the reason field is never read in shell or passed to the embedded Python block
- `mark_deferred` state (line 801) is the sole writer of `deferred.txt`, using `echo "$ID  $REASON" >> "$RUN_DIR/deferred.txt"` (two-space separator); `REASON` begins with `"blocked_by"` only for dep-gated issues, making `grep -q "blocked_by"` a reliable discriminator

## Proposed Solution

Filter `deferred.txt` entries by reason before checking deps. Only re-enqueue entries whose
reason line contains `blocked_by`:

```bash
# In the re_enqueue_unblocked while-loop:
REASON=$(echo "$line" | cut -d' ' -f2-)
if ! echo "$REASON" | grep -q "blocked_by"; then
    echo "$line" >> "$NEW_DEFERRED"   # keep in deferred; not blocked-by-driven
    continue
fi
# Existing blocked_by dep check follows...
```

Alternatively, parse the deferred reason from a structured format (e.g. JSON per entry) to
make filtering unambiguous.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `re_enqueue_unblocked` state (line 552), while-loop body (line 574): add reason-filter after `ID=` extraction at line 576

### Dependent Files (Callers/Importers)
- N/A — loop state machine; no Python callers invoke `re_enqueue_unblocked` directly

### Similar Patterns
- `mark_deferred` state (line 801 in same file) — sole writer of `deferred.txt`; confirms two-space `<ID>  <REASON>` format and the `"blocked_by"` prefix convention for dep-gated entries
- `init` state and `report` state also reference `deferred.txt` but only truncate/count — neither needs a reason-filter fix

### Tests
- `scripts/tests/test_rn_implement.py::TestReEnqueueUnblocked` (line 819) — 10 existing Pattern 1 tests (YAML string assertions, no shell execution)
  - Add `test_re_enqueue_skips_stall_deferred_entries`: assert action string contains `blocked_by` reason-filter logic (e.g. `assert 'grep -q "blocked_by"' in action` or equivalent substring)
  - For execution-level coverage: follow Pattern 3 from `test_rn_remediate.py` — extract the while-loop shell section from the loaded YAML, seed `tmp_path` with `deferred.txt` containing one stalled + one blocked entry, run via `subprocess.run(["bash", "-c", env + script], cwd=tmp_path)`, assert only the blocked entry is consumed and the stalled entry remains

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed 10 tests in class (not 8): includes `test_re_enqueue_unblocked_state_exists` (822) and `test_route_rem_implemented_routes_to_re_enqueue` (827) not counted in prior pass
- No existing tests break — string assertions remain valid after the reason-filter addition
- `test_re_enqueue_skips_issues_with_no_blocked_by` (861) tests the Python block (frontmatter check); the new fix adds a *shell-level* guard before Python runs — distinct coverage targets, no overlap

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` line 384 — `deferred.txt` artifact table row states: "`re_enqueue_unblocked` removes entries mid-run when their blockers resolve (ENH-2195)." After the fix, only `blocked_by`-reason entries are removed; stalled entries remain. Update wording to reflect the reason-filter gate.
- `docs/guides/LOOPS_REFERENCE.md` line 400 — FSM flow diagram parenthetical reads: `(scan deferred.txt for issues now unblocked)`. Update to note that only `blocked_by`-deferral entries are eligible for re-enqueue.

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/rn-implement.yaml`, navigate to `re_enqueue_unblocked` state (line 552), while-loop body starting at line 574
2. After `ID=$(echo "$line" | awk '{print $1}')` (line 576), add reason-filter: extract `REASON` from the deferral line; write `$line` to `$NEW_DEFERRED` and `continue` (skip re-enqueue) if `REASON` does not contain `blocked_by`
3. Confirm non-`blocked_by` entries flow to `echo "$line" >> "$NEW_DEFERRED"` before the `continue` so they persist in `deferred.txt` after the `mv "$NEW_DEFERRED" "$DEFERRED"` atomic rename at the end of the loop
4. Add test in `scripts/tests/test_rn_implement.py::TestReEnqueueUnblocked` (class at line 819): `test_re_enqueue_skips_stall_deferred_entries` — assert the action string contains the reason-filter (`grep -q "blocked_by"` or equivalent); optionally add an execution-level test following Pattern 3 from `test_rn_remediate.py`
5. Run `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` to confirm no new rule violations

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_REFERENCE.md` line 384 — revise the `deferred.txt` artifact table row to state that `re_enqueue_unblocked` only removes entries whose deferral reason contains `blocked_by`; stalled and depth-capped entries remain untouched
7. Update `docs/guides/LOOPS_REFERENCE.md` line 400 — revise the FSM flow diagram parenthetical `(scan deferred.txt for issues now unblocked)` to note the reason-filter gate

## Impact

- Every run that implements any issue after a stalled issue causes the stalled issue to be
  re-attempted, burning iterations and time with zero probability of different outcome.
- In the observed run: 13 wasted depth-0 iterations + 13 wasted depth-1 (rn-remediate) iterations.

## Acceptance Criteria

- [ ] `re_enqueue_unblocked` only re-enqueues entries whose deferral reason contains `blocked_by`
- [ ] Issues deferred for "remediation stalled", "depth-capped", "skipped", etc. remain in
      `deferred.txt` unchanged after `re_enqueue_unblocked` runs
- [ ] Add a test: seed `deferred.txt` with a stalled entry + a blocked entry; after implementing
      the blocker dependency, only the blocked entry is re-enqueued

## Status

**Open** | Created: 2026-06-17 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-17T16:27:50 - `b2ca9ab9-ae9a-445a-8889-96331c7bfcd4.jsonl`
- `/ll:wire-issue` - 2026-06-17T16:08:08 - `8d05cf97-d74d-42ee-ad63-4a73c61b6754.jsonl`
- `/ll:refine-issue` - 2026-06-17T15:59:23 - `f44eedec-25a6-4623-a9df-a02a2ced8039.jsonl`
- `/ll:format-issue` - 2026-06-17T15:50:25 - `3d25f02e-d82c-4d29-a0c1-042f2c86a5cb.jsonl`
