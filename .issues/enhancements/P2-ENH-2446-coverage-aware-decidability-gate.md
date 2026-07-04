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
parent: EPIC-2412
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

## Implementation Steps

1. **Add resolved/unresolved detector in `issue_parser.py`.** New sibling to
   `count_enumerable_options()` (line 269), e.g. `count_unresolved_options()`,
   that walks each option block in `## Proposed Solution` (or fallback sections
   per `_OPTION_FALLBACK_SECTIONS` at line 257) and returns the count of blocks
   lacking a `> **Selected:**` callout OR `### Decision Rationale` subsection
   within the same block (boundary = next `###` or `##` line). Use
   `_section_body()` (line 114) to extract each option's body.
2. **Add open-question section detector in `issue_parser.py`.** New function
   `count_open_questions_in_sections()` that combines `_section_body()` reads
   for `## Edge Cases`, `## Confidence Check Notes`, and `## Open Questions`,
   then applies the same `✅ RESOLVED` regex already defined in
   `skills/decide-issue/SKILL.md` Phase 3b-i (line 197) to count unresolved
   items. Mirror the `FormatGaps` dataclass shape at `issue_parser.py:135-159`
   for a typed return value.
3. **Add `cmd_check_open_questions` CLI in `scripts/little_loops/cli/issues/check_open_questions.py`.** Mirror `cmd_check_decidable`
   (`check_decidable.py:19`) and `cmd_format_check` (`format_check.py`) — exit
   0 when no open questions + no unresolved options remain, exit 1 with
   `OPEN_QUESTIONS_REMAIN: <ID> — N open question(s) and M unresolved option(s);
   run /ll:refine-issue <ID> --auto` otherwise. Register the subcommand in
   `cli/issues/__init__.py` (`check-decidable` parser at line 581-587 is the
   template; dispatch in `commands` switch at line 792-793).
4. **Wire the new probe into `check_decision_decidable` in
   `rn-remediate.yaml:263`.** After the existing marker short-circuit
   (`if [ -f "${context.run_dir}/decide_options_deposited_${context.issue_id}.txt" ]`),
   chain the new probe: `ll-issues check-open-questions "${context.issue_id}" || \
   ll-issues check-decidable "${context.issue_id}"`. Fail-open `on_error: decide`
   must be preserved (rn-remediate.yaml:283). Mirror the same change in
   `autodev.yaml:193-209` (parity test at `test_builtin_loops.py:2890-2922`).
5. **Add Layer 2 Option A progress gate.** Reuse the ENH-2428 `score_stall`
   pattern as the template: a new `open_question_stall` evaluator type that
   reads a per-round count history file (one number per line) under
   `${context.run_dir}/.open_questions_<ID>.history`. Wire it via:
   - `fsm/schema.py:61-103` — add `open_question_stall` to `EvaluateConfig.type`
     `Literal[…]` plus `history_file`/`max_stall`/`epsilon` fields.
   - `fsm/evaluators.py:602` — add `evaluate_open_question_stall()` (modeled on
     `evaluate_score_stall`).
   - `fsm/evaluators.py:1648-1777` — add to `_EXIT_CODE_AWARE_EVALUATORS` and
     dispatch in `evaluate()`.
   - `fsm/validation.py:64-79` — add to `EVALUATOR_REQUIRED_FIELDS` and a
     type-specific validation block (see `validation.py:321-336` for the
     `score_stall` precedent).
   - `loops/lib/common.yaml:162` — add `open_question_stall_gate` fragment
     modeled on `score_stall_gate`.
6. **Replace the write-once marker with a progress-gated re-fire.** The current
   `${context.run_dir}/decide_options_deposited_<ID>.txt` (written by
   `record_options_deposited` at `rn-remediate.yaml:300`) becomes the "we tried
   at least once" anchor; the *re-fire decision* moves to a new shell state
   that consults the `open_question_stall` evaluator against the count
   history. Bounded by `check_remediation_budget` (`rn-remediate.yaml:735`) so
   the existing 3-pass cap still applies, and the existing `STALLED_NEEDS_DECOMPOSE`
   superstring trick (BUG-2006) preserves the parent's substring-match.
