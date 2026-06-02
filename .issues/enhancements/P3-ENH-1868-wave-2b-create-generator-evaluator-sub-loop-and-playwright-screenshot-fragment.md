---
id: ENH-1868
title: "Wave 2b Part 1 \u2014 Create `generator-evaluator` Sub-loop and `playwright_screenshot`\
  \ Fragment"
type: ENH
priority: P3
parent: ENH-1775
size: Large
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-06-02 03:19:16+00:00
status: done
---

# ENH-1868: Wave 2b Part 1 — Create `generator-evaluator` Sub-loop and `playwright_screenshot` Fragment

## Summary

Design and create the new `generator-evaluator` oracle sub-loop at `loops/oracles/generator-evaluator.yaml` and the `playwright_screenshot` fragment in a new `loops/lib/harness.yaml` library. This is the foundational work that ENH-1869 (5 loop conversions) depends on.

## Current Behavior

The 5 harness loops (`html-website-generator`, `html-anything`, `hitl-md`, `p5js-sketch-generator`, `svg-image-generator`) each inline identical Playwright screenshot logic (two structural variants), and there is no shared oracle sub-loop or fragment library for generator-evaluator workflows. Adding or fixing screenshot behavior requires touching all 5 files independently.

## Expected Behavior

A `playwright_screenshot` fragment exists in `scripts/little_loops/loops/lib/harness.yaml` and a `generator-evaluator` oracle sub-loop exists in `scripts/little_loops/loops/oracles/generator-evaluator.yaml`. Both pass `ll-loop validate`. ENH-1869 can then convert the 5 harness loops to thin wrappers that compose against these artifacts.

## Parent Issue

Decomposed from ENH-1775: Wave 2b — Extract `generator-evaluator` Sub-loop and `playwright_screenshot` Fragment

## Proposed Solution

### Step 8: Create `playwright_screenshot` fragment in `scripts/little_loops/loops/lib/harness.yaml`

New fragment library file (does not exist yet). Fragment provides `action_type: shell` with the Playwright screenshot command extracted from the 5 harness loops. The `generator-evaluator` sub-loop's `evaluate` state composes from this fragment. Callers supply the file URL path via context. Follow the fragment definition pattern in `lib/common.yaml` (description + action_type + action + evaluator). The `_BUILTIN_LOOPS_DIR` constant at `fragments.py:38` resolves to `scripts/little_loops/loops/`, so `import: lib/harness.yaml` in a loop YAML resolves to `scripts/little_loops/loops/lib/harness.yaml` via the fallback at `fragments.py:96-98`.

Two structural variants to parameterize:
- Variant A (`html-website-generator.yaml:82`): Uses `${context.run_dir}` directly with `$(pwd)/` prefix, no `2>&1` stderr redirect.
- Variant B (all other loops): Uses `${captured.run_dir.output}`, includes `2>&1` stderr redirect, no `$(pwd)/` prefix.

