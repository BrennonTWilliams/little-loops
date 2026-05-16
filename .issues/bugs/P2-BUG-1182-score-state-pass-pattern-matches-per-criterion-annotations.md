---
id: 1182
type: BUG
priority: P2
captured_at: "2026-04-18T21:39:42Z"
completed_at: "2026-04-18T23:04:42Z"
discovered_date: "2026-04-18"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-1182: Score-state `PASS` pattern matches per-criterion annotations in loop evaluators

## Summary

Built-in FSM loop evaluators use `output_contains` with `pattern: "PASS"` to route between `on_yes` (done) and `on_no` (iterate). The scoring prompt also emits per-criterion annotations in the output body (e.g. `design_quality: 8/10 — PASS`), so the substring match fires on the annotation even when the overall verdict is `ITERATE`. The loop exits prematurely with failing criteria.

## Current Behavior

The `score` state routes to `done` whenever any per-criterion annotation contains the literal token `PASS`, even when the final verdict line is `ITERATE`. Loops exit early with failing criteria, producing inadequate artifacts.

## Expected Behavior

The `score` state should only route to `done` when the overall scoring verdict is a pass. Per-criterion annotations containing `PASS` should not trigger the `output_contains` evaluator's `on_yes` branch.

## Impact

- **Priority**: P2 — Affects output quality of three built-in generator loops; silent early termination produces user-visible quality regressions but does not break the harness.
- **Effort**: Small — Token substitution across three YAML files plus one regression guard test and three doc diagram label updates.
- **Risk**: Low — Evaluator routing semantics are preserved; only the disambiguation token changes. Consistent with existing compound-token conventions (`CONVERGED`, `PHASE1_PASS`, `BOTTLENECK_BLOAT`).
- **Breaking Change**: No

## Affected Files

