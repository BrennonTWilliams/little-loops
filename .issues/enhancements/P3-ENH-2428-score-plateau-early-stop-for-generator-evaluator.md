---
id: ENH-2428
type: enhancement
status: done
priority: P3
title: Score-plateau early-stop for generator-evaluator oracle
labels:
- loops
- harness
- generator-evaluator
relates_to: []
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
decision_needed: false
completed_at: 2026-07-01 22:51:50+00:00
---

# Score-plateau early-stop for generator-evaluator oracle

## Summary

The `oracles/generator-evaluator` sub-loop's stall guard watches git diff
bytes, which misses the real stagnation mode: visible/scored output plateaus
while the file keeps growing byte-for-byte. Add a **score-plateau** evaluator
that accepts best-so-far and routes to `done` when rubric scores stop
improving for `max_stall` consecutive rounds.

## Current Behavior

`check_stall` → `diff_stall_gate` (`scripts/little_loops/loops/lib/common.yaml:148`)
watches **git diff bytes**. This does not catch the real stagnation mode
observed in the `html-website-generator` run review
(`html-website-generator-20260701T105614`):

- `index.html` grew 94 KB → 124 KB across 16 refine rounds, so the git diff was
  never identical and `diff_stall` never fired.
- Meanwhile the **visible, scored output plateaued after ~iter-1** — every round
  scored at or near the same rubric values with diminishing visual change.
- Result: the loop burned ~2h15m / most of its iteration budget buying almost no
  scored improvement, then hit the step/time ceiling.

## Expected Behavior

A **score-plateau** signal replaces byte-diff as the primary stall axis: if
the rubric scores do not improve by more than a small epsilon for `max_stall`
(default 2) consecutive rounds, the loop accepts best-so-far and routes to
`done` instead of continuing to the step/time ceiling.

## Motivation

- The `html-website-generator` review found the loop burned ~2h15m — most of
  its iteration budget — buying almost no scored improvement after iter-1,
  because the stall guard watches the wrong signal (byte diff, not rubric
  score).
- A reusable `score_stall` evaluator fixes this for `oracles/generator-evaluator`
  and any other loop pairing an LLM `score` state with iterative refinement.
- Satisfies the MR-1 discriminator rule (non-LLM external evaluator paired
  with the LLM `score` state) noted in the Proposed Solution below.

## Context

