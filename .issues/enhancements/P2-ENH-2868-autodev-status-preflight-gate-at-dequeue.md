---
id: ENH-2868
type: ENH
priority: P2
status: done
captured_at: '2026-07-27T20:23:55Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- fsm
- autodev
- loops
- guard
completed_at: '2026-07-27T20:36:26Z'
---

# ENH-2868: autodev status pre-flight gate at dequeue

## Summary

`autodev.yaml` accepts any issue ID handed to it on the command line and runs
the full refinement pipeline against it without ever checking the issue's
`status`. A `done`, `cancelled`, or `deferred` issue is refined
(format → refine → wire → confidence-check) before any downstream guard notices
it should never have been processed. Add a status pre-flight state between
`dequeue_next` and `check_decision_at_dequeue` that routes closed/deferred
issues to `skip_inflight`.

## Current Behavior

Traced through `scripts/little_loops/loops/autodev.yaml`:

- **`init`** validates only that `context.input` is non-empty, splits it on
  commas, and writes every ID verbatim to `${context.run_dir}/autodev-queue.txt`.
  No `ll-issues show` / status lookup at all.
- **`dequeue_next`** pops the head and *does* call
  `ll-issues show "$CURRENT" --json`, but only to snapshot `confidence` into
  `autodev-pre-readiness.txt` (FEAT-2751). The `status` field in that same JSON
  payload is discarded.
- Routing goes straight to **`check_decision_at_dequeue`**, which gates only on
  the `decision_needed` flag, then to **`refine_current`**.
- The delegated `refine-to-ready-issue.yaml` has no status guard either — the
  only `status`-adjacent hits in that file are `ll-issues refine-status`, an
  unrelated command.

Every existing status check is **downstream** of a full refine cycle:

| Guard | Where | Catches |
|---|---|---|
| `check_blocked_by` | `rn-implement.yaml` | unmet `blocked_by` deps |
| `check_issue_status` | `rn-implement.yaml` | `done`/`cancelled` before re-entering `rn-remediate` (BUG-2201) |
| active-status filter in `_get_next_issue` | `issue_manager.py` | `implement_current`'s inner `ll-auto --only` finds no candidate for a closed issue → silent no-op |
| `[SKIP-DEFER]` guards | `autodev.yaml` deferral writers (`mark_gate_blocked`, `record_decision_unresolved`, `mark_oversized_atomic`, `recheck_after_size_review`) | prevents *overwriting* a `done`/`cancelled` status with `deferred` |

That last row is the tell: the loop already knows closed issues can flow
through it, but only defends the **write** side. Nothing stops the wasted
refine cycle on the **read** side.

## Expected Behavior

A closed or deferred issue passed to `autodev` is detected on its first
dequeue, recorded as skipped, and the queue advances — before any sub-loop
delegation or LLM call is made against it.

## Motivation

A full `refine-to-ready-issue` pass is the single most expensive unit of work
in the loop: it delegates format → refine → wire → confidence-check, each an
LLM call, per issue. Burning that on an issue that is already `done` is pure
waste, and the failure is silent — the run reports the issue as processed
rather than skipped, so the summary at `finalize_done` misrepresents what the
run actually accomplished.

This is a realistic input, not a hypothetical: `autodev` is invoked with
explicit comma-separated ID lists (by hand, by `auto-refine-and-implement`, and
by the sprint path), and those lists routinely go stale between authoring and
execution — an issue completed out-of-band in a parallel worktree is exactly
the BUG-2201 scenario that already justified the equivalent guard in
`rn-implement`.

## Proposed Solution

Add one state mirroring `rn-implement.yaml`'s `check_issue_status`, wired
between `dequeue_next` and `check_decision_at_dequeue`:

```yaml
  check_status_at_dequeue:
    # ENH-2868: pre-flight status gate. autodev is invoked with explicit ID
    # lists that go stale (issue completed out-of-band in a parallel worktree,
    # cancelled during triage, deferred by a prior run). Without this gate the
    # issue burns a full refine-to-ready-issue delegation before any downstream
    # guard notices. Mirrors rn-implement's check_issue_status (BUG-2201).
    #
    # `ll-issues show --json` reports status display-cased ("Done", "Deferred")
    # — lowercase before comparing, same idiom as record_decision_unresolved.
    # Fail-open: an unresolvable ID or parse error yields PROCESS so a gate
    # error never blocks the queue.
    action_type: shell
    action: |
      ID="${captured.input.output}"
      STATUS=$(ll-issues show "$ID" --json 2>/dev/null \
        | python3 -c "import json,sys; print((json.load(sys.stdin).get('status') or '').lower())" \
        2>/dev/null || echo "")
      case "$STATUS" in
        done|completed|cancelled|deferred)
          echo "SKIP_CLOSED $STATUS" ;;
        *)
          echo "PROCESS" ;;
      esac
    evaluate:
      type: output_contains
      pattern: "SKIP_CLOSED"
    on_yes: skip_inflight
    on_no: check_decision_at_dequeue
    on_error: check_decision_at_dequeue
```

Then repoint `dequeue_next`'s `on_yes: check_decision_at_dequeue` →
`on_yes: check_status_at_dequeue`.

**Design decisions worth confirming during refinement:**

