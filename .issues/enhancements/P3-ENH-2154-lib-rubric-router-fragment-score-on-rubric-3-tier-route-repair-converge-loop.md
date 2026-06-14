---
id: ENH-2154
type: ENH
priority: P3
status: open
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T23:28:19Z"
testable: true
---

# ENH-2154: lib/rubric-router Fragment — Score-on-Rubric → 3-Tier Route → Repair Converge Loop

## Summary

Add `scripts/little_loops/loops/lib/rubric-router.yaml` — a reusable fragment library that implements the "score an artifact on a multi-dimension rubric, route to tier-specific repair, re-score until quality passes" converge loop pattern. Callers import the fragment and supply a subject, rubric dimensions, thresholds, and repair actions; the fragment handles the score → parse → tier-route → re-enter cycle.

## Current Behavior

The converge-loop quality-gate pattern (score → repair → re-score until threshold met) is implemented ad-hoc in each loop that needs it. Today's built-in loops each wire their own version from scratch:

- `rn-plan-apo.yaml` defines `score_plans → route_convergence → apply_gradient → run_planner` independently (2-tier: converged / not)
- `lib/score-plan-quality.yaml` provides scoring only — no routing, no re-entry edge
- `loop-router.yaml` implements 1-dimensional threshold dispatch (`score_* → parse_*_score → select_loop`) with no repair cycle

Every loop author who wants score-and-improve behavior must write their own `parse` shell state (regex-extract the score), tier-routing states (`exit_code` evaluators), and re-entry edge from scratch. There is no shared abstraction.

## Motivation

The converge-loop quality-gate pattern (score → repair → re-score until high enough) is reimplemented ad-hoc across several built-in loops today:
- `rn-plan-apo.yaml` has `score_plans → route_convergence → apply_gradient → run_planner` (2-tier: converged / not)
- `lib/score-plan-quality.yaml` is a scoring-only fragment with no routing
- `loop-router.yaml` has `score_* → parse_*_score → select_loop` for confidence-based dispatch (1-dimensional, threshold only)

None of these are reusable as a generic quality gate. Every loop that wants to score-and-improve must wire its own parse shell state, route chain, and re-entry edge. A shared `lib/rubric-router.yaml` fragment eliminates that boilerplate, making the pattern available to project loop authors in ~5 lines.

## Expected Behavior

A project loop imports and uses the fragment:

```yaml
name: my-quality-loop
import:
  - lib/rubric-router.yaml

context:
  subject: "path/to/artifact.md"
  rubric_dimensions: "clarity|completeness|feasibility"
  threshold_high: "85"
  threshold_medium: "65"

states:
  start:
    fragment: rubric_score
    action: |
      Evaluate ${context.subject} on these dimensions: ${context.rubric_dimensions}.
      For each dimension output: DIMENSION: <score 0-100> — <one-sentence rationale>
      Final line: AGGREGATE: <int 0-100>
    capture: scores
    next: rubric_parse

  rubric_parse:
    fragment: rubric_parse_scores
    next: rubric_route_high

  rubric_route_high:
    fragment: rubric_route_high
    on_yes: done
    on_no: rubric_route_medium

  rubric_route_medium:
    fragment: rubric_route_medium
    on_yes: light_repair
    on_no: deep_repair

  light_repair:
    action_type: prompt
    action: |
      Apply light refinements to ${context.subject}.
      Focus on the lowest-scoring dimensions: ${captured.scores.output}
    next: start  # re-score after repair

  deep_repair:
    action_type: prompt
    action: |
      Apply comprehensive repairs to ${context.subject}.
      Scores: ${captured.scores.output}
    next: start  # re-score after repair

  done:
    terminal: true
```