The immediate churn drivers from the same review (full-page screenshot, and
score-driven termination that ignores the advisory "Issues to Address" list) were
already fixed directly in:
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` (`--full-page`)
- `scripts/little_loops/loops/lib/harness.yaml` (`playwright_screenshot` default)
- `scripts/little_loops/loops/html-website-generator.yaml` (rubric hardening +
  `max_steps` 30→12 / `timeout` 14400→3600)

This issue is the remaining, larger piece: a reusable **score-stall evaluator**
so the plateau is caught on the correct signal rather than relying only on the
lowered step ceiling as a backstop.

## Proposed Solution

- Persist each round's numeric rubric scores (the four criteria) to a small file
  under `${context.run_dir}/` (e.g. `.score_history` — per-run isolation per
  MR-3), written by the `score` state / `ll_rubric_score` path.
- Add a `score_stall` evaluator type (or a `score_stall_gate` fragment mirroring
  `diff_stall_gate`) that reads the history and returns `no` (plateaued) when the
  aggregate/weighted score has not improved by more than a small epsilon for
  `max_stall` (default 2) consecutive rounds.
- Wire `check_stall` in `generator-evaluator.yaml` to use the score-plateau
  signal (keep `diff_stall` as a secondary/OR condition if cheap).
- This is a non-LLM external evaluator, satisfying the MR-1 discriminator rule
  for the paired LLM `score` state.

`ll_rubric_score` (`scripts/little_loops/loops/lib/harness.yaml:16`) currently
emits only a binary `ALL_PASS`/`NEEDS_WORK` verdict — no numeric per-criterion
output. Persisting a score history (bullet 1 above) requires adding a
numeric-scoring prompt/capture/parse step first (mirroring
`rubric_score`/`rubric_parse_scores` in `lib/rubric-router.yaml`). There are two
ways to add that numeric output:

### Option A: Extend the shared `ll_rubric_score` fragment

Add numeric per-criterion score emission directly to the shared
`ll_rubric_score` fragment (`scripts/little_loops/loops/lib/harness.yaml:16`),
so every consumer gets numeric scores alongside the existing binary verdict.
`ll_rubric_score` is used by 7 loops: hitl-compare, html-anything,
html-website-generator, interactive-component-generator,
openscad-model-generator, hitl-md, svg-image-generator.

### Option B: Add a scoped numeric-scoring variant

Add a separate numeric-scoring evaluator/fragment used only by
`oracles/generator-evaluator`, leaving the shared `ll_rubric_score` fragment
(and its other 6 consumers) untouched.

> **Selected:** Option B — scopes the change to `generator-evaluator.yaml`
> alone, reusing the `from:`-inheritance precedent already established by
> `generator-evaluator-cli.yaml` instead of retrofitting capture/parse infra
> onto the shared, test-locked `ll_rubric_score` fragment.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-01.

**Selected**: Option B — Add a scoped numeric-scoring variant

**Reasoning**: `ll_rubric_score` is directly referenced by only 2 loops
(`oracles/generator-evaluator.yaml:97`, `openscad-model-generator.yaml:206`);
the other 5 named loops reach it transitively by calling
`loop: oracles/generator-evaluator` as a sub-loop. Scoping the change to
`generator-evaluator.yaml` therefore reaches those 5 identically while leaving
`openscad-model-generator.yaml` untouched — matching this issue's own Scope
Boundary that other-oracle wiring is separate follow-up work.
`generator-evaluator-cli.yaml` (`from: generator-evaluator`) already
demonstrates the exact scoping mechanism Option B needs. Option A would
instead retrofit capture+parse infrastructure onto a fragment whose binary
`output_contains: ALL_PASS` shape is asserted directly by
`test_fsm_fragments.py:1483` and mirrored across structural tests for all 7-8
consumers, each of which already emits its own bespoke numeric rubric text to
`critique.md` independent of the shared fragment — forcing an unrelated
consumer (`openscad-model-generator`) to absorb a shape change it doesn't need.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A: Extend shared fragment | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |
| B: Scoped variant | 3/3 | 2/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- Option A: `ll_rubric_score` has no `capture:`/parse step at all (unlike its
  sibling `rubric_score`/`rubric_parse_scores` in `lib/rubric-router.yaml`),
  and its binary contract is test-locked across all 8 consumers — retrofitting
  numeric emission here widens the change surface to unrelated loops.
- Option B: `generator-evaluator-cli.yaml` is direct precedent for scoping
  generator-evaluator-only changes via `from:` inheritance; the "7 loops"
  framing in this issue is transitive, not direct, so a scoped change still
  reaches all of them except `openscad-model-generator`, which doesn't need
  `score_stall` regardless.

## Scope Boundaries

- **In scope**: persisting per-round rubric scores under `${context.run_dir}/`;
  a `score_stall` evaluator (or fragment) with a `max_stall` knob and epsilon
  threshold; wiring `check_stall` in `oracles/generator-evaluator` to the
  score-plateau signal.
- **Out of scope**: removing `diff_stall` outright — it stays as a
  secondary/OR condition per the Proposed Solution; wiring `score_stall` into
  other oracle loops beyond `generator-evaluator` (the evaluator should be
  reusable, but adopting it elsewhere is separate follow-up work).

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Files to Modify

- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.type` `Literal[...]` (~line 58-72):
  add `"score_stall"`; add any new dataclass field(s) (e.g. epsilon/threshold,
  history-file path) if `score_stall` needs config beyond `max_stall`.
- `scripts/little_loops/fsm/fsm-loop-schema.json` —
  `evaluateConfig.properties.type.enum` (~line 514-528): add `"score_stall"`,
  must stay in sync with the Python `Literal` above.
- `scripts/little_loops/fsm/evaluators.py` — add `evaluate_score_stall()`
  (mirror `evaluate_diff_stall()`, ~line 507-599); add a dispatch branch in
  `evaluate()` (~line 1529) before the trailing `else: raise ValueError(...)`;
  review `_EXIT_CODE_AWARE_EVALUATORS` frozenset (~line 1565) for whether
  `score_stall` (a gate-style, non-shell evaluator like `diff_stall`) belongs
  in it.
