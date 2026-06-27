---
id: BUG-2346
title: Bash ${var:-default} syntax crashes FSM interpolator across 7 builtin-loop
  sites
type: BUG
status: done
priority: P1
captured_at: '2026-06-27T21:16:24Z'
completed_at: '2026-06-27T22:24:55Z'
discovered_date: '2026-06-27'
discovered_by: capture-issue
decision_needed: false
learning_tests_required:
- pytest
labels:
- loops
- fsm
- interpolation
- recursive-refine
relates_to:
- BUG-2347
- ENH-2348
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2346: Bash ${var:-default} syntax crashes FSM interpolator across 7 builtin-loop sites

## Summary

Several shipped builtin loop YAMLs use bash parameter-expansion default syntax
(`${context.X:-default}`) directly inside FSM action strings. The FSM interpolator
(`scripts/little_loops/fsm/interpolation.py`) does **not** support `:-` defaults — it
matches `${...}` up to the first `}`, splits the path on the first `.`, and tries to
resolve a literal path containing `:-`. The resolution fails and raises
`InterpolationError`, crashing the state before the shell ever runs.

The most consequential instance is `recursive-refine.yaml:50`, which is in `parse_input`
— the loop's **first** state. As a result `recursive-refine` crashes on essentially every
invocation with:

```
action_error: Path 'order:-queue' not found in context
```

This is the documented root cause of the `phantom` verdict in the
`sprint-build-and-validate` loop audit (`audit-sprint-build-and-validate-2026-06-27.md`,
Proposal 4): the recursive-refine sub-loop never reaches a user-defined state, so every
sprint issue proceeds at its pre-existing (unrefined) confidence score.

## Motivation

`recursive-refine` is a core builtin sub-loop used by `sprint-build-and-validate` (and is
the engine behind issue refinement). It has been dead-on-arrival since `176fe30`
(`improve(loops): fold issue-refinement deltas into recursive-refine and alias it`,
Jun 13 2026) — roughly two weeks. Any caller that delegates to it silently gets a failed
child whose verdict is then laundered (see BUG-2347), so the failure is invisible.

## Impact

`recursive-refine` has been silently non-functional since commit `176fe30` (Jun 13 2026) —
approximately two weeks before this bug was filed. Because the crash happens at the FSM
interpolation layer before any shell command runs, callers receive no visible error, only a
`failed` loop verdict that BUG-2347 shows gets laundered into a passing score by
`sprint-build-and-validate`.

Every sprint run using `sprint-build-and-validate` has been computing confidence scores
against unrefined issues during this window. Any other loop or skill that delegates to
`recursive-refine` is affected identically.

## Current Behavior

The interpolator splits `${context.order:-queue}` into namespace `context` and path
`order:-queue`, which is not a real context key. Empirically reproduced against the real
engine:

```text
'${context.order:-queue}'        -> CRASH: Path 'order:-queue' not found in context
'${context.order:default=queue}' -> 'queue'         # engine-native default
'$${ORDER:-queue}'               -> '${ORDER:-queue}' # escaped → shell handles default
'${context.order}'               -> 'queue'          # order is always seeded, so :- is redundant
```

The engine already supports defaults via `:default=` (`interpolation.py:232`) and shell
pass-through via `$${...}` escaping; the tests document this trap
(`scripts/tests/test_fsm_interpolation.py:221,364`). The YAML simply does not follow it.

## Affected Sites (all unescaped `${context.X:-...}`)

- `scripts/little_loops/loops/recursive-refine.yaml:50` — `ORDER="${context.order:-queue}"` (in `parse_input`, state 1)
- `scripts/little_loops/loops/recursive-refine.yaml:70` — `COMMIT_EVERY="${context.commit_every:-0}"`
- `scripts/little_loops/loops/recursive-refine.yaml:71` — `NO_RECURSION="${context.no_recursion:-false}"`
- `scripts/little_loops/loops/recursive-refine.yaml:106` — `ORDER="${context.order:-queue}"`
- `scripts/little_loops/loops/recursive-refine.yaml:275` — `NO_RECURSION="${context.no_recursion:-false}"`
- `scripts/little_loops/loops/recursive-refine.yaml:291` — `COMMIT_EVERY="${context.commit_every:-0}"`
- `scripts/little_loops/loops/rl-coding-agent.yaml:26` — `echo "... ${context.target_files:-<all changed files>}"` (note `:80` in the same file uses the correct `${context.target_files}` form — internally inconsistent)

