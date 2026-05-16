---
id: ENH-1326
type: ENH
priority: P3
captured_at: '2026-05-02T19:05:00Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
decision_needed: false
missing_artifacts: true
confidence_score: 96
outcome_confidence: 69
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 23
score_change_surface: 18
size: Very Large
---

# ENH-1326: `/ll:analyze-loop` Should Resolve `from:`, Fragments, and Sub-loops Before Judging

## Summary

`/ll:analyze-loop` Step 2 currently calls `ll-loop show <loop> --json` once and treats the resulting state map as authoritative. That output reflects only the literal YAML file. It does not merge `from:` inheritance, expand `fragment:` references against `lib/*.yaml`, or follow `loop:` sub-loop refs. Loops that depend on those mechanisms are effectively invisible to the analyzer's signal classifier and to Step 3b goal alignment.

## Motivation

Concrete loops the current resolver fails on:

- **`apo-textgrad`** extends `lib/apo-base.yaml` via `from:` — its real state graph isn't visible in `ll-loop show` output without the merge.
- **`eval-driven-development`** has `loop: issue-refinement` on `refine_issues`; `issue-refinement` itself has `loop: refine-to-ready-issue`. The actual work happens two levels down. Current analyzer can't see whether the child's verdict was discarded.
- **Any loop using `with_rate_limit_handling`, `shell_exit`, `llm_gate`, `numeric_gate`, `run_benchmark`** — the `evaluate` semantics live in the fragment, not the calling state. Step 3 signal rules need the resolved evaluator type to apply correctly.
- **Sub-loop verdict laundering** (`eval-driven-development.refine_issues` mapping `on_yes` and `on_no` to the same downstream state) is a real category of bug that's only detectable across the loop boundary.

## Current Behavior

`skills/analyze-loop/SKILL.md:91-97` calls:

```bash
ll-loop show <loop_name> --json
```

and parses `"states"` directly. Sub-loops are not followed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Important correction to the issue premise**: `from:` inheritance and `fragment:` references are **already fully resolved** in the current `ll-loop show --json` output. `scripts/little_loops/fsm/validation.py:load_and_validate()` runs `resolve_inheritance()` then `resolve_fragments()` (both in `scripts/little_loops/fsm/fragments.py`) before calling `FSMLoop.from_dict()`. By the time `FSMLoop.to_dict()` serializes to JSON, neither `from:` nor `fragment:` keys remain — all inherited state fields and fragment-expanded evaluator configs are present inline.

The **only genuine gap** is `loop:` sub-loop resolution. `scripts/little_loops/fsm/schema.py:StateConfig` stores `loop: str | None` as a bare name string. `StateConfig.to_dict()` emits only that string; the child loop's state map is never expanded. Sub-loop internals are loaded lazily at runtime by `scripts/little_loops/fsm/executor.py:_execute_sub_loop()`.

Consequence for the skill: Step 3 signal rules (`evaluate.type`, `on_no`, `max_retries`) and Step 3b goal alignment work correctly for states that use `from:` or `fragment:`, but are blind to any logic that lives inside a child loop referenced via `loop:`.

## Expected Behavior

Step 2 (or a new Step 2b inserted before classification) produces a **resolved state map**:

1. If the loop has `from: <parent>`, recursively load and deep-merge the parent first (state-level merge, child wins on key conflict).
2. For any state with `fragment: <name>`, look up `<name>` in the imported `lib/*.yaml` (per the `import:` declarations) and merge fragment fields underneath state-local fields.
3. For any state with `loop: <child>`, parse the child YAML one level deep and attach its resolved state map under a `_subloop` key on the parent state.
4. Classification (Step 3) and goal alignment (Step 3b) operate on the resolved map.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `--resolved` flag to `ll-loop show` subparser** — `scripts/little_loops/cli/loop/__init__.py:main_loop()` around line 357, after the existing `--json` arg: `show_parser.add_argument("--resolved", action="store_true", help="Expand sub-loop states inline under _subloop key")`. Follow the existing `store_true` + `getattr(args, "resolved", False)` convention used by `--verbose` and `--json`.

2. **Implement sub-loop expansion in `cmd_show()`** — `scripts/little_loops/cli/loop/info.py:cmd_show()`: when `--resolved` is set, iterate the `fsm.to_dict()["states"]` dict; for any state with a `"loop"` key, call `resolve_loop_path(state["loop"], loops_dir)` then `load_and_validate(child_path)` (both already imported in this file) and attach `child_fsm.to_dict()["states"]` as `_subloop` on the parent state dict before printing. Mirror the runtime loading pattern in `scripts/little_loops/fsm/executor.py:_execute_sub_loop()`. No new resolver module is needed — `load_and_validate` already handles inheritance + fragments for the child.

