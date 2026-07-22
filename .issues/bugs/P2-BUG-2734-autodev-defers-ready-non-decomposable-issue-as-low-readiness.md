---
id: BUG-2734
title: autodev defers a ready, deliberately-non-decomposable Very Large issue as low_readiness
  instead of implementing it
type: BUG
status: done
priority: P2
captured_at: '2026-07-21T00:00:00Z'
completed_at: '2026-07-22T03:30:26Z'
discovered_date: '2026-07-21'
discovered_by: human
labels:
- automation
- loops
- fsm
relates_to:
- BUG-2731
- BUG-1230
- ENH-2666
- ENH-2664
confidence_score: 98
outcome_confidence: 62
score_complexity: 13
score_test_coverage: 22
score_ambiguity: 17
score_change_surface: 10
decision_needed: false
---

# BUG-2734: autodev defers a ready, deliberately-non-decomposable Very Large issue as low_readiness

## Summary

When `/ll:issue-size-review --auto` classifies an issue **Very Large** but
**deliberately declines to decompose it** — because the candidate sub-tasks are
strictly sequential / share infrastructure / aren't independently shippable (and,
under `tdd_mode: true`, because splitting wiring from implementation is
forbidden) — the size-review's own recommendation is *"keep as one issue, it's
ready, proceed to implement."* autodev's graph cannot hear that recommendation.
`run_size_review` produces no child files, so `enqueue_or_skip` treats the
outcome as "no decomposition happened" and routes to `recheck_after_size_review`,
which re-applies the outcome-confidence gate and **defers a genuinely
implementation-ready issue as `low_readiness`** — even when its readiness score
is well above threshold.

## Current Behavior

Reproduced live on BUG-2731 (`ll-loop run autodev BUG-2731`, run
`autodev-20260721T200648`):

- `/ll:confidence-check` stamped `confidence_score: 95` (readiness, ≥ threshold)
  and `outcome_confidence: 56` (< outcome threshold 65).
- `run_size_review` (`/ll:issue-size-review BUG-2731 --auto`) scored it 11/11
  **Very Large** and emitted:
  `[BUG-2731] skipped: score 11 (ambiguous — strictly sequential/shared-infra
  children; recommend keeping as one issue)`, with the explicit next-step note
  *"proceed to implementation as a single issue (it's already at 95/100
  readiness)."* It created **zero** child issues by design.
- Because no children appeared, `enqueue_or_skip` exited 1 →
  `check_parent_resolved_post_size_review` (not resolved) →
  `recheck_after_size_review` → `check-readiness` failed on the outcome half
  (56 < 65) → `ll-issues set-status BUG-2731 deferred --by automation --reason
  low_readiness`.

Net result: an issue that size-review explicitly judged **ready to ship as-is**
was filed as "low readiness" and removed from active selection.

## Steps to Reproduce

1. Take an issue that is refined to passing readiness (`confidence_score ≥
   threshold`) but has sub-threshold `outcome_confidence`, and whose scope is a
   single atomic fix touching many call sites (not independently-shippable
   sub-tasks). BUG-2731 is a live example (readiness 95, outcome 56, Very Large).
2. Run `ll-loop run autodev <ID>`.
3. Observe the flow reach `run_size_review`, which scores the issue Very Large,
   deliberately declines to decompose (emitting `[ID] skipped: score N
   (ambiguous — ... recommend keeping as one issue)`), and creates no children.
4. Observe autodev route through `enqueue_or_skip` (no children) →
   `recheck_after_size_review` and defer the issue as `low_readiness`, despite
   size-review recommending immediate implementation.

## Expected Behavior

> **Design decision (2026-07-21 review)**: an earlier draft of this issue
> proposed routing the "keep as one issue" verdict **unconditionally to
> `implement_current`**, overriding the outcome-confidence gate whenever
> readiness passed, with a run-scoped `--context skip_keep_as_one_reroute`
> escape flag. That design was **rejected**: `issue-size-review` judges
> *decomposability* (structure), while `outcome_confidence` judges
> *autonomous-implementation risk* — "can't be split" does not imply "safe to
> auto-implement," and an unconditional reroute deletes the outcome gate for
> exactly the highest-risk class of issue (wide-surface atomic changes). The
> replacement is the two-step policy below: **earn the gate pass via correct
> Pattern-B scoring; otherwise defer honestly with a human waiver path.**

A "Very Large, deliberately not decomposed, readiness ≥ threshold" outcome from
`run_size_review` (the guard-2 marker — see Root Cause) must route through a
two-step policy instead of the `low_readiness` deferral:

**Step 1 — earn the pass (fix the score, not the gate).** Route to a
remediation step that qualifies the issue for **Criterion D Pattern B**
scoring: ensure the issue body carries an enumerated file/call-site list, a
verification grep, and an automated wiring test (the Pattern B verifiability
chain), then re-run `/ll:confidence-check` and re-evaluate the gate. A
genuinely mechanical "thread one signal through many call sites" fix should
score high on Criterion D once classified as Pattern B, pass
`outcome_confidence ≥ threshold` legitimately, and proceed to
`implement_current` with the gate intact. This requires closing the
**Criterion D scoring gap** (see Root Cause): Pattern B detection currently
only covers markdown/config/template fanouts, so uniform *code* call-site
sweeps always score under Pattern A blast radius no matter how well-enumerated
and verifiable they are.

**Step 2 — honest deferral with a human escalation valve.** If
`outcome_confidence` still fails after the Pattern-B rescoring pass, the risk
is real: **do not implement**. Defer, but with a truthful reason code —
`oversized_atomic` (readiness passed; outcome risk on a
structurally-large-but-atomic change) — never `low_readiness` when readiness
actually passed. `ll-issues deferred-triage` surfaces it under the new code.
The human escalation path is a **per-issue frontmatter waiver**:
`outcome_gate_waived: true` (stamped manually or by `/ll:go-no-go` after an
explicit risk review). On the next autodev pass, a waived issue routes to
`implement_current` bypassing the outcome half of the gate — auditable,
scoped to one issue, and recorded in the issue file itself. No run-scoped
`--context` toggle: a run-global flag would bypass the gate for every
keep-as-one issue in the run, which is the wrong granularity for a per-issue
risk judgment.

**Unchanged behavior:**

- Guard-1 qualitative skips (`skipped: structural score N but
  outcome_confidence low is qualitative ...`) continue to defer through the
  existing path — that verdict genuinely means "not ready, needs refinement."
- A genuine decomposition failure / analysis-only run (BUG-1183 shape, no
  verdict marker) continues through `recheck_after_size_review` unchanged.
- `recheck_after_size_review`'s `low_readiness` write remains correct for the
  case where readiness itself fails.

## Impact

Genuinely implementation-ready work is silently removed from active autodev
selection and parked in the deferred-triage surface under a misleading reason
code. Any Very Large but atomic (non-decomposable) issue — a common shape for
cross-cutting fixes that thread one signal through many call sites — is affected.
The user must notice the deferral, diagnose that it was a routing artifact rather
than a real readiness gap, and manually un-defer. Severity is moderate: no data
loss and a clear manual workaround exists, but it defeats the point of
autonomous processing for exactly the issues that are ready to ship.

## Root Cause

Three interlocking gaps:

1. **Routing gap** — **File**: `scripts/little_loops/loops/autodev.yaml`.
   **State**: `enqueue_or_skip` (action at ~lines 877–924) decides the parent's
   fate **purely on the presence/absence of newly-created child files** (the
   `comm -13` ID diff → `autodev-new-children.txt`). It has no visibility into
   *why* no children were created:
   - a genuine decomposition failure / analysis-only run (BUG-1183 shape), vs.
   - a deliberate, reasoned "do not decompose — this is atomic and ready" verdict.
   Both collapse to the same `exit 1` → `on_no:
   check_parent_resolved_post_size_review` → ... → `recheck_after_size_review`
   path, whose `check-readiness` gate then defers on the outcome-confidence half
   (`autodev.yaml:1054–1077`, `low_readiness`).

2. **Scoring gap** — **File**: `skills/confidence-check/SKILL.md` (Criterion D,
   lines 253–270) + `skills/confidence-check/rubric.md` (~line 460). Criterion D
   already distinguishes **Pattern A — Blast Radius** (penalizes caller count)
   from **Pattern B — Enumerated Mechanical Fanout** (scores by verifiability
   chain: enumerated file list + verification grep + wiring test). But Pattern B
   detection requires the fanout to be **">5 markdown, config, or template
   files"** — a uniform *code* call-site sweep can never qualify, so atomic
   cross-cutting code fixes are always scored under Pattern A's caller-count
   penalty regardless of how verifiable the sweep is. That is what produced
   BUG-2731's `outcome_confidence: 56` despite readiness 95. Compounding this,
   Phase 4.8 (`SKILL.md:428–446`) detects the Pattern-B shape and stamps
   `mechanical_fanout_suppressed: true` — but **nothing in the codebase consumes
   that flag** (verified by grep: the only references are the three lines in
   Phase 4.8 itself). It suppresses a risk *phrase*, never the score or the gate.

3. **Labeling gap** — the `low_readiness` reason code is written whenever the
   AND-ed `check-readiness` gate fails, even when only the outcome half failed
   and readiness was 95. `deferred_reason` has no per-half discrimination.