## Root Cause

`scripts/little_loops/fsm/interpolation.py` — `interpolate()` / `replace_var()`. The
`VARIABLE_PATTERN` match is non-greedy to the first `}`, then the path is split on the
first `.` with no awareness of bash `:-` operators. Because each affected context key is
already seeded in the loop's `context:` block, the `:-default` suffix is redundant even
where it is "intended."

### Codebase Research Findings

_Added by `/ll:refine-issue` — precise anchor and data-flow details:_

- **`VARIABLE_PATTERN`** (`interpolation.py:27`) — `re.compile(r"\$\{([^}]+)\}")` captures `context.order:-queue` verbatim
- **`replace_var()` inner closure** — checks `":default=" in full_path` (line ~231) then `.endswith("?")` (line ~233); bash `:-` matches neither branch
- **`_get_nested()`** (`interpolation.py:126–133`) — the actual crash site; tries `ctx["order:-queue"]`, raises `InterpolationError("Path 'order:-queue' not found in context")`
- **`$${...}` escape is irrelevant here** — it pre-substitutes `$${` with a placeholder before the regex runs; the 7 bad sites use single `$` so this mechanism never fires
- **State names for affected lines in `recursive-refine.yaml`**: `parse_input` (50, 70, 71), `dequeue_next` (106), `gate_recursion` (275), `maybe_commit` (291)
- **`rl-coding-agent.yaml` empty-string nuance**: `target_files` is seeded as `""` in the `context:` block. The engine's `:default=` fires only on a missing key (raises `InterpolationError`), not on an empty string. `${context.target_files:default=<all changed files>}` will resolve to `""` when the key is present-but-empty, not to the placeholder. Document this difference in the implementation step for that file.

## Expected Behavior

Each affected state interpolates cleanly and runs. `recursive-refine` reaches
`dequeue_next` and processes its queue.

## Proposed Solution

Replace the 7 unescaped `${context.X:-default}` occurrences with one of the two correct
forms the engine already supports:

- `${context.X:default=default}` — engine-native default, preserves the fallback intent
- `${context.X}` — simpler, valid because each key is always seeded in the loop's `context:` block

No changes to `interpolation.py` are required. For `rl-coding-agent.yaml:26`, match the
already-correct form used at line 80 of the same file. ENH-2348 tracks adding a static lint
so this class of bug cannot re-enter the codebase.

## Implementation Steps

1. Replace each `${context.X:-default}` site with the engine-native default
   `${context.X:default=default}` (clearest, preserves the default intent), or simply
   `${context.X}` where the key is always seeded.
   - For `rl-coding-agent.yaml:26`, match the form already used at line 80.
2. Run `ll-loop validate recursive-refine` and `ll-loop validate rl-coding-agent`.
3. Verify with a real run: `ll-loop run recursive-refine BUG-364,BUG-365` reaches
   `dequeue_next` instead of erroring at `parse_input`.
4. Coordinate with ENH-2348 (a static lint so this class of bug cannot recur).

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact per-site replacement table:_

**`recursive-refine.yaml` (6 sites):**

| Line | State | Bad form | Replacement |
|------|-------|----------|-------------|
| 50 | `parse_input` | `"${context.order:-queue}"` | `"${context.order:default=queue}"` |
| 70 | `parse_input` | `"${context.commit_every:-0}"` | `"${context.commit_every:default=0}"` |
| 71 | `parse_input` | `"${context.no_recursion:-false}"` | `"${context.no_recursion:default=false}"` |
| 106 | `dequeue_next` | `"${context.order:-queue}"` | `"${context.order:default=queue}"` |
| 275 | `gate_recursion` | `"${context.no_recursion:-false}"` | `"${context.no_recursion:default=false}"` |
| 291 | `maybe_commit` | `"${context.commit_every:-0}"` | `"${context.commit_every:default=0}"` |

All three keys (`order`, `commit_every`, `no_recursion`) are always seeded in the `context:` block, so bare `${context.X}` is also valid — but `:default=` is preferred to preserve the author's intent and guard against future seed removal.

**`rl-coding-agent.yaml` (1 site):**

| Line | State | Bad form | Replacement |
|------|-------|----------|-------------|
| 26 | `act` | `"${context.target_files:-<all changed files>}"` | `"${context.target_files:default=<all changed files>}"` |

