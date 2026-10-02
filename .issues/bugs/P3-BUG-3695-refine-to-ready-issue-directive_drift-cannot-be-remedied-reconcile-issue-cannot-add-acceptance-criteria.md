---
id: BUG-3695
type: BUG
title: 'refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue
  cannot add Acceptance Criteria'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:29Z'
parent: EPIC-3694
decision_needed: false
---

# BUG-3695: refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria

## Summary

`refine-to-ready-issue` routes a `DIRECTIVE_DRIFT` verify verdict to `reconcile_issue`, but `/ll:reconcile-issue` is forbidden from adding Acceptance Criteria, so the one remedy the verdict promises cannot clear the finding. The loop then exhausts its budgets and ends `GATE_UNMET`, even though the fix is small and fully specified by the verify finding.

## Current Behavior

Observed in run `refine-to-ready-issue-20261002T111524` on ENH-3678 (history run `2026-10-02T171524-refine-to-ready-issue`, 33 iterations, 24m39s, `failed`):

1. `verify_issue` returned `DIRECTIVE_DRIFT` on iterations 14, 20 and 29. Every claim about current code held; the only finding was a check B6 AC-coverage gap — the Integration Map lists a `ll-doctor` "rebuild pending" surface (`cli/doctor.py`) with no Acceptance Criterion. Later passes added further uncovered points: notice suppression on the automation-pruning path, the replay-duration measurement, and the `session_store/__init__.py` re-export.
2. `commands/verify-issues.md:263` defines `DIRECTIVE_DRIFT` as "remedied by `reconcile-issue`", and the loop routes `VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> `reconcile_issue` (`refine-to-ready-issue.yaml:589`).
3. `reconcile_issue` ran once (iteration 17) and reported `RECONCILED` with "Acceptance Criteria: unchanged". Its CONCERNS said adding the AC "would be a new requirement rather than a correction". That follows `commands/reconcile-issue.md:120`: "do not invent new requirements" — it only rewrites directive text contradicted by the issue's own findings.
4. `check_reconcile_limit` (counter increments on every entry, `target: 2`) allows one reconcile per run. The second `DIRECTIVE_DRIFT` fell to `check_gate_refine_limit` -> `refine_followup`, which is research-only and additive (`commands/refine-issue.md` §5c) and cannot add ACs; it appended more findings instead.
5. The third `DIRECTIVE_DRIFT` found both budgets exhausted -> `record_gate_unmet` -> `failed`.

This is a contract mismatch: a coverage gap (missing AC) is not a contradiction, so neither remedy state can fix it. Sibling of BUG-3574 (`PROPOSAL_UNSOUND` routed to reconcile, which cannot edit Proposed Solution) and ENH-3690 (`NON_VALID` citation-only findings have no repair route).

## Steps to Reproduce

1. Take an issue whose Integration Map lists a surface (e.g. `cli/doctor.py`) that no Acceptance Criterion covers, and whose code claims are otherwise accurate (ENH-3678 at the time of the observed run).
2. Run `ll-loop run refine-to-ready-issue ENH-3678`.
3. Observe `verify_issue` return `DIRECTIVE_DRIFT` (check B6 AC-coverage gap) and route to `check_reconcile_limit` -> `reconcile_issue`.
4. Observe `reconcile_issue` report `RECONCILED` with "Acceptance Criteria: unchanged", then `refine_followup` append findings without adding ACs.
5. Observe the loop exhaust both budgets and end `GATE_UNMET` via `record_gate_unmet` (`failed`).

## Expected Behavior

A `DIRECTIVE_DRIFT` verdict whose finding is "Integration Map entry has no Acceptance Criterion" is repaired in-loop by adding the missing AC(s), after which `verify_issue` returns `VALID`. Budget exhaustion is reached only when the repair genuinely cannot converge.

## Motivation

Any automated refinement run on an issue whose Integration Map has uncovered points burns ~25 minutes and 30+ iterations, then fails `GATE_UNMET`, although the fix (add the AC the verify finding names) is small and fully specified. The only workaround is a manual AC edit, which defeats the unattended `refine-to-ready-issue` path. It is the third instance of a verdict routed to a remedy that cannot clear it (see BUG-3574, ENH-3690), so fixing the contract also removes a recurring class of false `GATE_UNMET` exits.

## Proposed Solution

- **Option A (recommended — modified, per advisor review 2026-10-02):** a narrow, caller-flag-gated carve-out in `commands/reconcile-issue.md`.
  > **Selected:** Option A — copies the `verify-issues --from-evidence` (BUG-3637) flag shape and the ENH-2937 carve-out test pattern; no new state, counter or `max_steps` bump.
  - **Gate on a caller flag, not on frontmatter alone.** Add `--from-verify-evidence` to `/ll:reconcile-issue` (modelled on `verify-issues --from-evidence`). Only the loop's `reconcile_issue` state passes it. The carve-out applies only when the flag is set, `verify_verdict: DIRECTIVE_DRIFT` is present, and `verify_evidence` is non-empty. A frontmatter-only gate is unsafe: the verdict stays in frontmatter after a failed run (`record_gate_unmet` does not clear it, and `prepare-issue.yaml` never calls `clear-verify-verdict`), so `prepare-issue`'s `run_reconcile` would get the widened scope right after a `GATE_UNMET` exit. `reconcile_revision` and `run_reconcile` do not pass the flag, so they stay inert.
  - **Widen the source, not the sections.** `verify_evidence` counts as a recorded finding, and every added or rewritten bullet must trace to one `verify_evidence` item. The "do not invent new requirements" rule stays word-for-word. This is why the `b5a1b051` precedent does not apply: it rejected adding a new section (Program Design) whose content is refine's job, whereas Acceptance Criteria are already rewritable by reconcile.
  - **Cover all three DIRECTIVE_DRIFT sections** (Implementation Steps, Acceptance Criteria, Integration Map), not ACs only — B6's fixture-invalidation drift class has the same defect.
  - **Output Format:** `Acceptance Criteria: [rewritten | added | unchanged]`.
  - **Make verify enumerate every gap in one pass.** In the ENH-3678 run each verify pass found new uncovered points, so one repair can never converge if verify reveals gaps incrementally. Edit `commands/verify-issues.md` so B6 lists every uncovered Integration Map point in `verify_evidence` in a single pass. If a replay still fails, narrow B6 AC-coverage to behaviour-bearing entries (Files to Modify / Dependent Files) rather than every Tests/Documentation line `wire-issue` adds.
- **Option B (not recommended):** add a dedicated `add_missing_acs` repair state to `refine-to-ready-issue.yaml` with its own per-run budget counter (counter file under `${context.run_dir}`, seeded in `resolve_issue`, `output_numeric lt 2`, exhaustion to `record_gate_unmet`, plus the `max_steps` comment-block entry). Rejected in review: it is the same LLM editing the same sections, and costs a new counter, a `max_steps` bump and three `== 113` pin updates. Its one real advantage — an earlier `ACCEPTANCE_CRITERIA` reconcile cannot starve the drift repair — guards a case nobody has observed.
- **Rejected: a deterministic (non-LLM) route.** A templated AC such as "`cli/doctor.py` is covered" passes B6 by construction and games the gate. The non-LLM part is already the evaluator: `clear_verify_verdict` → a fresh `verify_issue`.
- **Leave `check_reconcile_limit` unchanged.** "Count only actual attempts" is a no-op (every entry under budget already is an attempt), and the observed run reconciled once then correctly ran out. The counter is shared with the `ACCEPTANCE_CRITERIA` route; that sharing did not cause this failure.

Either option must update the `DIRECTIVE_DRIFT` wording in `commands/verify-issues.md` and the dispatch tests (`TestRefineToReadyDispatch` route table in `scripts/tests/test_builtin_loops.py`, reconcile-issue tests).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-02.

**Selected**: Option A (modified, caller-flag-gated reconcile carve-out)

**Reasoning**: Option A reuses the closest sibling's mechanism — `verify-issues --from-evidence` (`commands/verify-issues.md:50-55`, explicit flag "never inferred from the field's presence") already passed from `correct_claims` in `refine-to-ready-issue.yaml:652` — and the ENH-2937 carve-out test pattern (`TestReconcileScopeBoundariesEligibility`). Option B copies `check_claim_correction_budget` structurally, but its `add_missing_acs` state still needs a repair command that can add ACs, which no existing command provides, so it reduces to Option A's reconcile carve-out plus a new counter, a `max_steps` bump past 113 and three pin updates.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |
| Option B | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- A: `reconcile-issue.md:125-131` already has a `### 0. Parse Flags` slot; only one test pin must change (`test_builtin_loops.py:1821` exact action string), plus new negative assertions for `reconcile_revision` and `prepare-issue.yaml` `run_reconcile`.
- A: the carve-out is prompt prose, not structurally enforced — mitigated by the explicit flag, the trace-to-`verify_evidence` rule, and string-presence tests; the B6 one-pass enumeration edit in `verify-issues.md` is a dependency for convergence.
- B: three `max_steps == 113` pins (`test_builtin_loops.py:1870`, `test_autodev_proof_reentry.py:131`, `test_advise_ready_gate.py:215`), `PRE_TABLE` edit, new routing/seeding tests with no template for the counter, and ≥6 steps per cycle.
- B's one advantage (a dedicated counter cannot be starved by an earlier `ACCEPTANCE_CRITERIA` reconcile) guards an unobserved case.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` - scope carve-out (Option A)
- `commands/verify-issues.md` - `DIRECTIVE_DRIFT` verdict table wording (~line 263) and B6 verdict text
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - route at ~589, `check_reconcile_limit`, `reconcile_issue` (Option B adds a state)

