---
id: ENH-1877
title: Add diff_stall_gate fragment and complete Wave 4 integration
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
completed_at: '2026-06-02T08:36:03Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
status: done
---

# ENH-1877: Add diff_stall_gate fragment and complete Wave 4 integration

## Summary

Add the `diff_stall_gate` fragment to `loops/lib/common.yaml`, convert the 3 caller loops, update documentation and skill references, bump the README loop count, and run the full Wave 4 validation suite. This is the final child of Wave 4 — it should be worked after ENH-1874 and ENH-1876 are merged so the README loop count reflects all new oracles.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

The `diff_stall` evaluator is used in 3 loops with identical configuration: `incremental-refactor.yaml` (state `execute_step`, `on_no: replan`), `harness-multi-item.yaml` (state `check_stall`, `on_no: advance`), and `harness-single-shot.yaml` (state `check_stall`, `on_no: done`). All three use `max_stall: 2`. The `evaluate:` block is duplicated across all three.

## Expected Behavior

- `diff_stall_gate` fragment in `loops/lib/common.yaml` supplying `evaluate.type: diff_stall` and `evaluate.max_stall: 2` as defaults; caller supplies `action`, `action_type`, and all routing (`on_yes`, `on_no`, `on_error`)
- `incremental-refactor.yaml:execute_step`, `harness-multi-item.yaml:check_stall`, and `harness-single-shot.yaml:check_stall` converted to use `fragment: diff_stall_gate`
- `README.md` loop count updated from `**68 FSM loops**` to `**69 FSM loops**` (ENH-1874 and ENH-1876 are already merged; verify exact current count with `ll-verify-docs` before bumping)
- Documentation updated in `skills/create-loop/reference.md` and `docs/guides/LOOPS_GUIDE.md`
- Full Wave 4 test suite passes

## Proposed Solution

1. Add `diff_stall_gate` fragment to `scripts/little_loops/loops/lib/common.yaml` — supplies `evaluate.type: diff_stall` and `evaluate.max_stall: 2`; model after `convergence_gate` (evaluator-only fragment); caller supplies `action`, `action_type`, and routing. Append after `queue_track` (currently the last fragment, around line 139):

   ```yaml
     diff_stall_gate:
       description: |
         Evaluator-only fragment that supplies evaluate.type: diff_stall and
         evaluate.max_stall: 2. Checks whether git diff has changed since the
         last iteration; returns yes on progress, no on stall (max_stall
         consecutive identical diffs).
         State must supply: action, action_type, and routing (on_yes, on_no);
         optionally on_error and evaluate.scope (list of paths) to limit the
         diff to specific subtrees. Default max_stall: 2 (EvaluateConfig default
         is 1; override per-state if needed).
       evaluate:
         type: diff_stall
         max_stall: 2
   ```

   **Note**: The fragment intentionally omits `action_type` because callers differ — `incremental-refactor.yaml:execute_step` uses `action_type: prompt` while both harness loops use `action_type: shell`. Each caller must supply `action_type` explicitly. This differs from `convergence_gate` which locks in `action_type: shell` because all its callers run shell metric commands.