- `scripts/little_loops/loops/html-website-generator.yaml` (lines 84–128)
- `scripts/little_loops/loops/svg-textgrad.yaml` (lines 98–143)
- `scripts/little_loops/loops/svg-image-generator.yaml` (lines 130–151 — confirmed same shape: `output exactly: PASS` at line 144, `pattern: "PASS"` at line 148)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-website-generator.yaml` — update `output exactly: PASS` (line 122), `pattern: "PASS"` (line 126), and comment on line 87 (`Uses output_contains: "PASS" for routing`)
- `scripts/little_loops/loops/svg-textgrad.yaml` — update `output exactly: PASS` (line 136) and `pattern: "PASS"` (line 140)
- `scripts/little_loops/loops/svg-image-generator.yaml` — update `output exactly: PASS` (line 144) and `pattern: "PASS"` (line 148)
- `scripts/tests/test_builtin_loops.py` — add regression guard test in existing `TestBuiltinLoopFiles` class (follows established iteration pattern)
- `docs/guides/LOOPS_GUIDE.md` — update `PASS → done` routing labels in FSM diagrams (lines 693, 748, 805 — one per affected loop) to `ALL_PASS → done` [wiring pass finding]

### Evaluator Implementation (background — no changes required)
- `scripts/little_loops/fsm/evaluators.py:269-305` — `evaluate_output_contains()` uses plain substring match (`pattern in source`); this is intentional semantics, so the fix belongs in the YAML tokens, not the evaluator.

### Precedent (Similar Compound-Token Patterns Already in Codebase)
- `scripts/little_loops/loops/apo-feedback-refinement.yaml:40-54` — uses `CONVERGED` / `NEEDS_REFINE`
- `scripts/little_loops/loops/apo-contrastive.yaml:53-64`, `apo-textgrad.yaml:40,48`, `apo-beam.yaml:47-56`, `apo-opro.yaml:85` — all use `pattern: "CONVERGED"`
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml:56-86` — uses `BOTTLENECK_BLOAT`, `BOTTLENECK_SIZE`, `BOTTLENECK_PRIORITY`
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml:51,56-63` — uses `PHASE1_PASS` / `PHASE1_FAIL`
- `scripts/little_loops/loops/evaluation-quality.yaml:81-121` — uses compound form `PRIMARY_CONCERN: NONE|ISSUES|CODE|BACKLOG`
- `scripts/little_loops/loops/svg-textgrad.yaml:191,212` — already uses `CONVERGED` for the outer refinement loop (consistent existing convention in the same file)

### Callers / Dependents
- None — the `pattern` tokens are internal to each loop file. No external code reads these string literals.

### Tests (Existing Patterns to Follow)
- `scripts/tests/test_builtin_loops.py:18-27` — `TestBuiltinLoopFiles.builtin_loops` fixture collects all `*.yaml` via `BUILTIN_LOOPS_DIR.glob("*.yaml")` — use this fixture for the new regression guard.
- `scripts/tests/test_builtin_loops.py:29-44` — established iterate-all-loops test pattern (loops the fixture inside the test body).
- `scripts/tests/test_fsm_evaluators.py` — unit tests for `evaluate_output_contains`; no changes needed there (behavior is correct; the bug is in caller tokens).

### Documentation (Review — No Changes Expected)
- `docs/ARCHITECTURE.md` — FSM evaluator semantics section (already describes substring matching correctly).
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; verify it recommends compound/unambiguous tokens.

_Wiring pass added by `/ll:wire-issue`:_ **NOTE: The above "No Changes Expected" is incorrect for LOOPS_GUIDE.md — changes ARE required:**
- `docs/guides/LOOPS_GUIDE.md:693` — FSM diagram for `html-website-generator` shows `├─ PASS    → done`; update routing label to `ALL_PASS → done` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:748` — FSM diagram for `svg-image-generator` shows `├─ PASS    → done`; update routing label to `ALL_PASS → done` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:805` — FSM diagram for `svg-textgrad` shows `├─ PASS    → done`; update routing label to `ALL_PASS → done` [Agent 2 finding]

## Root Cause

The `score` state's `evaluate.pattern` is the substring `"PASS"`. The LLM scoring prompt is free-form and includes `PASS` inside per-criterion annotations, so `output_contains` matches the annotation rather than the final verdict line.

File anchors:
- `scripts/little_loops/loops/html-website-generator.yaml:122` — `output exactly: PASS`
- `scripts/little_loops/loops/html-website-generator.yaml:126` — `pattern: "PASS"`
- `scripts/little_loops/loops/svg-textgrad.yaml:136` — `output exactly: PASS`
- `scripts/little_loops/loops/svg-textgrad.yaml:140` — `pattern: "PASS"`

## Reproduction

1. Run `ll-loop run html-website-generator` with a description.
2. Observe a score iteration where at least one criterion annotation contains `PASS` but the final verdict is `ITERATE`.
3. The loop routes to `done` instead of continuing to `generate`.

## Fix

Straight string substitution to a compound token (consistent with existing conventions like `CONVERGED`, `BOTTLENECK_BLOAT`, `PHASE1_PASS` in other built-in loops):

**html-website-generator.yaml**
- Line 122: `output exactly: PASS` → `output exactly: ALL_PASS`
- Line 126: `pattern: "PASS"` → `pattern: "ALL_PASS"`
- Line 87 comment: update `"PASS"` → `"ALL_PASS"`

**svg-textgrad.yaml**
- Line 136: `output exactly: PASS` → `output exactly: ALL_PASS`
- Line 140: `pattern: "PASS"` → `pattern: "ALL_PASS"`

**svg-image-generator.yaml** (verified: same shape as html-website-generator)
- Line 109 comment: update `"PASS"` → `"ALL_PASS"` (same comment pattern as html-website-generator.yaml:87 — missed in initial fix spec) [wiring pass finding]
- Line 144: `output exactly: PASS` → `output exactly: ALL_PASS`
- Line 148: `pattern: "PASS"` → `pattern: "ALL_PASS"`

No logic changes — evaluator routing semantics are preserved, only the token is disambiguated.

## Regression Guard

Add a test to the existing `TestBuiltinLoopFiles` class in `scripts/tests/test_builtin_loops.py`, reusing the established `builtin_loops` fixture (line 21-27) that globs `BUILTIN_LOOPS_DIR.glob("*.yaml")`. The test asserts that no `output_contains` evaluator in any built-in loop uses the bare `"PASS"` token. Concrete shape matching existing tests in that class:

```python
def test_no_bare_pass_token_in_output_contains(self, builtin_loops: list[Path]) -> None:
    """No built-in loop uses bare 'PASS' as output_contains pattern.

    Bare 'PASS' collides with per-criterion scoring annotations
    (e.g. 'design_quality: 8/10 — PASS') in free-form LLM output.
    Use compound tokens like 'ALL_PASS' or 'CONVERGED' instead.
    """
    for loop_file in builtin_loops:
        with open(loop_file) as f:
            data = yaml.safe_load(f)
        for state_name, state in (data.get("states") or {}).items():
            evaluate = state.get("evaluate") or {}
            if evaluate.get("type") == "output_contains":
                pattern = evaluate.get("pattern")
                assert pattern != "PASS", (
                    f"{loop_file.name}/{state_name} uses ambiguous 'PASS' token — "
                    "scoring output annotations will match substring. "
                    "Use a compound token (e.g. 'ALL_PASS')."
                )