Both emit `echo "CAPTURED"` and evaluate via `output_contains`. The fragment must parameterize the file path source and source filename (`index.html` vs. `image.svg`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Exact commands per variant (both evaluate via `output_contains: "CAPTURED"`):

**Variant A** (`html-website-generator.yaml:84`, `${context.run_dir}` path form, no `2>&1`):
```sh
playwright screenshot "file://$(pwd)/${context.run_dir}/index.html" "${context.run_dir}/screenshot.png" && echo "CAPTURED"
```

**Variant B** (all other harness loops, `${captured.run_dir.output}` path form, with `2>&1`):
```sh
playwright screenshot "file://${captured.run_dir.output}/index.html" "${captured.run_dir.output}/screenshot.png" 2>&1 && echo "CAPTURED"
```

The fragment must expose two caller-supplied template variables: `file_url` (the `file://` URL to the artifact) and `screenshot_path` (the output `.png` path). The `2>&1` redirect is included by default (Variant B); Variant A callers that need the `$(pwd)/` prefix must override `action:` at the call site — this is consistent with how `parse_tagged_json` in `lib/common.yaml` omits `action:` when nested interpolation prevents a safe default.

**Constraint**: `test_doc_counts.py:137` — `test_lib_fragments_are_not_runnable` automatically exercises `loops/lib/harness.yaml`; `harness.yaml` MUST NOT have an `initial:` field or this test fails.

### Step 1: Design sub-loop interface

Declare `parameters:` on the new sub-loop (following the pattern in `recursive-refine.yaml:19-23`). **Note**: `oracle-capture-issue.yaml` does NOT have a `parameters:` block — it uses `context_passthrough: true` (no declared contract, no `_validate_with_bindings()` enforcement). `generator-evaluator` must use explicit `parameters:` since ENH-1869's 5 wrapper loops invoke it via `with:` bindings; `_validate_with_bindings()` in `validation.py:326` only enforces declared parameters, so omitting the block means silent misbinding with no error. Required params:
- `run_dir` (path)
- `generate_prompt` (string)
- rubric criteria list with weights/thresholds

Optional:
- `pass_threshold` (number, default 6)
- `max_iterations` (number, default 20)
- `timeout` (number, default 7200)

Output: captured critique and final screenshot path.

Must abstract over:
- Whether run_dir comes from `context.` or `captured.`
- Whether pass_threshold is global or per-criterion (hitl-md has 13 per-criterion thresholds)
- Whether criteria are fixed or dynamic (html-anything uses dynamic rubric.md)
- Evaluate error routing behavior (per-loop variation)
- Post-score terminal states (smoke_test, finalize, done)

### Step 2: Extract `generator-evaluator` sub-loop to `scripts/little_loops/loops/oracles/generator-evaluator.yaml`

Compose the evaluate state from the `playwright_screenshot` fragment (`loops/lib/harness.yaml`). Use `import:` + `fragment:` to avoid inlining Playwright logic. Define `on_handoff: spawn` (only `html-website-generator.yaml` uses it; the sub-loop should declare its own independently). Internal states: `generate` (prompt) → `evaluate` (shell: playwright_screenshot fragment) → `score` (prompt: LLM rubric, `output_contains: "ALL_PASS"`) → iterate back to `generate` on no, terminal `done` on yes.

**Key design constraints from variation analysis**:
- Screenshot state name varies: `html-website-generator.yaml` calls it `capture`, others call it `evaluate`. The sub-loop uses `evaluate` internally.
- `on_handoff: spawn` is only present in `html-website-generator.yaml` (line 12); sub-loop declares its own independently.
- Score routing: `score.on_yes` maps to terminal `done` in the sub-loop; parent wrappers then route `on_yes` to their own states (`smoke_test`, `finalize`, or `done`).
- The sub-loop's `score` state MUST be designed as a single identifiable target for ENH-1776's `ll_rubric_score` fragment extraction.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Evaluate state routing** — the sub-loop's evaluate (playwright screenshot) state must declare `on_no` and `on_error`. Three patterns exist in current harness loops:
- `on_no: generate, on_error: failed` — strict: screenshot failure = bad HTML → force regeneration (html-website-generator)
- `on_no: score, on_error: score` — graceful: fall through to LLM scoring even without screenshot (html-anything)
- `on_no: score, on_error: generate` — mixed: bad file triggers regeneration, low-quality screenshot falls through (hitl-md)

Recommended for the sub-loop: `on_no: score, on_error: score` (graceful degradation). This gives the LLM a chance to evaluate intent without visual feedback, and avoids silent infinite loops when Playwright is unavailable in the caller's environment.

**Executor routing** — `executor.py:_execute_sub_loop()` routes sub-loop results as follows (lines 595–608): `terminated_by == "terminal" AND final_state == "done"` → parent's `on_yes`; `terminated_by == "terminal" AND final_state != "done"` → parent's `on_no`; `terminated_by == "error"` → parent's `on_error` if set, else `on_no`. This means the sub-loop MUST use `done` (not any other name) as its success terminal state for parent wrappers' `on_yes` to fire.

Model after `loops/oracles/oracle-capture-issue.yaml` (structure, not parameters approach). See also:
- `loops/loop-router.yaml:334` (`dispatch` state demonstrates `loop:` + `with:` + `capture:` + routing)
- `loops/outer-loop-eval.yaml:55` (`run_sub_loop` state)

### Validation

Run `ll-loop validate scripts/little_loops/loops/oracles/generator-evaluator.yaml` and `ll-loop validate scripts/little_loops/loops/lib/harness.yaml`. Fix any ERROR-severity issues.

### Tests (Step 12, partial)

With TDD mode enabled, all tests for new artifacts belong in this child:

**(a) `TestGeneratorEvaluatorOracle`** in `scripts/tests/test_builtin_loops.py` — follow `TestReadyToImplementGateLoop:4564`. Pattern: class-level `LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/generator-evaluator.yaml"` constant, single `@pytest.fixture` named `data` returning `yaml.safe_load(...)`, per-test access via `data["states"].get("<state>", {})`. Assert: declared parameters block, internal states (`generate`, `evaluate`, `score`), `playwright_screenshot` fragment key in `evaluate` state, terminal `done`.

**(b) `playwright_screenshot` fragment test class** in `scripts/tests/test_fsm_fragments.py` — new class following `TestCommonYamlNewFragments:523`. Pattern: static `_load_harness_yaml()` helper using `Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "harness.yaml"`, three tests per fragment (`_defined_in_harness_yaml`, `_has_correct_action_type` asserting `"shell"`, resolves via `resolve_fragments()`). Integration test: build a minimal loop dict with `import: ["lib/harness.yaml"]` and a state using `fragment: playwright_screenshot`, call `resolve_fragments(raw, loops_dir)`, assert `action_type == "shell"` and `"fragment"` not in resolved state.

**(c) `test_generator_evaluator_is_runnable`** spot-check in `scripts/tests/test_doc_counts.py` — follow `test_oracle_capture_issue_is_runnable:122`. Pattern: build path via `.resolve().parents[1] / "little_loops" / "loops" / "oracles" / "generator-evaluator.yaml"`, guard with `if oracle.exists():`, assert `is_runnable_loop(oracle) is True`.

Run: `python -m pytest scripts/tests/test_builtin_loops.py::TestGeneratorEvaluatorOracle scripts/tests/test_fsm_fragments.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_validation.py -v --tb=short`

## Integration Map

### Files to Create
- `scripts/little_loops/loops/lib/harness.yaml` — new fragment library; `playwright_screenshot` fragment
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — new oracle sub-loop

### Files to Modify
- `scripts/tests/test_builtin_loops.py` — add `TestGeneratorEvaluatorOracle` class
- `scripts/tests/test_fsm_fragments.py` — add `playwright_screenshot` fragment test class
- `scripts/tests/test_doc_counts.py` — add `test_generator_evaluator_is_runnable`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` uses `rglob("*.yaml") + is_runnable_loop()`; `generator-evaluator.yaml` auto-appears in `ll-loop list` output without code change [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — `resolve_loop_path()` and `get_builtin_loops_dir()` resolve the new oracle path; no change needed but path resolution must be tested [Agent 1 finding]
- `scripts/tests/test_ll_loop_commands.py` — tests `cmd_list()` subdirectory discovery with `rglob()`; auto-adapts to new oracle file without code change [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — **HARD COUPLING**: line 163 reads `"65 FSM loops"`; adding `generator-evaluator.yaml` shifts the `rglob`-based count to 66. `ll-verify-docs` (via `verify_documentation()` in `doc_counts.py`) **will fail** until this is updated to `"66 FSM loops"` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — line 3151 reads `"Five libraries ship with little-loops"`; adding `harness.yaml` makes six. Must update to `"Six libraries"` and add a `#### lib/harness.yaml` subsection documenting the `playwright_screenshot` fragment [Agent 2 finding]
- `docs/reference/CLI.md` — `#### ll-loop fragments <lib>` section's bash example block lists `lib/common.yaml`, `lib/cli.yaml`, `lib/benchmark.yaml`, `lib/prompt-fragments.yaml`; add `lib/harness.yaml` [Agent 2 finding]
- `docs/guides/AUDIT_REPORT.md` — line ~90 lists four-item fragment library inventory; add `harness.yaml` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py` — add `test_all_harness_yaml_fragments_have_description` alongside the new fragment class (follows `test_all_cli_yaml_fragments_have_description` at line 1125 — asserts every fragment in the new lib file has a `description` field) [Agent 3 finding]
- `scripts/tests/test_doc_counts.py::TestIsRunnableLoop.test_lib_fragments_are_not_runnable` — auto-exercises `harness.yaml` via `lib_dir.glob("*.yaml")`; passes automatically if `harness.yaml` lacks `initial:` — no code change needed but a constraint on the new file [Agent 3 finding]

### Files Unchanged (but awareness required)
- `scripts/little_loops/fsm/fragments.py:64` — `resolve_fragments()` three-step process: (1) tries `loop_dir / import_path`, falls back to `_BUILTIN_LOOPS_DIR / import_path` (lines 95–98); (2) merges loop's own `fragments:` block; (3) deep-merges each state with `fragment:` key — state fields win, `description:` stripped, `fragment:` key deleted from result
- `scripts/little_loops/fsm/executor.py:502` — `_execute_sub_loop()`: resolves and validates child FSM, injects `with:` bindings overriding child `context:`, clamps child timeout to parent's remaining budget, runs child, routes result: `terminated_by=="terminal" AND final_state=="done"` → `on_yes`; any other terminal → `on_no`; `terminated_by=="error"` → `on_error` else `on_no`
- `scripts/little_loops/fsm/validation.py:326` — `_validate_with_bindings()` only runs when child FSM has a `parameters:` block; checks for unknown keys, missing required params, and type mismatches on non-interpolated literals
- `scripts/little_loops/doc_counts.py` — `is_runnable_loop()` (from `validation.py:1346`): requires `name:` AND `initial:` AND (`states:` or `flow:`); lib fragment files have only `fragments:` and return False; `rglob("*.yaml")` auto-includes new `oracles/generator-evaluator.yaml` and auto-excludes `lib/harness.yaml` if it lacks `initial:`
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` uses `rglob("*.yaml")` + `is_runnable_loop()` filter; new oracle auto-appears

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `README.md` line 163 — change `"65 FSM loops"` → `"66 FSM loops"` (required: `ll-verify-docs` fails otherwise)
2. Update `docs/guides/LOOPS_GUIDE.md` line 3151 — change `"Five libraries"` → `"Six libraries"`; add `#### lib/harness.yaml` subsection documenting the `playwright_screenshot` fragment
3. Update `docs/reference/CLI.md` — add `ll-loop fragments lib/harness.yaml` to the example block in `#### ll-loop fragments <lib>`
4. Update `docs/guides/AUDIT_REPORT.md` line ~90 — add `harness.yaml` to the fragment library inventory list
5. In `scripts/tests/test_fsm_fragments.py` — add `test_all_harness_yaml_fragments_have_description` alongside the new `playwright_screenshot` fragment test class

## Scope Boundary

This child covers only artifact creation and their tests. ENH-1869 handles converting the 5 existing harness loops to thin wrappers, updating their test classes, and all documentation.

**Must not start ENH-1869 until this child is complete and `ll-loop validate` passes.**

## Success Metrics

- `loops/oracles/generator-evaluator.yaml` exists and passes `ll-loop validate`
- `loops/lib/harness.yaml` exists with `playwright_screenshot` fragment, passes `test_lib_fragments_are_not_runnable`
- `TestGeneratorEvaluatorOracle`, playwright_screenshot fragment test, and `test_generator_evaluator_is_runnable` all pass
- No regressions in `test_fsm_fragments.py`, `test_fsm_executor.py`, `test_fsm_validation.py`

## Impact

- **Priority**: P3 — Foundational dependency for ENH-1869 (5 loop thin-wrapper conversions); not user-blocking on its own.
- **Effort**: Large — New YAML artifacts (`lib/harness.yaml`, `oracles/generator-evaluator.yaml`), three new test classes, and doc count updates across README, LOOPS_GUIDE, CLI.md, and AUDIT_REPORT.md.
- **Risk**: Low — Adds new files only; existing 5 harness loops are unchanged until ENH-1869.
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fsm`, `wave-2b`, `oracles`

## Session Log
- `/ll:ready-issue` - 2026-06-02T03:07:34 - `b837481b-1a38-43c3-ae17-eedf6f38b172.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `1758d419-8959-4946-ab38-e7f9cbf959a8.jsonl`
- `/ll:wire-issue` - 2026-06-02T03:00:26 - `10a59d95-6c12-4cb1-b539-7d0b84baca76.jsonl`
- `/ll:refine-issue` - 2026-06-02T02:55:22 - `3673a3c8-2050-4df5-b47a-8461172c76a2.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ecf075d8-f165-4bd9-ad2a-2a2a8e1ddeea.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
