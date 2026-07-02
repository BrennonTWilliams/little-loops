---
id: ENH-2443
title: decide-issue and rn-remediate should detect decision_needed:true issues with
  no enumerable options before MANUAL_REVIEW_NEEDED
type: enhancement
status: done
priority: P2
captured_at: '2026-07-02T17:13:28Z'
completed_at: 2026-07-02 19:35:23+00:00
discovered_date: 2026-07-02
discovered_by: capture-issue
decision_needed: false
implementation_order_risk: true
labels:
- rn-remediate
- decide-issue
- rn-implement
- format-guard
relates_to:
- ENH-2426
confidence_score: 98
outcome_confidence: 74
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 17
---

## Summary

When an issue has `decision_needed: true` but its `## Proposed Solution` section contains no enumerable implementation alternatives (no `### Option A/B/C`, no `> [!compare]` blocks, no decodeable bullet alternatives), `/ll:decide-issue --auto` silently preserves `decision_needed: true` and the FSM emits `MANUAL_REVIEW_NEEDED` on the next convergence pass. Operators hitting this path receive `blocked: 1` in `summary.json` with no signal that the underlying issue is "the skill had nothing to score." Make the absence of enumerable options a first-class outcome of both the skill and the FSM so that automation recovers (deposits options via `/ll:refine-issue --auto`) and operators get a clear diagnostic when it cannot.

## Current Behavior

`/ll:decide-issue --auto` (called from `rn-remediate` → `decide` action in `scripts/little_loops/loops/rn-remediate.yaml:434-442`, or invoked directly) enters Phase 3 of `skills/decide-issue/SKILL.md`. With `AUTO_MODE = true`:

- Pattern 4 (informal bullet list): `if the ONLY options found came from Pattern 4 and AUTO_MODE = true, do NOT route them to Phase 4 scoring. Set OPTIONS = 0 so flow proceeds to Phase 3b` (`:135`).
- Phase 3b looks for a clear-winner marker in `## Codebase Research Findings`.
- No clear winner → `:228`: "leaving decision_needed unchanged."

The flag persists. `rn-remediate`'s `decide` action then routes:
- `on_yes` → `re_assess` → `/ll:confidence-check --auto` → `check_convergence`.
- `check_convergence` (`:650-666`) emits `NEEDS_MANUAL_REVIEW` whenever `TOTAL_DELTA <= 0` AND `POST_DECISION == "true"` — exactly the persisted-flag + stalled-scores state.

`rn-implement` (`:840-847`) maps `MANUAL_REVIEW_NEEDED` → `mark_blocked` → `blocked: 1` in summary. The operator sees a blocked issue with no actionable diagnostic.

Concrete reproduction (MC-vault, 2026-07-02): `ll-loop run rn-implement FEAT-398` exited with `Loop completed: done (18 iterations, 8m 40s)` and `summary.json: {"blocked":1,"implemented":0}`. FEAT-398's `## Proposed Solution` had `### Files to Add / ### Files to Modify / ### Implementation Outline / ### Design Decisions to Make` (an empty stub subsection) but no enumerable alternatives. The flag persisted and the convergence gate escalated.

`ENH-2426`'s `ll-issues format-check <ID>` (deterministic structural linter for missing/renamed/empty/boilerplate sections) correctly reports FEAT-398 as compliant — the failure is semantic, not structural. The current gate is not the right one to catch it.

## Expected Behavior

Two layered changes so that both skill-direct and FSM-driven calls surface the malformed-decision case.

**Skill-side — `/ll:decide-issue`**:

1. Add a `--validate-only` flag that probes an issue without performing scoring or frontmatter writes. Exit codes:
   - `0` — 2+ enumerable options AND no clear winner marker → proceed to scoring.
   - `0` — exactly one option (auto-clears `decision_needed: false`, exists today as Phase 3 single-option branch).
   - `1` with reason — 0 enumerable options → emit `OPTIONS_MISSING: decision_needed is true but ## Proposed Solution has no enumerable alternatives; run /ll:refine-issue to deposit options`.
2. Add a Phase 2.5 detection gate so direct invocations also surface the clear diagnostic instead of silently returning inconclusive.
3. In `--auto` mode only: when validation fails, auto-invoke `/ll:refine-issue ${issue_id} --auto` (1 retry, marker-bounded) and re-validate. If validation still fails after refine → keep the existing "leaving decision_needed unchanged" path AND emit the new diagnostic on stderr so callers can capture it.

**FSM-side — `rn-remediate`**:

1. Insert a new `check_decision_decidable` state between the existing `check_decision_needed` (`:256-261`) and `decide` (`:434-442`). The state calls `/ll:decide-issue ${context.issue_id} --auto --validate-only`.
2. On `no` (validation failed) → route to a new `deposit_options` action that runs `/ll:refine-issue ${context.issue_id} --auto`. `--auto` mode for refine deposits competing option blocks into `## Proposed Solution` and may set/clear `decision_needed`.
3. After `deposit_options` succeeds → loop back to `check_decision_decidable`. After it succeeds the second time → proceed to `decide`.
4. Add write-once marker `decide_options_deposited_${ISSUE_ID}.txt` so the deposit-options detour runs at most once per issue (write-once, monotonic, mirrors `refined_${ID}.txt` / `wired_${ID}.txt`).
5. Fail-open per the existing pattern: any state error in `check_decision_decidable` falls through to `decide` (preserves the BUG-2222 BUG-1985 chain).

After the change, the FEAT-398-class outcome is one of:
- Refine successfully deposits options → decide has work to do → either CONVERGED_PASS or genuine CONVERGED_STALLED.
- Refine also can't deposit options → check_format_gaps linter has already caught the structural case in Phase 0 (`ensure_formatted`); the semantic case is rare and the diagnostic now surfaces.

## Motivation

