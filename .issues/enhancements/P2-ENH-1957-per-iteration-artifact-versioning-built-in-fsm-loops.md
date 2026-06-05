---
id: ENH-1957
status: done
type: enh
priority: P2
decision_needed: false
captured_at: '2026-06-05T04:04:47Z'
completed_at: '2026-06-05T18:25:24Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 89
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 23
---

# ENH-1957: Add Per-Iteration Artifact Versioning to Built-in FSM Loops

## Summary

70+ built-in FSM loops exist, and the majority that iteratively refine artifacts (images, HTML, plans, issues) **overwrite** the same file on every iteration within a run. Only the final result survives — all intermediate versions are lost. The runner already provides run-level isolation (timestamped `run_dir`), but within a single run, every iteration overwrites the previous one.

This enhancement adds per-iteration artifact snapshots so every scored version is preserved in `iter-N/` subdirectories within the run directory, enabling debugging, comparison, and rollback across iterations.

## Current Behavior

Most iterative FSM loops (e.g., `svg-image-generator`, `html-website-generator`, `rn-refine`, `refine-to-ready-issue`) write to a flat artifact path like `${run_dir}/image.svg` or `${run_dir}/plan.md`. Each iteration overwrites the previous output. Only 2 of ~70 loops preserve intermediate versions:

- `adversarial-redesign.yaml` — copies `iter-$ITER.svg` + `iter-$ITER-critique.json` per iteration
- `svg-textgrad.yaml` — tracks `best.svg` / `best-brief.md` when score improves (but not all iterations)