- `scripts/little_loops/fsm/validation.py` — add `"score_stall": []` to
  `EVALUATOR_REQUIRED_FIELDS` (~line 64-78; this dict is the actual
  source-of-truth allowlist that `NON_LLM_EVALUATOR_TYPES` derives from, so
  this single edit is what makes `score_stall` satisfy MR-1 for a paired
  `check_semantic`/`llm_structured` state — no separate allowlist to edit);
  add a `score_stall` validation block in `_validate_evaluator()` (mirror the
  `diff_stall` block, ~line 310-318, e.g. `max_stall >= 1`); append
  `score_stall` to the MR-1 error message prose list (~line 1199, currently
  hardcodes `"...of: exit_code, output_numeric, convergence, diff_stall,
  action_stall, mcp_result."`).
- `scripts/little_loops/loops/lib/common.yaml` — new `score_stall_gate`
  fragment (mirror `diff_stall_gate`, ~line 148-160: same
  `description:` + bare `evaluate: {type: score_stall, max_stall: 2, ...}`
  shape).
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` —
  `check_stall` state (~line 106) routes through `score_stall` (OR
  `diff_stall`, per Scope Boundaries); `score` state (~line 96) needs the
  scoped numeric-score capture/parse override discussed in Proposed Solution
  (mirror `rubric_score`/`rubric_parse_scores` in `lib/rubric-router.yaml`,
  applied as a local override here — precedent: the `evaluate:` state
  override pattern in `generator-evaluator-cli.yaml` — NOT by editing
  `lib/harness.yaml`'s `ll_rubric_score`).

### Dependent Files (Callers/Importers)

- 6 loops reach `oracles/generator-evaluator` transitively as a sub-loop and
  inherit this change automatically (already enumerated in Decision
  Rationale above): `html-website-generator.yaml`, `html-anything.yaml`,
  `svg-image-generator.yaml`, `hitl-md.yaml`,
  `interactive-component-generator.yaml`, `hitl-compare.yaml` — no direct
  edits needed; listed for regression-test awareness only.
- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml` —
  inherits `check_stall`/`score` via `from:` resolution; verify the resolved
  states pick up the new fragment/override correctly (existing
  `TestGeneratorEvaluatorCliOracle` is the regression guard).
- `scripts/little_loops/cli/loop/info.py` — `_EVALUATE_TYPE_DISPLAY` dict
  (~line 1063-1074), cosmetic display-label mapping for `ll-loop show`;
  falls back gracefully via `.get(ev_type, ev_type)` so this is optional but
  recommended.

### Documentation

- `.claude/CLAUDE.md` — MR-1 rule table row lists evaluator types by name
  (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `mcp_result`);
  add `score_stall`.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — same MR-1 row; CLAUDE.md
  calls this file "the source of truth this table summarizes."
- `docs/reference/CLI.md` (~line 628) — MR-1 prose evaluator list.
- `docs/reference/API.md` (~line 4598-4623) — hand-mirrors the
  `EvaluateConfig` dataclass; update the type list and any new field
  comments to match `schema.py`.
- `docs/guides/LOOPS_GUIDE.md` (~line 288-289) — evaluator reference table
  row.
- `docs/generalized-fsm-loop.md` — evaluator-type list comment (~line 307);
  new `#### score_stall` subsection following the `#### diff_stall` template
  (~line 692-711: YAML example + verdict table + "Result details" line).
- `skills/create-loop/loop-types.md` (~line 961) — "Stall Detection" section
  documents `diff_stall`; add `score_stall` as a companion/OR-condition
  evaluator.
- `skills/create-loop/reference.md` (~line 1306) and
  `docs/guides/LOOPS_REFERENCE.md` (~line 3108) — both maintain a duplicate
  Fragment Catalog table; add a `score_stall_gate` row to both.
- `docs/reference/loops.md` (~line 443, 460, 521) — ASCII state diagrams for
  `oracles/generator-evaluator` and `generator-evaluator-cli` currently show
  `check_stall (fragment: diff_stall_gate; max_stall=3)`; update once
  `check_stall` gains the OR-condition.

### Tests

- `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` (~line
  1294-1468) — copy-template for a new `TestScoreStallEvaluator`
  (first-iteration success, identical-history-at-threshold failure,
  below-threshold success, reset-on-progress, dispatch tests).