Note: `target_files` is seeded as `""` (empty string). The `:default=` form fires only when the key is absent (raises `InterpolationError`), not when it is present-but-empty. When `target_files=""`, both the old crash form and the new `:default=` form will produce an empty resolution (no placeholder shown). This is a pre-existing behavioral limitation — the fix's goal is to stop the crash, not to change empty-string display behavior.

**Canonical examples to follow** (`:default=` form, wide usage in codebase): `general-task.yaml` (lines 218, 291, 296, 502), `harness-optimize.yaml`, `loop-router.yaml`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Correct `docs/generalized-fsm-loop.md` — the "Bash default values" row in `## Variable Interpolation` (line 1130) currently endorses `${var:-default}` for optional context variables. This is wrong for FSM `context.*` namespace variables. Update to describe `${context.X:default=val}` as the correct engine-native form and note that `${context.X:-default}` causes `InterpolationError`. [Agent 2 finding]
6. Add `test_bash_default_operator_raises_interpolation_error` to `TestInterpolate` in `test_fsm_interpolation.py` after line 239 — permanently documents that `:-` on FSM namespace variables raises `InterpolationError`. [Agent 3 finding]
7. Add `TestRlCodingAgentLoop.test_act_state_uses_no_bash_default_operator` to `test_builtin_loops.py` after line 4984 — verifies `rl-coding-agent.yaml` `act` state contains no `:-` patterns post-fix. [Agent 3 finding]
8. Add `TestRecursiveRefineInterpolation` class to `test_loops_recursive_refine.py` — loads YAML, extracts `parse_input` action, calls `interpolate()` with seeded context; catches `InterpolationError` if `:-` syntax re-enters the YAML. [Agent 3 finding]
9. Add secondary regex to `test_no_bare_bash_variable_in_shell_actions` (`test_builtin_loops.py:188`) detecting `${valid_namespace.*:-...}` patterns across all builtin loops. [Agent 3 finding]

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — 6 sites (lines 50, 70, 71, 106, 275, 291)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — 1 site (line 26)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — delegates to `recursive-refine` as a sub-loop

### Codebase Research Findings

_Added by `/ll:refine-issue` — additional callers of `recursive-refine` discovered by codebase search:_

- `scripts/little_loops/loops/rn-build.yaml` — references `recursive-refine`
- `scripts/little_loops/loops/issue-refinement.yaml` — references `recursive-refine`
- `scripts/little_loops/loops/autodev.yaml` — references `recursive-refine`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — references `recursive-refine`
- `scripts/little_loops/loops/eval-driven-development.yaml` — references `recursive-refine`