The size-review skill already prints a **machine-detectable verdict** for the
deliberate-keep case — the guard-2 status line `[ID] skipped: score X
(ambiguous)` with `X ≥ 8` (see research findings below). That signal is written
to the transcript and thrown away — the FSM never reads it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The quoted verdict line is a composite, not a literal template.** Grepping
  `skills/issue-size-review/SKILL.md` for `recommend keeping as one issue` and
  `skipped: score` finds only three sites, none of which alone produces the
  fused line quoted above: `SKILL.md:242` defines the general auto-mode
  status-line grammar `[ID] skipped: score N (ambiguous)`; `SKILL.md:208`
  (Phase 4 step 4) defines a *separate* advisory sentence — `Consider keeping
  as one issue — strictly sequential children with shared scope offer no
  parallelism benefit and add tracking overhead.` — presented as "a reason for
  the user to reconsider the split, but do not block the proposal"; `SKILL.md:453`
  restates the same guidance in a Common Pitfalls bullet. **Implication for the
  fix**: detection should rely on the guard-2 status line's numeric score
  (`skipped: score X (ambiguous)` with `X ≥ 8`), which is already stable and
  machine-greppable, rather than any prose about "keeping as one issue."
- **`run_size_review` uses `action_type: slash_command`, not `shell`** —
  confirmed at `autodev.yaml:855–866`.
- **The `capture:` field works identically for `action_type: slash_command`
  and `action_type: prompt`.** Confirmed precedent: `harness-multi-item.yaml:66`
  (`capture: execute_result`) and `general-task.yaml:236`
  (`action_type: prompt`, `capture: work_result`) both capture non-`shell`
  action stdout the same way `implement_current` captures `shell` stdout.
  `scripts/little_loops/fsm/executor.py`'s `_action_mode()` dispatches
  `prompt`/`slash_command` through the same `ActionRunner.run(...,
  is_slash_command=True)` path, so `run_size_review` can add a plain
  `capture: size_review_output` (no file-tee workaround needed) and read it
  downstream via `${captured.size_review_output.output}`.
- **The closest existing grep-and-branch template** is the fragment
  `ll_auto_learning_gate_check` (`scripts/little_loops/loops/lib/common.yaml:327–351`):
  `grep -qF '&lt;marker&gt;' "${context.run_dir}/ll_auto_last.txt"` → echo
  `GATE_BLOCKED`/`OK` → `evaluate: {type: output_contains, pattern: "GATE_BLOCKED"}`.
  A new state detecting the size-review verdict should follow this shape.
- **`ll-issues check-readiness` has no readiness-only mode** — confirmed via
  `scripts/little_loops/cli/issues/check_readiness.py:14–53` and the
  `check-readiness` subparser (`scripts/little_loops/cli/issues/__init__.py:662–683`):
  both `--readiness` and `--outcome` are always hard-ANDed
  (`return 0 if (confidence >= readiness and outcome_val >= outcome) else 1`),
  there is no flag to evaluate only one threshold. To gate on readiness alone
  (or to honor `outcome_gate_waived`), a state must either call
  `check-readiness` with `--outcome 0` as an override, or read frontmatter
  directly from `ll-issues show --json` inline (mirroring the pattern already
  used by `check_spike_needed`, `autodev.yaml:787–814`).
- **`deferred_reason` has no enum/schema validation** — confirmed via
  `scripts/little_loops/cli/issues/set_status.py:38–63` (`_status_updates()`):
  `--reason` is written verbatim to frontmatter with no allowlist check. The
  vocabulary is only a soft display-ordering dict, `_REASON_RANK` in
  `scripts/little_loops/cli/issues/deferred_triage.py:12–22`
  (`{"remediation_stalled": 0, "blocked_by_unmet": 1, "gate_blocked": 2,
  "decision_unresolved": 3, "low_readiness": 4}`, unknown codes fall to
  `_DEFAULT_REASON_RANK = 5`, sorting last). **Implication**: adding
  `oversized_atomic` requires no schema migration — just the shell string
  literal at the new call site, an entry in `_REASON_RANK`, and a regression
  test asserting the literal (see Acceptance Criteria test guidance below).

### Codebase Research Findings (refine pass 2)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`skills/issue-size-review/SKILL.md`'s Auto Mode Behavior (Phase 5, lines
  232–248) defines TWO distinct skip guards with different implications:**
  1. **Qualitative-skip guard** (line 236–238): fires only when
     `score_ambiguity ≥ 18` **and** `score_complexity ≥ 18`. Emits
     `[ID] skipped: structural score N but outcome_confidence low is
     qualitative (ambiguity: A, complexity: C) — suggest /ll:refine-issue or
     /ll:wire-issue`. This case is a genuine "not ready, needs more refinement"
     verdict — it must **not** enter the new two-step policy; the existing
     deferral path is correct here.
  2. **Normal auto-mode ambiguous-decomposition skip** (line 242): fires for
     Large (5–7) issues generically, and for Very Large (8+) issues where the
     candidate split isn't unambiguous (the strictly-sequential/shared-infra
     shape this bug targets). Emits `[ID] decomposed: N child issues` or
     `[ID] skipped: score X (ambiguous)` — **this** is the marker the fix must
     detect, and it already embeds the numeric score `X`, so `X ≥ 8` is
     sufficient to distinguish "Very Large, declined" from a Large-issue skip
     without needing to parse any additional prose.
  - **Verified against the live repro**: BUG-2731's frontmatter scores
    `score_ambiguity: 18`, `score_complexity: 10` — complexity is below the
    qualitative-skip guard's 18 threshold, so guard 1 did **not** fire for the
    reproduction case; BUG-2731 went through path 2. The fix's detection logic
    must not accidentally also route guard-1 outcomes into the two-step policy.