**Key architectural insight**: `oracles/generator-evaluator.yaml` is the **shared sub-loop** used by 7 thin-wrapper harness loops (`html-website-generator`, `html-anything`, `svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `hitl-md`). Adding versioning to this one oracle fixes all 7 wrappers at once.

## Expected Behavior

Every iterative loop that refines an artifact should preserve per-iteration snapshots in `iter-N/` subdirectories within the run directory. The `generator-evaluator.yaml` oracle should provide this as a built-in `snapshot` state between `evaluate` and `score`. A new MR-5 validation rule should warn when harness-category loops write to flat artifact paths in iterative cycles without declaring versioning intent.

## Motivation

- **Debugging**: If iteration 3 produces a great SVG but iteration 4 degrades it, only the degraded version survives — the better version is lost forever
- **Comparison**: Users cannot diff or compare how artifacts evolved across iterations without per-iteration snapshots
- **Rollback**: No way to revert to a previous iteration's output without re-running the entire loop
- **Scale**: 70+ loops affected, but the oracle fix alone addresses 7 at once. Remaining individual loops need targeted updates
- **Prevention**: MR-5 validation prevents future loops from silently regressing on this pattern

## Proposed Solution

Three-phase approach combining **infrastructure support** (schema flag + validation rule + library fragment) with **targeted YAML updates** to the oracle and affected loops.

### Phase 1: Oracle Fix (Highest Leverage — Fixes 7 Loops)

Modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml` to add a `snapshot` state between `evaluate` and `score`:

```
Before: generate → evaluate → score → on_no → generate → ...
After:  generate → evaluate → snapshot → score → on_no → generate → ...
```

**Snapshot state** (shell action):
```bash
RUN_DIR="${context.run_dir}"
COUNTER=$(cat "$RUN_DIR/.iter_counter" 2>/dev/null || echo 0)
COUNTER=$((COUNTER + 1))
echo "$COUNTER" > "$RUN_DIR/.iter_counter"
mkdir -p "$RUN_DIR/iter-$COUNTER"
cp "$RUN_DIR/${context.artifact_path}" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
cp "$RUN_DIR/screenshot.png" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
```

Routing: unconditional `next: score` — snapshot always succeeds. Evaluate's `on_yes`/`on_no` now point to `snapshot` instead of `score`. Add `artifact_versioning: true` top-level declaration.

### Phase 2: Schema and Infrastructure

- Add `artifact_versioning: bool = False` and `artifact_versioning_ok: bool = False` to `FSMLoop` dataclass in `fsm/schema.py` (~line 970), with serialization in `to_dict()` (~line 1038) and deserialization in `from_dict()` (~line 1095)
- Add both to `KNOWN_TOP_LEVEL_KEYS` in `validation.py` (~line 153)
- Add `_validate_artifact_overwrite()` function: **WARNING** when a harness-category loop writes to a flat artifact path in an iterative `generate→evaluate→generate` cycle without `artifact_versioning: true` or `artifact_versioning_ok: true`. Wire into `validate_fsm()` (~line 994)
- Add `snapshot_artifact` library fragment in `loops/lib/common.yaml` for non-oracle loops to compose in

### Phase 3: Update Remaining Individual Loops

| Loop | Change |
|------|--------|
| `svg-textgrad.yaml` | Add per-iteration snapshot lines to `track_best` state + `artifact_versioning: true` |
| `adversarial-redesign.yaml` | Add `artifact_versioning: true` (already writes `iter-$ITER.svg`) |
| `rn-refine.yaml` | Add `snapshot` state after `synthesize` + `artifact_versioning: true` |
| `refine-to-ready-issue.yaml` | Add shell state after `refine_issue` to copy issue into `run_dir/iter-N-issue.md` + `artifact_versioning: true` |
| `recursive-refine.yaml` | Add `artifact_versioning: true` (sub-loops handle snapshots) |
| `general-task.yaml` | Add `artifact_versioning_ok: true` (artifact varies by task — suppress MR-5) |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Oracle flow verified**: The actual `generator-evaluator.yaml` flow (verified against current code) is `generate → evaluate → score → done` (on_yes) or `→ generate` (on_no/on_error). The proposed snapshot insertion between `evaluate` and `score` is correct: evaluate already routes ALL verdicts (yes/no/error) unconditionally to the next state, so changing its target to `snapshot` (with `next: score`) captures every iteration's artifact regardless of score outcome — essential for debugging regressions where a passing artifact is degraded by a subsequent iteration.
- **Fragment parameter validation**: `_validate_fragment_bindings()` in `validation.py` cross-validates `with:` bindings against fragment `parameters:` blocks. The `snapshot_artifact` fragment's `parameters:` (e.g., `artifact_path`, `run_dir`) will be automatically validated when states reference the fragment with `with:` — no additional validation code needed beyond declaring the parameters in the fragment YAML.
- **Suppression flag convention**: All existing `_ok` flags (`meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`) follow an identical pattern: boolean default `False`, checked at the top of their validation function for early return `[]`, serialized in `to_dict()` only when `True`, added to `KNOWN_TOP_LEVEL_KEYS`. The new `artifact_versioning_ok` flag follows this exact convention.
- **`artifact_versioning` vs `artifact_versioning_ok` semantics**: `artifact_versioning: true` is an affirmative declaration that the loop snapshots per-iteration artifacts (used by MR-5 to suppress false positives). `artifact_versioning_ok: true` is a suppression-only flag for loops that intentionally overwrite without versioning (e.g., `general-task.yaml` where the artifact varies by task). This matches the `shared_state_ok` precedent: a suppression flag that silences a WARNING when the pattern is intentional.

## Integration Map

### Files to Modify
| Priority | File | Change |
|----------|------|--------|
| **P0** | `loops/oracles/generator-evaluator.yaml` | Add `snapshot` state + `artifact_versioning: true` |
| **P0** | `fsm/schema.py` | Add `artifact_versioning`, `artifact_versioning_ok` fields |
| **P0** | `fsm/validation.py` | Add MR-5 validation rule + KNOWN_TOP_LEVEL_KEYS entries |
| P1 | `loops/lib/common.yaml` | Add `snapshot_artifact` fragment |
| P1 | `loops/svg-textgrad.yaml` | Per-iteration snapshot + versioning flag |
| P1 | `loops/rn-refine.yaml` | Snapshot state + versioning flag |
| P1 | `loops/refine-to-ready-issue.yaml` | Issue snapshot + versioning flag |
| P1 | `scripts/tests/test_fsm_validation.py` | MR-5 test cases |
| P2 | `loops/adversarial-redesign.yaml` | Add `artifact_versioning: true` |
| P2 | `loops/recursive-refine.yaml` | Add `artifact_versioning: true` |
| P2 | `loops/general-task.yaml` | Add `artifact_versioning_ok: true` |
| P2 | `skills/create-loop/templates.md` | Default versioning in harness template |
| P2 | `skills/create-loop/reference.md` | Document new config keys |

_Wiring pass added by `/ll:wire-issue`:_
| **P0** | `scripts/tests/test_builtin_loops.py` | Fix generator-evaluator tests that WILL BREAK (state name + routing assertions) |
| P1 | `scripts/tests/test_fsm_schema.py` | Add `TestArtifactVersioning` / `TestArtifactVersioningOk` round-trip test classes |
| P2 | `docs/reference/CLI.md` | Add MR-5 entry to validation rules list |
| P2 | `.claude/CLAUDE.md` | Add MR-5 rule to Loop Authoring section |
| P2 | `skills/review-loop/reference.md` | Add MR-5 row to Validation Rules table |

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — FSM executor reads loop YAML and instantiates `FSMLoop` dataclass
- `scripts/tests/test_fsm_validation.py` — existing MR-1 through MR-4 tests; add MR-5 cases

_Wiring pass added by `/ll:wire-issue`:_

_These files import FSMLoop or related types and are downstream consumers — no code changes required (new fields default to `False`), but implementers should be aware of the dependency chain:_

- `scripts/little_loops/fsm/__init__.py` — re-exports `FSMLoop` and `validate_fsm` (line 133-148, 159-164); no export change needed
- `scripts/little_loops/fsm/persistence.py` — imports `FSMLoop`, serialization uses `to_dict()`/`from_dict()` (line 39)
- `scripts/little_loops/cli/loop/info.py` — calls `fsm.to_dict()` in `ll-loop show --json` path (line 958); new fields appear in JSON output when `True`
- `scripts/little_loops/cli/loop/_helpers.py` — imports `FSMLoop`, `load_and_validate` (lines 22-27)
- `scripts/little_loops/cli/loop/layout.py` — imports `FSMLoop` for diagram layout (line 19)
- `scripts/little_loops/cli/loop/run.py` — imports `load_and_validate` for loop execution (line 98)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `PersistentExecutor`, `LoopState`, `RateLimitCircuit` from fsm modules
- `scripts/little_loops/extension.py` — imports `FSMExecutor`, `RouteContext`, `PersistentExecutor` from fsm modules (lines 26-29)
- `scripts/little_loops/doc_counts.py` — calls `is_runnable_loop` from fsm.validation (line 13)
- `scripts/little_loops/analytics/variance.py` — imports `_verdict_is_yes`, `HISTORY_DIR` from fsm.persistence
- `scripts/little_loops/cli/harness.py` — imports `evaluate_llm_structured` from fsm.evaluators (line 14)
- `scripts/little_loops/transport.py` — imports `list_running_loops` from fsm.persistence (line 580)
- `scripts/little_loops/cli/loop/testing.py` — imports `RateLimitCircuit`, evaluators, executor from fsm modules

_YAML loops importing from `common.yaml` (33 total) — new `snapshot_artifact` fragment is additive; no changes needed to these consumers but they should be validated post-change:_
- `loops/rn-implement.yaml`, `loops/rn-remediate.yaml`, `loops/rn-decompose.yaml`, `loops/migrate-sdk-version.yaml`, `loops/harness-plan-research-implement-report.yaml`, `loops/autodev.yaml`, `loops/harness-single-shot.yaml`, `loops/incremental-refactor.yaml`, `loops/harness-multi-item.yaml`, `loops/oracles/research-coverage.yaml`, `loops/sprint-refine-and-implement.yaml`, `loops/auto-refine-and-implement.yaml`, `loops/oracles/implement-issue-chain.yaml`, `loops/oracles/enumerate-and-prove.yaml`, `loops/integrate-sdk.yaml`, `loops/adopt-third-party-api.yaml`, `loops/rl-coding-agent.yaml`, `loops/test-coverage-improvement.yaml`, `loops/agent-eval-improve.yaml`, `loops/harness-optimize.yaml`, `loops/rl-policy.yaml`, `loops/docs-sync.yaml`, `loops/dead-code-cleanup.yaml`, `loops/assumption-firewall.yaml`, `loops/prompt-across-issues.yaml`, `loops/learning-tests-audit.yaml`, `loops/proof-first-task.yaml`, `loops/fix-quality-and-tests.yaml`, `loops/sprint-build-and-validate.yaml`, `loops/issue-refinement.yaml`

### Similar Patterns
- `adversarial-redesign.yaml` already implements per-iteration versioning — use as reference pattern for the `iter-N/` convention
- `svg-textgrad.yaml` has best-score tracking — extend to full per-iteration snapshots

### Tests

**New tests to write:**
- `scripts/tests/test_fsm_validation.py` — add MR-5 unit tests (`TestArtifactVersioning` class following `TestArtifactIsolation` pattern at line 1036):
  - MR-5 fires for harness loop overwriting artifact without versioning
  - MR-5 does NOT fire with `artifact_versioning: true`
  - MR-5 does NOT fire with `artifact_versioning_ok: true`
  - MR-5 does NOT fire for non-iterative loops
  - `artifact_versioning` / `artifact_versioning_ok` recognized as top-level keys (via `load_and_validate` + YAML)
  - MR-5 wired into `validate_fsm()` (end-to-end)
- `scripts/tests/test_fsm_schema.py` — add `TestFSMLoopArtifactVersioning` class (following `TestFSMLoopRequiredInputs` pattern at line 3226):
  - `artifact_versioning` defaults to `False`, `to_dict` omits when `False`, includes when `True`
  - `artifact_versioning_ok` defaults to `False`, `to_dict` omits when `False`, includes when `True`
  - `from_dict` parses both fields via `data.get()`
  - Round-trip: both fields survive `to_dict`/`from_dict` cycle

**Existing tests that WILL BREAK and MUST be updated:**

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_required_states_exist` (line 5412) — asserts exactly 4 states `("generate", "evaluate", "score", "done")`; must add `"snapshot"` to the tuple
- `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_evaluate_routes_to_score_on_all_outcomes` (line 5423) — asserts `on_yes == "score"`, `on_no == "score"`, `on_error == "score"`; must change to `== "snapshot"`
- `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle` — optionally add `test_snapshot_state_exists` and `test_snapshot_routes_to_score` to verify new state

**Existing tests to verify (should NOT break but validate as regression gate):**
- `scripts/tests/test_fsm_fragments.py` (lines 822, 858) — "Unknown top-level" string assertions depend on `KNOWN_TOP_LEVEL_KEYS` being current
- `scripts/tests/test_benchmark_fragment.py` (line 270) — same
- `scripts/tests/test_general_task_loop.py` — validates general-task FSM; `artifact_versioning_ok: true` is additive
- `scripts/tests/test_rn_refine.py` — validates rn-refine routing; new `snapshot` state is additive between existing states
- `scripts/tests/test_fsm_executor.py` — 176 `FSMLoop` constructions all use keyword args; new fields default to `False`

**Smoke test:**
- `ll-loop run svg-image-generator --builtin --max-iterations 2 --input '{"description": "a simple blue circle"}' --context pass_threshold=4` — verify `run_dir` contains `iter-1/` and `iter-2/`

### Documentation
- `skills/create-loop/templates.md` — default versioning in harness template
- `skills/create-loop/reference.md` — document new `artifact_versioning` / `artifact_versioning_ok` config keys
- `docs/reference/API.md` — update FSMLoop dataclass field documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (lines 534-549) — add MR-5 entry to validation rules list; add `artifact_versioning_ok: true` to suppression flags sentence at line 545
- `.claude/CLAUDE.md` (lines 123-137) — add MR-5 rule description in Loop Authoring section following MR-1/MR-3/MR-4 format (rule number, severity, suppression flag, ENH reference)
- `skills/review-loop/reference.md` (lines 40-43) — add MR-5 row to Validation Rules table (currently lists MR-1 through MR-4)
- `skills/audit-loop-run/SKILL.md` (line 90) — optional: update enumerated list of conditional `to_dict()` keys to include `artifact_versioning` / `artifact_versioning_ok`

### Configuration
- N/A — no config changes; new fields are loop-level YAML declarations

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verified anchor references**: All file:line references validated against current codebase:
  - `schema.py`: `FSMLoop` dataclass at lines 944-972; `to_dict()` at 974-1041; `from_dict()` at 1043-1096. The `_ok` suppression flags (`meta_self_eval_ok`, `shared_state_ok`, `partial_route_ok`) are at lines 968-970 — new `artifact_versioning` / `artifact_versioning_ok` fields follow the same pattern (boolean default `False`, serialized only when `True`, deserialized via `data.get()`).
  - `validation.py`: `KNOWN_TOP_LEVEL_KEYS` at lines 119-154 (closing `}` at line 154). `validate_fsm()` MR rule wiring at lines 988-1004 — MR-5 call should be inserted after MR-4 at line 996 following the existing `errors.extend(_validate_*(fsm))` pattern.
  - `cli/loop/config_cmds.py`: `cmd_validate()` at lines 11-34 handles the `ll-loop validate` command — invokes `load_and_validate()`, splits errors by severity, returns exit code 1 on ERROR.
- **Fragment resolution pipeline**: `fragments.py:resolve_fragments()` (lines 64-151) deep-merges fragment fields into referencing states. The `snapshot_artifact` fragment in `common.yaml` should follow the `retry_counter` pattern (lines 23-45 in `common.yaml`) which uses `parameters:` with `with:` bindings validated by `_validate_fragment_bindings()`.
- **`${iteration}` already available**: The executor's `_build_context()` at `executor.py:1581` injects `iteration=self.iteration` into `InterpolationContext`. The proposed manual counter file (`iter_counter`) is preferred over `${iteration}` because `${iteration}` tracks the FSM iteration count (reset on resume), while the snapshot counter should track artifact versions independently across the run lifecycle.
- **Cycle detection precedent**: `_find_reachable_states()` at `validation.py:1484-1522` performs BFS reachability analysis — the MR-5 iterative cycle detector can build on this graph traversal pattern using `StateConfig.get_referenced_states()` to detect `generate → evaluate → generate` (or similar) cycles.
- **Oracle wrapper verification**: The 7 thin-wrapper loops that use `oracles/generator-evaluator.yaml` (`html-website-generator.yaml`, `html-anything.yaml`, `svg-image-generator.yaml`, `p5js-sketch-generator.yaml`, `pixi-generative-art.yaml`, `pixi-data-viz.yaml`, `hitl-md.yaml`) all invoke the oracle via `loop:` state with `with:` parameter bindings. Adding the `snapshot` state to the oracle propagates to all 7 wrappers without changing any wrapper YAML.
- **`loops/lib/common.yaml`**: 11 existing fragments defined; all follow the same pattern — a `fragments:` top-level key with named fragment dicts containing `description:`, `action_type:`, `action:`, `evaluate:`, and optional `parameters:` blocks.

## Implementation Steps

1. Add `artifact_versioning` and `artifact_versioning_ok` fields to `FSMLoop` dataclass in `fsm/schema.py` with `to_dict()`/`from_dict()` support
2. Add MR-5 validation rule (`_validate_artifact_overwrite`) in `fsm/validation.py` with iterative-cycle detection heuristic; wire into `validate_fsm()`
3. Add `snapshot_artifact` library fragment in `loops/lib/common.yaml`
4. Modify `generator-evaluator.yaml` oracle to insert `snapshot` state between `evaluate` and `score` (fixes 7 wrapper loops at once)
5. Update `svg-textgrad.yaml` with per-iteration snapshots in `track_best` state
6. Add `snapshot` state to `rn-refine.yaml` after `synthesize`
7. Add issue-copy state to `refine-to-ready-issue.yaml` after `refine_issue`
8. Declare `artifact_versioning: true` on `adversarial-redesign.yaml` and `recursive-refine.yaml`
9. Add `artifact_versioning_ok: true` to `general-task.yaml`
10. Add MR-5 unit tests to `test_fsm_validation.py`
11. Run `ll-loop validate` on all affected loops + full test suite (`python -m pytest scripts/tests/ -v --tb=short` + `ruff check scripts/`)
12. Smoke test with `svg-image-generator` to verify `iter-N/` directories are created

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Fix `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_required_states_exist` (line 5412) — add `"snapshot"` to expected state tuple
14. Fix `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_evaluate_routes_to_score_on_all_outcomes` (line 5423) — change routing assertions from `== "score"` to `== "snapshot"`
15. Add `TestFSMLoopArtifactVersioning` round-trip test class to `scripts/tests/test_fsm_schema.py` (following `TestFSMLoopRequiredInputs` pattern at line 3226) — tests for `artifact_versioning`/`artifact_versioning_ok` defaults, `to_dict` omission, `from_dict` parsing, and round-trip
16. Add MR-5 rule entry (`artifact_versioning_ok: true` suppression flag) to validation rules documentation in `docs/reference/CLI.md` (lines 534-549)
17. Add MR-5 rule description to `.claude/CLAUDE.md` Loop Authoring section (follow MR-1/MR-3/MR-4 format)
18. Add MR-5 row to Validation Rules table in `skills/review-loop/reference.md` (lines 40-43)
19. Verify no regressions in `scripts/tests/test_fsm_fragments.py` and `scripts/tests/test_benchmark_fragment.py` (unknown-top-level assertions depend on `KNOWN_TOP_LEVEL_KEYS`)
20. Validate all 33 `common.yaml` consumer loops with `ll-loop validate` to confirm new MR-5 warnings are intentional or suppressed

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (schema.py)**: New `artifact_versioning: bool = False` and `artifact_versioning_ok: bool = False` fields should be inserted after `partial_route_ok` at line 970, following the same pattern as existing `_ok` suppression flags. In `to_dict()`, add serialization blocks after line 1039: `if self.artifact_versioning: result["artifact_versioning"] = self.artifact_versioning` (only serialized when `True`, matching the convention). In `from_dict()`, add deserialization after line 1094: `artifact_versioning=data.get("artifact_versioning", False), artifact_versioning_ok=data.get("artifact_versioning_ok", False),`.
- **Step 2 (validation.py)**: Add `"artifact_versioning"` and `"artifact_versioning_ok"` to `KNOWN_TOP_LEVEL_KEYS` (line 147 area, alphabetically before `circuit`). Insert `errors.extend(_validate_artifact_overwrite(fsm))` after line 996 in `validate_fsm()`. The `_validate_artifact_overwrite()` function should follow the existing MR rule pattern: check `fsm.artifact_versioning_ok` for early return `[]`, check `fsm.category` for `"harness"`, traverse state transitions to detect iterative artifact-writing cycles, return `list[ValidationError]` with WARNING severity.
- **Step 3 (common.yaml)**: Add `snapshot_artifact` fragment following the `retry_counter` pattern (uses `parameters:` block with `with:` bindings). The fragment needs `artifact_path` (string, required) and `run_dir` (string, required) parameters. Action copies `${param.run_dir}/${param.artifact_path}` to `${param.run_dir}/iter-<counter>/<filename>`.
- **Step 4 (generator-evaluator.yaml)**: The oracle's current flow (verified against actual code) is: `generate → evaluate → score → generate/done`. Insert `snapshot` state between `evaluate` and `score` by changing evaluate's `on_yes/no/error` routing from `score` to `snapshot`, then `snapshot` with `next: score` (unconditional forward). This captures every iteration BEFORE scoring, preserving artifacts that both pass and fail — important for debugging regressions.
- **Steps 5-9 (individual loops)**: Each loop's `states:` section needs inspection to identify the correct insertion point. For loops using sub-loop delegation (`loop: oracles/generator-evaluator`), only the `artifact_versioning: true` flag is needed — the oracle handles snapshots. For standalone iterative loops (`rn-refine.yaml`, `refine-to-ready-issue.yaml`), a new shell state must be inserted at the point where the artifact is fully materialized but before quality-gate routing.
- **Step 10 (tests)**: Follow the test patterns in `test_fsm_validation.py`:
  - Class `TestArtifactVersioning(TestCase)` following `TestArtifactIsolation` (lines 1036-1129) pattern
  - Helper method `_simple_fsm()` to construct minimal FSMs with `artifact_versioning`/`artifact_versioning_ok` flags
  - Tests: MR-5 fires for harness loop overwriting flat artifact path; suppressed by `artifact_versioning_ok: true`; suppressed by `artifact_versioning: true`; does not fire for non-iterative or non-harness loops; `artifact_versioning` / `artifact_versioning_ok` recognized as top-level keys
  - Use `make_state()` helper (line 41-43) and `ValidationSeverity.WARNING` for assertions
- **Step 11 (validate + test suite)**: `ll-loop validate` runs `cmd_validate()` at `config_cmds.py:11-34`. Run on all affected loops: `generator-evaluator`, `svg-textgrad`, `rn-refine`, `refine-to-ready-issue`, `adversarial-redesign`, `recursive-refine`, `general-task`. Test suite: `python -m pytest scripts/tests/test_fsm_validation.py -v --tb=short`.
- **Step 12 (smoke test)**: Use `ll-loop run svg-image-generator --builtin --max-iterations 2 --input '{"description":"a simple blue circle"}' --context pass_threshold=4` and verify `${run_dir}/iter-1/image.svg`, `${run_dir}/iter-2/image.svg` exist. The `--builtin` flag resolves loops from `scripts/little_loops/loops/` via `resolve_loop_path()`.

## Success Metrics

- **Debugging efficiency**: Users can inspect any iteration's artifact without re-running the loop — saving ~2-5 minutes per debug session for iterative refinement loops
- **Coverage**: 70+ loops have versioning infrastructure available; 10+ loops actively snapshot artifacts (7 via oracle fix, 3+ individually updated)
- **MR-5 adoption**: Zero loops incorrectly suppress MR-5 via `artifact_versioning_ok` without documented reason
- **Smoke test**: `ll-loop run svg-image-generator --builtin --max-iterations 2 --input '{"description": "a simple blue circle"}'` produces `run_dir/iter-1/` and `run_dir/iter-2/` directories with artifacts

## Scope Boundaries

- **In scope**:
  - Add `artifact_versioning` and `artifact_versioning_ok` fields to `FSMLoop` schema (dataclass, serialization, validation)
  - Add MR-5 validation rule (WARNING severity) for overwrite detection in iterative harness loops
  - Add `snapshot` state to `generator-evaluator.yaml` oracle (fixes 7 wrapper loops)
  - Add `snapshot_artifact` library fragment in `loops/lib/common.yaml`
  - Update individual loops: `svg-textgrad.yaml`, `rn-refine.yaml`, `refine-to-ready-issue.yaml`, `adversarial-redesign.yaml`, `recursive-refine.yaml`, `general-task.yaml`
  - MR-5 unit tests and smoke test
  - Documentation: create-loop templates and API reference

- **Out of scope**:
  - Retrofitting ALL 70+ loops (only 10+ targeted loops updated; remaining loops get MR-5 warning on next validation but not blocked)
  - Changing executor behavior (snapshots are YAML-level state additions, not executor-level hooks)
  - Automatic artifact diffing or comparison tooling (future enhancement; this issue establishes the snapshot infrastructure)
  - Changing the `run_dir` isolation model (timestamped directories are sufficient; no deeper hierarchy changes)

## API/Interface

New optional fields on `FSMLoop` dataclass (`fsm/schema.py`):

```python
@dataclass
class FSMLoop:
    # ... existing fields ...
    artifact_versioning: bool = False       # Loop snapshots artifacts per iteration
    artifact_versioning_ok: bool = False    # Loop intentionally overwrites (suppress MR-5)