All 5 are affected by BUG-2346 identically: they invoke a sub-loop that crashes before reaching any meaningful state.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — not a direct sub-loop caller; reads artifact files `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` produced by `recursive-refine`. While the artifact format does not change with this fix, this file documents the output dependency. [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/interpolation.py` — engine under fix; do not modify

### Tests
- `scripts/tests/test_fsm_interpolation.py` — lines 221, 364 document correct/incorrect forms; add a regression test for the `:-` crash pattern
- `scripts/tests/test_loops_recursive_refine.py` — dedicated recursive-refine test file; add integration coverage here
- `scripts/tests/test_builtin_loops.py:188` — `test_no_bare_bash_variable_in_shell_actions` is the existing cross-loop guard; it does NOT catch BUG-2346 because `context` is a valid namespace (only the namespace token is checked, not the path suffix)

### Codebase Research Findings

_Added by `/ll:refine-issue` — test pattern details:_

- **Crash regression** — follow `TestInterpolateEdgeCases.test_escape_bash_default_value` (line 363) docstring format; use `with pytest.raises(InterpolationError)` to document the broken form
- **Fix verification** — follow `TestSafeInterpolation.test_default_suffix_in_context_namespace` (line ~560): `InterpolationContext(context={})` with `interpolate("${context.order:default=queue}", ctx)` → `"queue"`
- **Real-loop YAML loading** — follow BUG-2094 bypass-guard pattern (lines 749–819): load `recursive-refine.yaml` via `yaml.safe_load`, extract a `parse_input` action, interpolate against a seeded context, and assert no exception

Suggested test skeleton:
```python
def test_bash_default_operator_raises_interpolation_error(self) -> None:
    """${context.key:-default} (bash :-) raises InterpolationError. BUG-2346."""
    ctx = InterpolationContext(context={"order": "queue"})
    with pytest.raises(InterpolationError):
        interpolate('ORDER="${context.order:-queue}"', ctx)

def test_engine_default_replaces_bash_default_operator(self) -> None:
    """${context.key:default=val} is the correct engine-native form."""
    ctx = InterpolationContext(context={})
    result = interpolate('ORDER="${context.order:default=queue}"', ctx)
    assert result == 'ORDER="queue"'
```

_Wiring pass added by `/ll:wire-issue`:_
- **Precise insertion point for crash-regression test**: `TestInterpolate` class in `test_fsm_interpolation.py`, after line 239 (before `class TestInterpolateDict` at line 242). The existing neighbors `test_check_lifetime_limit_bash_fallback` (line 217) and `test_nested_variable_syntax_raises_interpolation_error` (line 230) handle the same crash category — place BUG-2346 tests in this group. [Agent 3 finding]
- **`test_engine_default_replaces_bash_default_operator` — check for overlap**: `TestSafeInterpolation.test_default_suffix_in_context_namespace` (line 554) already tests `${context.missing:default=N/A}` returning `"N/A"`. If added, place in `TestSafeInterpolation` with a BUG-2346 comment; otherwise skip as redundant. [Agent 3 finding]
- **New `TestRlCodingAgentLoop.test_act_state_uses_no_bash_default_operator`**: add to `test_builtin_loops.py` after `TestRlCodingAgentLoop` line 4984. `TestRlCodingAgentLoop` (line 4933) has 7 tests but none examine the `action` field. Pattern to follow: `test_evaluate_code_uses_run_dir` (line 572, `TestEvaluationQualityLoop`). [Agent 3 finding]
- **New `TestRecursiveRefineInterpolation` class in `test_loops_recursive_refine.py`**: that file (1514 lines) tests bash-script behavior by running hardcoded `_DONE_SCRIPT` strings via `_bash()`, bypassing the FSM interpolator entirely. A new class loading `recursive-refine.yaml`, extracting `parse_input` action, and calling `interpolate()` with a seeded `InterpolationContext` would have caught BUG-2346 at this layer. [Agent 3 finding]
- **Enhancement to `test_no_bare_bash_variable_in_shell_actions` (`test_builtin_loops.py:188`)**: add a secondary regex pass that specifically flags `\$\{(context|captured|prev|result|state|loop|env|messages|param)\.[^}]*:-[^}]*\}` — the current check extracts only the namespace token and allows any `context.*` match through without examining the `:-` path suffix. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — **MUST UPDATE**: the "Bash default values" row in `## Variable Interpolation` at line 1130 explicitly states that `${var:-default}` is valid for optional context variables. This is factually wrong for `context.*` namespace variables and directly endorses the bug pattern. The rows immediately above (`:default=` at line 1127, `$${...}` escaping) describe the correct alternatives. After the YAML fix, this row remains as misinformation that could cause future loop authors to re-introduce BUG-2346. Correct or remove the row as part of this fix. [Agent 2 finding]

### Configuration
- N/A

## Acceptance Criteria

- [ ] All 7 sites no longer use unescaped `${...:-...}` syntax.
- [ ] `ll-loop run recursive-refine "<ids>"` no longer emits `Path 'order:-queue' not found in context`.
- [ ] `rl-coding-agent` first action interpolates without error.
- [ ] A test exercises the previously-broken interpolation form (or the new lint from ENH-2348 covers it).

## Steps to Reproduce

1. `ll-loop run recursive-refine BUG-364,BUG-365`
2. Observe `action_error: Path 'order:-queue' not found in context` at `parse_input`.
3. Loop terminates in `failed`.

## Session Log
- `/ll:ready-issue` - 2026-06-27T22:15:47 - `5d9226e6-d661-431a-95de-1ee52b9fa296.jsonl`
- `/ll:confidence-check` - 2026-06-27T22:00:00Z - `3bc5e776-bac2-4637-b313-116292da1660.jsonl`
- `/ll:wire-issue` - 2026-06-27T21:45:04 - `c9c37fb9-c085-4081-b3d7-dbe77eaba98e.jsonl`
- `/ll:refine-issue` - 2026-06-27T21:30:55 - `265ed482-e8e6-4a78-a5cf-d16f10ac38ee.jsonl`
- `/ll:format-issue` - 2026-06-27T21:22:16 - `b08dcd42-b1ea-42cd-97d5-276a58fd2363.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md