```

## Acceptance Criteria

- [ ] All three built-in loops use a compound token (e.g. `ALL_PASS`) instead of bare `PASS`.
- [ ] `evaluate.pattern` and the scoring prompt's final output instruction are in sync in every affected file.
- [ ] Structural guard test in `scripts/tests/test_builtin_loops.py` asserts the pattern is never `"PASS"` for `score`-state evaluators.
- [ ] Existing loop tests still pass.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM evaluator semantics (`output_contains` routing). |
| `.claude/CLAUDE.md` | Built-in loops live under `scripts/little_loops/loops/`. |

## Labels

`bug`, `fsm-loops`, `captured`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/guides/LOOPS_GUIDE.md:693` — change `PASS → done` routing label to `ALL_PASS → done` in html-website-generator FSM diagram
2. Update `docs/guides/LOOPS_GUIDE.md:748` — change `PASS → done` routing label to `ALL_PASS → done` in svg-image-generator FSM diagram
3. Update `docs/guides/LOOPS_GUIDE.md:805` — change `PASS → done` routing label to `ALL_PASS → done` in svg-textgrad FSM diagram
4. Update `scripts/little_loops/loops/svg-image-generator.yaml:109` — update comment from `"PASS"` to `"ALL_PASS"` (same pattern as html-website-generator.yaml:87)

## Resolution

Replaced the ambiguous `PASS` routing token with compound `ALL_PASS` in the three
scoring-state FSMs whose prompts also emit per-criterion annotations. The evaluator
(`evaluate_output_contains`) intentionally uses plain substring matching, so the
disambiguation belongs at the caller. This aligns these loops with existing
compound-token conventions elsewhere in the built-in set (`CONVERGED`,
`PHASE1_PASS`, `BOTTLENECK_BLOAT`).

**Files changed:**
- `scripts/little_loops/loops/html-website-generator.yaml` — `PASS` → `ALL_PASS`
  (pattern, prompt output token, routing comment).
- `scripts/little_loops/loops/svg-textgrad.yaml` — `PASS` → `ALL_PASS`
  (pattern, prompt output token).
- `scripts/little_loops/loops/svg-image-generator.yaml` — `PASS` → `ALL_PASS`
  (pattern, prompt output token, routing comment).
- `docs/guides/LOOPS_GUIDE.md` — updated three FSM diagram labels from
  `PASS → done` to `ALL_PASS → done`.
- `scripts/tests/test_builtin_loops.py` — added
  `test_no_bare_pass_token_in_output_contains` structural guard on
  `TestBuiltinLoopFiles`, asserting no built-in loop uses bare `"PASS"` as an
  `output_contains` pattern.

**Verification:** Red phase confirmed the guard failed before the token swap;
after the swap, the full `scripts/tests/` suite passes (4999 passed, 5 skipped).

## Status

**Closed** | Created: 2026-04-18 | Resolved: 2026-04-18 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-04-18T23:04:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ebf18b86-90e8-419c-85c4-636d7515ec7b.jsonl`
- `/ll:ready-issue` - 2026-04-18T22:59:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d69ef660-a2a7-485b-9f21-398f4f601b30.jsonl`
- `/ll:confidence-check` - 2026-04-18T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfb3ce3d-2be5-4a39-a8eb-5876065ed811.jsonl`
- `/ll:wire-issue` - 2026-04-18T22:54:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f6f93f8-12b3-48b0-b846-6ce004eba5dc.jsonl`
- `/ll:refine-issue` - 2026-04-18T22:48:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02cd84b4-bd62-4f1c-b16d-d7128c5c8cab.jsonl`
- `/ll:capture-issue` - 2026-04-18T21:39:42Z - user-provided direct mode
