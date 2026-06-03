---
id: ENH-1900
title: Harden svg-textgrad loop (best.svg, on_error, threshold)
type: enhancement
priority: P3
status: done
captured_at: '2026-06-03T19:12:59Z'
completed_at: '2026-06-03T20:29:57Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
labels:
- loops
- svg-textgrad
confidence_score: 100
outcome_confidence: 86
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# ENH-1900: Harden `svg-textgrad` loop (best.svg, on_error, threshold)

## Summary

Three content fixes to the bundled `scripts/little_loops/loops/svg-textgrad.yaml`
surfaced by the 2026-06-03 two-run audit: missing best-output artifacts on
first-pass success, a missing error route on the `generate` state, and a quality
gate that is both mislabeled and too loose to catch a measured 9.3% quality
regression between runs.

## Current Behavior

1. **Missing best-output artifacts.** `track_best` (line ~191) copies
   `image.svg` → `best.svg`, but only fires via `on_no`/`on_error` (lines
   ~188–189). When `verify_score` passes on the first iteration, the FSM jumps
   straight to `done` (line ~298) and `best.svg`/`best-brief.md` are never
   created — even though the `done` prompt (line ~312) claims they are "present
   if at least one score was recorded." The audit confirmed both files missing
   in both runs.
2. **`generate` has no `on_error`.** The `generate` prompt state (lines ~61–85)
   has `next: screenshot` and no error route, while neighboring states route to
   `diagnose`/`check_capture_fails`. A prompt failure (API error, token limit)
   aborts the whole loop instead of producing a structured failure report.
3. **Quality gate mislabeled and loose.** `pass_threshold: 6` (line ~18) is
   commented `# minimum score per criterion (1-10) to pass`, but line ~172 uses
   it as a weighted-average gate `(2×VC + 2×OG + CR + SC) / 6 ≥ threshold`
   (36/60). The comment is wrong, and the weighted formula masks weak individual
   criteria: Run B passed with scalability 5/10 (below the nominal threshold)
   and a 39/60 weighted score (65%) vs Run A's 43/60 (71.7%).

## Expected Behavior

1. `best.svg` and `best-brief.md` always exist when the loop reaches `done`
   having recorded at least one score (including first-pass success).
2. A `generate` prompt failure routes to `diagnose` for a structured failure
   report rather than aborting the loop.
3. The quality gate is correctly documented and tight enough that a
   per-criterion regression (e.g. scalability 5/10) forces a gradient iteration
   instead of passing.

## Motivation

The loop's gradient-optimization path is a fallback that, in practice, never
fired in either audited run because the first generation always cleared the
loose threshold. Tightening the gate exercises the textgrad machinery when
quality actually regresses, and the artifact/error-route fixes close
correctness gaps a downstream consumer would hit.

## Proposed Solution

**(a) New `seal_artifacts` shell state before `done`** — `done` uses
`action_type: prompt`; shell commands cannot run inside a prompt action. The
correct approach inserts a dedicated shell state that guarantees best-artifact
copies exist, then routes to `done`. Two existing `on_yes: done` routes must be
redirected to `seal_artifacts`:

```yaml
# New state — insert between track_best/route_convergence and done:
  seal_artifacts:
    # Ensures best.svg and best-brief.md always exist when done is reached,
    # including first-pass success where track_best is bypassed.
    action_type: shell
    action: |
      DIR="${captured.run_dir.output}"
      [ -f "$DIR/best.svg" ] || cp "$DIR/image.svg" "$DIR/best.svg"
      [ -f "$DIR/best-brief.md" ] || cp "$DIR/brief.md" "$DIR/best-brief.md"
    next: done
```

Routing changes (two places):
- `verify_score.on_yes: done` → `verify_score.on_yes: seal_artifacts` (line 188)
- `route_convergence.on_yes: done` → `route_convergence.on_yes: seal_artifacts` (line 254)

**(b) `generate` error route** — add `on_error: diagnose` to the `generate` state
(line 86, after `next: screenshot`):

```yaml
generate:
  action_type: prompt
  next: screenshot
  on_error: diagnose
```

This matches the existing convention used by `score` (line 157) and mirrors the
`on_error: diagnose` pattern in `general-task.yaml` (11 states), `rn-refine.yaml`
(4 states), and `refine-to-ready-issue.yaml` (10 states).

**(c) Tighten + relabel the gate** — fix the misleading comment, raise
`pass_threshold` to 7 (≈70% / 42/60), and add a per-criterion floor in the
`verify_score` shell action:

