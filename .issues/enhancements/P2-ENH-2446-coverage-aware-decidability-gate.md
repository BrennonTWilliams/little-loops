---
id: ENH-2446
type: enhancement
status: open
priority: P2
title: Make decidability gate coverage-aware, not count-aware, and re-provision the refine/decide budget for high-open-question issues
labels:
- loops
- rn-remediate
- decision-handling
- ll-issues
captured_at: 2026-07-02 00:00:00+00:00
discovered_date: 2026-07-02
discovered_by: capture-issue
decision_needed: true
---

# P2-ENH-2446: Make decidability gate coverage-aware, not count-aware, and re-provision the refine/decide budget for high-open-question issues

## Summary

`rn-remediate`'s decision-handling path decides whether an issue's decisions are
resolved by *counting* enumerable options in `## Proposed Solution`. This misfires
on the common mixed-issue shape: an issue that has some already-decided Option A/B
blocks **plus** free-form open questions living in Edge Cases / Confidence Check
output. Because ≥1 option already exists, the decidability gate reports the issue
"decidable," routes straight to `decide` (an idempotent no-op on already-decided
options), flips `decision_needed: false`, and the free-form questions are never
converted into decidable options. The one state whose job is to deposit those
options (`deposit_options`) is skipped, and it is single-shot even when reached.

Observed on FEAT-2339 (5 open design questions coexisting with 2 already-decided
options): the manual workflow required repeated `/ll:refine-issue` → `/ll:decide-issue`
rounds, which the automated loop cannot reproduce.

## Current Behavior

Decision handling in `scripts/little_loops/loops/rn-remediate.yaml`:

1. `check_decision_needed` reads the `decision_needed` frontmatter flag.
2. `check_decision_decidable` runs `ll-issues check-decidable`
   (`scripts/little_loops/cli/issues/check_decidable.py`), which calls
   `count_enumerable_options()` (`scripts/little_loops/issue_parser.py:269`).
   It exits 0 (decidable) when the count of enumerable options in
   `## Proposed Solution` (falling back to Codebase Research / Implementation
   Status) is **≥ 1**.
3. Decidable → `decide` (`/ll:decide-issue --auto`). Not decidable →
   `deposit_options` (`/ll:refine-issue --auto`, once, marker-bounded by
   `decide_options_deposited_<ID>.txt` via `record_options_deposited`).
4. `decide` → `re_assess` → `check_convergence` → (budget-gated) `diagnose` →
   `refine`. `max_remediation_passes` defaults to **3** (`rn-implement.yaml:26`,
   threaded into `rn-remediate`).

Two structural gaps result:

- **Count, not coverage.** `count_enumerable_options` cannot distinguish
  "2 options, both already resolved" from "2 live options to decide." An issue
  with resolved options *plus* unmodeled free-form questions passes the gate and
  bypasses `deposit_options` entirely. The free-form questions only get
  re-addressed if `confidence-check` happens to score them low enough to keep the
  convergence loop running through generic `refine` — and if it does not, the
  loop can emit `CONVERGED_PASS` and implement with open questions unresolved.
- **Single-shot deposit + fixed budget.** `deposit_options` runs at most once per
  issue, and `max_remediation_passes: 3` cannot clear an issue whose N free-form
  questions each need their own refine→decide round (N=5 on FEAT-2339). Realistic
  terminal outcome: budget exhausts → `emit_stalled_needs_decompose` →
  `run_decomposition` → `NO_CHILDREN` → `mark_deferred` with a generic
  "remediation stalled" reason rather than "N open questions need options."

## Expected Behavior

- The decidability probe should detect **unresolved** open questions (in Edge
  Cases, Confidence Check output, and/or undecided option blocks), not merely
  count option blocks. An issue with resolved options plus open free-form
  questions should route to option-deposition, not straight to `decide`.
- `deposit_options` / the refine→decide cycle should be able to make progress
  across multiple open questions rather than being capped at one deposit pass and
  three total remediation passes for issues that are demonstrably still improving.

## Motivation

- Prevents the mixed-issue blind spot from either (a) deferring an actionable
  issue with an unhelpful generic reason, or (b) implementing prematurely with
  open design questions unresolved (`CONVERGED_PASS` false-positive).
- Aligns the automated loop with the manual `/ll:refine-issue` → `/ll:decide-issue`
  workflow operators already run for these issues.
- Builds directly on ENH-2443, which introduced `check-decidable` /
  `deposit_options` / the `MANUAL_REVIEW_RECOMMENDED` split — this closes the case
  ENH-2443's count-based probe does not cover.

## Proposed Solution

Two independent layers.

### Layer 1 — Coverage-aware decidability probe

Replace (or supplement) the count-based `check-decidable` with an
open-question–aware probe. Options for the detection signal:

- Parse `## Edge Cases` and the `## Confidence Check`/`Confidence Check Notes`
  output for unresolved-question markers (open checkboxes, "open question",
  "TBD", "needs decision") in addition to counting undecided option blocks in
  `## Proposed Solution` (an option block **without** a `> **Selected:**` /
  `### Decision Rationale` callout is "undecided"; one with it is "resolved").
- Add a new `ll-issues check-open-questions <ID>` probe (deterministic, non-LLM,
  mirroring `check-decidable`/`format-check`) that exits non-zero when unresolved
  questions remain, and route `deposit_options` on that signal so the state fires
  for the mixed case.

Net effect: `check_decision_decidable` should send the mixed issue to
`deposit_options` (to convert free-form questions into enumerable options) rather
than to `decide`.

### Layer 2 — Budget / re-fire for high-open-question issues

The user's explicit fork — pick one:

- **Option A — progress-gated `deposit_options` re-fire**: allow `deposit_options`
  to run again while it is still making measurable progress (e.g., open-question
  count strictly decreasing, or new resolved options appearing), replacing the
  single write-once `decide_options_deposited_<ID>.txt` marker with a
  progress/stall check. Bound by a stall detector so it terminates.
- **Option B — scale the remediation budget by open-question count**: raise
  `max_remediation_passes` (or add a derived per-issue budget) as a function of
  the number of detected open questions, so an N-question issue gets enough
  refine→decide rounds instead of a fixed 3.

Recommended: **Option A** — a progress gate is self-bounding and does not require
per-issue budget tuning, and it keeps the existing convergence/stall machinery as
the terminator. Option B is simpler but risks either under-provisioning (fixed
multiple too low) or burning budget on genuinely stuck issues.

## Acceptance Criteria

- [ ] A mixed issue (≥1 resolved option + ≥1 unresolved free-form question)
      routes to option-deposition, not straight to `decide`.
- [ ] The decidability probe distinguishes resolved vs. unresolved option blocks
      (`> **Selected:**` / `### Decision Rationale` present = resolved).
- [ ] Open questions in `## Edge Cases` and Confidence Check output are detected
      as unresolved decision surface.
- [ ] Layer 2 (whichever option is chosen) lets an N-open-question issue clear
      more than one question per run without unbounded looping (stall/progress
      terminator present).
- [ ] An issue that genuinely cannot deposit options still terminates as
      `MANUAL_REVIEW_RECOMMENDED`/`MANUAL_REVIEW_NEEDED` (ENH-2443 behavior
      preserved), not an infinite loop.
- [ ] `python -m pytest scripts/tests/` exits 0, including new cases in
      `scripts/tests/test_decide_issue_skill.py` / `test_rn_remediate.py`.

## Scope Boundaries

- **In scope**: coverage-aware decidability detection; `deposit_options`
  re-fire *or* budget re-provisioning; the routing edges in `rn-remediate.yaml`
  that consume the new signal; tests.
- **Out of scope**: changing `/ll:decide-issue`'s idempotency contract; changing
  how `/ll:refine-issue` deposits options; the FIFO/value-ranked scheduling in
  `rn-implement`.

## Key Files

- `scripts/little_loops/cli/issues/check_decidable.py` — count-based probe to make
  coverage-aware (or sibling to a new `check-open-questions`).
- `scripts/little_loops/issue_parser.py:269` — `count_enumerable_options()`;
  needs a resolved-vs-unresolved companion.
- `scripts/little_loops/loops/rn-remediate.yaml` — states
  `check_decision_decidable`, `deposit_options`, `record_options_deposited`,
  `check_convergence`, `check_remediation_budget`, `emit_needs_manual_review`.
- `scripts/little_loops/loops/rn-implement.yaml:26` — `max_remediation_passes`
  context default (Layer 2 Option B); `route_rem_manual_review_recommended`.
- `scripts/tests/test_decide_issue_skill.py`, `scripts/tests/test_rn_remediate.py`
  — existing test harnesses to extend.

## Related

- ENH-2443 — introduced `check-decidable` / `deposit_options` /
  `MANUAL_REVIEW_RECOMMENDED`; this issue extends its count-based probe to be
  coverage-aware. Prior art for the deterministic-probe pattern.

## Impact

- **Priority**: P2 — decision-handling correctness gap that can cause premature
  implementation (open questions unresolved) or unhelpful deferrals.
- **Effort**: Medium — new/extended deterministic probe + one routing change +
  a progress/budget mechanism + tests.
- **Risk**: Medium — touches the ENH-2443 decision path; must preserve the
  manual-review terminators and remain self-bounding.

## Status

**Open** | Created: 2026-07-02 | Priority: P2