2. Convert `scripts/little_loops/loops/incremental-refactor.yaml:execute_step` `evaluate:` block to use `fragment: diff_stall_gate`; `on_no` routes to `replan`
3. Convert `scripts/little_loops/loops/harness-multi-item.yaml:check_stall` to use `fragment: diff_stall_gate`; `on_no: advance`
4. Convert `scripts/little_loops/loops/harness-single-shot.yaml:check_stall` to use `fragment: diff_stall_gate`; `on_no: done`
5. Run `ll-loop validate` on all 3 modified loops
6. Update `skills/create-loop/reference.md` — add `diff_stall_gate` row to `## Fragment Catalog → ### lib/common.yaml fragments` table; update `## Stall Detection` code example (~line 391) to show `fragment: diff_stall_gate` pattern
7. Update `docs/guides/LOOPS_GUIDE.md` — revise `### Stall Detection` inline example (~line 2766) to use `fragment: diff_stall_gate`
8. Update `README.md` — ENH-1874 and ENH-1876 are **already merged** (confirmed in git log); run `ll-verify-docs` first to get the authoritative current count, then update `README.md` line 163 from `**68 FSM loops**` to whatever `ll-verify-docs` reports (expected `**69 FSM loops**` after the two oracle files are counted); confirm with `ll-verify-docs` again after the bump
9. Run expanded Wave 4 test suite: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/loops/README.md` — append `diff_stall_gate` to the `lib/common.yaml` row's fragment inventory list in the "Fragment Libraries" table
11. Update `skills/create-loop/loop-types.md` — revise "Stall Detection (native `diff_stall` evaluator)" section (~lines 888–919) inline YAML and single-shot (~line 713) / multi-item (~line 801) template blocks to show `fragment: diff_stall_gate`
12. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — revise "Stall Detection (`check_stall`)" section inline YAML to use `fragment: diff_stall_gate`
13. Add `test_check_stall_uses_diff_stall_gate_fragment()` to `scripts/tests/test_builtin_loops.py::TestHarnessCapture` for both harness files, following `test_score_uses_convergence_gate_fragment` pattern in `TestHarnessOptimize`
14. Add `incremental-refactor.yaml` to `migration_targets` in `scripts/tests/test_fsm_fragments.py::TestBuiltinLoopMigration` (lines 998–999)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `diff_stall_gate` fragment after `queue_track` (~line 139); ENH-1875 already merged, no conflict
- `scripts/little_loops/loops/incremental-refactor.yaml` — convert `execute_step` evaluate block; this state uses `action_type: prompt`, so caller must supply `action_type: prompt` explicitly
- `scripts/little_loops/loops/harness-multi-item.yaml` — convert `check_stall`; caller uses `action_type: shell` with `echo 'checking stall'` no-op
- `scripts/little_loops/loops/harness-single-shot.yaml` — convert `check_stall`; same shell no-op pattern; `on_no: done` (terminates loop on stall)
- `README.md` — bump loop count (line 163, currently `**68 FSM loops**`); verify target with `ll-verify-docs`
- `skills/create-loop/reference.md` — append row to Fragment Catalog table (lines 1120–1131); update Stall Detection inline example (lines 391–409)
- `docs/guides/LOOPS_GUIDE.md` — update Stall Detection section (lines 2758–2771)

### Dependent Files
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` implementation; persists state to `.loops/tmp/ll-diff-stall-<hash>.txt`; optional `scope:` field limits diff to specific paths — read to understand what the fragment wraps

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — Fragment Libraries table: append `diff_stall_gate` to the `lib/common.yaml` row's fragment inventory list (currently ends with `queue_track`) [Agent 2 finding]
- `skills/create-loop/loop-types.md` — "Stall Detection (native `diff_stall` evaluator)" section (~lines 888–919): update inline `check_stall` YAML example from bare `type: diff_stall` to show `fragment: diff_stall_gate`; also update single-shot (~line 713) and multi-item (~line 801) template YAML blocks [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — "Stall Detection (`check_stall`)" section: update inline `check_stall` YAML example to use `fragment: diff_stall_gate` [Agent 2 finding]

### Ordering Constraint
- **All dependencies already merged** (confirmed in git log):
  - ENH-1875 (`queue_pop`/`queue_track` fragments) — merged; `common.yaml` has no conflict
  - ENH-1874 (`implement-issue-chain` oracle) — merged
  - ENH-1876 (`research-coverage` oracle) — merged
- Step 8 README count bump can proceed immediately; run `ll-verify-docs` to confirm the authoritative count before editing

### Tests
- `scripts/tests/test_fsm_fragments.py` — append `TestDiffStallGateFragment` class after line 1720 (current end of file), following the `TestConvergenceGateFragment` pattern (lines 1527–1596). Exact four-test shape:
  ```python
  class TestDiffStallGateFragment:
      @staticmethod
      def _load_common_yaml() -> dict:
          import yaml
          lib_path = (
              Path(__file__).parent.parent
              / "little_loops" / "loops" / "lib" / "common.yaml"
          )
          with open(lib_path) as f:
              return yaml.safe_load(f)

      def test_diff_stall_gate_defined_in_common_yaml(self):
          data = self._load_common_yaml()
          assert "diff_stall_gate" in data["fragments"]

      def test_diff_stall_gate_has_diff_stall_evaluator(self):
          frag = self._load_common_yaml()["fragments"]["diff_stall_gate"]
          assert frag["evaluate"]["type"] == "diff_stall"
          assert frag["evaluate"]["max_stall"] == 2

      def test_diff_stall_gate_has_description(self):
          frag = self._load_common_yaml()["fragments"]["diff_stall_gate"]
          assert "description" in frag
          assert frag["description"].strip()

      def test_diff_stall_gate_resolves_in_loop(self):
          from scripts.little_loops.fsm.fragments import resolve_fragments
          raw = {
              "import": ["lib/common.yaml"],
              "states": {
                  "check_stall": {
                      "fragment": "diff_stall_gate",
                      "action": "echo 'checking stall'",
                      "action_type": "shell",
                      "on_yes": "next_state",
                      "on_no": "done",
                  }
              },
          }
          resolved = resolve_fragments(raw, loop_dir=<common_yaml_parent_dir>)
          state = resolved["states"]["check_stall"]
          assert state["evaluate"]["type"] == "diff_stall"
          assert state["evaluate"]["max_stall"] == 2
          assert "fragment" not in state
  ```
  Adjust the `resolve_fragments` import path and `loop_dir` to match the pattern used in `TestConvergenceGateFragment.test_convergence_gate_resolves_in_loop`.
- Ensure `test_all_common_yaml_fragments_have_description` passes for `diff_stall_gate`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestHarnessCapture` — add `test_check_stall_uses_diff_stall_gate_fragment()` methods for harness-multi-item and harness-single-shot, following the `test_score_uses_convergence_gate_fragment` pattern in `TestHarnessOptimize`; assert `check_stall` state carries `fragment: diff_stall_gate` after the YAML conversion [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py::TestBuiltinLoopMigration` — `incremental-refactor.yaml` is absent from the `migration_targets` list (lines 998–999) but will use `fragment: diff_stall_gate` after conversion; add it to the migration targets list to ensure load-after-migration still validates [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### `convergence_gate` fragment structure (the model to follow)

`scripts/little_loops/loops/lib/common.yaml` — the existing evaluator-only fragment:
```yaml
convergence_gate:
  action_type: shell
  evaluate:
    type: convergence
    direction: maximize
```
Note: `convergence_gate` includes `action_type: shell` because all its callers run shell metric commands. `diff_stall_gate` omits `action_type` because callers differ (one uses `prompt`, two use `shell`).

#### Current `diff_stall` blocks in the three caller loops

`scripts/little_loops/loops/incremental-refactor.yaml` — state `execute_step`:
```yaml
execute_step:
  action: "Execute the next incomplete refactoring step..."
  action_type: prompt    # ← LLM action; must be supplied by caller after conversion
  evaluate:
    type: diff_stall
    max_stall: 2
  on_yes: verify_tests
  on_no: replan
  # no on_error handler
```

`scripts/little_loops/loops/harness-multi-item.yaml` — state `check_stall`:
```yaml
check_stall:
  action: "echo 'checking stall'"
  action_type: shell
  evaluate:
    type: diff_stall
    max_stall: 2
  on_yes: check_concrete
  on_no: advance
  on_error: check_concrete
```

`scripts/little_loops/loops/harness-single-shot.yaml` — state `check_stall`:
```yaml
check_stall:
  action: "echo 'checking stall'"
  action_type: shell
  evaluate:
    type: diff_stall
    max_stall: 2
  on_yes: check_concrete
  on_no: done
  on_error: done
```

#### `evaluate_diff_stall()` semantics (`scripts/little_loops/fsm/evaluators.py`)

Parameters (from `EvaluateConfig`):
- `max_stall: int` — default `1` in `EvaluateConfig`; all three callers explicitly set `2`. The fragment defaults to `2`, so callers only need to override if they want a different threshold.
- `scope: list[str] | None` — default `None` (whole-tree diff). When set, `--` plus the path list is appended to `git diff --stat`. None of the three current callers use `scope`.

State files: `.loops/tmp/ll-diff-stall-<scope-hash>.txt` (previous diff snapshot) and `.loops/tmp/ll-diff-stall-<scope-hash>.count` (stall counter).

#### `resolve_fragments` deep_merge behavior (`scripts/little_loops/fsm/fragments.py`)

`_deep_merge(fragment, state)`: fragment is the **base**, state-level fields **win**. For nested dicts, merges recursively — so a state supplying `evaluate: {max_stall: 3}` will produce `{type: diff_stall, max_stall: 3}` (fragment's `type` preserved, state overrides `max_stall`). The `description:` key is popped from the fragment copy before merging and never appears in the expanded state.

#### Documentation update locations (verified line numbers)

| File | Section | Lines | Change |
|------|---------|-------|--------|
| `skills/create-loop/reference.md` | Fragment Catalog table | 1120–1131 | Append `diff_stall_gate` row after `queue_track` |
| `skills/create-loop/reference.md` | Stall Detection inline example | 391–409 | Update to show `fragment: diff_stall_gate` form |
| `docs/guides/LOOPS_GUIDE.md` | `### Stall Detection` | 2758–2771 | Update inline YAML to use `fragment: diff_stall_gate` |
| `README.md` | FSM loop count | 163 | `**68 FSM loops**` → `**69 FSM loops**` (verify with `ll-verify-docs`) |

Fragment Catalog table row to append (after the `queue_track` row):
```
| `diff_stall_gate` | `evaluate.type: diff_stall` + `evaluate.max_stall: 2` — yes on progress, no on N consecutive identical diffs | `action`, `action_type`, routing (`on_yes`, `on_no`); optionally `on_error` and `evaluate.scope` |
```

## Success Metrics

- `diff_stall_gate` standardizes `diff_stall` evaluator configuration across 3 loops
- All modified loops pass `ll-loop validate`
- All Wave 4 documentation updated
- `ll-verify-docs` passes with updated loop count
- Full Wave 4 test suite passes: test_builtin_loops, test_fsm_fragments, test_loops_recursive_refine, test_deep_research, test_deep_research_arxiv, test_doc_counts

## Scope Boundaries

- Do not change the observable behavior of `incremental-refactor`, `harness-multi-item`, or `harness-single-shot` from the user's perspective
- Do not restructure caller loop states beyond the `fragment: diff_stall_gate` delegation pattern; routing (`on_yes`, `on_no`, `on_error`) and `action` remain caller-supplied
- Updating test files for post-conversion structure is in scope; refactoring unrelated test classes in those files is NOT
- README loop count bump is in scope only for the count that `ll-verify-docs` reports as authoritative at implementation time

## Impact

- **Priority**: P3 - Eliminates duplicated `evaluate.type: diff_stall` + `max_stall: 2` config block across 3 loops; low urgency but clear technical-debt cost
- **Effort**: Medium - Add fragment to `common.yaml` + convert 3 loops + add 6+ tests + update 5 doc files + README count
- **Risk**: Low - All three loops have test coverage; observable behavior is unchanged (fragment merges transparently); no external API surface
- **Breaking Change**: No (behavior preserved; `resolve_fragments` deep-merge is transparent to loop execution)

## Labels

`refactoring`, `loops`, `fragments`, `code-quality`, `wave-4`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T08:28:41 - `cb86ac6b-391c-40ee-907c-50aa3288839c.jsonl`
- `/ll:wire-issue` - 2026-06-02T08:22:49 - `1163fbae-3344-4304-bdec-2a00f998c520.jsonl`
- `/ll:refine-issue` - 2026-06-02T08:15:21 - `7776cb3a-0137-4ee4-bb60-4e6062aee003.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `02c87e24-ec85-432e-b689-42054521c528.jsonl`