1. **Is `deferred` in the skip set?** Arguments both ways. `deferred` is
   autodev's own not-ready exit code (ENH-2666), so a re-run of the same ID
   list would skip issues the previous run deferred — which is the intended
   ENH-2666 policy ("visibility via `ll-issues deferred-triage`, not by
   re-evaluating the issue every run"). But an operator explicitly re-passing
   a deferred ID may intend a retry. Recommend: **include `deferred` in the
   skip set** for policy consistency, and let operators clear it with
   `ll-issues set-status <ID> open` — matching how ENH-2666 already expects
   deferrals to be resolved. Flag this in the skipped-summary output so the
   skip is not silent.
2. **`blocked` status** — leave it processing. `blocked` (as a status value) is
   distinct from unmet `blocked_by` deps, which `rn-implement` already gates,
   and refinement of a blocked issue is often exactly what unblocks it.
3. **Reuse vs. duplicate** — the lowercase-status shell idiom now appears at
   five sites in `autodev.yaml` (lines ~502, ~664, ~827, ~1371, ~1477) plus
   this new one. Consider extracting it to a `lib/common.yaml` fragment as
   part of this change, or note it as follow-up debt.

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` — new `check_status_at_dequeue`
  state; `dequeue_next.on_yes` repointed. Verify `skip_inflight` records the
  skip in `autodev-skipped.txt` in a form `finalize_done` surfaces distinctly
  (it may need a reason discriminator so "skipped: already done" reads
  differently from "skipped: refine failed").
- `scripts/tests/test_builtin_loops.py` — structural assertions on the new
  state's presence and routing, matching how other autodev guards are covered.
- No Python changes expected; this is loop-YAML only.

## Implementation Steps

1. Read `skip_inflight` in `autodev.yaml` and confirm what it writes to
   `autodev-skipped.txt`; decide whether a skip-reason discriminator is needed
   so `finalize_done`'s summary distinguishes closed-issue skips from
   refinement failures.
2. Add the `check_status_at_dequeue` state as sketched above.
3. Repoint `dequeue_next.on_yes`.
4. Run `ll-loop validate autodev` — confirm no MR-rule regressions (the new
   state is a `shell` state with an `output_contains` evaluator, so MR-1 is
   satisfied; check capture-reachability on `${captured.input.output}`, which
   `dequeue_next` dominates).
5. Add test coverage in `scripts/tests/test_builtin_loops.py`.
6. Run `python -m pytest scripts/tests/`.

## Impact

- **Cost**: eliminates a full 4-call refine delegation per stale ID.
- **Correctness**: run summaries stop reporting closed issues as processed.
- **Risk**: low — fail-open on any gate error, and the guard is a strict
  superset of behavior downstream guards already enforce later.
- **Blast radius**: `autodev.yaml` only; the sprint path
  (`auto-refine-and-implement`) inherits the fix for free.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Issue File Format | canonical status enum; `deferred` discriminator semantics (ENH-2664/ENH-2666) |
| `.claude/CLAUDE.md` § Loop Authoring | `ll-loop validate` MR-rule table |
| `scripts/little_loops/loops/rn-implement.yaml` | `check_issue_status` (BUG-2201) — the pattern to mirror |

## Resolution

Implemented 2026-07-27. The as-built shape diverged from the sketch above in
two places, both deliberate:

1. **`on_yes` targets a new `skip_already_resolved` state, not `skip_inflight`.**
   `skip_inflight` is coupled to refine-failure classification — it reads
   `refine-terminal-class` and exits 1 to hand off to `skip_inflight_infra`
   (ENH-2727). Reusing it would have laundered a clean pre-flight skip through
   a failure-classification path. The new state ledgers the `already_<status>`
   reason stem, clears `autodev-inflight` (BUG-1226), and returns to
   `dequeue_next`.
2. **`finalize_done` gained an `Already-resolved` bucket**, excluded from the
   generic `Skipped` count — the discriminator flagged as an open question in
   Implementation Step 1, resolved the same way ENH-2727 split out
   `refine_failed_infra`.

Design questions from Proposed Solution, as resolved:

- **`deferred` is in the skip set** (per the recommendation) — ENH-2666 policy
  consistency; clear with `ll-issues set-status <ID> open` to force a retry.
- **`blocked` processes normally**, as proposed.
- **Idiom extraction deferred** — the lowercase-status shell block now appears
  at six sites in `autodev.yaml`. Left as follow-up debt rather than widening
  this change's blast radius into five untouched states.

Worth recording: the display-casing quirk is load-bearing, not defensive
padding. `ll-issues show --json` reports `done` as `"Completed"`, verified
against real issues (`BUG-2865 -> SKIP_CLOSED completed`) — a gate matching
only `done` would have been silently inert. Pinned by a parametrized test.

**Changed files**

| File | Change |
|---|---|
| `scripts/little_loops/loops/autodev.yaml` | `check_status_at_dequeue` + `skip_already_resolved` states; `dequeue_next.on_yes` repointed; `finalize_done` bucket |
| `scripts/tests/test_builtin_loops.py` | 18 tests (routing, 11-case classification matrix, ledger stem + fallback, bucket disjointness) |
| `scripts/tests/test_autodev_decision_gate.py` | BUG-2513 assertion rewritten to walk the fall-through chain rather than pin the literal edge |

`ll-loop validate autodev` clean (no new MR warnings). Suite: 16,569 passed;
the 4 remaining failures are pre-existing, from uncommitted `general-task.yaml`
/ ENH-2857 work — confirmed by stashing that file, which flips
`test_no_failure_edge_routes_to_a_success_terminal` green.

## Session Log
- `/ll:capture-issue` - 2026-07-27T20:23:55Z - conversation-mode capture from autodev status-gate trace
- implementation + close - 2026-07-27T20:36:26Z - gate states, tests, BUG-2513 assertion rework

---

## Status

done