_Wiring pass added by `/ll:wire-issue`:_

**Additional sites inside known files to Modify**
- `commands/reconcile-issue.md:116` — the "Every rewritten claim must trace to an existing finding" rule ending "Outside that one branch, do not invent new requirements" (L120) is the Option A edit site; the ENH-2937 Scope Boundaries branch 2b ("carved out of the tracing requirement") in `Contract (read this first)` is the carve-out precedent to mirror [Agent 3 finding]
- `commands/reconcile-issue.md:309` — Output Format line `- Acceptance Criteria: [rewritten | unchanged]` in `Output Format`; a carve-out that adds ACs needs an output-format form reporting added criteria (the loop's CONCERNS text keys off it) [Agent 2 finding]
- `commands/verify-issues.md:184` — B6 "AC coverage of identified integration points" sub-check in `B6` and the DIRECTIVE_DRIFT assignment rule (~L197–206) in `C. Verdict`, which define which findings are classed as drift [Agent 1 finding]
- `commands/verify-issues.md:395` — persistence bullet "route it to `reconcile_issue`" in `Persist the verdict to frontmatter` (also ~L371 and ~L384 bullets naming `reconcile_issue`) must be reworded alongside the L263 table row [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:23` — header route-table comment (`VERIFY:DIRECTIVE_DRIFT → check_reconcile_limit`, L23/L31/L41) in the file header comment block [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:111` — `max_steps: 113` comment block (L74–147) in the header; Option B needs an "X -> Y for ..." entry and a bump, which breaks the three `== 113` pins listed under Tests [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:199` — `resolve_issue` seeds/resets every per-run counter file; an Option B counter (or any change to `refine-to-ready-reconcile-attempts` semantics) must be seeded here [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:623` — `check_claim_correction_budget` (BUG-3637) is the existing budget-then-repair-state shape to copy for Option B's `add_missing_acs` [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1252` — `record_gate_unmet` echo text names "verify verdict, placeholders, Program Design, or acceptance criteria"; exhaustion target for Option B [Agent 2 finding]

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:589` — `ACCEPTANCE_CRITERIA` obligation also routes to `check_reconcile_limit` (ENH-3248) and shares the same `refine-to-ready-reconcile-attempts` counter as `VERIFY:DIRECTIVE_DRIFT`; changing counter semantics (Implementation Step 3) affects both routes in `route_score_obligation` [Agent 3 finding]
- `scripts/little_loops/loops/prepare-issue.yaml:118` — `run_reconcile` invokes `/ll:reconcile-issue` (profile `reconcile-issue-auto`); an Option A carve-out must stay inert here. **Correction (advisor review):** gating on frontmatter `verify_verdict` does NOT keep this caller inert — the verdict persists after a failed run and `prepare-issue.yaml` never calls `clear-verify-verdict`. `run_reconcile` must simply not pass `--from-verify-evidence`; add a test asserting the action string lacks the flag [Agent 1 finding, corrected]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:718` — `reconcile_revision` (BUG-3574 proposal-revision path) also runs `/ll:reconcile-issue`; it must not pass `--from-verify-evidence`, so the carve-out stays inert there [Agent 1 finding]
- `scripts/little_loops/preparation_policy.py:638` — `reconcile_check` / `pick_remedy` "reconcile" decision; calls the same command, no code change expected in `pick_remedy` [Agent 2 finding]
- `scripts/little_loops/cli/issues/check_verify_verdict.py:86` — `--directive-drift` flag help text ("route to `reconcile_issue`") in `classify_verify_verdict` / argparse help; update if the remedy name changes [Agent 1 finding]
- `scripts/little_loops/cli/issues/next_obligation.py:77` — `VERIFY:DIRECTIVE_DRIFT` token emission in `_verify_class`; no change unless the verdict taxonomy changes [Agent 1 finding]
- `skills/ll-reconcile-issue/SKILL.md` — Codex bridge copying the command's `description`/`argument-hint`; regenerate (`ll-adapt --host codex --apply`) only if the `commands/reconcile-issue.md` frontmatter `description` (which enumerates rewritable sections) is edited [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:153` — token-table row "`VERIFY:DIRECTIVE_DRIFT`, `ACCEPTANCE_CRITERIA` | `check_reconcile_limit` (one `reconcile_issue` pass)" and L195 prose "`DIRECTIVE_DRIFT` ... goes to `reconcile-issue`" in `refine-to-ready-issue` route table [Agent 1 finding]
- `docs/reference/COMMANDS.md:300` — `/ll:reconcile-issue` section ("rewrite ... in place", "left untouched", "reconciles the issue **against itself**") in `/ll:reconcile-issue`; plus the L1105 command-list row [Agent 2 finding]
- `docs/reference/CLI.md:2639` — `--directive-drift` flag row (and the `next-obligation` VERIFY `sub_reason` list ~L2435) in `check-verify-verdict` [Agent 1 finding]
- `docs/reference/API.md:975` — "three directive sections `/ll:reconcile-issue` rewrites" in the reconcile/issue-parser section [Agent 2 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` - `TestRefineToReadyDispatch` route table
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` and reconcile-issue tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:3116` — `PRE_TABLE` exact-equality in `TestRefineToReadyDispatch.test_pre_score_routing_table` (pins `VERIFY:DIRECTIVE_DRIFT` and `ACCEPTANCE_CRITERIA` → `check_reconcile_limit`); update only if the route changes (Option B) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:1643` — `test_check_reconcile_limit_state_routing`, `test_check_reconcile_limit_counts_up_and_gates_at_two`, `test_check_reconcile_limit_counter_is_per_run`, `test_resolve_issue_seeds_reconcile_attempts_counter` pin counter file name, `lt 2`, `1`/`2` outputs and `on_no`/`on_error == check_gate_refine_limit`; will break if Implementation Step 3 changes counting [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:1814` — `test_reconcile_issue_state_routing` pins the exact action `/ll:reconcile-issue ${captured.issue_id.output}`, no fragment, `next`/`on_error == normalize_structure`; **will break under the chosen Option A** (the action gains `--from-verify-evidence`) — update the pinned string, and add sibling assertions that `reconcile_revision` and `prepare-issue.yaml` `run_reconcile` actions do NOT carry the flag [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:1870` — `data["max_steps"] == 113` in `test_precheck_format_and_fallback_routing`; breaks if Option B bumps `max_steps` [Agent 3 finding]
- `scripts/tests/test_autodev_proof_reentry.py:131` — `test_max_steps_raised` `== 113` pin; breaks on an Option B `max_steps` bump [Agent 3 finding]
- `scripts/tests/test_advise_ready_gate.py:215` — `test_max_steps_113` pin; breaks on an Option B `max_steps` bump [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:2762` — `test_proposal_revision_cycle_routing` asserts `check_reconcile_limit.on_yes == "reconcile_issue"` and `reconcile_revision` reachability; the BUG-3574 repair-cycle precedent to copy for an Option B routing test (alongside `test_resolve_issue_resets_proposal_revision_state`) [Agent 3 finding]
- `scripts/tests/test_reconcile_issue_command.py` — new test file entry (not yet listed): add a class modelled on `TestReconcileScopeBoundariesEligibility` asserting the Option A carve-out in the Contract slice; existing assertions `test_tracing_requirement_carve_out_for_decision_directive` (needs "carved out" / "does not need a tracing finding"), `test_not_a_general_rewrite_addition` ("narrow", "Preserve untouched") and `test_scope_boundaries_conditionally_eligible` must keep passing; no test currently pins "do not invent new requirements" [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py:119` — `TestDirectiveDriftVerdict.test_verdict_table_and_persistence_have_directive_drift` asserts the literal `"| DIRECTIVE_DRIFT |"` and `verify_verdict: DIRECTIVE_DRIFT` / `verify_evidence:` in the persist slice; keep these literals when rewording, and add a method asserting the new remedy wording [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py:487` — `test_host_artifacts_are_not_stale` (gemini, kimi-code, qwen, codex, omp) fails after the `commands/verify-issues.md` edit until mirrors are regenerated [Agent 3 finding]
- `scripts/tests/test_verify_skill_prose.py` — growth guard (`BASELINE_COUNT = 17`) scanning `commands/*.md` for prose markers; new carve-out prose must not match them [Agent 3 finding]
- `scripts/tests/test_docs_audience_gate.py` — `commands/` edits must not cite `scripts/tests/` or `scripts/little_loops/` paths [Agent 3 finding]
- No existing test steps the real `refine-to-ready-issue.yaml` FSM with a stubbed `DIRECTIVE_DRIFT` verdict (all are static YAML or bash-state subprocess tests); the AC-coverage-only regression case is a new test shaped like `_run_check_reconcile_limit` or a stubbed `PersistentExecutor` run (`test_autodev_characterization.py` pattern) [Agent 3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- Mirrors: `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen|codex> --apply` after `commands/verify-issues.md` edits; `commands/reconcile-issue.md` has `disable-model-invocation: true` so body-only edits have no mirror impact [Agent 2 finding]
- `.ll/decisions.d/b5a1b051-4f32-42a8-b4ef-148a54801c52.json` — records the rejected option of widening reconcile-issue's contract to Program Design; Option A must be reconciled with that precedent (state why an AC-coverage carve-out is different) [Agent 1 finding]

## Program Design

### Types

- `verify_verdict: str` — the `verify_issue` verdict (`DIRECTIVE_DRIFT` here)
- `verify_evidence: str` — the finding text naming the uncovered Integration Map entries

### Signatures

- `reconcile_issue(issue_id: str, verify_verdict: str, verify_evidence: str) -> str` — existing state running `/ll:reconcile-issue ${captured.issue_id.output} --from-verify-evidence`; under Option A, only when that flag is set AND `verify_verdict` is `DIRECTIVE_DRIFT` AND `verify_evidence` is non-empty, `verify_evidence` counts as a recorded finding and reconcile may add or rewrite bullets in Implementation Steps, Acceptance Criteria and Integration Map, each traceable to one `verify_evidence` item. Every other "no new requirements" rule is unchanged.
- `add_missing_acs(issue_id: str, verify_evidence: str) -> str` — Option B only: new repair state with its own per-run budget counter under `${context.run_dir}`, exhaustion routing to `record_gate_unmet`.

### Call Path

`verify_issue` -> `check_reconcile_limit` -> `reconcile_issue` -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue` — the repair loop that must now converge on `VALID`. `verify_evidence` is still in frontmatter when `reconcile_issue` runs; `clear_verify_verdict` runs only after it.

`check_reconcile_limit` -> `check_gate_refine_limit` -> `refine_followup` -> `record_gate_unmet` — the observed failing path (research-only follow-up, then `GATE_UNMET`).

## Implementation Steps

1. Option A (modified, caller-flag-gated) selected via `/ll:decide-issue` on 2026-10-02 (see Decision Rationale); Option B rejected.
2. Add the `--from-verify-evidence` flag and carve-out to `commands/reconcile-issue.md` (flag parsing in `### 0. Parse Flags`, carve-out near L116–121, Output Format `[rewritten | added | unchanged]`); pass the flag only from `refine-to-ready-issue.yaml` `reconcile_issue`.
3. Edit `commands/verify-issues.md`: B6 lists every uncovered Integration Map point in `verify_evidence` in one pass, and the `DIRECTIVE_DRIFT` wording names the actual remedy.
4. Leave `check_reconcile_limit` unchanged: the counting change is a no-op (see Proposed Solution), and the budget stays at one reconcile per run (re-confirmed in the 2026-10-02 Fable review). Convergence depends on B6's one-pass enumeration; until the manual replay passes, that is unproven.
5. Update `TestRefineToReadyDispatch`/`test_reconcile_issue_state_routing` and the reconcile-issue tests; add the flag-inert assertions for `reconcile_revision` and `prepare-issue.yaml` `run_reconcile`, and an AC-coverage-only `DIRECTIVE_DRIFT` regression. Add a test that pins the carve-out as inert on the `ACCEPTANCE_CRITERIA` route. That route reaches the same `reconcile_issue` state, so the action carries the flag, but `next_obligation` orders `VERIFY` before `ACCEPTANCE_CRITERIA`. The persisted verdict therefore cannot be `DIRECTIVE_DRIFT` when the `ACCEPTANCE_CRITERIA` obligation fires. Assert that ordering in `little_loops.cli.issues.next_obligation`.
6. Regenerate host mirrors, run `python -m pytest scripts/tests/`. Manually replay an AC-coverage-only drift (a fresh fixture issue, not ENH-3678 — it no longer carries the verdict) as a non-gating verification note.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `commands/verify-issues.md` — reword the `| DIRECTIVE_DRIFT |` row (~L263) **and** the persistence bullets (~L371, ~L384, ~L395–397); keep the literals `| DIRECTIVE_DRIFT |`, `verify_verdict: DIRECTIVE_DRIFT`, `verify_evidence:`, `double-quoted YAML scalar` that `test_enh3250_verify_issues_proposal_vs_code.py` asserts
- Update `commands/reconcile-issue.md` (Option A) — add the `--from-verify-evidence` flag to `### 0. Parse Flags` and the carve-out near L116–121 keeping "carved out"/"narrow"/"Preserve untouched" in the Contract slice, and extend the L309 Output Format line to `Acceptance Criteria: [rewritten | added | unchanged]`; gate the carve-out on the flag (plus `verify_verdict: DIRECTIVE_DRIFT` and non-empty `verify_evidence`) so `prepare-issue.yaml` `run_reconcile` and `reconcile_revision` stay inert even with a stale verdict in frontmatter
- Update `commands/verify-issues.md` B6 so a single verify pass lists every uncovered Integration Map point in `verify_evidence`
- If Option B: seed the new counter in `resolve_issue`, route `VERIFY:DIRECTIVE_DRIFT` to the new budget state, add the `max_steps` comment-block entry, and bump `max_steps` — then update the three `== 113` pins (`test_builtin_loops.py:1870`, `test_autodev_proof_reentry.py:131`, `test_advise_ready_gate.py:215`) and `PRE_TABLE`
- `check_reconcile_limit` counting is intentionally unchanged (advisor review); `ACCEPTANCE_CRITERIA` keeps sharing the counter, so the `check_reconcile_limit` test family needs no edits
- Update `docs/guides/LOOPS_REFERENCE.md` (L153, L195), `docs/reference/COMMANDS.md` (`/ll:reconcile-issue`), and `docs/reference/CLI.md` (`--directive-drift`) to describe the new remedy
- Add tests: carve-out class in `test_reconcile_issue_command.py`; new method in `TestDirectiveDriftVerdict`; AC-coverage-only `DIRECTIVE_DRIFT` regression (none exists today)
- Regenerate host mirrors — `ll-adapt --host <gemini|kimi-code|qwen|codex> --apply` after the `commands/verify-issues.md` edit (`test_host_artifacts_are_not_stale`)

## Impact

- **Priority**: P3 - blocks automated refinement of any issue whose Integration Map has uncovered points; a manual AC edit is the workaround
- **Effort**: Small (Option A) to Medium (Option B)
- **Risk**: Low - scoped to one verdict path

## Acceptance Criteria

- [ ] `refine-to-ready-issue.yaml` `reconcile_issue` action carries `--from-verify-evidence`; `reconcile_revision` and `prepare-issue.yaml` `run_reconcile` actions do not (asserted by tests)
- [ ] `commands/reconcile-issue.md` names the carve-out: applies only with the flag, `verify_verdict: DIRECTIVE_DRIFT` and non-empty `verify_evidence`; each added bullet must trace to one `verify_evidence` item; the "do not invent new requirements" rule is otherwise unchanged and the carve-out is inert without the flag (asserted by a new test class in `test_reconcile_issue_command.py`)
- [ ] `reconcile-issue` Output Format reports `Acceptance Criteria: [rewritten | added | unchanged]`
- [ ] `commands/verify-issues.md` B6 requires listing every uncovered Integration Map point in `verify_evidence` in one pass, and the `DIRECTIVE_DRIFT` verdict table names the actual remedy
- [ ] A test pins `VERIFY` ahead of `ACCEPTANCE_CRITERIA` in the `next_obligation` pre-score order, so the flagged `reconcile_issue` action cannot apply the carve-out on the `ACCEPTANCE_CRITERIA` route
- [ ] A regression test covers an AC-coverage-only `DIRECTIVE_DRIFT` route (stubbed verdict) through `reconcile_issue` → `normalize_structure` → `clear_verify_verdict` → `verify_issue`
- [ ] Host mirrors regenerated, route-table and reconcile tests updated, and `python -m pytest scripts/tests/` exits 0
- _Manual verification (non-gating):_ replaying an AC-coverage-only drift on a fresh fixture issue no longer ends in `GATE_UNMET`

## Secondary Observations

- _(Moved out)_ `refine_followup`'s vanished scratch snapshot is now tracked as BUG-3702.
- `verify_issue` on iteration 29 spent turns on a failed glob for the issue file before recovering.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-02_

> **Stale (2026-10-02 review):** these scores were measured while the Option A/B decision was still open, and the frontmatter scores were cleared. Re-run `/ll:confidence-check`.

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- Unresolved design decision: Option A (reconcile carve-out) vs Option B (`add_missing_acs` state) is not selected, and Implementation Step 3 (whether `check_reconcile_limit` counts only real reconcile attempts) is also open. The counter is shared with the `ACCEPTANCE_CRITERIA` route, so the choice changes behavior beyond `DIRECTIVE_DRIFT`.
- Broad enumeration across ~15 sites (command prose, loop YAML, 4 docs, host mirrors, 3 `max_steps == 113` pins under Option B).
- `reconcile-issue` has 3 callers (`reconcile_issue`, `reconcile_revision`, `prepare-issue.yaml` `run_reconcile`); the carve-out must be gated on `verify_verdict: DIRECTIVE_DRIFT` or it widens writes for the other two.
- Precedent in `.ll/decisions.d/b5a1b051-…json` rejected widening reconcile's contract to Program Design; Option A must justify why an AC-coverage carve-out differs.
- No test steps the real FSM with a stubbed `DIRECTIVE_DRIFT` verdict; the AC-coverage regression is a new test shape.
- _(Resolved 2026-10-02)_ `/ll:decide-issue BUG-3695` selected Option A; `decision_needed` cleared.

## Session Log
- `/ll:decide-issue` - 2026-10-02T20:01:51 - `c7a25ce4-f603-4faf-97bd-88495061e012.jsonl`
- `/ll:confidence-check` - 2026-10-02T19:45:19 - `9a15ba2c-4c77-475b-8d6d-2e5aa8b1186f.jsonl`
- `/ll:wire-issue` - 2026-10-02T19:42:57 - `4830feb2-90ba-4747-9939-6d60a5df22df.jsonl`
- `/ll:refine-issue` - 2026-10-02T17:56:39 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`
