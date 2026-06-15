---
id: ENH-2154
type: ENH
priority: P3
status: done
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T23:28:19Z'
completed_at: '2026-06-15T00:02:56Z'
testable: true
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

- [x] `scripts/little_loops/loops/lib/rubric-router.yaml` exists and defines these named fragments:
  - `rubric_score` — `action_type: prompt` scaffold; caller must supply `action:` and `capture:`; includes a standard instruction to emit `AGGREGATE: <int>` on the final line
  - `rubric_parse_scores` — `action_type: shell` that reads `${captured.scores.output}`, extracts `AGGREGATE` integer, computes tier (`high` if ≥ `${context.threshold_high}`, `medium` if ≥ `${context.threshold_medium}`, else `low`), writes `rubric-aggregate.txt` and `rubric-tier.txt` to `${context.run_dir}/`, prints `aggregate=<N> tier=<tier>`
  - `rubric_route_high` — `action_type: shell` + `evaluate: exit_code`; exits 0 if `rubric-tier.txt` == `"high"`, else 1
  - `rubric_route_medium` — same pattern; exits 0 if `rubric-tier.txt` == `"medium"`, else 1
- [x] Fragment context variables (`threshold_high`, `threshold_medium`) have documented defaults (85 and 65) and can be overridden via `context:` in the importing loop
- [x] `ll-loop validate` passes on `lib/rubric-router.yaml` with no errors or warnings (MR-1, MR-3, MR-4) — fragment libs behave identically to `lib/common.yaml` (no MR violations; validate exits early on missing top-level keys, which is expected for fragment-only files)
- [x] At least one built-in loop is updated to import `lib/rubric-router.yaml` and use the fragments — new `loops/rubric-refine.yaml` example loop
- [x] `scripts/tests/test_builtin_loops.py` continues to pass after adding the fragment library (987 tests pass)

## Implementation Steps

1. **Create `scripts/little_loops/loops/lib/rubric-router.yaml`** with `fragments:` block defining the four fragments above. Use `${context.run_dir}/rubric-aggregate.txt` and `${context.run_dir}/rubric-tier.txt` for run-isolated state (MR-3 compliant).

