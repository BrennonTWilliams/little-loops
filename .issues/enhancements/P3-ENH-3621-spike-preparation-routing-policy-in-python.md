---
id: ENH-3621
type: ENH
title: 'Spike: preparation routing policy in Python'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:17:01Z'
parent: EPIC-3565
labels:
- spike
blocked_by:
- ENH-3618
relates_to:
- ENH-3606
blocks:
- ENH-3606
---

# ENH-3621: Spike: preparation routing policy in Python

## Summary

Time-boxed spike (1–2 days) to test whether autodev's second-pass preparation routing can be
expressed as a pure Python policy (`decide(snapshot, facts) -> Step`) driven by a small
dispatch loop and an append-only fact log, instead of relocating the 39-state ladder into
`prepare-issue.yaml` intact (ENH-3606). The spike's evidence decides ENH-3606's shape.

Spike code lives on branch `spike/preparation-policy` and is **not merged to `main`**. Only the
report (`thoughts/spikes/preparation-policy-spike.md`) and issue updates land.

## Current Behavior

ENH-3606 plans to move the strongly connected second-pass cluster (selectors, wire/refine,
reconcile/design remedy, size-review/atomic, go/no-go, pre-deferral remedy, shared rescoring
chain) into the wrapper as YAML states. Five design reviews kept finding boundary bugs, and
the move regresses resume: the executor restores only the parent's `current_state`, so a
mid-ladder resume restarts the `loop:` child from `initial` (see ENH-3606 "Resume and
handoff"). The routing policy is encoded in graph shape plus ~20 run_dir handshake files
(repair-cycle counter, rescore origin, retry/contradiction/remedy/pending/armed markers,
once-per-pass markers, guard-2 captured stdout).

## Expected Behavior

A report with a per-scenario parity table, resume matrix, checkpoint/rule table, quirks
found, LOC, and a PASS/FAIL recommendation versus ENH-3606, measured against the ENH-3618
characterization harness.

## Proposed Solution

- **Policy** `scripts/little_loops/preparation_policy.py` (spike branch only):
  - `StepKind` = `RUN_CHILD`, `WIRE`, `REFINE_GAP`, `RESCORE`, `RECONCILE`, `SIZE_REVIEW`,
    `GO_NO_GO`, `FINISH`, `STOP`;
  - frozen `Step(kind, seq, payload, reason, evidence)`;
  - `next_preparation_step(config, issue_id, run_dir, *, readiness_threshold,
    outcome_threshold) = decide(snapshot_issue(...), load_facts(...))`, with `decide()` pure;
  - reuses `select_next_obligation` (tier-1 skipped) and the existing check-design /
    check-gate / readiness helpers.
- **Fact log** `run_dir/prep-facts/<ID>.jsonl` (`{pass, seq, kind: intent|done|obs, step,
  payload}`), append-only, keyed by (pass, seq). Pass id from `prep-pass-<ID>`, written by
  autodev's `dequeue_next`. Replaces: the repair-cycle counter (count of done facts), the
  rescore return address (the done fact preceding `RESCORE`), the retry / contradiction /
  remedy / pending / armed handshakes, "once per pass" graph constraints, and guard-2
  captured stdout (`guard2` on the `SIZE_REVIEW` done fact). Keep `design-gate-failed`
  never-cleared for parity, flagged as a bug candidate (see BUG-3620).
- **Writers separated from decisions**:
  - `ll-issues prep step` — replay an open intent, else decide + append intent + idempotent
    preconditions;
  - `ll-issues prep record [--guard2]`;
  - `ll-issues prep apply` — sole writer of ledger row → set-status → run-record → reopen →
    rm inflight.
  - The wrapper never stages; autodev's `check_passed` does.
- **Prototype** `loops/prepare-issue-policy.yaml`, ≤ 15 states: `select_step` → one action
  state per kind (`run_child` is `loop: refine-to-ready-issue`) → `record_step` →
  `select_step`; `run_size_review` → `classify_guard2`; `apply_outcome` → done/failed;
  `mark_rate_limited`; `max_steps: 80` plus a policy infra-STOP at > 15 done facts per pass.
- **Harness hookup**: the prototype is copied into the tmp `loops_dir` as `prepare-issue.yaml`;
  a fixture applies ENH-3606's boundary-edge retargets to a copy of `autodev.yaml` and adds
  the `prep-pass-$CURRENT` write in `dequeue_next` (ENH-3618 parametrization hooks).
- **De-risk first**: before coding, write the checkpoint → rule-order table for the four
  hardest scenarios: guard-2 across epochs, first gate skipping check-design,
  DECISION/PROOF re-entry, go/no-go requiring prior deferral.

### Pass criteria

**PASS (all)**:
1. Every characterization scenario matches today on skipped rows (order), queue, staged,
   record token, status/`deferred_reason`, `summary.json` and slash-command sequence, with
   differences only from an enumerated, justified list (known: scores-absent →
   `refine_failed_infra`).
2. No autodev event enters a moved state.
3. Crash injection at each action boundary and mid-action + `resume()` yields identical
   artifacts, ≤ 1 replayed command, identical counters.
4. `decide()` is table-tested; wrapper ≤ 15 states; no `rm -f` in the wrapper.

**FAIL (any)**: a rule needs an implicit program counter beyond "last done fact"; > 2
unexplained diffs; a resumed run diverges; the hardest 4 scenarios are not at parity by the
end of day 1.

## Integration Map

### Files to Modify
- Spike branch only: `scripts/little_loops/preparation_policy.py`,
  `scripts/little_loops/loops/prepare-issue-policy.yaml`, `ll-issues prep` subcommands
- On `main`: `thoughts/spikes/preparation-policy-spike.md` (report)

### Dependent Files (Callers/Importers)
- `little_loops.cli.issues` next-obligation (`select_next_obligation`), check-design,
  check-gate, check-readiness helpers

### Similar Patterns
- `little_loops.fleet_improve` (thin shell → module)

### Tests
- ENH-3618 characterization suite, parametrized with the prototype; table tests for `decide()`

### Documentation
- The spike report only

### Configuration
- N/A

## Impact

- **Priority**: P3 — decides ENH-3606's shape before its Very Large implementation starts
- **Effort**: Small-Medium — 1–2 day time box
- **Risk**: Low — isolated branch; only the report lands
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: spike branch code, the report, and issue updates (ENH-3606 / EPIC-3565).
- **Out of scope**: merging any spike code to `main`; implementing ENH-3606 or its
  replacement; unifying preparation across `recursive-refine` and `rn-*` loops.

## Acceptance Criteria

- [ ] Checkpoint → rule-order table for the four hardest scenarios exists before coding
- [ ] Report at `thoughts/spikes/preparation-policy-spike.md` with per-scenario parity table, resume matrix, checkpoint/rule table, quirks found, LOC, and a recommendation versus ENH-3606
- [ ] The verdict is stated as PASS or FAIL against the criteria above, with evidence per criterion
- [ ] No spike code is merged to `main`

## Status

**Open** | Created: 2026-09-27 | Priority: P3