- `scripts/tests/test_fsm_fragments.py::TestDiffStallGateFragment` (~line
  1708-1755) — copy-template for a new `TestScoreStallGateFragment`
  (defined-in-yaml, correct evaluator config, has-description,
  resolves-in-loop).
- `scripts/tests/test_fsm_validation.py::TestMetaLoopValidation
  .test_mr1_passes_when_exit_code_evaluator_present` (~line 996-1010) —
  copy-template for a new `test_mr1_passes_when_score_stall_evaluator_present`.
- `scripts/tests/test_builtin_loops.py::TestGeneratorEvaluatorOracle`
  (~line 6431-6486) — add an assertion that `check_stall` routes through
  `score_stall` (or the OR-combination); existing
  `test_required_states_exist` / `test_score_uses_output_contains_all_pass` /
  `test_score_routes_to_done_on_yes` in this class are regression guards.
- `scripts/tests/test_builtin_loops.py::TestMR4BuiltinFalsePositives
  .test_generator_evaluator_no_mr4_warnings` (~line 385-400) — regression
  guard: `check_stall` routing changes must not introduce MR-4 dead-ends.
- `scripts/tests/test_builtin_loops.py::TestGeneratorEvaluatorCliOracle` —
  regression guard: inheritance resolution must still pick up the new
  `check_stall`/`score` behavior unchanged via `from:`.