3. **Update `skills/analyze-loop/SKILL.md` Step 2** — change the `ll-loop show <loop_name> --json` call to `ll-loop show <loop_name> --resolved --json`. Add a note that states with `_subloop` contain the child's resolved state map one level deep.

4. **Update Step 3b to walk `_subloop` entries** — when a parent state has `_subloop`, treat sub-loop states as separate counters (do not add to parent totals). Flag cross-boundary routing distinctly. `skills/assess-loop/SKILL.md` Step 8 already implements the verdict-laundering check pattern for `assess-loop` — replicate that logic for `analyze-loop`.

5. **Add sub-loop verdict laundering signal** — when a state has `loop:`, check whether `on_yes == on_no` (parent routing). If identical, emit `BUG — Sub-loop verdict discarded` (P3). Existing fixture at `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` demonstrates the exact scenario.

6. **Add tests in `TestCmdShowJson`** — `scripts/tests/test_ll_loop_commands.py:TestCmdShowJson` (line 2421): add a `TestCmdShowResolved` class following the same direct-import + `argparse.Namespace(json=True, resolved=True)` pattern. Write a parent loop YAML with `loop: child-name` state and a `child-name.yaml` in `tmp_path/.loops/`; assert the JSON output has `_subloop` on the parent state.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_ll_loop_commands.py:TestCmdShowJson` (lines 2450, 2471, 2501) — add `resolved=False` to all 3 `argparse.Namespace(json=True, verbose=False)` constructor calls to prevent `AttributeError` if `cmd_show` accesses `args.resolved` directly
8. Create `scripts/tests/fixtures/fsm/inner-eval.yaml` — minimal terminal child loop so `assess-subloop-laundering.yaml` fixture is fully exercisable in `TestCmdShowResolved`
9. Update `docs/guides/LOOPS_GUIDE.md` subcommands table (line 1917) — add `--resolved` to the `(--json for raw FSM config)` parenthetical
10. Update `docs/reference/COMMANDS.md` — `/ll:analyze-loop` entry (line 529): note that Step 2 uses `--resolved --json` and sub-loop states are now visible to signal detection
11. Update `docs/reference/COMMANDS.md` — `/ll:assess-loop` entry (line 577): if `assess-loop` SKILL.md is updated in parallel, reflect sub-loop laundering detection improvement
12. Add new `CHANGELOG.md` concrete version entry for the `--resolved` flag addition

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()`: add `--resolved` flag to `show_parser` (around line 357)
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()`: handle `--resolved`; expand `loop:` states with child `_subloop` dict
- `skills/analyze-loop/SKILL.md` — Step 2: use `--resolved --json`; Step 3b: walk `_subloop` keys; new laundering signal

### Dependent Files (Callers / Context)
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` — runtime sub-loop loading pattern to mirror (calls `resolve_loop_path` + `load_and_validate`)
- `scripts/little_loops/fsm/fragments.py` — `resolve_inheritance()`, `resolve_fragments()`, `_deep_merge()`: no changes needed; already called by `load_and_validate`
- `skills/assess-loop/SKILL.md` — Step 2 and Step 8: also uses `ll-loop show --json`; should be updated to `--resolved` for consistent sub-loop visibility
- `scripts/little_loops/loops/eval-driven-development.yaml` — two-level sub-loop chain (`loop: issue-refinement` → `loop: refine-to-ready-issue`) useful as acceptance test target
- `scripts/little_loops/loops/apo-textgrad.yaml` — uses `from: lib/apo-base.yaml` + fragments; verifies that `--resolved` doesn't break already-resolved inheritance

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/SKILL.md` — references `ll-loop show` as a tool to run; no `--json`/`--resolved` usage — no immediate change required, but flag is now available [Agent 1 finding]
- `scripts/tests/test_ll_loop_commands.py:TestCmdShow` — exercises `cmd_show` via `main_loop()` + `sys.argv` patch; will auto-receive `resolved=False` once flag is registered in argparse — no manual fix needed [Agent 3 finding]

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` — exact pattern for loading + running a child loop; reuse `resolve_loop_path` + `load_and_validate` for `--resolved` expansion
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — existing fixture for the verdict-laundering scenario; reusable in new tests