7. **Mirror in `autodev.yaml`.** Both loops consume the new probe + evaluator
   identically (the marker name `autodev-decide-options-deposited` becomes a
   "tried at least once" anchor; the count history file is
   `${context.run_dir}/.open_questions_<ID>.history` in both loops).
8. **Extend test surface.** Mirror `TestCheckDecisionDecidableState`
   (`test_rn_remediate.py:189-231`) for the new gate ordering, add a
   `TestOpenQuestionsStall` class to `test_decide_issue_skill.py` (mirror
   `TestOptionsMissingExitCodes` at line 511-534) and a `TestFEAT2339MixedShapeSnapshot`
   golden-file fixture (mirror `TestFEAT398Snapshot` at line 475-509) under
   `scripts/tests/fixtures/issues/FEAT-2339-mixed-resolved-unresolved.md`. Add
   a `TestMR1NonLLMEvaluatorForOpenQuestionStall` case to `test_rn_remediate.py`'s
   `TestFSMHealth` (line 1128-1145) so the new evaluator is locked as a
   non-LLM gate. Mirror the same tests in `test_builtin_loops.py:2890-2922`
   for `autodev.yaml` parity.
9. **Update docs.** `docs/reference/CLI.md:1398-1412` (add `ll-issues
   check-open-questions` alongside `check-decidable`), `docs/reference/API.md:829-834`
   (add `count_unresolved_options` + `count_open_questions_in_sections` to the
   issue-parser API), `docs/guides/LOOPS_REFERENCE.md:580-609` (Phase 1.5
   Decidability Gate description), and the new evaluator's display label in
   `cli/loop/info.py:1063-1079` `_EVALUATE_TYPE_DISPLAY`.
10. **Run gates.** `python -m pytest scripts/tests/` (per project policy —
    this *is* the CI), then `ruff check scripts/`, `ruff format scripts/`,
    `python -m mypy scripts/little_loops/`. Confirm no regression in
    `test_builtin_loops.py` autodev parity tests.

## Key Files

- `scripts/little_loops/cli/issues/check_decidable.py:19` — `cmd_check_decidable`;
  count-based probe to make coverage-aware (or sibling to a new
  `check-open-questions`).
- `scripts/little_loops/issue_parser.py:269` — `count_enumerable_options()`;
  add `count_unresolved_options()` and `count_open_questions_in_sections()`
  as siblings. Reuse `_section_body()` (line 114), `_OPTION_PATTERNS` (line
  250), and `_OPTION_FALLBACK_SECTIONS` (line 257).
- `scripts/little_loops/issue_parser.py:135-159` — `FormatGaps` dataclass;
  precedent for a typed graded-gap return value.
- `scripts/little_loops/loops/rn-remediate.yaml` — states `check_decision_decidable`
  (line 263), `deposit_options` (line 285), `record_options_deposited` (line
  300), `check_convergence` (line 636), `check_remediation_budget` (line 735),
  `emit_needs_manual_review` (line 793).
- `scripts/little_loops/loops/autodev.yaml:193-231` — parallel implementation
  of the ENH-2443 gate; mirror the new probe and progress-gate here. The
  marker name is `autodev-decide-options-deposited` (parity test at
  `test_builtin_loops.py:2890-2922`).
- `scripts/little_loops/loops/rn-implement.yaml:26` — `max_remediation_passes`
  context default (Layer 2 Option B). `route_rem_manual_review_recommended`
  (line 840-852) and `route_rem_manual_review` (line 854-861) consume the
  parent's outcome token.
- `scripts/little_loops/loops/lib/common.yaml:15,61,162` — `shell_exit`,
  `with_rate_limit_handling`, and `score_stall_gate` fragments (precedent for
  the new `open_question_stall_gate`).
- `scripts/little_loops/fsm/evaluators.py:602` — `evaluate_score_stall`; the
  "strictly-decreasing counter" template. `fsm/evaluators.py:1648-1777` for
  the dispatcher + `_EXIT_CODE_AWARE_EVALUATORS`.
- `scripts/little_loops/fsm/validation.py:64-79` — `EVALUATOR_REQUIRED_FIELDS`;
  the schema registration site. See `validation.py:321-336` for the
  `score_stall` validation block to mirror.