Operators hit this with no diagnostic feedback today. The `rn-implement FEAT-398` run spent 18 iterations and 8m 40s terminating with `blocked: 1` and a `subloop_outcome_FEAT-398.txt` of `MANUAL_REVIEW_NEEDED` — opaque without reading the SKILL source. The BUG-2222 routing fix correctly sends issues with the flag to `/ll:decide-issue`, and the BUG-1985 escalation to `NEEDS_MANUAL_REVIEW` is the right safety net against infinite loops. Both are working as designed; the missing piece is the layer between them — the "decision is not decidable, retry by depositing options" case.

P2 (not P0/P1) because: no data corruption, no security risk, no throughput regression. But operators lose 8+ minutes per occurrence and gain no diagnostic, so a single iteration of the current sprint is the right home.

## Proposed Solution

Sketch below. Final anchor references should be confirmed with `/ll:refine-issue` once the issue is implementation-ready.

### Skill change (`skills/decide-issue/SKILL.md`)

- **Phase 2.5 (new)**: After parsing the issue file, scan `## Proposed Solution` for enumerable option markers (`### Option <letter>`, numbered `1./2.` alternatives at the same heading depth, declarative recommendation blocks naming a single option). Count `OPTIONS`. Branch:
  - `OPTIONS >= 2` → Phase 3 (existing path).
  - `OPTIONS == 1` (and decision_needed is true) → Phase 7 with `decision_needed: false` (existing single-option branch).
  - `OPTIONS == 0` → emit `OPTIONS_MISSING` on stdout/stderr, exit non-zero. In `--auto` mode: invoke `/ll:refine-issue ${ISSUE_ID} --auto` once, bounded by a `--deposit-attempted` runtime flag, then re-run the validation. If still empty: keep `decision_needed: true`, exit `MANUAL_REVIEW_RECOMMENDED` (distinct from the existing `MANUAL_REVIEW_NEEDED` so callers can distinguish "skill had nothing to score" from other manual-review causes).
- **New flag**: `--validate-only` — runs Phases 1-2.5 only. Exit `0` if `OPTIONS >= 1` AND no clear-winner markers in `## Codebase Research Findings`; `1` with the structured reason otherwise.

### FSM change (`scripts/little_loops/loops/rn-remediate.yaml`)

Insert after `check_decision_needed`:

```
check_decision_decidable:
  # ENH-2443: validate before decide. Catches issues with decision_needed: true
  # but no enumerable options in ## Proposed Solution. Without this gate,
  # decide's silent pass-through on no options lets check_convergence escalate
  # to NEEDS_MANUAL_REVIEW even when the underlying case is "deposit options
  # first and try again". Mirrors check_decision_needed_post's failure philosophy
  # (fail-open: a validation-tooling error still routes to decide).
  fragment: shell_exit
  action: "/ll:decide-issue ${context.issue_id} --auto --validate-only"
  on_yes: decide
  on_no: deposit_options
  on_error: decide

deposit_options:
  # Bounded retry: refine --auto may deposit Option A/B/C blocks that decide can
  # then score. Write-once marker (mirrors refined_<ID>/wired_<ID>) prevents
  # infinite loops if refine also can't deposit options — falls through to decide
  # with no enumerable options; check_convergence then escalates to
  # MANUAL_REVIEW_NEEDED with the diagnostic now visible.
  fragment: with_rate_limit_handling
  action_type: slash_command
  action: "/ll:refine-issue ${context.issue_id} --auto"
  on_yes: record_options_deposited
  on_no: decide
  on_partial: record_options_deposited
  on_error: decide
  on_rate_limit_exhausted: rate_limit_diagnostic

record_options_deposited:
  # Marker ensures the deposit_options detour runs at most once per issue —
  # subsequent cycles of check_convergence -> check_decision_decidable skip
  # deposit_options and fall through to decide (which will properly escalate
  # to NEEDS_MANUAL_REVIEW after one cycle).
  action_type: shell
  action: |
    echo "1" > "${context.run_dir}/decide_options_deposited_${context.issue_id}.txt"
  next: check_decision_decidable
```

Plus a tweak to `deposit_options`/`check_decision_decidable` so the second-time-through path is the existing bypass: gate `check_decision_decidable` on `[ ! -f "${context.run_dir}/decide_options_deposited_${context.issue_id}.txt" ]` and route to `decide` directly when the marker is present. This bounds the workload to one refine detour per issue.

Plus update `ensure_formatted` (`:88-117`) doc comment to reference the new path (no behavioral change; the existing structural linter remains the first line of defense).

### Test coverage

Add to `scripts/tests/test_decide_issue.py` (or whatever the existing test module is — confirm with codebase search during implementation): a case where `--validate-only` returns non-zero on FEAT-398's actual file content (snapshot/golden test). Add a case where `--auto` plus `--deposit-attempted` runtime flag falls through to the existing manual-review branch without infinite-looping on the second deposit_options entry. Add a case that confirms the single-option branch still auto-clears `decision_needed: false` (regression guard for the existing behavior at `:213`).

Add to `scripts/tests/test_rn_remediate.py`: a state-flow test that walks `check_decision_needed` → `check_decision_decidable` (no) → `deposit_options` → `record_options_deposited` → `check_decision_decidable` (yes) → `decide`. Plus the marker-bounded second-time-through path (marker present → `check_decision_decidable` exits 0 → `decide` directly, skipping `deposit_options`).

## API/Interface

```python
# /ll:decide-issue CLI surface (Phase 1 argument parsing)
ISSUE_ID: str
AUTO_MODE: bool
DRY_RUN: bool
VALIDATE_ONLY: bool   # NEW — when True, run only Phases 1-2.5 and exit.
DEPOSIT_ATTEMPTED: bool  # NEW — runtime flag, auto-set by FSM in --auto mode
              # after one /ll:refine-issue --auto invocation.
```