```yaml
context:
  pass_threshold: 7          # weighted-average gate: (2VC+2OG+CR+SC)/6 >= threshold
  min_per_criterion: 6       # each criterion must be >= this
```

In `verify_score` (lines 159–190), insert the floor check between score extraction
and the weighted-average check:

```bash
# after extracting VC OG CR SC (lines 174–177), before THRESH= (line 178):
MIN="${context.min_per_criterion}"
if [ "$VC" -lt "$MIN" ] || [ "$OG" -lt "$MIN" ] || \
   [ "$CR" -lt "$MIN" ] || [ "$SC" -lt "$MIN" ]; then
  echo "SHELL_ITERATE"; exit 0
fi
```

Also update the weighted-average comment at line 173 from
`# --- External weighted average: (2×VC + 2×OG + CR + SC) / 6 >= pass_threshold ---`
to accurately describe the threshold: with `pass_threshold: 7`, the gate is
`WEIGHTED >= 42` (not `/6`).

Per the audit, `pass_threshold: 7` + `min_per_criterion: 6` would have caught
Run B on both the weighted average (39 < 42) and the scalability floor (5 < 6).

## Scope Boundaries

- In scope: edits to `svg-textgrad.yaml` only.
- Out of scope: the runtime `model: "unknown"` attribution gap (see BUG-1897)
  and a `required_inputs` guard (see ENH-1898) — both are framework-level and
  tracked separately.

## Backwards Compatibility

Loop-local changes only; no schema or runtime impact. Tighter thresholds change
pass/fail behavior for borderline generations by design.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-textgrad.yaml` — single file; all three fixes are here

### States to Change

| State | Lines | Change |
|---|---|---|
| `context` block | 17–20 | Fix comment on `pass_threshold`; raise to 7; add `min_per_criterion: 6` |
| `generate` | 62–86 | Add `on_error: diagnose` after `next: screenshot` (line 86) |
| `verify_score` | 159–190 | Insert per-criterion floor check (lines 174–177 → 178); update arithmetic comment |
| `verify_score` routing | 188 | Change `on_yes: done` → `on_yes: seal_artifacts` |
| `route_convergence` routing | 254 | Change `on_yes: done` → `on_yes: seal_artifacts` |
| NEW: `seal_artifacts` | insert before `done` (line 299) | New shell state: copies `image.svg`→`best.svg` and `brief.md`→`best-brief.md` if absent |
| `done` | 299–317 | No content changes; `seal_artifacts.next: done` ensures it is still reached |

### Dependent Callers — No Runtime or Schema Impact
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_state()` and `_route()`: these handle `on_error` and `next:` generically; no changes needed
- `scripts/little_loops/fsm/validation.py` — `ll-loop validate` enforces MR-1 (non-LLM evaluator pairing); the new `seal_artifacts` state uses `next:` (unconditional) so no evaluator is required and MR-1 does not apply

### Tests

- `scripts/tests/test_builtin_loops.py` — covers built-in loop schema validation; run after editing to confirm `seal_artifacts` is reachable and `on_error` on `generate` is valid

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must update):**
- `TestSvgTextgradLoop.test_verify_score_routes_to_done_on_yes` (line 3778) — asserts `on_yes == "done"`; rename and change assertion to `== "seal_artifacts"`
- `TestSvgTextgradLoop.test_route_convergence_on_yes_routes_to_done` (line 3735) — asserts `on_yes == "done"`; rename and change assertion to `== "seal_artifacts"`

**Existing test to update (no break, coverage gap):**
- `TestSvgTextgradLoop.test_required_states_exist` (line 3564) — add `"seal_artifacts"` to the `required` set

**New tests to write in `TestSvgTextgradLoop`:**
- `test_seal_artifacts_state_exists` — assert `"seal_artifacts"` in `data["states"]`
- `test_seal_artifacts_is_shell` — assert `action_type == "shell"` (pattern: `test_track_best_is_shell`)
- `test_seal_artifacts_routes_to_done` — assert `next == "done"` (unconditional)
- `test_generate_on_error_routes_to_diagnose` — assert `generate.on_error == "diagnose"`
- `test_context_pass_threshold_is_7` — assert `context["pass_threshold"] == 7`
- `test_context_has_min_per_criterion` — assert `"min_per_criterion"` in `context`
- `test_verify_score_action_uses_min_per_criterion` — assert `"min_per_criterion"` in `verify_score.action`
- `test_seal_artifacts_action_copies_best_svg` — assert `"best.svg"` and `"best-brief.md"` in `seal_artifacts.action`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — FSM flow diagram (§ svg-textgrad, ~line 1364) shows `→ done` for both `verify_score.on_yes` and `route_convergence.on_yes`; must update to `→ seal_artifacts → done`. Context variable table (~line 1353) lists `pass_threshold` default as `6`; must update default to `7`, fix gate description, and add `min_per_criterion` row.