- `scripts/little_loops/fsm/schema.py:61-103` — `EvaluateConfig` dataclass;
  add `open_question_stall` to the `Literal[…]` `type` field.
- `scripts/little_loops/cli/loop/info.py:1063-1079` — `_EVALUATE_TYPE_DISPLAY`;
  add the new evaluator's display label.
- `skills/decide-issue/SKILL.md:194-213` — Phase 3b-i `✅ RESOLVED` marker
  detection; the canonical "open vs resolved" regex to reuse in the new
  probe.
- `skills/confidence-check/SKILL.md:356-371` — signal-phrase detection that
  sets `decision_needed: true`; confirms `## Confidence Check Notes` as a
  legitimate source of unresolved questions.
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check`; the
  ENH-2426 sibling deterministic-probe pattern (`--format text|json`, exit 0/1,
  stderr token + side-effect-free).
- `scripts/tests/test_decide_issue_skill.py:475-534` — `TestFEAT398Snapshot`
  + `TestOptionsMissingExitCodes`; precedent for fixture-driven
  characterization + subprocess-level unit tests.
- `scripts/tests/test_rn_remediate.py:189-330` — `TestCheckDecisionDecidableState`,
  `TestDepositOptionsState`, `TestRecordOptionsDepositedState`,
  `TestDecisionDecidableFlow`, `TestManualReviewRecommendedToken`; the FSM
  wiring test suite to extend.
- `scripts/tests/test_builtin_loops.py:2890-2922` — autodev.yaml parity tests;
  mirror for the new probe.
- `scripts/tests/fixtures/issues/FEAT-398-decide-empty-proposed.md` — existing
  0-enumerable-options fixture; add `FEAT-2339-mixed-resolved-unresolved.md`
  alongside for the new mixed-shape golden file.

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

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Coverage gap is concrete and localized.** `count_enumerable_options`
  (`scripts/little_loops/issue_parser.py:269`) does NOT inspect the
  `> **Selected:**` callout or `### Decision Rationale` subsection that
  `skills/decide-issue/SKILL.md:357-413` writes when it resolves an option.
  Confirmed via grep: at least `P3-BUG-1870-...md:81`, `P2-BUG-1799-...md:54`,
  and `P3-BUG-1870-...md:132` carry these markers in `## Proposed Solution`
  but contribute to the count regardless. The fix is local: a new sibling
  function that filters the matched option blocks by marker presence.
- **Section-scoped detection is already centralized.** `_section_body()`
  (`scripts/little_loops/issue_parser.py:114`) is the canonical "give me the
  text of `## <heading>`" helper. A new `count_open_questions_in_sections()`
  reuses it for `## Edge Cases`, `## Confidence Check Notes`, and
  `## Open Questions`. The `✅ RESOLVED` regex family (defined inline at
  `skills/decide-issue/SKILL.md:197`) is the resolved-question signal — copy
  it to `issue_parser.py` so both the LLM skill and the deterministic probe
  read the same markers.
- **Deterministic-probe pattern is well-established.** `cmd_check_decidable`
  (`scripts/little_loops/cli/issues/check_decidable.py:19`) and
  `cmd_format_check` (`format_check.py`) are the two precedents. Both are
  stdlib-only, side-effect-free, and exit 0/1 with a stderr token for
  non-passing cases. A new `cmd_check_open_questions` should match this
  shape exactly: `_resolve_issue_id()` → file read → deterministic analysis
  → token + exit code. Register the subcommand in
  `scripts/little_loops/cli/issues/__init__.py` (the `check-decidable`
  parser at line 581-587 and dispatch in the `commands` switch at line
  792-793 are the templates).
- **Progress-gated re-fire pattern is well-established.** The `score_stall`
  evaluator + `score_stall_gate` fragment (ENH-2428) is the exact precedent
  for Layer 2 Option A. Touch points are:
  `fsm/schema.py:61-103` (EvaluateConfig.type Literal),
  `fsm/evaluators.py:602` (evaluate_score_stall body + dispatcher in
  `fsm/evaluators.py:1648-1777`), `fsm/validation.py:64-79`
  (EVALUATOR_REQUIRED_FIELDS + the score_stall-specific validation block at
  line 321-336), `loops/lib/common.yaml:162` (score_stall_gate fragment),
  `cli/loop/info.py:1063-1079` (_EVALUATE_TYPE_DISPLAY), and MR-1 prose in
  `.claude/CLAUDE.md`. ENH-2428 itself is the canonical "make count-aware
  into coverage-aware" issue and its integration map is the template.
