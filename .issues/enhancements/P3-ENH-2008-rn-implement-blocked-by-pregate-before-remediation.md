---
id: ENH-2008
title: "rn-implement: gate on blocked_by frontmatter before running remediation"
type: ENH
priority: P3
status: open
captured_at: '2026-06-07T00:00:00Z'
discovered_date: '2026-06-07'
discovered_by: rn-implement-vision-review
blocked_by:
- BUG-2003
- BUG-2006
relates_to:
- BUG-2006
- FEAT-1991
labels:
- rn-implement
- orchestration
- efficiency
---

# ENH-2008: Gate on blocked_by frontmatter before running remediation

## Summary

In default FIFO mode, `rn-implement` runs the **entire** remediation cycle on an issue whose
`blocked_by` frontmatter dependencies are not yet satisfied — `assess → diagnose → wire/refine →
re_assess` for up to `max_remediation_passes` iterations, then `run_decomposition → NO_CHILDREN` —
before BUG-2006 finally defers it. The blocker is structural (an unmerged dependency), so no amount
of prose remediation can raise the scores. The work is wasted: in run `rn-implement-20260607T122052`,
FEAT-2001 and FEAT-2002 (both carrying `blocked_by` deps under EPIC-1867) consumed **2 of 6**
processed slots this way (33% of the run) with zero output.

A cheap upfront gate — *"if this issue has unmet `blocked_by` deps, defer it before scoring"* —
eliminates the wasted passes and is the change that lets the per-issue router honor the issue
**frontmatter**, not just the dimensional scores. Today `blocked_by` is consulted only in the
`value_ranked` *queue-ordering* path (`select_next`), never in the per-issue *route*.

## Current Behavior

- `dequeue_next → fifo_pop` pops the head with **no** `blocked_by` check (only `select_next`, used
  by `schedule_mode: value_ranked`, checks dependency readiness — and even it only affects ordering,
  not whether the issue is processed)
- `check_depth → run_remediation` enters `rn-remediate`, which scores and remediates the issue
- Scores do not move (structural blocker) → `CONVERGED_STALLED → NEEDS_DECOMPOSE`
- `run_decomposition → NO_CHILDREN`
- (post-BUG-2006) `mark_deferred` — but only **after** the full remediation budget is spent

## Expected Behavior

- After dequeue (both `fifo_pop` and `select_next`), before `check_depth`/`run_remediation`,
  `rn-implement` checks the dequeued issue's `blocked_by` frontmatter against completed issues
- If any `blocked_by` dependency is **not** `done`, route directly to `mark_deferred` (BUG-2006's
  state) with a dependency-specific reason — skipping `run_remediation` and `run_decomposition`
  entirely
- If all `blocked_by` deps are satisfied (or there are none), proceed to `check_depth` as today
- The deferred issue's `status` is set so it re-surfaces naturally once its blocker merges

## Motivation

1. **Wasted budget**: a structurally-blocked issue burns up to `max_remediation_passes` LLM-driven
   remediation passes plus a decomposition attempt, all guaranteed to fail to move scores
2. **Honors the vision**: the user's intent is routing "based on those scores **and** the issue
   frontmatter." `blocked_by` is first-class frontmatter that should short-circuit the router, not
   just reorder the queue
3. **Faster, clearer signal**: the issue is deferred with an accurate "blocked by X (not done)"
   reason immediately, instead of an after-the-fact "scores didn't converge" inference

## Scope Boundaries

- Does **not** modify `rn-remediate` internals — the gate lives entirely within `rn-implement`'s post-dequeue router
- Does **not** change `select_next` (value_ranked) ordering behavior — only adds a per-issue check after dequeue in both FIFO and value_ranked paths
- Does **not** change the `blocked_by` frontmatter schema or semantics
- Does **not** implement automatic re-queuing when a blocker is resolved — re-surfacing is passive (user marks blocker done, re-runs)
- Does **not** apply to any loop other than `rn-implement`

## Proposed Solution

Add a `check_blocked_by` state between dequeue and `check_depth`. Both `fifo_pop.on_yes` and
`select_next.on_yes` route to it (instead of directly to `check_depth`):