### Validation Command
```bash
ll-loop validate svg-textgrad
```

## Implementation Steps

All edits are in `scripts/little_loops/loops/svg-textgrad.yaml`.

1. **Fix `context` block (lines 17–20)**: Change `pass_threshold: 6` → `7`; fix
   the comment to read `# weighted-average gate: (2VC+2OG+CR+SC)/6 >= threshold`;
   add `min_per_criterion: 6  # each criterion must be >= this`.
2. **Add `on_error: diagnose` to `generate` (after line 86)**: Insert `on_error: diagnose`
   on the line after `next: screenshot`.
3. **Update `verify_score` (lines 159–190)**:
   a. After the four score-extraction lines (174–177), insert the per-criterion floor check
      (`MIN="${context.min_per_criterion}"` + the four-way `if [ ... -lt ... ]` block).
   b. Update the arithmetic comment at line 173 to remove the misleading `/6` phrasing.
   c. Change `on_yes: done` (line 188) → `on_yes: seal_artifacts`.
4. **Update `route_convergence` (line 254)**: Change `on_yes: done` → `on_yes: seal_artifacts`.
5. **Insert `seal_artifacts` state** before the `done:` definition (line 299):
   New `action_type: shell` state with `next: done`; copies `image.svg` → `best.svg` and
   `brief.md` → `best-brief.md` using `[ -f ... ] || cp ...` guards.
6. **Validate**: Run `ll-loop validate svg-textgrad`; expect clean output (no MR-1/MR-3 errors).
7. **Smoke test (optional)**: Run `ll-loop run svg-textgrad --input description="test"` with a
   low `pass_threshold` (e.g. 10) to force a regressed generation and confirm `seal_artifacts`
   runs and `best.svg` is present in the run output directory.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_builtin_loops.py` — fix the two breaking tests: rename `test_verify_score_routes_to_done_on_yes` → `test_verify_score_routes_to_seal_artifacts_on_yes` and `test_route_convergence_on_yes_routes_to_done` → `test_route_convergence_on_yes_routes_to_seal_artifacts`, changing `== "done"` to `== "seal_artifacts"` in both; add `"seal_artifacts"` to the `required` set in `test_required_states_exist`; write the 8 new tests listed in the Tests section.
9. Update `docs/guides/LOOPS_GUIDE.md` — update the FSM flow diagram (both `→ done` exits to `→ seal_artifacts → done`), change `pass_threshold` default from `6` to `7` in the context variable table, and add a `min_per_criterion` row describing the per-criterion floor.

## Impact

Closes two correctness gaps (artifacts, error handling) and makes the quality
gate actually discriminating, so the gradient path is exercised when output
quality drops.

- **Priority**: P3 - Quality/correctness hardening of one bundled loop; no
  active consumer is blocked, but the gaps produce silently-missing artifacts
  and an unexercised gradient path.
- **Effort**: Small - Three localized edits to a single YAML file
  (`svg-textgrad.yaml`); no new patterns, reuses existing FSM states and
  context variables.
- **Risk**: Low - Loop-local changes only, no schema or runtime impact. Tighter
  thresholds alter pass/fail for borderline generations by design (see
  Backwards Compatibility).
- **Breaking Change**: No

## Status

- **Created**: 2026-06-03 via `/ll:capture-issue` (from `svg-textgrad` audit)
- **State**: open

## Session Log
- `/ll:ready-issue` - 2026-06-03T20:26:14 - `9a55e072-e0d9-43c1-b103-6e602a2e9e29.jsonl`
- `/ll:confidence-check` - 2026-06-03T20:45:00Z - `31b2bc85-a0b5-413e-94f6-06c7a9e7124c.jsonl`
- `/ll:wire-issue` - 2026-06-03T20:21:46 - `19bd6a32-49de-4e4e-aee4-cfc71bf924f9.jsonl`
- `/ll:refine-issue` - 2026-06-03T20:16:58 - `ab834a21-9998-4af9-89b6-a7bd885c7c3b.jsonl`
- `/ll:format-issue` - 2026-06-03T19:21:26 - `2115b373-786c-489c-aa3d-71ed6687c4c6.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cba1a69-7a53-425f-8c5d-4f1ba61f51bb.jsonl`