## Integration Map

### Files to Modify

- `skills/confidence-check/SKILL.md` + `skills/confidence-check/rubric.md` —
  **close the Criterion D scoring gap (Step 1's prerequisite)**:
  - Extend Pattern B detection (`SKILL.md:253–270`) to cover **uniform code
    call-site sweeps** — same uniform-substitution requirement, but allow the
    enumerated ">5 files" list to be source files when each site receives the
    identical mechanical change AND the issue carries the full verifiability
    chain (enumerated list + verification grep + automated wiring test). Keep
    Pattern A for call sites that may each behave differently.
  - Update the Pattern B scoring table in `rubric.md` (~line 460) if the
    code-sweep variant needs its own row(s).
  - **Decision (2026-07-22)**: retire `mechanical_fanout_suppressed` (Phase
    4.8, `SKILL.md:428–446`). Fold Phase 4.8's detection logic into the
    extended Pattern B classification (Phase 2, Criterion D) instead of
    keeping it as a separate post-hoc pass. Rationale: Phase 4.8 runs *after*
    Phase 3 has already summed the score — it only edits frontmatter and
    suppresses a risk phrase in the write-up, it never corrects the
    Criterion D number itself. Once Phase 2's Pattern B detection is extended
    to recognize uniform code call-site sweeps (this issue's Step 1
    requirement), the score comes out right on the first pass and Phase
    4.8's job — patching a risk phrase after a wrong Pattern-A score —
    becomes redundant. Wiring the flag into scoring instead would keep two
    independent classification passes (Phase 2 and Phase 4.8) that could
    disagree; retiring removes that duplication and satisfies AC #1's "no
    write-only flag remains" directly. Before implementing, grep for any
    issue already stamped `mechanical_fanout_suppressed: true` (e.g.
    BUG-2731) and confirm none remain as dangling references after removal.
- `scripts/little_loops/loops/autodev.yaml`
  - `run_size_review` (~lines 855–866): add `capture: size_review_output`
    (confirmed viable for `action_type: slash_command` — see research
    findings; no file-tee workaround needed) so a downstream state can branch
    on `${captured.size_review_output.output}`. Detection must match the
    guard-2 marker specifically (`skipped: score X (ambiguous)` with `X ≥ 8`),
    not guard-1's qualitative-skip marker.
  - `enqueue_or_skip` (~lines 868–927) / new branch state modeled on
    `check_parent_resolved_post_size_review`: on the no-children branch with
    the guard-2 verdict present AND readiness ≥ threshold (readiness half
    only — via `check-readiness ... --outcome 0` or inline `ll-issues show
    --json`), route to the **Step 1 remediation state** (Pattern-B
    qualification + `/ll:confidence-check` re-run), NOT directly to
    `implement_current`.
  - New **rescore-and-regate state(s)**: after remediation, re-run the full
    AND-ed `check-readiness` gate. Pass → `implement_current`. Fail →
    `ll-issues set-status <ID> deferred --by automation --reason
    oversized_atomic`.
  - **Waiver check**: before the outcome gate (both in the new path and in
    `recheck_after_size_review`), read `outcome_gate_waived` from `ll-issues
    show --json` (mirror `check_spike_needed`, `autodev.yaml:787–814`); when
    `true`, bypass the outcome half and route to `implement_current`.
    Guard against re-remediation loops: if the issue already carries a
    prior `oversized_atomic` deferral or a completed rescoring pass, do not
    re-enter Step 1 — defer directly (one remediation attempt per run).
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum (~lines
  58–71): add `OVERSIZED_ATOMIC = "oversized_atomic"` alongside
  `LOW_READINESS`/`GATE_BLOCKED`/`DECISION_UNRESOLVED`.
- `scripts/little_loops/cli/issues/deferred_triage.py` — `_REASON_RANK`
  (~lines 12–22): add `oversized_atomic` (suggested rank: between
  `decision_unresolved` and `low_readiness` — it is an explicit
  needs-human-decision signal, more actionable than generic low readiness).
- `skills/go-no-go/SKILL.md` (optional, follow-on acceptable): document
  stamping `outcome_gate_waived: true` as the GO-with-accepted-risk output for
  an `oversized_atomic`-deferred issue.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum; add the
  `OVERSIZED_ATOMIC` member or writers relying on this enum won't recognize
  the new value.
- `scripts/tests/test_autodev_decision_gate.py` (`TestDecidePathSpikeGate` at
  line 424, `TestReconcilePlateauStructural` at line 482) — a **third** test file
  (beyond `test_builtin_loops.py`) that pins the exact `enqueue_or_skip` →
  `check_parent_resolved_post_size_review` → `check_spike_needed_before_skip`
  → `check_reconcile_needed` → `recheck_after_size_review` routing chain via
  hand-built FSM fixtures. Any new branch state spliced into this chain
  needs a parallel update here or these tests break.
- `scripts/tests/test_set_status_cli.py` —
  `test_set_status_deferred_stamps_autodev_reason_codes` (~line 304),
  parametrized over `["low_readiness", "gate_blocked", "decision_unresolved"]`
  — a closed-enumeration test; add an `oversized_atomic` case.
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLIDeferredTriage`
  (~line 6117), specifically `test_remediation_stalled_ranked_above_blocked_by_unmet`
  (~6148) — the rank-ordering test pattern to mirror (new fixture issue file
  stamped with `deferred_reason: oversized_atomic` + an ordering assertion
  against its rank-neighbors) for the new `_REASON_RANK` entry.

### Dependent Behavior / Precedent

- `recheck_after_size_review` (`autodev.yaml:1044–1081`) is the current terminal
  gate; its `low_readiness` write is what this bug reroutes around for the
  ready-but-atomic case. Do **not** change its behavior for the genuinely
  low-readiness case (readiness half actually failing).
- `check_parent_resolved_post_size_review` (`autodev.yaml:929–948`) is the
  closest structural template for a new "inspect size-review outcome and branch"
  shell-exit state.
- `check_spike_needed` (`autodev.yaml:787–814`) is the template for reading a
  boolean frontmatter flag (`outcome_gate_waived`) via `ll-issues show --json`.
  Note: `ll-issues show --json` status is display-cased — lowercase before
  matching (see project memory).
- BUG-1230 (`autodev skips implementation when size-review declines
  decomposition`) is the sibling bug this overlaps with — that fix added the
  `recheck_after_size_review` score-recheck so leaf issues aren't dropped; this
  bug is the mirror case where the score-recheck's *outcome half* is the wrong
  gate because the issue is ready but oversized-and-atomic. Reconcile with its
  intent.
- ENH-2666 (unified not-ready deferral policy) and ENH-2664 (deferral reason
  discriminator) define the `deferred_by`/`deferred_reason` contract that
  `oversized_atomic` extends.

### Test Anchors

_Added by `/ll:refine-issue` (`scripts/tests/test_builtin_loops.py`, class
`TestAutodevLoop`, starts line 3498):_

- `test_required_states_exist` (~3514–3550) — add any new state name to this
  membership set.
- `test_enqueue_or_skip_on_no_routes_to_recheck_after_size_review`
  (~4052–4082) — existing precedent for asserting the multi-hop `on_no` chain;
  new branch states inserted into this chain need equivalent routing
  assertions.
- `test_mark_gate_blocked_defers_via_set_status` (~3799),
  `test_record_decision_unresolved_defers_via_set_status` (~3807),
  `test_recheck_after_size_review_defers_low_readiness_via_set_status`
  (~3815) — the three existing per-reason-code assertion tests (each greps
  the state's `action` string for `--reason <code>`); `oversized_atomic`
  needs a parallel test in this style.
- `test_run_size_review_uses_auto_flag` (~5122–5127) — **CORRECTION (wiring
  pass): this test is in `TestRecursiveRefineLoop`, not `TestAutodevLoop`,
  and asserts `recursive-refine.yaml`'s `run_size_review` state, not
  `autodev.yaml`'s.** `TestAutodevLoop` has **no existing test** asserting
  autodev's own `run_size_review.action` content — a new test covering the
  `capture:` change must be added fresh in `TestAutodevLoop`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — Issue File Format section, "Deferral discriminator
  (ENH-2664)" / "Unified not-ready policy (ENH-2666)" bullets: enumerate
  autodev's not-ready exits and reason codes; add `oversized_atomic` and the
  `outcome_gate_waived` escalation contract.
- `docs/reference/CLI.md`:
  - Line 1176 — closure-context bullet listing the closed `deferred_reason`
    enum (`blocked_by_unmet`, `remediation_stalled`, `low_readiness`,
    `gate_blocked`, `decision_unresolved`).
  - Line 1660 — `--reason <...>` flag description, same literal closed enum.
  - Lines 1721–1722 — `deferred-triage` section's explicit rank-order
    sentence, which mirrors `_REASON_RANK`'s dict order verbatim.
- `docs/reference/API.md` (~lines 3742–3750) — `cmd_deferred_triage`
  docstring-style prose restates "autodev's not-ready exits" and the same
  rank order; update alongside the new reason code.
- `skills/audit-loop-run/SKILL.md` (~line 290, Step 6a) — `skipped_breakdown`
  example JSON and interpretive guidance sentence frame a run dominated by
  `low_readiness` as unambiguously "a genuine quality signal worth flagging."
  With ready-but-atomic issues rerouted to `oversized_atomic`, add the new
  code to the breakdown example and a caveat distinguishing the two.
- `skills/confidence-check/SKILL.md` — Criterion D / Pattern B / Phase 4.8
  changes are implementation surface (listed above), but the skill's own
  documentation of Pattern B scope must be updated in the same edit.

_Wiring pass #2 added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~line 1034, "Outcome failure triage"
  narrative, BUG-1277/ENH-1291/ENH-1415/BUG-2654/ENH-2689) — narrates the
  exact `enqueue_or_skip` → `check_spike_needed_before_skip` →
  `recheck_after_size_review` → `low_readiness` chain this bug reroutes,
  explicitly stating "a `spike_needed: true` issue was skipped as
  `low_readiness`". Update alongside the fix so this guide doesn't describe
  stale routing once the guard-2 branch and `oversized_atomic` are added.

### Test Anchors (wiring pass #2)

_Added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py`, `TestCriterionDDualPattern`
  (~265–285, uses a `_criterion_d_text()` slicing helper) — the existing
  Pattern B assertions only check that the ">5 markdown/config/template
  files" heading language is present; they assert nothing about a code
  call-site sweep. Extending Pattern B detection (Step 1's prerequisite) has
  **zero existing coverage** — add new test method(s) in this class (or a
  sibling class) following the same `_criterion_d_text()` convention.
- `scripts/tests/test_issue_size_review_skill.py` — the guard-2 verdict
  marker (`skipped: score X (ambiguous)`, `X ≥ 8`) that the new `autodev.yaml`
  branch state must detect has **no existing test coverage**, unlike guard-1's
  qualitative-skip marker (`TestIssueSizeReviewQualitativeGuard`, ~70–132,
  which asserts `"outcome_confidence low is qualitative"` via a `_phase5_text()`
  slicing helper). Add a sibling test class asserting the guard-2 line's exact
  grammar and `X ≥ 8` threshold literal.
- `scripts/tests/test_autodev_decision_gate.py::test_reconcile_gate_routing`
  (~520–525) — pins `check_reconcile_needed.on_no ==
  "recheck_after_size_review"` **unconditionally**. This is the precise
  terminal edge immediately before `recheck_after_size_review` in the chain
  this bug modifies. If the new guard-2 detection/remediation branch is
  spliced in at this edge (rather than earlier, at `enqueue_or_skip` itself
  per the issue's stated plan), this exact assertion must be updated, not
  just extended.

## Acceptance Criteria

- [ ] **Criterion D scoring gap closed**: a uniform code call-site sweep with
      the full verifiability chain (enumerated list + verification grep +
      automated wiring test) qualifies for Pattern B scoring in
      `/ll:confidence-check`; the orphaned `mechanical_fanout_suppressed` flag
      is either consumed by Criterion D scoring or retired (no write-only
      flag remains).
- [ ] When `run_size_review` emits the guard-2 verdict (`skipped: score X
      (ambiguous)`, `X ≥ 8`, zero children) AND readiness ≥ threshold, autodev
      routes to a Pattern-B qualification + confidence-check re-run
      (remediation) step — NOT directly to `implement_current`, and NOT to a
      `low_readiness` deferral.
- [ ] After remediation, a passing re-run of the full readiness+outcome gate
      routes to `implement_current`; a still-failing outcome defers via
      `set-status <ID> deferred --by automation --reason oversized_atomic`.
      Only one remediation attempt per run (no rescore loop).
- [ ] An issue with `outcome_gate_waived: true` in frontmatter bypasses the
      outcome half of the gate and routes to `implement_current` (readiness
      half still enforced). No run-scoped `--context` gate-bypass flag is
      introduced.
- [ ] Guard-1 qualitative skips (`skipped: structural score N ... qualitative`)
      and genuine no-verdict decomposition failures are unaffected — they
      continue through the existing `recheck_after_size_review` path, and
      `low_readiness` is only ever written when the readiness half actually
      fails.
- [ ] `DeferReason` gains `OVERSIZED_ATOMIC`; `_REASON_RANK` gains
      `oversized_atomic`; `.claude/CLAUDE.md` / `docs/reference/CLI.md` /
      `docs/reference/API.md` / `skills/audit-loop-run/SKILL.md` prose stays
      accurate (reason-code enums, rank order, not-ready-exit framing).
- [ ] Regression coverage in `scripts/tests/test_builtin_loops.py`
      (`TestAutodevLoop`) AND `scripts/tests/test_autodev_decision_gate.py`
      (routing-chain fixtures): (a) guard-2 verdict + passing readiness routes
      to the remediation step; (b) remediated-and-passing routes to
      `implement_current`; (c) remediated-and-still-failing defers with
      `--reason oversized_atomic`; (d) `outcome_gate_waived: true` routes to
      `implement_current`; (e) guard-1 verdict keeps the pre-fix path. Plus
      the per-reason-code `set-status` grep test, the
      `test_set_status_cli.py` parametrize case, and the
      `deferred-triage` rank-ordering test for `oversized_atomic`.

## Notes

- Discovered while investigating why BUG-2731 (readiness 95, outcome 56, Very
  Large, atomic) was auto-deferred. BUG-2731 has been manually un-deferred
  (status → open) as the immediate remediation; this issue fixes the underlying
  routing gap so it doesn't recur for the next ready-but-atomic issue.
- 2026-07-21: issue rewritten after design review. The original
  "unconditional reroute to `implement_current` + `--context` escape flag"
  design was replaced with the two-step earn-the-pass / honest-deferral policy
  (see Expected Behavior). Prior `confidence_score`/`outcome_confidence`/
  `score_*` stamps were dropped from frontmatter as stale — the directive
  sections they scored no longer exist; re-run `/ll:confidence-check` after
  this rewrite.
- Sequential decomposition (`blocked_by` chains) was considered and rejected as
  an alternative: `issue-size-review`'s objection is "not independently
  shippable," not "not parallelizable," and under `tdd_mode` splitting wiring
  from implementation is forbidden — forcing a chain adds tracking overhead
  without de-risking the change.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad multi-layer touch surface: FSM routing (`autodev.yaml`), skill scoring
  rubric (`confidence-check` SKILL.md/rubric.md), a Python enum
  (`issue_lifecycle.py`), and CLI ranking (`deferred_triage.py`) — four
  distinct layers, each needing parallel updates across three separate test
  files (`test_builtin_loops.py`, `test_autodev_decision_gate.py`,
  `test_set_status_cli.py`, `test_issues_cli.py`).
- One open decision point remains and should be resolved before implementing:
  whether to wire `mechanical_fanout_suppressed` into Criterion D scoring or
  retire the flag ("decide during implementation" per Files to Modify) — left
  open, it risks mid-implementation rework.

_Re-checked by `/ll:confidence-check` on 2026-07-21 (post wiring-pass #2, after
`/ll:decide-issue`, `/ll:refine-issue`, `/ll:wire-issue` rounds)_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

All Root Cause claims (state names/line numbers in `autodev.yaml`,
`issue_lifecycle.py`'s `DeferReason` enum, `deferred_triage.py`'s
`_REASON_RANK`, the guard-2 verdict text in `issue-size-review/SKILL.md`, and
the write-only status of `mechanical_fanout_suppressed`) were re-verified
directly against the current codebase and confirmed accurate. Readiness rose
to 98 (from 96) on the strength of that verification and the wiring pass #2
test-anchor additions (`test_confidence_check_skill.py`,
`test_issue_size_review_skill.py`, `test_autodev_decision_gate.py::test_reconcile_gate_routing`),
docked 2 points on Criterion 4 for the still-unresolved
`mechanical_fanout_suppressed` design question below.

### Outcome Risk Factors
- Wide, still-broad touch surface persists (fanout across FSM routing, a
  scoring skill + rubric, a Python enum, and CLI ranking logic, verified
  against six distinct test files this pass) — Criterion A/D remain the
  dominant drag on outcome confidence: broad enumeration across many sites,
  not deep per-site complexity.
- **The open decision flagged in the prior check is still unresolved.**
  `/ll:decide-issue` ran since (session log, 2026-07-22T02:38:05) but resolved
  the *earlier* design fork (unconditional reroute vs. two-step policy,
  captured in Expected Behavior's "Design decision" note) — it did not touch
  this narrower question. The Integration Map (`Files to Modify`, autodev.yaml
  bullet) still reads "decide during implementation" for whether to wire
  `mechanical_fanout_suppressed` into Criterion D scoring or retire the
  orphaned flag. This is an open decision that should be resolved before
  implementing, not deferred mid-PR — it changes which files the
  confidence-check skill edit touches.

## Resolution

Implemented the two-step earn-the-pass / honest-deferral policy exactly as scoped in Expected Behavior, resolving the "Files to Modify" decision (retire `mechanical_fanout_suppressed`, not wire it in):

- **Routing gap** (`scripts/little_loops/loops/autodev.yaml`): `run_size_review` now captures its status-line output (`capture: size_review_output`). A new `check_guard2_verdict` state (spliced at `check_reconcile_needed.on_no`) detects the guard-2 "declined to decompose, Very Large (8-11)" verdict via `evaluate: {type: output_contains, source: "${captured.size_review_output.output}"}` — matched Python-side against the captured text, never interpolated into a shell action (BUG-2594). On a match, `check_readiness_for_atomic_remediation` checks Readiness alone (frontmatter read, ignoring Outcome); on pass, `remediate_oversized_atomic` (`/ll:wire-issue --auto`) → `rerun_confidence_after_atomic_remediation` (`/ll:confidence-check`) → `regate_after_atomic_remediation` re-checks the full gate once: pass routes to `decide_current`/`implement_current`, a still-failing outcome defers via `set-status ... --reason oversized_atomic`. Guard-1's qualitative-skip line and no-verdict decomposition failures are unaffected (unmatched, fall through unchanged). Both `recheck_after_size_review` and `regate_after_atomic_remediation` honor a per-issue `outcome_gate_waived: true` frontmatter flag, bypassing only the outcome half of the gate.
- **Scoring gap** (`skills/confidence-check/SKILL.md` + `rubric.md`): Criterion D's Pattern B detection now covers uniform *code* call-site sweeps (not just markdown/config/template), keyed on the same uniform-substitution + verifiability-chain requirement. Phase 4.8 (`mechanical_fanout_suppressed`) is retired — no code consumed the flag; the corrected classification now scores right on the first pass instead of patching a risk phrase after the fact.
- **Labeling gap**: `DeferReason.OVERSIZED_ATOMIC` added (`issue_lifecycle.py`); `oversized_atomic` added to `_REASON_RANK` (ranked between `decision_unresolved` and `low_readiness`) and to the `ll-issues set-status --reason` CLI choices (an argparse allowlist the issue's research had missed).
- Docs updated: `.claude/CLAUDE.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, `skills/audit-loop-run/SKILL.md`, `docs/guides/LOOPS_REFERENCE.md`, `skills/go-no-go/SKILL.md` (documents stamping `outcome_gate_waived: true` as the GO-with-accepted-risk output).
- Regression coverage added across `test_builtin_loops.py` (`TestAutodevLoop`), `test_autodev_decision_gate.py` (routing-chain fixtures, including updating two pre-existing assertions that pinned the now-spliced `check_reconcile_needed.on_no` edge), `test_set_status_cli.py`, `test_issues_cli.py` (deferred-triage rank ordering), `test_confidence_check_skill.py` (Pattern B code-sweep coverage + Phase 4.8 retirement), and `test_issue_size_review_skill.py` (guard-2 marker grammar).
- Full suite green: `python -m pytest scripts/tests/` (15765 passed, 38 skipped), `ruff check scripts/` clean, `python -m mypy scripts/little_loops/` clean, `ll-loop validate autodev` valid (one pre-existing-shape informational warning allowlisted — a runtime-safe static false positive on `check_broke_down`'s shortcut branch).

## Status

done


## Session Log
- `/ll:manage-issue bug fix BUG-2734` - 2026-07-22T03:29:23Z - `cd077f06-bc0c-4bb9-a781-105902e39439.jsonl`
- `/ll:ready-issue` - 2026-07-22T02:58:51 - `323e3e87-37e7-490a-bf43-84cc90f431c8.jsonl`
- `/ll:decide-issue` - 2026-07-22T02:55:40 - `7aff5313-cb05-4e32-9fd4-3fdbf19a7157.jsonl`
- `/ll:decide-issue` - 2026-07-22T02:50:37 - `7aff5313-cb05-4e32-9fd4-3fdbf19a7157.jsonl`
- `/ll:confidence-check` - 2026-07-22T02:50:00Z - `cc303719-64a8-40dd-b2ce-8343c3fe6fc0.jsonl`
- `/ll:wire-issue` - 2026-07-22T02:44:06 - `5a5ba3fc-13a1-4308-8cd8-6ac36d07ba89.jsonl`
- `/ll:decide-issue` - 2026-07-22T02:38:05 - `9510436f-3099-43c0-b225-13df856a2f3d.jsonl`
- `/ll:ready-issue` - 2026-07-22T02:33:04 - `19edf6bf-3d15-46f0-9e74-fddbe471da81.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00Z - `bda19863-3e61-424d-983a-4d598aebaed2.jsonl`
- `/ll:refine-issue` - 2026-07-22T02:15:56 - `07679e7a-8225-4510-97c4-1ef363caacf3.jsonl`
- `/ll:ready-issue` - 2026-07-22T02:05:53 - `377dd845-1369-4726-8b92-03aaf5c02bab.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00Z - `189fb9b8-518d-4f1e-b2a8-c2967f3530fd.jsonl`
- `/ll:wire-issue` - 2026-07-22T02:01:53 - `39381a5d-4c9d-444b-9ece-85a2723dfd97.jsonl`
- `/ll:refine-issue` - 2026-07-22T01:56:21 - `dce1dc66-b93c-47dc-8e1f-a47125b84ab6.jsonl`