The fragment library provides the scoring scaffold, parse shell state, and tier-routing exit_code states. Callers supply the scoring prompt body, repair actions, and terminal states.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/lib/rubric-router.yaml` exists and defines these named fragments:
  - `rubric_score` — `action_type: prompt` scaffold; caller must supply `action:` and `capture:`; includes a standard instruction to emit `AGGREGATE: <int>` on the final line
  - `rubric_parse_scores` — `action_type: shell` that reads `${captured.scores.output}`, extracts `AGGREGATE` integer, computes tier (`high` if ≥ `${context.threshold_high}`, `medium` if ≥ `${context.threshold_medium}`, else `low`), writes `rubric-aggregate.txt` and `rubric-tier.txt` to `${context.run_dir}/`, prints `aggregate=<N> tier=<tier>`
  - `rubric_route_high` — `action_type: shell` + `evaluate: exit_code`; exits 0 if `rubric-tier.txt` == `"high"`, else 1
  - `rubric_route_medium` — same pattern; exits 0 if `rubric-tier.txt` == `"medium"`, else 1
- [ ] Fragment context variables (`threshold_high`, `threshold_medium`) have documented defaults (85 and 65) and can be overridden via `context:` in the importing loop
- [ ] `ll-loop validate` passes on `lib/rubric-router.yaml` with no errors or warnings (MR-1, MR-3, MR-4)
- [ ] At least one built-in loop is updated to import `lib/rubric-router.yaml` and use the fragments (candidate: a new `loops/rubric-refine.yaml` example loop, or migration of `rn-plan-apo`'s route_convergence chain)
- [ ] `scripts/tests/test_builtin_loops.py` continues to pass after adding the fragment library

## Implementation Steps

1. **Create `scripts/little_loops/loops/lib/rubric-router.yaml`** with `fragments:` block defining the four fragments above. Use `${context.run_dir}/rubric-aggregate.txt` and `${context.run_dir}/rubric-tier.txt` for run-isolated state (MR-3 compliant).

2. **Define default context values** as comments in the fragment file (since fragments don't own a `context:` block — that lives in the importing loop). Document the expected variables and their defaults in the fragment file's header comment.

3. **Write `rubric_parse_scores` shell action** using the same Python heredoc pattern as `loop-router.yaml`'s `parse_project_score` state: regex-extract `AGGREGATE:\s*(\d+)`, compare against threshold variables, write tier to `${context.run_dir}/rubric-tier.txt`.

4. **Write `rubric_route_high` and `rubric_route_medium` shell actions** following the `route_branch_*` pattern from `loop-router.yaml`: single `test "$(cat ${context.run_dir}/rubric-tier.txt)" = "high"` with `evaluate: exit_code`.

5. **Validate the fragment file** with `ll-loop validate lib/rubric-router.yaml` — fix any MR-1/MR-3/MR-4 warnings.

6. **Create example loop** `scripts/little_loops/loops/rubric-refine.yaml` that imports `lib/rubric-router.yaml`, accepts `context.subject` and `context.rubric_dimensions`, and provides placeholder `light_repair`/`deep_repair` prompt states. This serves as both a runnable example and a regression test for the fragments.

7. **Update `scripts/little_loops/loops/README.md`** to list the new `lib/rubric-router.yaml` library and its fragments alongside `lib/common.yaml`.

8. **Verify `test_builtin_loops.py` passes** after the new file is added.

## Scope Boundaries

- **In scope**: `lib/rubric-router.yaml` with the four named fragments (`rubric_score`, `rubric_parse_scores`, `rubric_route_high`, `rubric_route_medium`); one runnable example loop (`loops/rubric-refine.yaml`); `loops/README.md` update to list the new library
- **Out of scope**: Migrating existing loops (`rn-plan-apo.yaml`, `loop-router.yaml`) to import the new fragment — that is a separate follow-on; changes to FSM executor or YAML schema; defining built-in rubric dimensions or domain-specific scoring prompts; adding more than two routing tiers (high / medium / low) in v1

## Impact

- **Priority**: P3 — Reduces loop authoring boilerplate for the common converge-quality-gate pattern; no blocking dependency
- **Effort**: Small — Pure YAML authoring + one example loop; builds on FEAT-937 infrastructure already in place
- **Risk**: Low — Additive fragment library; no changes to FSM executor or schema; existing loops unaffected
- **Breaking Change**: No

## API/Interface

New fragment library: `scripts/little_loops/loops/lib/rubric-router.yaml`

Expected context variables (provided by importing loop):
- `context.subject` — what is being evaluated (path, ID, etc.)
- `context.rubric_dimensions` — pipe-separated dimension names, e.g. `"clarity|completeness|feasibility"`
- `context.threshold_high` — aggregate score ≥ this routes to `on_yes: done` (default: 85)
- `context.threshold_medium` — aggregate score ≥ this routes to light repair (default: 65)
- `context.run_dir` — injected by the runner; used for `rubric-aggregate.txt` / `rubric-tier.txt`

Fragment names exported:
- `rubric_score`
- `rubric_parse_scores`
- `rubric_route_high`
- `rubric_route_medium`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/rubric-router.yaml` (new — fragment library)
- `scripts/little_loops/loops/rubric-refine.yaml` (new — runnable example loop)
- `scripts/little_loops/loops/README.md` (update — add rubric-router to the `lib/` listing alongside `common.yaml`)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py` — existing schema/validation tests; must pass after new files are added

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` — existing fragment library; follow same `fragments:` block authoring conventions
- `scripts/little_loops/loops/loop-router.yaml` — reference for `parse_*_score` regex pattern and `route_branch_*` `exit_code` evaluator pattern

### Tests
- `scripts/tests/test_builtin_loops.py` — verify new YAML files pass existing loop schema and validate checks

### Documentation
- `scripts/little_loops/loops/README.md` — list `lib/rubric-router.yaml` and its four exported fragment names
- `docs/guides/LOOPS_GUIDE.md` — candidate for a new "Quality Gate" pattern section once this ships (separate follow-on)

### Configuration
- N/A — no config changes; fragments consume context variables injected by the importing loop

## Related Key Documentation

- [`scripts/little_loops/loops/lib/common.yaml`](../../scripts/little_loops/loops/lib/common.yaml) — existing fragment library (`shell_exit`, `retry_counter`); rubric-router follows the same authoring conventions
- [`scripts/little_loops/loops/lib/score-plan-quality.yaml`](../../scripts/little_loops/loops/lib/score-plan-quality.yaml) — scoring-only fragment for rn-plan-apo; rubric-router generalizes this pattern
- [`scripts/little_loops/loops/loop-router.yaml`](../../scripts/little_loops/loops/loop-router.yaml) — reference for the `parse_*_score` and `route_branch_*` shell patterns to model the parse/route fragments after
- [`scripts/little_loops/loops/rn-plan-apo.yaml`](../../scripts/little_loops/loops/rn-plan-apo.yaml) — reference for the `route_convergence` pure-evaluator pattern and the overall score → route → repair → re-score loop shape
- [`docs/guides/LOOPS_GUIDE.md`](../../docs/guides/LOOPS_GUIDE.md) — loop authoring guide; may need a "Quality Gate" pattern section added once this ships

## Labels

`enh`, `loops`, `fsm`, `dx`, `fragments`

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-14T23:32:01 - `6e7f0496-f1ae-4122-93b0-98f03ca9b145.jsonl`
- `/ll:capture-issue` - 2026-06-14T23:28:19Z - `73467968-0364-48c2-83d2-1f061bc4e059.jsonl`