- `scripts/tests/test_fsm_fragments.py:1483
  test_ll_rubric_score_has_output_contains_evaluator` — regression guard,
  must NOT be modified (this issue's own Option B constraint).
- New fixture-driven test proving plateau detection over a flat score
  history, satisfying this issue's own Acceptance Criteria ("verified by a
  test that feeds a flat score history") — closest existing precedent is the
  `mock_git`-mutate-between-calls pattern in `TestDiffStallEvaluator` plus
  the `clean_state_files`/`monkeypatch.chdir(tmp_path)` isolation fixture,
  both in `test_fsm_evaluators.py`.
- `scripts/tests/test_fsm_schema_fuzz.py`'s `malformed_evaluate_config()`
  `valid_types` list (~line 44-57) — not test-locked, but omitting
  `score_stall` here silently drops it from fuzz coverage; low priority.

## Acceptance Criteria

- [x] A per-run score-history artifact is written under `${context.run_dir}/`
      (never bare `.loops/tmp/`).
- [x] A `score_stall` evaluator (type or fragment) exists with a `max_stall`
      knob and an epsilon threshold, unit-tested in `scripts/tests/`.
- [x] `oracles/generator-evaluator` routes to `done` when scores plateau for
      `max_stall` rounds, verified by a test that feeds a flat score history.
- [x] `ll-loop validate oracles/generator-evaluator` stays green.
- [x] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — quality-of-life fix for harness resource usage; wastes
  iteration budget on real runs but is not a correctness bug.
- **Effort**: Small-Medium — new evaluator type/fragment plus a small
  per-round persistence write path, mirroring the existing `diff_stall_gate`
  pattern already in `common.yaml`.
- **Risk**: Low — additive evaluator; `diff_stall` is retained as a
  secondary/OR condition, so existing stall detection isn't removed.
- **Breaking Change**: No.

## Notes

Source: `html-website-generator-run-review-20260701.md` (finding 3, "Diminishing
returns after iter-1" / "Add an early-stop on stagnation").

## Resolution

Implemented the `score_stall` evaluator as a non-LLM external discriminator
(satisfies MR-1) plus per-run score-history persistence, following Option B
(scoped to `generator-evaluator.yaml`; the shared `ll_rubric_score` fragment
and its other consumers were left untouched).

- **New evaluator** `evaluate_score_stall()` in `fsm/evaluators.py`: reads a
  per-round `.score_history` file and tracks the running best-so-far, returning
  `no` once the aggregate score has not improved by more than `epsilon`
  (default 0.5) for `max_stall` consecutive rounds. Stateless across calls —
  the history file *is* the persisted state — so a flat score history
  deterministically produces the plateau verdict. Added to
  `_EXIT_CODE_AWARE_EVALUATORS`.
- **Schema**: `score_stall` added to the `EvaluateConfig.type` `Literal` and the
  `fsm-loop-schema.json` enum (verified in sync); new `history_file` and
  `epsilon` fields with `to_dict`/`from_dict` round-trip.
- **Validation**: `score_stall` added to `EVALUATOR_REQUIRED_FIELDS` (so it
  derives into `NON_LLM_EVALUATOR_TYPES` and satisfies MR-1), a
  `max_stall >= 1` / `epsilon >= 0` validation block, and the MR-1 error prose.
- **Fragment**: new `score_stall_gate` in `lib/common.yaml` (mirrors
  `diff_stall_gate`, default `max_stall: 2`).
- **Wiring** in `oracles/generator-evaluator.yaml`: `score` gains a scoped
  numeric-score override (emits `SCORE: <0-10>`, captured); a new `record_score`
  shell state appends the parsed score to `${context.run_dir}/.score_history`
  (per-run isolation, MR-3); `check_stall` now routes through `score_stall`
  (primary), falling through to a new `check_diff_stall` state (`diff_stall`
  retained as a secondary/OR condition per Scope Boundaries). Inherited
  unchanged by `generator-evaluator-cli.yaml` via `from:`.
- **Tests**: `TestScoreStallEvaluator` (11 cases incl. flat-history plateau),
  `TestScoreStallGateFragment`, an MR-1 pass test, and two structural asserts on
  `check_stall`/`record_score`; fuzz `valid_types` and `ll-loop show`
  display-label updated.
- **Docs**: MR-1 evaluator lists, evaluator-type tables, fragment catalogs, the
  `#### score_stall` reference subsection, and the `generator-evaluator` /
  `-cli` state diagrams. (`.claude/CLAUDE.md`'s MR-1 row is the one remaining
  doc site — it is a protected path in this session and must be updated
  manually to add `score_stall` to the MR-1 parenthetical.)

Verified: `ll-loop validate oracles/generator-evaluator` green; FSM-core test
modules (evaluators/fragments/validation/schema/schema-fuzz) 960 passed;
`test_builtin_loops` green (the 5 failing `TestAutodevLoop`/`TestAutoRefine…`
cases are pre-existing and fail without this change too); `ruff check` clean.

## Status

**Done** | Created: 2026-07-01 | Completed: 2026-07-01 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- Wide enumeration across 6 core sites (`schema.py`, `fsm-loop-schema.json`,
  `evaluators.py`, `validation.py`, `lib/common.yaml`,
  `generator-evaluator.yaml`) plus 10 documentation files and 4 test files —
  each site is a Local/mechanical mirror of the existing `diff_stall` pattern,
  but the sheer site count leaves room for a missed sync point (e.g. the
  `schema.py` Literal and `fsm-loop-schema.json` enum drifting apart).
- 7 dependent loops (6 sub-loop consumers of `oracles/generator-evaluator`
  plus `generator-evaluator-cli.yaml`) inherit `check_stall`/`score` changes
  transitively with no direct edits — broad by count, though Option B
  deliberately keeps `openscad-model-generator.yaml` and the shared
  `ll_rubric_score` fragment untouched to bound the surface.
- The exact epsilon threshold and whether plateau is judged on the aggregate
  score or all four criteria individually are still left to implementation
  judgment — pick sane defaults (e.g., epsilon relative to the 0-10
  `pass_threshold` scale) rather than blocking on further design work.

## Session Log
- `/ll:ready-issue` - 2026-07-01T22:21:46 - `ae864ae3-043c-452d-8dc7-c8c4b8c318fa.jsonl`
- `/ll:confidence-check` - 2026-07-01T17:17:55 - `e551695b-56a7-46b9-8d96-49315fc6c7a0.jsonl`
- `/ll:wire-issue` - 2026-07-01T22:12:36 - `2f36e09f-d631-49a6-a80e-08af006dd961.jsonl`
- `/ll:decide-issue` - 2026-07-01T22:00:53 - `e2dc9663-430b-41e8-84a4-c35f45fe09bb.jsonl`
- `/ll:format-issue` - 2026-07-01T20:26:06 - `6a483798-afef-41ef-99f1-d9709fa879a5.jsonl`
- `/ll:confidence-check` - 2026-07-01T20:34:06 - `39568524-616e-4270-8660-34ace681fd21.jsonl`