### Tests
- `scripts/tests/test_ll_loop_commands.py:TestCmdShowJson` (line 2421) — extend with `TestCmdShowResolved` class
- `scripts/tests/test_fsm_fragments.py:TestLoadAndValidateIntegration` — reference pattern for combined inheritance+fragment tests
- `scripts/tests/test_fsm_inheritance.py:TestFromCombinedWithFragments` — reference pattern for `from:` + `fragment:` combined tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py:TestCmdShowJson` (lines 2450, 2471, 2501) — **update**: 3 `Namespace(json=True, verbose=False)` calls omit `resolved`; add `resolved=False` to each to prevent `AttributeError` if `args.resolved` is accessed directly rather than via `getattr` [Agent 3 finding — tests to update]
- New `TestCmdShowResolved` class in `test_ll_loop_commands.py` — follow `TestCmdShowJson` pattern: `argparse.Namespace(json=True, verbose=False, resolved=True)`; write parent YAML with `loop: inner-eval` state + `inner-eval.yaml` in `tmp_path/.loops/`; assert JSON output has `_subloop` key on the parent state dict [Agent 3 finding — new test to write]
- New fixture `scripts/tests/fixtures/fsm/inner-eval.yaml` — companion child loop for `assess-subloop-laundering.yaml`; provides the missing `inner-eval` body so that fixture is fully exercisable in `TestCmdShowResolved` [Agent 3 finding — new file needed]

### Documentation
- `docs/reference/CLI.md` — document `--resolved` flag for `ll-loop show`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — subcommands table at line 1917; parenthetical `(--json for raw FSM config)` needs `--resolved` added [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `/ll:analyze-loop` entry (line 529): add note that Step 2 uses `--resolved --json` and sub-loop states are now visible to signal classification [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `/ll:assess-loop` entry (line 577): if `assess-loop` SKILL.md is updated to `--resolved`, update description of sub-loop laundering detection [Agent 2 finding]
- `CHANGELOG.md` — add new concrete version entry for `--resolved` flag when implemented (do not add under `[Unreleased]`) [Agent 2 finding]
- `README.md` (lines 325–326) — optional: add `ll-loop show <name> --resolved --json` line alongside existing `--json` example [Agent 2 finding]

## API/Interface

- New: `ll-loop show <name> --resolved --json`
- Skill change: `analyze-loop` Step 2 uses `--resolved` and parses `_subloop` keys.
- New signal: `BUG — Sub-loop verdict discarded` (P3) when child's terminal verdict doesn't differentiate parent routing.

## Acceptance Criteria

- [ ] `ll-loop show --resolved --json` returns a merged state map for loops using `from:`, `fragment:`, and `loop:`.
- [ ] `/ll:analyze-loop` on `apo-textgrad` correctly classifies its `apply_gradient` and `compute_gradient` states (which depend on `lib/apo-base` inheritance).
- [ ] `/ll:analyze-loop` on `eval-driven-development` reports the sub-loop verdict laundering at `refine_issues` (where `on_yes` and `on_no` may both route to `tradeoff_review`).
- [ ] Existing tests for `/ll:analyze-loop` still pass (no regressions on loops without inheritance/fragments/sub-loops).

## Labels

`enhancement`, `loops`, `analysis`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- **load_and_validate import gap**: Issue step 2 claims it is "already imported in this file" but `load_and_validate` is NOT currently imported in `scripts/little_loops/cli/loop/info.py`. Implementer must add `from little_loops.fsm.validation import load_and_validate` manually.
- **inner-eval.yaml fixture absent**: `assess-subloop-laundering.yaml` references `loop: inner-eval` but no `inner-eval.yaml` exists yet in `scripts/tests/fixtures/fsm/`. The `TestCmdShowResolved` test depends on this missing artifact being created (step 8).
- **assess-loop SKILL.md coupling**: Updating `skills/assess-loop/SKILL.md` to `--resolved` is listed as optional; if deferred, the two skills will have inconsistent sub-loop visibility.

## Session Log
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b37ceff-241e-4ddb-8c92-dbcb8cc24dac.jsonl`
- `/ll:wire-issue` - 2026-05-02T21:23:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94faadcc-1622-46db-a2a3-05ae22038062.jsonl`
- `/ll:refine-issue` - 2026-05-02T21:17:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e712cefa-7a5f-4f34-865c-8db6b646a184.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3504f81c-8403-4c3e-84f2-f27905b579d2.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-02
- **Reason**: Issue too large for single session (score: 9/11 — Very Large)

### Decomposed Into
- ENH-1333: `ll-loop show --resolved`: CLI flag and sub-loop expansion with tests
- ENH-1334: `analyze-loop` and `assess-loop` skill updates for sub-loop visibility