```

New validation rule (`fsm/validation.py`):

```python
def _validate_artifact_overwrite(loop: FSMLoop) -> list[ValidationIssue]:
    """MR-5: Warn when harness loop overwrites artifacts without versioning."""
    ...
```

No CLI argument changes. No config file changes. No breaking changes to existing loop YAML — new fields default to `False`.

## Impact

- **Priority**: P2 — Important improvement for debugging and observability of FSM loop runs. Not blocking any current workflow but addresses a systematic gap across 70+ loops.
- **Effort**: Medium — ~13 files to modify, but changes are well-scoped and additive. The oracle fix provides highest leverage (7 loops fixed with one change). Schema changes are straightforward field additions.
- **Risk**: Low — New fields are optional (default `False`). MR-5 is WARNING severity, not ERROR. Snapshot state is a non-destructive copy operation. No breaking changes to existing loop behavior or runtime.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop system design and component architecture |
| [docs/reference/API.md](../../docs/reference/API.md) | FSMLoop dataclass and validation API reference |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | Loop authoring rules and meta-loop design constraints |
| [docs/guides/AUTOMATIC_HARNESSING_GUIDE.md](../../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md) | Harness validation and baseline comparison patterns |

## Labels

`enhancement`, `fsm-loops`, `artifact-versioning`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-05T18:05:12 - `d4a968d6-a27f-4f29-8dc3-b70addddd7c5.jsonl`
- `/ll:wire-issue` - 2026-06-05T17:59:14 - `1c39a1e2-a8e3-432d-a400-4a506a2478ca.jsonl`
- `/ll:refine-issue` - 2026-06-05T17:51:03 - `3eaa6213-01d5-4f45-b1c9-b2a9516f0a10.jsonl`
- `/ll:format-issue` - 2026-06-05T13:35:39 - `c3bd2858-d88a-43f7-8d08-f568c899ef49.jsonl`
- `/ll:capture-issue` - 2026-06-05T04:04:47Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f9cd92c-4c6c-4bd0-906d-86f3c89b4a18.jsonl`
- `/ll:confidence-check` - 2026-06-05T18:03:00Z - `41939cab-9a1f-4c66-8366-bf6fc21a2aba.jsonl`
- `/ll:manage-issue` - 2026-06-05T18:25:24Z - `9edab612-eab6-4879-a972-4253dedf5115.jsonl`

## Status

**Done** | Created: 2026-06-05 | Completed: 2026-06-05 | Priority: P2