- **Existing routing tokens already accommodate a third MANUAL_REVIEW_*
  variant.** `STALLED_NEEDS_DECOMPOSE` is a deliberate superstring of
  `NEEDS_DECOMPOSE` to keep substring-match compatibility in
  `route_rem_decompose` (BUG-2006). The same trick lets us add e.g.
  `MANUAL_REVIEW_RECOMMENDED_AFTER_DEPOSITS_EXHAUSTED` without changing the
  parent's `route_rem_manual_review_recommended` arm
  (`rn-implement.yaml:840-852`) — but a cleaner name is to *keep*
  `MANUAL_REVIEW_RECOMMENDED` and add the progress-gate behavior, since
  the operator-facing diagnostic stays the same.
- **`autodev.yaml` is a parity copy of the ENH-2443 gate.** The new probe and
  progress gate must be mirrored in `autodev.yaml:193-231`. Its marker name
  is `autodev-decide-options-deposited` (parity test at
  `test_builtin_loops.py:2890-2922`). The count history file convention
  should remain loop-agnostic (`${context.run_dir}/.open_questions_<ID>.history`)
  so both loops share the same evaluator.
- **`## Edge Cases` is marked `deprecated: true` in the FEAT template**
  (`scripts/little_loops/templates/feat-sections.json:177-185`). The
  coverage-aware probe should mirror `is_formatted()`'s deprecated-section
  guard at `issue_parser.py:218-221` and skip deprecated sections when
  scanning for open questions — otherwise the probe will over-fire on
  issues that have a `## Edge Cases` section purely for legacy reasons.
- **Confidence-check sets `decision_needed: true` via 10 signal phrases**
  (`skills/confidence-check/SKILL.md:356-371`): `"open decision"`, `"unresolved
  decision"`, `"decision point"`, `"either/or"`, `"open question"`, `"Option
  A/B" without resolution`, etc. These phrases can appear inside `## Edge
  Cases` and `## Confidence Check Notes` bodies — the coverage-aware probe
  will catch them via section-scoped regex, and the parent
  decision-routing already trusts the resulting `decision_needed: true`
  flag (no further changes needed in confidence-check).
- **MR-1 must continue to hold.** The new `open_question_stall` evaluator
  is a non-LLM gate (it reads a number from a file), so the new shell
  states wiring it into `rn-remediate.yaml` / `autodev.yaml` remain
  MR-1-compliant. Add a `TestMR1NonLLMEvaluatorForOpenQuestionStall` case
  to `test_rn_remediate.py`'s `TestFSMHealth` (line 1128-1145) to lock this.
- **Per-run artifact isolation (MR-3) is preserved.** Both the existing
  `${context.run_dir}/decide_options_deposited_<ID>.txt` marker and the
  new `${context.run_dir}/.open_questions_<ID>.history` file live under
  `${context.run_dir}/` (not bare `.loops/tmp/`), satisfying MR-3. The
  test `test_marker_bounded_second_pass_short_circuits` at
  `test_rn_remediate.py:225` locks the marker ordering.
- **Single-pass / single-issue budget (BUG-2006 superstring trick).** The
  parent `rn-implement.yaml` reads `subloop_outcome_<ID>.txt` via
  longest-prefix-first `output_contains` routing
  (`route_rem_manual_review_recommended` at line 840-852 is checked
  before `route_rem_manual_review` at line 854-861 per ARCH-090). Any new
  outcome token should be designed as a *superstring* of an existing one
  if it must keep triggering the same parent arm.

## Status

**Open** | Created: 2026-07-02 | Priority: P2 | Refined: 2026-07-02 by `/ll:refine-issue --auto`


## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - Parented to EPIC-2412 (was unparented; assigned per /ll:create-epics-from-unparented sweep).
- `/ll:refine-issue` - 2026-07-03T00:46:39 - `230f87c5-0430-4e63-818f-efd86398fff5.jsonl`