```yaml
check_blocked_by:
  action_type: shell
  action: |
    ID="${captured.input.output}"
    # Resolve issue file (reuse the hardened lookup from BUG-2003)
    ISSUE_FILE=$(find .issues -name "*$ID*" ! -path "*/completed/*" 2>/dev/null | head -1)
    [ -z "$ISSUE_FILE" ] && { echo "READY"; exit 0; }   # unresolved → let downstream handle
    # Extract blocked_by (list or comma-separated scalar)
    DEPS=$(ll-issues show "$ID" --json 2>/dev/null | jq -r '.blocked_by // [] | .[]?' 2>/dev/null)
    [ -z "$DEPS" ] && { echo "READY"; exit 0; }
    DONE_IDS=$(ll-issues list --json --status done 2>/dev/null | jq -r '.[].id')
    UNMET=""
    for d in $DEPS; do
      echo "$DONE_IDS" | grep -qxF "$d" || UNMET="$UNMET $d"
    done
    if [ -n "$UNMET" ]; then
      echo "$UNMET" > "${captured.run_dir.output}/blocked_by_unmet_$${ID}.txt"
      echo "BLOCKED"
    else
      echo "READY"
    fi
  capture: blocked_by_status
  next: route_blocked_by
  on_error: check_depth   # fail-open: never block processing on a gate error

route_blocked_by:
  evaluate:
    type: output_contains
    source: "${captured.blocked_by_status.output}"
    pattern: "BLOCKED"
  on_yes: mark_deferred   # reuse BUG-2006's state; reason = "blocked_by <unmet> not done"
  on_no: check_depth
  on_error: check_depth
```

`mark_deferred` (added by BUG-2006) should incorporate the unmet-dependency list in its reason
string when `blocked_by_unmet_<ID>.txt` exists, so the deferred reason names the specific blocker.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — add `check_blocked_by` + `route_blocked_by`
  states; repoint `fifo_pop.on_yes` and `select_next.on_yes` to `check_blocked_by`; enrich
  `mark_deferred` reason with the unmet-dependency list

### Dependent Files (Callers/Importers)
- None — purely internal to `rn-implement`

### Similar Patterns
- `select_next` (`rn-implement.yaml`) already computes a dependency-ready set via `blocked_by` +
  `ll-issues list --status done`; this gate reuses the same readiness logic for FIFO mode
- `mark_deferred` (BUG-2006) — shared defer target

### Tests
- TBD — `ll-loop run rn-implement` on a backlog with a `blocked_by`-gated issue; assert it lands in
  `deferred.txt` with a dependency reason and that `run_remediation` was never entered for it

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — note that FIFO mode now defers on unmet `blocked_by`

### Configuration
- Optional: a `respect_blocked_by` context flag (default `true`) to disable the gate

## Implementation Steps

1. Add `check_blocked_by` (shell state) and `route_blocked_by` (evaluate state) to `rn-implement.yaml`
2. Repoint `fifo_pop.on_yes` and `select_next.on_yes` edges to `check_blocked_by` (was `check_depth`)
3. Enrich `mark_deferred` reason string with the unmet dep list from `blocked_by_unmet_<ID>.txt` when it exists
4. Run `ll-loop validate rn-implement` to confirm no new MR violations
5. Smoke test: run with a `blocked_by`-gated issue in the backlog and verify it lands in `deferred.txt` without entering `run_remediation`

## Acceptance Criteria

- An issue with an unmet `blocked_by` dependency is deferred **without** entering `run_remediation`
  or `run_decomposition`
- The deferred reason names the specific unmet dependency (e.g. "blocked_by FEAT-2001 (not done)")
- An issue with all `blocked_by` deps `done` (or none) proceeds normally through `check_depth`
- The gate fails open: any resolution/lookup error routes to `check_depth`, never silently drops
- Re-running after the blocker is marked `done` lets the previously-deferred issue proceed

## Dependencies

- **BUG-2006** — provides the `mark_deferred` state this gate routes into. Implement BUG-2006 first
  (or land both together).
- **BUG-2003** — provides the hardened issue-file lookup reused here.

## Impact

- **Priority**: P3 — efficiency + correctness-of-signal improvement; not blocking, but it reclaimed
  ~33% of a real run's processed slots and makes frontmatter-aware routing real
- **Effort**: Small-to-Medium — two new states + rewiring two `on_yes` edges; reuses existing
  readiness logic and the BUG-2006 defer state
- **Risk**: Low — fail-open gate; happy path (no/satisfied deps) is unchanged
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-07 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-07T20:59:17 - `8f5b7fbd-10dd-41b7-b7e6-6117a812b179.jsonl`
