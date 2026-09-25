---
id: BUG-3588
type: BUG
title: Autodev post-repair rescoring accepts stale or absent confidence scores
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T01:54:10Z'
parent: EPIC-3565
blocks:
- BUG-3572
- ENH-3577
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3588: Autodev post-repair rescoring accepts stale or absent confidence scores

## Summary

Split from BUG-3571 (the refine-to-ready half stays there). Autodev's post-repair rescoring
reads readiness evidence for presence, not currency:

- The `rerun_confidence_after_decide|wire|spike|atomic_remediation|reconcile` states route both
  `next` and `on_error` to a successor that reads scores. None of them clears scores first, so a
  rescoring that errors or writes nothing falls through to the pre-repair scores.
- Only `reconcile_current` clears scores (via `/ll:reconcile-issue`'s `set-scores --clear`).
  `rerun_confidence_after_reconcile` is also reached from `count_repair_cycle_refine_for_design`
  (the BUG-3002 Program Design remedy, `/ll:refine-issue`), which clears nothing — so that path
  is stale too.
- On the reconcile path the opposite failure occurs: scores are cleared, and if the rescoring
  writes nothing, `recheck_after_size_review`'s `int(d.get('confidence') or 0)` reads 0 and
  defers the issue as `low_readiness` — an infra failure recorded as a quality verdict.

## Current Behavior

A failed post-repair rescoring in autodev is followed by a gate decision based on the scores from
before the repair, or (after reconcile) on a coerced 0.

## Expected Behavior

Each post-repair gate decides only on scores written by the rescoring that immediately preceded
it. A rescoring that writes nothing is retried once, then classified as infra — never a pass on
old scores and never a quality deferral.

## Steps to Reproduce

1. Run autodev on an issue that carries scores and reaches `run_wire` (or `run_spike`,
   `run_decide`, `remediate_oversized_atomic`, `refine_for_design`)
2. Make the following `/ll:confidence-check` write nothing (host error, or the model skips the
   `ll-issues set-scores` call)
3. Observe the successor gate read the pre-repair scores (or, after reconcile, read 0 and defer
   as `low_readiness`)

## Motivation

Autodev's repair loop edits issue content and then rescores. Without freshness, the
implementation gate can be satisfied by scores about content that no longer exists.

## Root Cause

- **Rerun successors** (`scripts/little_loops/loops/autodev.yaml`): `next` and `on_error` are the
  same target in all five rerun states — `recheck_after_decide`, `enqueue_or_skip` (wire and
  spike), `regate_after_atomic_remediation`, `recheck_after_size_review` (reconcile and
  refine-for-design).
- **Score readers downstream of the reruns** all coerce absence to 0:
  - `ll-issues check-readiness` (`cli/issues/check_readiness.py:readiness_status`) —
    `int(fm.get(...) or 0)`; `ReadinessStatus.raw_confidence`/`raw_outcome` already carry `None`
    for absence (but also for non-digit values, via `_coerce_optional_int`)
  - inline Python in `recheck_after_size_review` (GATE and `CUR_CONFIDENCE`),
    `regate_after_atomic_remediation` (GATE)
  - `check_reconcile_needed` (`cur = str(d.get('confidence') or '')`) — on the wire/spike path
    (`enqueue_or_skip` → `check_parent_resolved_post_size_review` →
    `check_spike_needed_before_skip` → `check_reconcile_needed` → … →
    `recheck_after_size_review`); with a cleared score its `contradiction` branch can still spend
    a `reconcile_current` rewrite before any later gate sees the absence
- **Retry**: `oracles/verify-confidence-scores.yaml` retries once because the dominant no-write
  cause is the model skipping `set-scores`; autodev's reruns call `/ll:confidence-check` bare,
  with no retry and no presence check.

## Proposed Solution

Clear-then-require at the call site, with one presence gate per rerun (same decision as BUG-3571,
Option 3):

1. **Clear before each rerun.** A dedicated shell state (`ll-issues set-scores <ID> --clear`)
   immediately before each of the five `rerun_confidence_after_*` states. The rerun states use
   `fragment: with_rate_limit_handling` on a slash command, so the clear cannot go in their
   action. Predecessors to retarget (six, feeding five clear states): `mark_decide_ran`
   (`on_no`/`on_error`), `run_refine` (wire path — the clear goes after `run_refine`, not after
   `count_repair_cycle_wire`), `count_repair_cycle_spike`, `remediate_oversized_atomic`,
   `count_repair_cycle_reconcile` and `count_repair_cycle_refine_for_design`. The reconcile
   path's predecessor is `count_repair_cycle_reconcile` (`:2149`), not `reconcile_current` —
   `reconcile_current` routes to the counter, which routes to the rerun. Both reconcile-entry
   predecessors target one shared clear state; clearing again after `/ll:reconcile-issue`
   already cleared is a no-op and keeps the two entry paths identical.
2. **Presence gate after each rerun — one state per path, gate and retry folded together.**
   Retarget every rerun's `next`/`on_error` to a per-path `fragment: harness_exit` state
   whose action reads `ll-issues show --json` and:
   - exits 0 when `confidence` and `outcome` are both non-`None` → `on_yes`: the original
     successor;
   - on the first miss, increments a run-dir counter
     (`autodev-rescore-retry-<path>-$ID`), exits 1 → `on_no`: back to the rerun state itself
     (not the clear state — the scores are already absent);
   - on the second miss, exits 3 → `on_cannot_judge: mark_scores_absent_infra`.

   `on_error` → `mark_scores_absent_infra`. The counter is filename-scoped per issue; clear it
   in `dequeue_next` anyway so a re-dequeue in the same run gets its retry back. This catches
   absence before any downstream reader — including `check_reconcile_needed` — so the
   reader-by-reader fixes below are a second line of defense, not the primary fix.
3. **Infra state.** New `mark_scores_absent_infra`, modelled on `mark_gate_infra` (`:1097`):
   append the ID to a new `autodev-scores-absent.txt` (not `autodev-gate-infra.txt`, which is
   the learning-gate record — keep the two causes separable), `rm -f autodev-inflight`, echo a
   distinct `[SCORES_ABSENT]` token, `next: dequeue_next`. The issue is not deferred.
4. **`check-readiness` exit 3.** `cmd_check_readiness` returns 3 with a `SCORES_ABSENT` stderr
   token when `confidence_score` or `outcome_confidence` is absent, before threshold comparison
   and regardless of `--honor-waiver`. Test key presence (`fm.get(key) is None`), not
   `raw_* is None` — `_coerce_optional_int` also returns `None` for present non-digit values,
   which are not "absent".
5. **Defense in depth at existing readers — per-site exit-3 targets.**
   - Switch the three `check-readiness` call sites to `fragment: harness_exit`, but route
     `on_cannot_judge` per site (see the Integration Map table). Only `recheck_after_decide`
     is post-rescore and routes to `mark_scores_absent_infra`. `check_passed` and
     `recheck_scores` run after the refine-to-ready sub-loop, where absent scores are
     legitimate (the sub-loop can break the issue down before scoring): today that is exit 1 →
     `triage_outcome_failure` → … → `detect_children`. Routing it to infra would skip
     `detect_children` and orphan the children, so those two sites route exit 3 to their
     current `on_no` target — explicit, behaviour-preserving.
   - In the two inline-Python GATE readers (`recheck_after_size_review`,
     `regate_after_atomic_remediation`), add the `is None` → exit 3 branch **after** the
     `resolved_by_subloop` status check and **before** the design-gate / `readiness_stagnated`
     / `low_readiness` / `oversized_atomic` branches. A done/cancelled parent with no scores
     must still record `resolved_by_subloop`, not infra.

## Program Design

### Types

- `ABSENT` exit code `3` — new outcome for `check-readiness` when a score field is missing;
  0 pass / 1 fail / 2 issue not found are unchanged.

### Signatures

- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int` — existing; returns 3
  with a `SCORES_ABSENT` token when either score key is absent from frontmatter.

### Call Path

`cmd_check_readiness` -> `readiness_status`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/check_readiness.py` — `cmd_check_readiness`: absent key →
  exit 3; update docstring
- `scripts/little_loops/cli/issues/__init__.py` — `check-readiness` help / `_USAGE` line (`:143`)
- `scripts/little_loops/loops/autodev.yaml` — 11 new states (5 clear + 5 presence gate + 1
  infra):
  - five `clear_scores_before_*` states and six predecessor retargets (Proposed Solution 1)
  - five presence-gate states (`harness_exit`, retry folded in); clear the retry counters in
    `dequeue_next`
  - `mark_scores_absent_infra` (writes `autodev-scores-absent.txt`)
  - `check-readiness` call sites → `harness_exit`, with a per-site exit-3 target:

    | State | `check-readiness` call line | Current `on_no` / `on_error` | Reached after a rescore? | Exit-3 (`on_cannot_judge`) target |
    |---|---|---|---|---|
    | `check_passed` | `:656` | `triage_outcome_failure` / `detect_children` | no — after the refine-to-ready sub-loop | `triage_outcome_failure` (unchanged behaviour; keeps the breakdown → `detect_children` path) |
    | `recheck_after_decide` | `:791` | `snap_and_size_review` | yes (`rerun_confidence_after_decide`) | `mark_scores_absent_infra` |
    | `recheck_scores` | `:1370` | `check_decision_before_size_review` | no — after the refine sub-loop | `check_decision_before_size_review` (unchanged behaviour) |

    All three are `check-readiness … && …` chains; `&&` short-circuits with the failing status,
    so exit 3 survives — keep it that way (no `|| true`, no pipes). `check-design` (chained in
    `recheck_scores`) returns only 0/1/2.
  - inline-Python `is None` → exit 3: `recheck_after_size_review` (`:2208`),
    `regate_after_atomic_remediation` (`:1895`); both route via `shell_exit`
    (`on_error: dequeue_next`), so switch to `harness_exit` +
    `on_cannot_judge: mark_scores_absent_infra`. Place the branch after the
    `resolved_by_subloop` check, before every deferral branch. `recheck_after_size_review` has
    about seven predecessors (`:1667`, `:1768`, `:1788`, `:1818`, `:1836`, `:1857`, `:2204`), most
    of them not rescore paths — the branch applies to all of them

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/rn-remediate.yaml:198` `check_readiness` — safe: its preceding
  state exits 1 to `emit_scores_missing` when either score is missing, so it never sees
  absence; exit 3 would land on `on_error: check_outcome`
- `ll-auto` / manage-issue use `readiness_status()` in-process (`issue_manager.py`), not the
  CLI — unaffected
- `skills/confidence-check/SKILL.md` Phase 4 (`ll-issues set-scores`) — writer unchanged

### Similar Patterns

- `oracles/verify-confidence-scores.yaml` retry-once shape
- `mark_gate_infra` / `GATE_INFRA_FAILED` infra classification
- `fragment: harness_exit` exit-3 abstain routing (ENH-3224)

### Documentation

- `docs/reference/CLI.md` — `ll-issues check-readiness` exit codes (add 3)
- `docs/guides/LOOPS_REFERENCE.md:1041-1063` — autodev flow diagram shows
  `rerun_confidence_after_* → recheck/enqueue` directly; insert the clear and presence-gate hops
- `docs/reference/DEFERRAL_CODES.md` — note that scores-absent is an infra outcome
  (`[SCORES_ABSENT]`, `autodev-scores-absent.txt`), not a deferral code

### Tests

- `scripts/tests/test_check_readiness.py` — add absent-confidence and absent-outcome → exit 3
  cases (with and without `--honor-waiver`) to `TestCheckReadinessExitCodes`; add a present
  non-digit value case that is not reported as absent
- `scripts/tests/test_autodev_loop.py` — clear-before-rerun routing for all five reruns; presence
  gate → retry → `mark_scores_absent_infra`; `check-readiness` exit 3 routing at the three call
  sites (per-site targets from the table); breakdown-without-scores at `check_passed` still
  reaches `detect_children`; done/cancelled parent with no scores at
  `recheck_after_size_review` records `resolved_by_subloop`, not infra
- `scripts/tests/test_autodev_decision_gate.py` — stubs `check-readiness` exit codes
  (`:955`, `:1096`, `:1117`); re-check those cases after the `harness_exit` switch
- Technique: run the real state `action` under `bash -c` against a stub `ll-issues` on `PATH`
  (`test_autodev_loop.py:644-688`); persist state across calls through run-dir files

## Implementation Steps

1. `check-readiness`: absent key → exit 3 (`SCORES_ABSENT`); CLI tests; help text; CLI.md
2. autodev: `mark_scores_absent_infra` (writes `autodev-scores-absent.txt`)
3. autodev: clear state before each rerun; retarget the six predecessors (reconcile path:
   `count_repair_cycle_reconcile`)
4. autodev: one `harness_exit` presence-gate state per rerun (0 → successor, 1 → retry the
   rerun, 3 → infra); counters cleared in `dequeue_next`
5. autodev: `check-readiness` call sites → `harness_exit` with per-site `on_cannot_judge`
   (infra only at `recheck_after_decide`)
6. autodev: `is None` → exit 3 branch in `recheck_after_size_review` and
   `regate_after_atomic_remediation`, after `resolved_by_subloop`, before deferral branches
7. Docs: LOOPS_REFERENCE.md flow diagram, DEFERRAL_CODES.md infra note
8. Regression tests (stateful stubs): failed rescoring after decide/wire/spike/atomic/
   refine-for-design does not pass on pre-repair scores; failed rescoring after reconcile lands on
   infra, not `low_readiness`; a first-attempt no-write followed by a successful retry proceeds
   normally; breakdown without scores still reaches `detect_children`; done parent without
   scores records `resolved_by_subloop`

## Impact

- **Priority**: P2 — post-repair content can reach implementation on scores about earlier content.
- **Effort**: Medium
- **Risk**: Medium. A run that clears scores and then stops (rate-limit finalize, crash) leaves
  the issue unscored: `ll-auto` reports it as "never assessed", and `ll-issues next-issue` (which
  ranks by `outcome_confidence`/`confidence_score`) orders it below scored issues until it is
  rescored.
- **Accepted risk — unscorable issue repeats across runs**: `mark_scores_absent_infra` does not
  defer, so an issue that `/ll:confidence-check` can never score takes the infra path on every
  run with no bound (previously it deferred as `low_readiness`). Accepted for this fix; if it
  shows up in practice, follow up with a cross-run `[SCORES_ABSENT]` counter under
  `.loops/diagnostics/` that defers after N runs.
- **Sequencing**: independent of BUG-3571 (disjoint files). BUG-3572 retargets
  `rerun_confidence_after_spike`'s `next`, which this issue routes through a new presence gate —
  land this first. ENH-3577 is blocked by both.

## Acceptance Criteria

- [ ] A rescoring that fails after decide, wire, spike, atomic remediation or refine-for-design
      cannot pass on pre-repair scores
- [ ] A rescoring that writes nothing is retried once; a second miss lands on
      `mark_scores_absent_infra`, not `low_readiness`, `readiness_stagnated`, `oversized_atomic`
      or a reconcile rewrite
- [ ] Every `check-readiness` call site in autodev routes exit 3 explicitly; none reaches size
      review or deferral through `on_error`. Post-rescore sites route to
      `mark_scores_absent_infra`; post-sub-loop sites (`check_passed`, `recheck_scores`) keep
      their current `on_no` behaviour
- [ ] An issue broken down by the refine-to-ready sub-loop without scores still reaches
      `detect_children`; a done/cancelled parent without scores records `resolved_by_subloop`
- [ ] `ll-issues check-readiness` exits 3 when a score key is absent; 0/1/2 semantics otherwise
      unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-25T02:37:40 - `fc091aae-52aa-4a34-b6c1-775f9e4b8dff.jsonl`