```yaml
# /ll:decide-issue SKILL.md — new Phase 2.5 outcome token (returned on stdout)
OPTIONS_MISSING:
  reason: "decision_needed is true but ## Proposed Solution has no enumerable alternatives"
  suggested_command: "/ll:refine-issue ${ISSUE_ID} --auto"
  exit_code: 1
```

```yaml
# rn-remediate.yaml — new marker file (mirrors refined_<ID>.txt)
${run_dir}/decide_options_deposited_${ISSUE_ID}.txt
  shape: "1\n"
  semantics: write-once; existence means deposit_options already ran for this issue
```

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — Phase 2.5 detection, `--validate-only` flag, `--deposit-attempted` runtime flag, `OPTIONS_MISSING` token.
- `scripts/little_loops/loops/rn-remediate.yaml` — new `check_decision_decidable` / `deposit_options` / `record_options_deposited` states; `lib/common.yaml` may need an updated `with_rate_limit_handling` fragment if it isn't already imported (verify during implementation).
- `docs/reference/CONTRIBUTING.md` and `docs/guides/DECISION_AUTOMATION.md` (if exists) — document the new flag, the new marker, the new diagnostic.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/rn-implement.yaml` — implicitly affected (sub-loop now reports differently for the convergence case). No change needed unless the summary line for `blocked` should add a sub-counter for "BLOCKED-OPTIONS-MISSING" (defer to implementation if it stays the same count shape).
- `scripts/little_loops/loops/autodev.yaml` (`:151-194`) — has its own `check_decision_needed` flow; verify it doesn't need a parallel `check_decision_decidable` insertion (likely yes, for parity).
- `scripts/little_loops/loops/recursive-refine.yaml` (`:538-558`) — already handles `decision_needed: true` by skipping the issue; not affected by this change (this issue's scope is rn-remediate + rn-implement).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — top-level orchestrator that transitively exercises `decide-issue` via the `autodev` sub-loop (no direct change, listed for awareness).
- `scripts/little_loops/loops/brainstorm.yaml:357` — sets `decision_needed: true` after a decision-options report; consumers may emit issues that hit the new `OPTIONS_MISSING` gate.
- `scripts/little_loops/loops/hitl-compare.yaml:96, 105` — references `/ll:decide-issue` in pipeline context (no flag changes affect this surface).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:194-212` — has its own `check_decision_needed` shell_exit gate that calls `ll-issues check-flag ... decision_needed`; out of scope per the issue (this fix is rn-remediate-only) but a sibling parity insertion could be a follow-on.
- `scripts/little_loops/parallel/types.py:353-354, 416-426` — `decide_command` template + `get_decide_command()` builder. The `--auto` suffix is appended by the caller; the new `--validate-only` flag is skill-side only (does NOT need a config template change).
- `scripts/little_loops/parallel/worker_pool.py:488-498` — direct `_run_claude_command(decide_cmd, ...)` invocation; routes via `issue.decision_needed is True`. Will benefit from the new validation gate (downstream `rn-remediate` runs now pre-validate).
- `scripts/little_loops/issue_manager.py:830-849` — Decision-gate block that invokes `/ll:decide-issue {issue_id} --auto` in the single-issue `process_issue_inplace` path. Same benefit (downstream FSM pre-validates).
- `scripts/little_loops/cli/issues/__init__.py:78-89, 569-577, 780` — `ll-issues` help text + `check-flag` subparser registration (`cf` alias) + dispatcher. No change needed; `--validate-only` is a skill flag, not a CLI subcommand.
- `scripts/little_loops/cli/issues/show.py:186, 290-291` — surfaces `decision_needed` in `ll-issues show --json`. No change needed; the field schema is unchanged.
- `scripts/little_loops/issue_parser.py:413, 605-613, 752` — `IssueInfo.decision_needed` field declaration + reads via `frontmatter.get("decision_needed")`. No change needed.