2. **Define default context values** as comments in the fragment file (since fragments don't own a `context:` block — that lives in the importing loop). Document the expected variables and their defaults in the fragment file's header comment.

3. **Write `rubric_parse_scores` shell action** using the same Python heredoc pattern as `loop-router.yaml`'s `parse_project_score` state: regex-extract `AGGREGATE:\s*(\d+)`, compare against threshold variables, write tier to `${context.run_dir}/rubric-tier.txt`.

4. **Write `rubric_route_high` and `rubric_route_medium` shell actions** following the `route_branch_*` pattern from `loop-router.yaml`: single `test "$(cat ${context.run_dir}/rubric-tier.txt)" = "high"` with `evaluate: exit_code`.

5. **Validate the fragment file** with `ll-loop validate lib/rubric-router.yaml` — fix any MR-1/MR-3/MR-4 warnings.

6. **Create example loop** `scripts/little_loops/loops/rubric-refine.yaml` that imports `lib/rubric-router.yaml`, accepts `context.subject` and `context.rubric_dimensions`, and provides placeholder `light_repair`/`deep_repair` prompt states. This serves as both a runnable example and a regression test for the fragments.

7. **Update `scripts/little_loops/loops/README.md`** to list the new `lib/rubric-router.yaml` library and its fragments alongside `lib/common.yaml`.

8. **Verify `test_builtin_loops.py` passes** after the new file is added, and add `TestRubricRouterLib` to `test_fsm_fragments.py` (see Tests in Integration Map).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact `rubric_parse_scores` shell script pattern** (modeled on `loop-router.yaml:parse_project_score`):

```yaml
rubric_parse_scores:
  action_type: shell
  action: |
    python3 << 'PYEOF'
    import re, sys
    output = """${captured.scores.output}"""
    agg_m = re.search(r'AGGREGATE:\s*(\d+)', output)
    if not agg_m:
        print("aggregate=0 tier=low")
        sys.exit(0)
    agg = int(agg_m.group(1))
    thresh_high = int("${context.threshold_high}" or "85")
    thresh_med  = int("${context.threshold_medium}" or "65")
    tier = "high" if agg >= thresh_high else ("medium" if agg >= thresh_med else "low")
    with open('${context.run_dir}/rubric-aggregate.txt', 'w') as f:
        f.write(str(agg))
    with open('${context.run_dir}/rubric-tier.txt', 'w') as f:
        f.write(tier)
    print(f"aggregate={agg} tier={tier}")
    PYEOF
```

FSM interpolation resolves `${context.*}` and `${captured.*}` references **before** the string is passed to the shell, so they become literal values inside the Python heredoc.

**`$${...}` escaping rule** — bare shell `$VAR` references (not FSM context vars) inside `action:` blocks must use `$${VAR}` to avoid the FSM interpolation engine raising "expected namespace.path". Python f-string `${...}` in heredocs is safe because single-quoted `'PYEOF'` suppresses shell expansion; FSM interpolation still runs first and only FSM namespace patterns match.

**Exit-code routing state pattern** (from `loop-router.yaml:route_branch_*`):

```yaml
rubric_route_high:
  action_type: shell
  action: |
    python3 << 'PYEOF'
    import sys
    tier = open('${context.run_dir}/rubric-tier.txt').read().strip()
    sys.exit(0 if tier == 'high' else 1)
    PYEOF
  evaluate:
    type: exit_code
  on_yes: done        # caller supplies; fragment leaves as placeholder
  on_no: rubric_route_medium
```

**`is_runnable_loop()` gate** (from `fsm/validation.py`) — lib fragment files have no `name:`, `initial:`, or `states:` keys and return `False`, so `test_builtin_loops.py`'s universal `TestBuiltinLoopFiles` fixture automatically excludes them. `rubric-refine.yaml` (a real loop) IS included and must pass `validate_fsm` with no ERROR-severity items.

**Fragment library file structure** (from `lib/common.yaml` conventions):
- Single top-level key: `fragments:` — no loop-level keys (`name:`, `initial:`, `states:`)
- Each fragment entry: `description:` (stripped before merge; doc-only), then state keys
- `description:` and `parameters:` are stripped before `_deep_merge()` into the consuming state
- State-level keys **win** over fragment keys — callers can override any field by supplying it on the referencing state

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
- `scripts/little_loops/loops/lib/harness.yaml` — `ll_rubric_score` fragment; closest existing rubric-scoring fragment (prompt scaffold with `parameters:` block); model for `rubric_score` fragment design

### Tests
- `scripts/tests/test_builtin_loops.py` — verify `rubric-refine.yaml` passes the universal `TestBuiltinLoopFiles` fixture (schema + validate_fsm + description field); `lib/rubric-router.yaml` is **excluded** from this fixture by `is_runnable_loop()` in `fsm/validation.py` because it has no `name:`, `initial:`, or `states:` keys
- `scripts/tests/test_fsm_fragments.py` — add `TestRubricRouterLib` class here (modeled on `TestCommonLib`, `TestHarnessLib`, etc.); should assert all four fragment names are present under `fragments:`, and optionally test import resolution via `load_and_validate` on `rubric-refine.yaml`

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
- `/ll:ready-issue` - 2026-06-14T23:53:47 - `c26723fd-66c3-4132-972c-1251d85cddd9.jsonl`
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `8062b5b2-6c26-4fa7-85f7-85ad9dfdf6e8.jsonl`
- `/ll:refine-issue` - 2026-06-14T23:47:29 - `ad1f4e38-2510-4a56-a311-0f8270703aaf.jsonl`
- `/ll:confidence-check` - 2026-06-14T23:45:00Z - `73be1d05-a464-4e7e-8a56-66632e88305b.jsonl`
- `/ll:format-issue` - 2026-06-14T23:32:01 - `6e7f0496-f1ae-4122-93b0-98f03ca9b145.jsonl`
- `/ll:capture-issue` - 2026-06-14T23:28:19Z - `73467968-0364-48c2-83d2-1f061bc4e059.jsonl`