**Design coupling surfaced by Agent 2**: `rn-implement.yaml:844` substring-matches `MANUAL_REVIEW_NEEDED` (pattern: `"MANUAL_REVIEW_NEEDED"`). If a new `MANUAL_REVIEW_RECOMMENDED` token is added (per the issue's Phase 2.5 — "distinct from the existing `MANUAL_REVIEW_NEEDED` so callers can distinguish 'skill had nothing to score' from other manual-review causes"), it is a SUPERSTRING of the existing token and would misroute to `mark_blocked`. **Verify at implementation time**: either (a) reuse `MANUAL_REVIEW_NEEDED` for both cases (operator sees blocked, with the diagnostic on stderr distinguishing them), or (b) route the new token with a longer-prefix pattern first. The implementation should confirm this design decision before shipping.

### Similar Patterns

- `check_decision_needed_post` (`:534-544`) — the closest analog: same shape (shell_exit fragment + on_yes/on_no/on_error branching); reuse its evaluate type and the existing `with_rate_limit_handling` fragment pattern.
- `ENH-2223`'s `--auto` knob in refine (`refine_light` vs `refine`) — precedent for `decision_needed: false` only when validate passes; the same flag-shape pattern.

### Tests

- `scripts/tests/test_decide_issue.py` (or equivalent; verify during implementation): `--validate-only` exit-code cases (0/0/1 for 2+/1/0 options), `OPTIONS_MISSING` payload shape, single-option regression.
- `scripts/tests/test_rn_remediate.py`: state-flow test for the new three-state insertion; marker-bounded second-time-through path; fail-open coverage on `check_decision_decidable`.
- `scripts/tests/test_builtin_loops.py`: FSM validate-level smoke test for `rn-remediate` (MR-1 etc. unaffected — the new state has the same evaluation structure as the existing gate).

_Wiring pass added by `/ll:wire-issue`:_

**Tests that MUST be updated** (will fail without changes):
- `scripts/tests/test_rn_remediate.py:174-184` — `test_check_decision_needed_routes_yes_to_decide` and `test_check_decision_needed_routes_no_to_diagnose`. The `_yes` test asserts `check_decision_needed.on_yes == "decide"`. After this change, `on_yes` must route to `check_decision_decidable` (not directly to `decide`). Update the assertion target to `"check_decision_decidable"`.
- `scripts/tests/test_rn_remediate.py:1002-1029` — `test_mr1_non_llm_evaluators_present`. Add `"check_decision_decidable": "exit_code"` to the `mr1_states` set. The new state uses `shell_exit` fragment with `exit_code` evaluator, so MR-1 is satisfied automatically; only the enumeration needs updating.
- `scripts/tests/test_rn_remediate.py:1053-1085` — `test_all_states_reachable_from_initial` will automatically pass via BFS, but verify the new states are reachable: `check_decision_needed → check_decision_decidable → decide` is the primary path; `deposit_options → record_options_deposited → check_decision_decidable` is the retry path.
- `scripts/tests/test_rn_remediate.py:1087` — `test_all_referenced_targets_exist` (verify exact line) will catch any `on_yes`/`on_no`/`next` reference to a non-existent state. New states must be defined in `data["states"]`.

**New test classes to add** (mirroring the issue's Test coverage paragraph):
- `scripts/tests/test_decide_issue_skill.py` — new `TestValidateOnly` class (mirrors `TestFlagParsing` at lines 17-50): assert `--validate-only` is documented in `Phase 1: Parse Arguments`.
- `scripts/tests/test_decide_issue_skill.py` — new `TestOptionsMissing` class (mirrors `TestPhase3bResolvedFilter` at lines 276-313): assert `OPTIONS_MISSING` token presence, the `decision_needed remains true` policy, and `Do NOT edit` policy.
- `scripts/tests/test_decide_issue_skill.py` — new `TestDepositAttemptedFlag` class (mirrors `TestFlagParsing`): assert `--deposit-attempted` runtime flag is documented in Phase 1.
- `scripts/tests/test_decide_issue_skill.py` — new `TestPhase2_5Detection` class: assert Phase 2.5 enumeration of `### Option [A-Z0-9]`, numbered `1./2.` alternatives, and declarative recommendation blocks is documented.
- `scripts/tests/test_decide_issue_skill.py` — new `TestSingleOptionRegression` class: regression guard for the existing Phase 3 single-option auto-clear at `skills/decide-issue/SKILL.md:139`.
- `scripts/tests/test_decide_issue_skill.py` — new `TestFEAT398Snapshot` class: golden-file test using new fixture `scripts/tests/fixtures/FEAT-398-decide-empty-proposed.md` (snapshotted from MC-vault). Assert `--validate-only` exits 1 + emits `OPTIONS_MISSING`.
- `scripts/tests/test_decide_issue_skill.py` — new `TestOptionsMissingExitCodes` class: subprocess-level test of `--validate-only` exit codes (0/0/1 for 2+/1/0 options), mirroring `_run_gate` in `scripts/tests/test_rn_remediate.py:1483-1499`.
- `scripts/tests/test_rn_remediate.py` — new `TestCheckDecisionDecidableState` class: assert the new `check_decision_decidable` state exists, uses `shell_exit` fragment, and the action string contains `--validate-only`.
- `scripts/tests/test_rn_remediate.py` — new `TestDepositOptionsState` class: assert `deposit_options` uses `with_rate_limit_handling` fragment and action is `/ll:refine-issue ${context.issue_id} --auto` (no `--full-rewrite`).
- `scripts/tests/test_rn_remediate.py` — new `TestRecordOptionsDepositedState` class: assert `record_options_deposited` writes `decide_options_deposited_<ID>.txt` and routes `next: check_decision_decidable` (mirrors `test_marker_writers_are_monotonic_and_route_to_decision_check` at line 560-573).
- `scripts/tests/test_rn_remediate.py` — new `TestDecisionDecidableFlow` class: state-flow walk `check_decision_needed → check_decision_decidable (no) → deposit_options → record_options_deposited → check_decision_decidable (yes) → decide` (mirrors `test_only_diagnose_route_reaches_destructive_refine` at lines 468-501).
- `scripts/tests/test_rn_remediate.py` — new `TestMarkerBoundedSecondPass` class: assert `decide_options_deposited_<ID>.txt` present → `check_decision_decidable` exits 0 → routes directly to `decide`, skipping `deposit_options`.

**Related test files** (for awareness, not direct changes):
- `scripts/tests/test_issue_parser.py:1991-2118` — `TestIssueInfoDecisionNeeded` covers `decision_needed` field reads (no change needed).
- `scripts/tests/test_issues_cli.py:2563-2591` — `test_show_json_includes_decision_needed` covers `decision_needed` propagation (no change needed).
- `scripts/tests/test_frontmatter.py:400-414` — `test_update_decision_needed_bool_false` covers the `update_frontmatter` path (no change needed; the skill does not use `update_frontmatter()`).
- `scripts/tests/test_rn_implement.py:240-292` — `TestSubLoopDelegation.test_run_remediation_*` covers `loop: rn-remediate` delegation. Verify the substring-matching route on `MANUAL_REVIEW_NEEDED` still works after the design decision for `MANUAL_REVIEW_RECOMMENDED` (Agent 2's design coupling).
- `scripts/tests/test_issue_manager.py:3560-3654` — `TestDecideIssueInvocation` covers `ll-auto` and `ll-parallel` decision-gate invocation paths (no change needed).
- `scripts/tests/test_builtin_loops.py:7820-7954` — `TestRnRemediateNonYesHandling` (BUG-2075) covers `assess`, `decide`, `wire`, `refine` state routing. Consider adding a sibling class for `check_decision_decidable`.
- `scripts/tests/test_builtin_loops.py:8885-9022` — `TestLearningGateConsistency` covers the `LEARNING_GATE_BLOCKED` cross-loop token pattern. If `OPTIONS_MISSING` is promoted to a shared fragment, mirror this class.

**Test fixture**:
- `scripts/tests/fixtures/FEAT-398-decide-empty-proposed.md` (new) — snapshot of FEAT-398's `## Proposed Solution` section from `/Users/brennon/AIProjects/MC-vault/.loops/runs/rn-implement-20260702T101635/`. The existing `scripts/tests/fixtures/issues/` directory has 21 issue files; place the new fixture alongside.

### Documentation

- `docs/reference/API.md` — `IssueInfo` doesn't change; `decide-issue` skill reference table should add `--validate-only` row and `OPTIONS_MISSING` exit token.
- `docs/reference/CONFIGURATION.md` — no config-key change (the new flag is per-invocation, not per-project).
- `docs/ARCHITECTURE.md` § FSM loops — short note that `rn-remediate` now has a "pre-decide validation detour" with marker-bounded retry (matches the document's tone for ENH-2223 / BUG-2222 entries).

_Wiring pass added by `/ll:wire-issue`:_

**Documentation files to update** (not yet in the issue's Files to Modify):
- `docs/reference/COMMANDS.md:231-242` — `/ll:decide-issue` reference currently documents only `--auto` and `--dry-run`. **Add `--validate-only` row** to the flags table.
- `docs/reference/COMMANDS.md:240` — Phase 3b provisional-decision narrative may shift if a new Phase 2.5 is inserted before Phase 3. Verify the ordering text.
- `docs/reference/COMMANDS.md:1006` — skill table row `decide-issue^` (no description change needed; auto-discovery).
- `docs/reference/CLI.md:1386-1413` — `ll-issues check-flag` subcommand reference; cross-references `format-check` and `decision_needed`. No flag changes here, but the new `OPTIONS_MISSING` flow makes this section more important.
- `docs/reference/API.md:480` — `decide_command: str = "decide-issue {{issue_id}}"` template reference. No change (template is unchanged).
- `docs/reference/API.md:664` — `IssueInfo.decision_needed: bool | None = None` description. No change (field semantics unchanged).
- `docs/reference/API.md:815, 3093` — `format-check` cross-reference and CLI template reference. No change needed.
- `docs/reference/CONFIGURATION.md:64, 354` — `decide_command` config-key row. No change (per-invocation flag, not config key).
- `docs/reference/ISSUE_TEMPLATE.md:886` — `decision_needed` frontmatter field doc. No change.
- `docs/guides/LOOPS_REFERENCE.md:143, 188, 192, 200-202, 350, 368, 444, 521, 555, 569-587, 890-921, 1016, 1051, 1378-1385` — narrative + diagrams covering `rn-remediate` decide path, `autodev` decide path, `recursive-refine` decision-need check. **Line 577** documents `assess → verify_scores_persisted → check_readiness → check_outcome → check_decision_needed`; add `check_decision_decidable` to this chain. **Line 587** documents the existing `/ll:decide-issue --auto` slash_command entry — note the new pre-decide validation gate.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:209` — subloop outcome token table; the `MANUAL_REVIEW_NEEDED` row may need a footnote about the `OPTIONS_MISSING` detour path.
- `docs/guides/DECISIONS_LOG_GUIDE.md:14, 31, 42, 162-169, 180, 193-204` — describes how `decision_needed` gates automation. **Add a short paragraph** noting that `OPTIONS_MISSING` is a structured-diagnostic case (the issue is structurally compliant but the skill has nothing to score).
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:214, 220, 381, 405` — pipeline order mentioning `decide-issue` and `score_ambiguity ≤ 10` rule. **Add a paragraph** about the new `--validate-only` flag for FSM-style callers.
- `docs/guides/GETTING_STARTED.md:318` — guide index pointer. No change needed.
- `CONTRIBUTING.md:133` — directory tree entry for `skills/decide-issue/`. No change needed.

**Cross-skill references** (skills that mention `/ll:decide-issue`; no flag-level changes required, but worth verifying the surrounding narrative is still accurate):
- `skills/wire-issue/SKILL.md:474, 486, 489` — pipeline diagram and "before" pointer.
- `skills/confidence-check/SKILL.md:373-377` — `decision_needed: true` writeback.
- `skills/confidence-check/rubric.md:385` — `score_ambiguity ≤ 10 → /ll:decide-issue`.
- `skills/manage-issue/SKILL.md:166` — pre-implementation decision gate.
- `skills/manage-issue/templates.md:219-232` — same gate in templates.
- `skills/issue-workflow/SKILL.md:76, 84` — workflow diagram.
- `commands/refine-issue.md:291-295, 598, 601, 638` — `decision_needed` writeback after `refine-issue --auto`.
- `commands/help.md` — likely lists `/ll:decide-issue`.

**CHANGELOG.md**: Per the project's release-prep convention (`docs/development/TROUBLESHOOTING.md` and `CONTRIBUTING.md`), this change warrants a CHANGELOG entry during release prep. The issue's Proposed Solution does not mention CHANGELOG; defer to the release owner.

### Configuration

- N/A. The behavior is enabled by default (no opt-out needed); `--skip-decide-deposit` could be added as a parity knob with `skip_learning_gate` if operators hit false positives, but defer until the feature has been exercised.

### Codebase Research Findings

_Added by `/ll:refine-issue --auto` (Phase 3 / 2026-07-02) — based on codebase analysis:_

**Anchor verification** (current state of cited files):
- Phase 3 single-option auto-clear is at `skills/decide-issue/SKILL.md:139` (the issue cites `:213` — off by a section-break; current single-option branch sits at the Phase 3 OPTIONS-count check, not in Phase 7b)
- Pattern 4 + AUTO_MODE handling at `:124-135` (issue cite `:135` correct)
- Phase 3b no-clear-winner branch (`leaving decision_needed unchanged`) at `:228` (issue cite correct)
- Phase 7b frontmatter-write idempotency rule at `:357-368`
- `scripts/little_loops/loops/rn-remediate.yaml`: `import` at `:26-27`; `ensure_formatted` at `:88-117`; `check_decision_needed` at `:256-261`; `gate_implement` (consumes markers) at `:342-369`; `decide` at `:434-442`; `mark_refined` write-once at `:514-522`; `mark_wired` write-once at `:524-532`; `check_decision_needed_post` (closest analog) at `:534-544`; `check_convergence` at `:650-666`; `emit_needs_manual_review` at `:746-750` — all anchor references verified.

**Existing patterns to model after** (newly surfaced):
- `--check` flag precedent at `skills/format-issue/SKILL.md:47,381-393` and the mirror at `skills/map-dependencies/SKILL.md:65,191` — closer analog for `--validate-only` than the `--auto` knob alone. The `--check` flag exits 0/1 and integrates with FSM `evaluate: type: exit_code`. Companion CLI `ll-issues format-check` at `scripts/little_loops/cli/issues/format_check.py:35-71` documents the contract (0 = compliant, 1 = gaps found). The proposed `--validate-only` should mirror this exact shape: exits 0 when `OPTIONS >= 1`, exits 1 when `OPTIONS = 0` (or when clear-winner marker is present).
- `NO_ACTIONABLE_DECISIONS` token at `skills/decide-issue/SKILL.md:162-166` — the *same skill*, structured stdout precedent for `OPTIONS_MISSING`. Mirrors the two-element output shape (semantic token on stdout + explicit `do NOT edit` policy + exit 0 with structured reason text). The new `OPTIONS_MISSING` token should follow the same shape: emit the token + a clear `do NOT edit decision_needed` policy + the structured `suggested_command: /ll:refine-issue ...` payload, then exit non-zero.
- `LEARNING_GATE_BLOCKED` stdout marker — fragment-mediated token detection at `scripts/little_loops/loops/lib/common.yaml:302-324` (`ll_auto_learning_gate_check`). State pattern: `fragment: ll_auto_learning_gate_check` → on detection, capture and emit a sub-loop outcome token. This is the third existing pattern for "FSM detects a specific stdout token and routes accordingly" — `OPTIONS_MISSING` could optionally become a fragment if it spreads to multiple skill consumers.
- `autodev-decide-ran` write-once marker at `scripts/little_loops/loops/autodev.yaml:205-214` — sibling precedent for the proposed `decide_options_deposited_<ID>.txt`. Uses `printf '1' > ${context.run_dir}/autodev-decide-ran` (no per-issue ID in the filename); per-issue naming is closer to `refined_<ID>.txt` / `wired_<ID>.txt` which is the existing rn-remediate convention — keep the per-issue naming.

**Helper functions** (newly surfaced):
- `update_frontmatter(content, updates)` at `scripts/little_loops/frontmatter.py:191-214` — Python-side union-merge helper for `decision_needed` writes. Callers: `scripts/little_loops/recursive_finalize.py:164,186`, `scripts/little_loops/parallel/orchestrator.py:1022`, `scripts/little_loops/cli/issues/set_scores.py`. Skill-side writers use Edit-on-`---`-block with explicit idempotency rule (`skills/decide-issue/SKILL.md:215-225`, `:357-368`).
- `cmd_check_flag()` at `scripts/little_loops/cli/issues/check_flag.py:13-33` — already implements `decision_needed` exit-code reads. The proposed `--validate-only` flag should NOT compose on top of this CLI; instead the skill itself should expose the exit code directly (mirroring `format-issue`'s `--check`).
- `scripts/little_loops/cli_args.py:214-220` — `add_skip_learning_gate_arg()` is the CLI factory pattern for adding flag-parsing boilerplate. If `--deposit-attempted` is ever exposed as a CLI flag (not just runtime FSM-set), this is the insertion point.

**Filename / path corrections**:
- The Implementation Steps § "Test coverage" paragraph cites `scripts/tests/test_decide_issue.py` — the actual module is `scripts/tests/test_decide_issue_skill.py`. Implementer should reference the latter.
- `FEAT-398` test fixture: not present in this repo. The Status section notes it's sourced from `/Users/brennon/AIProjects/MC-vault/.loops/runs/rn-implement-20260702T101635/`. For a self-contained unit test, snapshot FEAT-398's `## Proposed Solution` section into `scripts/tests/fixtures/FEAT-398-decide-empty-proposed.md` (or similar) and reference from `test_decide_issue_skill.py`.
- `docs/guides/DECISION_AUTOMATION.md` (parenthetical "(if exists)") — does not exist. Closest analogs: `docs/guides/DECISIONS_LOG_GUIDE.md` (decisions log mechanics) and `docs/reference/API.md` skill reference table (where `--validate-only` row should land). Update both rather than creating a new doc.
- `docs/reference/CLI.md` — separate from API.md, also documents `decision_needed` field and `format-check` subcommand. Add the new `--validate-only` row here too.

**Test patterns to mirror** (for implementation):
- `scripts/tests/test_decide_issue_skill.py:17-50` (`TestFlagParsing` class) — slice `content[phase1_start:phase2_start]` to assert flag-documentation presence. Add `test_validate_only_flag_documented` and `test_deposit_attempted_flag_documented` to this class.
- `scripts/tests/test_rn_remediate.py:468-501` (`test_only_diagnose_route_reaches_destructive_refine`) — walks every transition key on every state. Mirror shape for `check_decision_decidable → deposit_options → record_options_deposited → check_decision_decidable → decide` plus the marker-bounded second-time-through path (`decide_options_deposited_<ID>.txt` present → `check_decision_decidable` exits 0 → `decide` directly, skipping `deposit_options`).
- `scripts/tests/test_rn_remediate.py:1002-1029` (`test_mr1_non_llm_evaluators_present`) — add `check_decision_decidable` to the `mr1_states` set. The new state uses `shell_exit` fragment with `exit_code` evaluator, so MR-1 is satisfied without further annotation.
- `scripts/tests/test_rn_remediate.py:1053-1085` (`test_all_states_reachable_from_initial`) — ensure the new states are reachable from the loop's `initial` state via the existing `check_decision_needed → decide` path.
- `scripts/tests/test_decide_issue_skill.py` snapshot-test pattern — for `--validate-only` exit-code cases (0/0/1 for 2+/1/0 options), `OPTIONS_MISSING` payload shape, and single-option regression. Slice `## Proposed Solution` content via a fixture file and assert the exit code via subprocess (`subprocess.run(["ll-decide-issue", ...])`) or via a Python wrapper that imports the SKILL body and runs Phase 2.5 logic directly.

## Implementation Steps

1. Phase 0 (skill-only, shippable independently): add `--validate-only` flag and `OPTIONS_MISSING` token to `skills/decide-issue/SKILL.md`. Add unit tests against an existing issue fixture (`FEAT-398`'s `.issues/features/P3-FEAT-398-...md` is the canonical "structurally compliant but no enumerables" case — use it as the test fixture).
2. Phase 1 (skill-only): add `--deposit-attempted` runtime flag and the bounded `OPTIONS_MISSING -> /ll:refine-issue --auto` retry in `--auto` mode. Confirm single-invocation marker behavior with a test.
3. Phase 2 (FSM): insert `check_decision_decidable` in `rn-remediate.yaml`. Gate on `decide_options_deposited_${ISSUE_ID}.txt` not present. Wire to `deposit_options` (new action) → `record_options_deposited` (new marker state) → loop. Add state-flow tests.
4. Phase 3 (verification): run `python -m pytest scripts/tests/` to confirm `test_decide_issue`, `test_rn_remediate`, and the FSM validate suite pass. Run `ll-loop validate rn-remediate` (MR-1 etc. — the new state has a paired evaluator in `check_decision_decidable`, so MR-1 is satisfied).
5. Phase 4 (docs update): add `--validate-only` row to API reference, document `OPTIONS_MISSING` token, add short ARCHITECTURE note. Run `ll-verify-docs` to confirm link integrity.
6. Phase 5 (live verification, optional): run `ll-loop run rn-remediate FEAT-398 --max-iterations 5` against `MC-vault` (or a snapshot fixture); confirm the run now exits with `IMPLEMENTED` or `CONVERGED_STALLED` (and a useful diagnostic) instead of opaque `MANUAL_REVIEW_NEEDED`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis (3 parallel agents: caller-tracer, side-effect-tracer, test-gap-finder) and must be included in the implementation:_

7. **Phase 2 expanded**: when inserting `check_decision_decidable` in `rn-remediate.yaml`, **also insert the parallel gate in `autodev.yaml`**. The issue's Files to Modify says "verify... likely yes, for parity" — Agent 1 confirms autodev has `decide_current` (`:176-190`) and `run_decide` (`:192-203`) with the same `decision_needed` gate pattern; the same insertion (validate before run_decide) is needed for parity.
8. **Phase 4 expanded — additional doc files**: in addition to the API/ARCHITECTURE docs already listed, **update `docs/reference/COMMANDS.md:231-242`** (the `/ll:decide-issue` reference table currently lists only `--auto`/`--dry-run` — add `--validate-only` row) and **`docs/guides/DECISIONS_LOG_GUIDE.md`** (add a paragraph noting `OPTIONS_MISSING` as a structured-diagnostic case) and **`docs/guides/ISSUE_MANAGEMENT_GUIDE.md:214, 220, 381, 405`** (note the new `--validate-only` flag for FSM callers).
9. **Phase 4 expanded — additional LOOPS_REFERENCE updates**: **`docs/guides/LOOPS_REFERENCE.md:577, 587`** must document the new `check_decision_decidable` gate insertion in the state-chain narrative and the `decide` state description.
10. **Phase 4 expanded — RECURSIVE_LOOPS_GUIDE update**: **`docs/guides/RECURSIVE_LOOPS_GUIDE.md:209`** outcome-token table — the `MANUAL_REVIEW_NEEDED` row may need a footnote about the `OPTIONS_MISSING` detour path (verify at implementation).
11. **Phase 3 expanded — additional test class updates**: in addition to the test classes listed in Implementation Steps §"Test coverage", **update `scripts/tests/test_rn_remediate.py:174-184`** — the `_yes` route assertion must change from `decide` to `check_decision_decidable` (the existing `_no` route to `diagnose` is preserved). Without this update, `test_check_decision_needed_routes_yes_to_decide` will fail.
12. **Phase 3 expanded — MR-1 update**: **add `"check_decision_decidable": "exit_code"` to the `mr1_states` set in `scripts/tests/test_rn_remediate.py:1002-1029`** (`test_mr1_non_llm_evaluators_present`).
13. **Phase 0 expanded — fixture creation**: **snapshot FEAT-398's `## Proposed Solution` section to `scripts/tests/fixtures/FEAT-398-decide-empty-proposed.md`** (sourced from MC-vault; existing `scripts/tests/fixtures/issues/` directory has 21 fixtures). Reference from new `TestFEAT398Snapshot` class in `scripts/tests/test_decide_issue_skill.py`.
14. **Design verification (must confirm at implementation)**: confirm whether the new `MANUAL_REVIEW_RECOMMENDED` token (Phase 2.5) is a superstring-misroute risk for `rn-implement.yaml:844` (`pattern: "MANUAL_REVIEW_NEEDED"`). Either (a) reuse `MANUAL_REVIEW_NEEDED` and rely on stderr diagnostic to distinguish, or (b) route the new token via a longer-prefix pattern first. Document the decision in Implementation Steps Phase 0.
    - **Resolved 2026-07-02**: chose option (b) — emit `MANUAL_REVIEW_RECOMMENDED` from `/ll:decide-issue` Phase 2.5 and order `rn-implement.yaml:844`'s `pattern:` list longest-prefix-first so `MANUAL_REVIEW_RECOMMENDED` matches before the `MANUAL_REVIEW_NEEDED` substring fallback. Recorded as architecture decision `ARCHITECTURE-090` in `.ll/decisions.yaml`. Rationale: distinct stdout token preserves the diagnostic-distinction purpose of ENH-2443 (rejected option (a) — stderr-distinguishing defeats the issue's purpose); longest-prefix ordering eliminates the superstring-misroute risk at the FSM pattern matcher.
15. **CHANGELOG note (deferred to release prep)**: per the project's release-prep convention, add a CHANGELOG entry under the next release's `## [X.Y.Z] - DATE` section (NOT `[Unreleased]` per the user's feedback memory).

## Impact

- **Operator UX**: reduces `MANUAL_REVIEW_NEEDED` escalations on the "decision_needed: true + no enumerables" failure mode from 100% (today) to roughly the residual rate where `/ll:refine-issue --auto` also fails to deposit options.
- **Token cost**: marginal — `--auto` mode already invoked `/ll:refine-issue --auto` for the convergence-stall case downstream; this changes WHEN it runs (earlier, with bounded retry) but not the per-occurrence LLM cost.
- **FSM safety**: the BUG-1985 stall-detection + `NEEDS_MANUAL_REVIEW` safety net remains intact. The new path is an *earlier* recovery, not a replacement; if it can't recover, the existing safety net fires as before.
- **Downstream callers**: `rn-implement` summary shape stays the same (`blocked` count). A future iteration may split `blocked` into `blocked-decision` and `blocked-other` for finer triage, but that's a separate issue.

## Scope Boundaries

- **In scope**: `skills/decide-issue/SKILL.md` (Phase 2.5 detection, `--validate-only`, `--deposit-attempted`, `OPTIONS_MISSING` token) and `scripts/little_loops/loops/rn-remediate.yaml` (`check_decision_decidable` / `deposit_options` / `record_options_deposited` states). Parity insertion into `scripts/little_loops/loops/autodev.yaml`'s `decide_current`/`run_decide` gate is also in scope (Implementation Steps #7 — same `decision_needed` gate pattern, same fix needed for consistency).
- **Out of scope**: `scripts/little_loops/loops/recursive-refine.yaml` — already skips `decision_needed: true` issues outright and is unaffected by this change.
- **Out of scope**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`'s own `check_decision_needed` shell_exit gate — has a parallel but independent implementation; a sibling parity insertion there is a candidate follow-on issue, not part of this change.
- **Out of scope**: splitting `rn-implement`'s `blocked` summary counter into `blocked-decision` / `blocked-other` sub-counters for finer triage — noted in Impact as a separate future issue.
- **Out of scope**: a `--skip-decide-deposit` opt-out flag (parity with `skip_learning_gate`) — deferred until the feature has been exercised in production and false positives are observed.
- **Out of scope**: CHANGELOG entry — deferred to release prep per project convention (added under the next release's dated section, not `[Unreleased]`).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM loop architecture; relevant for the new rn-remediate states and the BUG-1985 / BUG-2222 context |
| `docs/reference/API.md` | `IssueInfo` field reference; `decide-issue` skill runtime flags |
| `docs/reference/CONFIGURATION.md` | No change needed, but referenced for the parity argument with `skip_learning_gate` |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | FSM authoring rules (the new states are not meta-loop edits, so MR-1..MR-10 don't apply, but worth a sanity check during implementation) |

## Status

- **open** — captured 2026-07-02 from `/ll:capture-issue` (MC-vault `rn-implement FEAT-398` failure analysis).
- **Discovered by**: investigation of `rn-implement` run dir `/Users/brennon/AIProjects/MC-vault/.loops/runs/rn-implement-20260702T101635/` (summary.json + subloop_outcome_FEAT-398.txt + post_scores_FEAT-398.json showed decision_needed=true persisted across all passes; `/ll:decide-issue` had no clear winner).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-02_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 74/100 → below threshold (75)

### Outcome Risk Factors
- open decision: `MANUAL_REVIEW_RECOMMENDED` superstring-misroute risk for `rn-implement.yaml:844` (pattern: `"MANUAL_REVIEW_NEEDED"`) — resolve before implementing by choosing reuse vs longer-prefix pattern (Agent 2 design coupling)
- tests are co-deliverables — Implementation Steps Phase 0 ships skill change + unit tests together; do not implement skill change in isolation (add `FEAT-398-decide-empty-proposed.md` fixture as part of the same change)
- broad enumeration across ~16 files spanning 4 subsystems (skill, FSM loops, tests, docs) — sequence carefully to avoid breaking `test_rn_remediate.py:174-184` and `:1002-1029` (assertion updates required before the new state insertions can be merged)
- `autodev.yaml` parity insert is a sibling change — verify `decide_current` (`:176-190`) and `run_decide` (`:192-203`) need the same `check_decision_decidable` gate before shipping

## Session Log
- `/ll:manage-issue` - 2026-07-02T19:35:38 - `14090f08-d410-4dc3-8714-789f6cef805b.jsonl`
- `/ll:decide-issue` - 2026-07-02T18:20:54 - `5526c50e-f474-4735-b6e5-eed9abd93740.jsonl`
- `/ll:ready-issue` - 2026-07-02T18:07:12 - `0e78f12e-777f-4ff5-b92f-3b098222c98b.jsonl`
- `/ll:confidence-check` - 2026-07-02T18:00:00 - `1d194b50-bfcb-4b17-85fb-41616e6fbc85.jsonl`
- `/ll:wire-issue` - 2026-07-02T17:39:44 - `f15e037d-a62c-446e-8783-2cb1cc420b0b.jsonl`
- `/ll:refine-issue` - 2026-07-02T17:25:12 - `1ae9d1a7-bf98-4f1e-b9a8-8bfefe964edd.jsonl`

- `/ll:capture-issue` - 2026-07-02T17:13:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/69eac6b7-733d-4883-b000-bd978814825a.jsonl`
