---
id: FEAT-1544
priority: P3
type: FEAT
parent: FEAT-1532
size: Medium
status: done
completed_at: 2026-05-17T06:59:43Z
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1544: Write eval YAML + pytest for loop-specialist full behavioral round-trip

## Summary

Write the eval YAML and pytest that validates the `loop-specialist` agent executes the full monitor → diagnose → contract → refine → verify round-trip against a seeded broken loop fixture. This is the behavioral integration eval for the agent created in FEAT-1543.

## Use Case

A developer creates or modifies the `loop-specialist` agent and wants to verify it correctly executes the full monitoring → diagnosis → contract → refinement → verification workflow. They run `python -m pytest scripts/tests/test_feat1544_loop_specialist_eval.py -v` and get deterministic confirmation that the FSM plumbing is correct and the eval YAML passes schema validation, without needing a live Claude CLI.

## Current Behavior

No eval YAML or pytest exists for the `loop-specialist` agent. The agent was created in FEAT-1543 with a documented diagnosis artifact contract and failure-mode taxonomy, but has zero behavioral test coverage. There is no way to verify the agent's FSM harness is structurally valid or that its round-trip workflow is correctly wired.

## Expected Behavior

An eval YAML at `scripts/little_loops/loops/loop-specialist-eval.yaml` and a pytest at `scripts/tests/test_feat1544_loop_specialist_eval.py` exist. Structural tests pass unconditionally in CI (no live LLM required). An optional `@pytest.mark.slow` + `@pytest.mark.skipif` behavioral class validates the full end-to-end round-trip when a live Claude CLI is available.

## Impact

- **Priority**: P3 - Completes test coverage for the loop-specialist agent; not blocking any active work
- **Effort**: Medium - Follows well-established patterns from `test_outer_loop_eval.py` and `test_create_eval_from_issues.py`; no new infrastructure required
- **Risk**: Low - New files only; no changes to existing production code
- **Breaking Change**: No

## Labels

`testing`, `eval-harness`, `loop-specialist`, `fsm`

## Parent Issue
Decomposed from FEAT-1532: agent-loop-specialist monitors, analyzes, refines-and-optimizes-FSM-loops

## Prerequisite

**Requires FEAT-1543 to be complete.** The agent file `agents/loop-specialist.md` must exist before this eval can be written and run meaningfully. The structural assertions (load_and_validate + validate_fsm) can be written before the agent exists, but the execute state (which calls the real LLM) requires the agent.

## Context

From parent FEAT-1532:

> Write an eval YAML + pytest following `test_create_eval_from_issues.py` VARIANT_A pattern: `execute` state (`action_type: prompt`) drives the agent against a seeded broken loop, `check_skill` state uses `evaluate.type: llm_structured` to assert the contracted predicate fired after the agent called `ll-loop run --max-iterations 1`. Structural assertions follow `test_outer_loop_eval.py` pattern (`load_and_validate` + `validate_fsm`). The eval must cover the full contract → refine → verify round-trip, not just static diagnosis.

**Verification tooling (from codebase research)**:
- `ll-loop run <name> --max-iterations 1` is the only invocation that calls the real LLM; `ll-loop simulate --scenario` uses `SimulationActionRunner` returning synthetic strings and CANNOT verify content predicates
- `ll-loop test <loop> --state <name>` is only valid for shell-action states  
- No `--start-state` flag exists; to verify a non-initial state, reach it via `--max-iterations N` from initial or test a shell state via `ll-loop test`

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Create
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — eval FSM with `category: harness`, `initial: execute`, `action_type: prompt` execute state, `check_skill` state with `evaluate.type: llm_structured`, terminal `done`
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — pytest with `TestLoopSpecialistEvalFile` (structural) + `TestLoopSpecialistEvalStates` (per-state) + optional behavioral class
- `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` — seeded broken loop (model after `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — verify state's `on_no` self-loops with no escape path)

### Pattern Files to Model After (read these first)
- `scripts/tests/test_create_eval_from_issues.py:25-65` — `VARIANT_A_YAML` inline constant (the canonical eval-harness YAML shape)
- `scripts/tests/test_create_eval_from_issues.py:142-210` — `TestEvalHarnessVariantA` class (structural assertion idioms)
- `scripts/tests/test_create_eval_from_issues.py:337-342` — `test_variant_a_passes_fsm_validation` (tmp-file + `load_and_validate` + `validate_fsm` form)
- `scripts/tests/test_outer_loop_eval.py:1-37, 122-130` — `TestOuterLoopEvalFile.test_validates_as_fsm` (validator-on-real-file form)
- `scripts/tests/test_outer_loop_eval.py:61-151` — `TestOuterLoopEvalStates` (per-state action_type/capture/routing assertions)
- `scripts/little_loops/loops/outer-loop-eval.yaml:80-92` — live example of `evaluate.type: llm_structured` with `source:` override + `min_confidence: 0.7`
- `scripts/little_loops/loops/harness-multi-item.yaml:118-134` — live `check_skill` state with slash_command + llm_structured

### Imports the New Test Will Need
- `from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm` (defined at `scripts/little_loops/fsm/validation.py:32, 616, 783`)
- `from pathlib import Path`; `import yaml`; `import pytest`
- For mocked behavioral path: `from unittest.mock import patch, MagicMock` + see `scripts/tests/test_fsm_evaluators.py:550-578` (`TestLLMStructuredEvaluator`) for the canonical mock of `little_loops.fsm.evaluators.subprocess.run`

### CLI Invocation Contracts (for the agent under test)
- `ll-loop run <name> --max-iterations 1` (`scripts/little_loops/cli/loop/run.py:cmd_run`, line 380) — only path that hits the real LLM via `DefaultActionRunner`; `FSMExecutor.run()` (`scripts/little_loops/fsm/executor.py:248`) caps at 1 iter and returns exit code 1 via `EXIT_CODES["max_iterations"]` (`scripts/little_loops/cli/loop/_helpers.py:29`)
- `ll-loop simulate --scenario` (`scripts/little_loops/cli/loop/testing.py:cmd_simulate`, line 175) uses `SimulationActionRunner.run()` (`scripts/little_loops/cli/loop/runners.py:191`) which returns the literal string `"[simulated output for: <action>]"` — CANNOT validate content predicates
- `ll-loop test <loop> --state <name>` (`scripts/little_loops/cli/loop/testing.py:cmd_test`) — shell-action states only

### Agent Under Test (already exists per FEAT-1543)
- `agents/loop-specialist.md` — defines the failure-mode taxonomy (lines 55-63): `ambiguous-output`, `infinite-cycle`, `premature-termination`, `feature-stubbing`, `drift`, `self-evaluation bias`
- Diagnosis artifact contract (lines 69-110): writes `.loops/diagnostics/<loop>-<UTC-timestamp>.md` with sections `## Failure modes observed`, `## Evidence`, `## Intended contract`, `## Proposed change`, `## Verification`, `## Open questions`
- Verification step (line 116): "re-run a single real iteration with `ll-loop run <name> --max-iterations 1`"
- No existing Python code writes to `.loops/diagnostics/` — the agent itself does it via Bash (`mkdir -p` then write). Test must check the directory after agent runs

### Schema Reference
- `EvaluateConfig.from_dict` at `scripts/little_loops/fsm/schema.py:122`
- `EVALUATOR_REQUIRED_FIELDS["llm_structured"] = []` at `scripts/little_loops/fsm/validation.py:69` (no required fields, but prompt non-empty per convention)
- `DEFAULT_LLM_SCHEMA` at `scripts/little_loops/fsm/evaluators.py:59-84` — verdict (`yes|no|blocked|partial`) + confidence (0-1) + reason

### Conftest Fixtures Available
- `scripts/tests/conftest.py:29-33` — `fixtures_dir`, `fsm_fixtures` (path to `scripts/tests/fixtures/fsm/`)
- `scripts/tests/conftest.py:229-235` — `temp_project_dir`

### Files to Modify (mandatory — not just create)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **MANDATORY**: add `"loop-specialist-eval"` to the hardcoded `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` (line ~65). This test asserts `expected == actual` with exact set equality; adding the new YAML to `loops/` without updating this set will cause an `AssertionError` in CI.
- `scripts/little_loops/loops/README.md` — add a row for `loop-specialist-eval` in the "Harness / Templates" section (around line 96-103) to keep the loop catalog current.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — update `test_expected_loops_exist`: add `"loop-specialist-eval"` to `expected` set. All four dynamic sweep tests (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field`, `test_no_bare_pass_token_in_output_contains`) will auto-cover the new YAML via `BUILTIN_LOOPS_DIR.glob("*.yaml")` — no separate changes needed for those.
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — new file (already in plan); add a third class `TestBrokenVerifyFixture` mirroring the `TestAssessLoopSkill` pattern from `scripts/tests/test_audit_loop_run_skill.py:30-227`. Load `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` explicitly and assert: it parses cleanly (`load_and_validate` + `validate_fsm` → no ERROR), its `verify` state has `on_no: verify` (the self-loop pathology), and the state has an `llm_structured` evaluator. This isolates the fixture's semantic intent from the eval YAML's tests.

### Auto-Coverage Note

_Wiring pass added by `/ll:wire-issue`:_
The following tests in `test_builtin_loops.py` will automatically exercise `loop-specialist-eval.yaml` once placed in `loops/` — no additional work needed, but the new YAML must satisfy their constraints:
- `test_all_have_description_field` — eval YAML **must** have a non-empty top-level `description:` field or this sweep fails
- `test_all_validate_as_valid_fsm` — eval YAML must pass `load_and_validate` + `validate_fsm` with no `ERROR`-severity results
- `test_all_parse_as_yaml` — eval YAML must be valid YAML
- `test_no_bare_pass_token_in_output_contains` — no `output_contains.pattern: "PASS"` (already satisfied by using `llm_structured`)

## Proposed Approach

_Added by `/ll:refine-issue`:_

There are two viable approaches for the behavioral assertion (the structural assertion path is the same in both):

### Option A: Mock the LLM subprocess (recommended for CI)

> **Selected:** Option A — mocked subprocess gives deterministic CI coverage via 9 existing patch-site precedents (score: 12/12)

Follow `scripts/tests/test_fsm_evaluators.py:550-578` (`TestLLMStructuredEvaluator`) — patch `little_loops.fsm.evaluators.subprocess.run` to return canned `{"verdict": "yes", "confidence": 0.9, "reason": "..."}` payloads. Drive `FSMExecutor.run()` directly (in-process, not via CLI subprocess) on a fixture eval YAML against the seeded broken loop. Assert that the recorded route transitions follow `execute → check_skill → done` and that the agent contract (writing a diagnosis artifact) is exercised by intercepting the prompt action.

**Pros**: Deterministic, fast, runs in CI unconditionally. Matches existing project convention (`test_fsm_evaluators.py` mocks rather than skips).
**Cons**: Doesn't validate the actual loop-specialist prompt produces the expected behavior — only validates the FSM plumbing.

### Option B: Live LLM behavioral test guarded by `pytest.mark.skipif`

Use the per-method skip pattern from `scripts/tests/test_transport.py:265` adapted to a `shutil.which("claude")` check (no precedent for this exact guard in the codebase, but `test_codex_adapter.py:27-28` uses the analogous `shutil.which("bash")` module-level form). The test invokes `ll-loop run loop-specialist-eval --max-iterations N` as a real subprocess, then asserts `.loops/diagnostics/*.md` was created with the expected sections AND that the contracted predicate fired (route transition observed in `.loops/.history/`).

**Pros**: Validates the full round-trip end-to-end, including whether the agent prompt is actually well-formed enough to drive the contract → refine → verify loop.
**Cons**: Slow, non-deterministic, requires a live `claude` CLI; will be skipped in standard CI.

### Recommended split

Ship both: Option A for the always-on structural + plumbing test (in `test_feat1544_loop_specialist_eval.py`), and Option B as a separate behavioral test marked `@pytest.mark.skipif(shutil.which("claude") is None, ...)` and `@pytest.mark.slow`. This matches the issue's acceptance criterion "tests pass in CI (or are marked with appropriate skip conditions if requiring live LLM)".

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-17.

**Selected**: Option A — Mock the LLM subprocess (recommended for CI)

**Reasoning**: Option A achieves a perfect 12/12 score because all three core mechanisms — `patch("little_loops.fsm.evaluators.subprocess.run")` (9 existing call sites), `FSMExecutor.run()` in-process with `MockActionRunner` (30+ call sites), and `load_and_validate` + `validate_fsm` structural assertions — are directly reusable without new infrastructure. Option B scores 5/12 due to non-deterministic LLM behavior, the absence of any `shutil.which("claude")` guard precedent in the test suite, and zero existing tests invoking `ll-loop run` as an out-of-process subprocess. Option B is not excluded — per the "Recommended split," ship it as a supplementary `@pytest.mark.slow` + `@pytest.mark.skipif` behavioral class in the same file.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 2/3 | 1/3 | 1/3 | 1/3 | 5/12 |

**Key evidence**:
- **Option A**: `patch("little_loops.fsm.evaluators.subprocess.run")` appears 9 times across `test_fsm_evaluators.py` and `test_fsm_executor.py`; `MockActionRunner` + `FSMExecutor.run()` in-process has 30+ call sites — zero new infrastructure required.
- **Option B**: No existing `shutil.which("claude")` guard anywhere in the test suite; no existing test invokes `ll-loop run` as an out-of-process subprocess; non-deterministic LLM output makes CI assertions fragile without significant scaffolding.

## Acceptance Criteria

- [ ] Eval YAML exists (e.g., `scripts/little_loops/loops/loop-specialist-eval.yaml`) with valid FSM schema (passes `load_and_validate` + `validate_fsm`)
- [ ] `execute` state uses `action_type: prompt` to drive the loop-specialist agent against a seeded broken fixture loop
- [ ] `check_skill` state uses `evaluate.type: llm_structured` to assert the agent (a) wrote a diagnosis artifact to `.loops/diagnostics/`, (b) called `ll-loop run --max-iterations 1` to verify, and (c) the contracted predicate fired (transition routing changed after the edit)
- [ ] Pytest covers the full contract → refine → verify round-trip (not just static diagnosis)
- [ ] Structural pytest assertions follow `test_outer_loop_eval.py` pattern
- [ ] Eval file is listed or discoverable; tests pass in CI (or are marked with appropriate skip conditions if requiring live LLM)

## Implementation Steps

1. **Read the pattern sources** before writing anything:
   - `scripts/tests/test_create_eval_from_issues.py:25-65` (VARIANT_A_YAML) and `:142-210` (TestEvalHarnessVariantA)
   - `scripts/tests/test_outer_loop_eval.py:1-37, 61-151` (validator pattern + per-state assertions)
   - `scripts/little_loops/loops/outer-loop-eval.yaml:80-92` (live `source:` override example)
   - `agents/loop-specialist.md` lines 55-63, 69-110, 116 (failure-mode taxonomy, artifact contract, verification step)

2. **Create the seeded broken fixture** at `scripts/tests/fixtures/fsm/broken-verify-loop.yaml`. Model after `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml`: a `verify` state whose `evaluate.type: llm_structured` prompt asks for a `PASS` verdict, but the action emits ambiguous output (e.g., "Looks mostly okay") — exemplifies the `ambiguous-output` failure mode from `agents/loop-specialist.md:55-63`. Route `on_no: verify` (no escape).

3. **Write the eval YAML** at `scripts/little_loops/loops/loop-specialist-eval.yaml` with this skeleton:
   ```yaml
   name: loop-specialist-eval
   category: harness
   initial: execute
   max_iterations: 5
   timeout: 1800
   context:
     broken_loop_path: "scripts/tests/fixtures/fsm/broken-verify-loop.yaml"
   states:
     execute:
       action: >
         Use the loop-specialist agent against ${context.broken_loop_path}.
         Follow the full monitor → diagnose → contract → refine → verify workflow.
         Write the diagnosis artifact to .loops/diagnostics/ per the agent contract,
         then re-run via `ll-loop run <name> --max-iterations 1` to verify.
       action_type: prompt
       agent: loop-specialist
       capture: agent_run
       timeout: 600
       next: check_skill
     check_skill:
       action: >
         Inspect what the loop-specialist agent did on the broken fixture.
       action_type: prompt
       timeout: 180
       evaluate:
         type: llm_structured
         source: "${captured.agent_run.output}"
         prompt: >
           Did the loop-specialist agent complete the full round-trip?
           Answer YES only if ALL of the following are true:
           (1) A diagnosis artifact was written to .loops/diagnostics/<loop>-<ts>.md
               with sections "## Failure modes observed", "## Evidence",
               "## Proposed change", "## Verification"
           (2) The agent invoked `ll-loop run <name> --max-iterations 1` for verification
           (3) The contracted predicate fired AFTER the edit (route transition
               changed compared to the broken baseline)
         min_confidence: 0.7
       on_yes: done
       on_no: execute
     done:
       terminal: true
   ```

4. **Write pytest** at `scripts/tests/test_feat1544_loop_specialist_eval.py` with two classes:
   - `TestLoopSpecialistEvalFile` — module-level `LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-specialist-eval.yaml"`; `test_validates_as_fsm` using `load_and_validate` + `validate_fsm` (filter to `ValidationSeverity.ERROR`); `test_name`, `test_initial_state`, `test_category_is_harness`, `test_terminal_done`
   - `TestLoopSpecialistEvalStates` — `REQUIRED_STATES = {"execute", "check_skill", "done"}`; `test_execute_is_prompt_with_agent`; `test_check_skill_has_llm_structured_evaluator`; `test_check_skill_routes_on_yes_to_done`; `test_check_skill_routes_on_no_to_execute`
   - Optional `TestLoopSpecialistEvalBehavioral` — behavioral assertion, gated by `@pytest.mark.skipif(shutil.which("claude") is None, reason="live LLM required")` per the Proposed Approach section (Option B)

5. **Run the structural tests**:
   ```bash
   python -m pytest scripts/tests/test_feat1544_loop_specialist_eval.py -v
   ll-loop validate loop-specialist-eval
   ```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_builtin_loops.py` — add `"loop-specialist-eval"` to the `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` (line ~65). Do this in the same commit as or immediately after creating `loop-specialist-eval.yaml` to avoid breaking CI.

7. Ensure the eval YAML has a non-empty top-level `description:` field — `test_all_have_description_field` in `TestBuiltinLoopFiles` sweeps every YAML in `BUILTIN_LOOPS_DIR` and will fail without it.

8. Update `scripts/little_loops/loops/README.md` — add a row for `loop-specialist-eval` in the "Harness / Templates" section (currently lines 96-103). Follow the existing row format used for other harness entries (`harness-optimize`, `harness-multi-item`, etc.).

9. Add `TestBrokenVerifyFixture` class to `scripts/tests/test_feat1544_loop_specialist_eval.py` — mirror the `TestAssessLoopSkill` pattern from `scripts/tests/test_audit_loop_run_skill.py:30-227` to assert the fixture's specific pathology (`on_no: verify` self-loop).

## Files to Create

- `scripts/little_loops/loops/loop-specialist-eval.yaml` — eval FSM definition
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — pytest with structural + behavioral assertions
- `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` — seeded broken fixture (note: `fsm/` subdirectory, matching the pattern reference in the Integration Map above)

## Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — add `"loop-specialist-eval"` to `expected` set in `test_expected_loops_exist` (mandatory)
- `scripts/little_loops/loops/README.md` — add harness catalog row for `loop-specialist-eval`

## Related

- Parent: FEAT-1532
- Prerequisite child: FEAT-1543 (agent must exist first)

## Resolution

Implemented via `/ll:manage-issue` on 2026-05-17.

**Files created:**
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — eval FSM (category: harness, initial: execute, execute→check_skill→done, llm_structured evaluator with source override)
- `scripts/tests/test_feat1544_loop_specialist_eval.py` — 25 tests: TestLoopSpecialistEvalFile (8), TestLoopSpecialistEvalStates (8), TestBrokenVerifyFixture (8), TestLoopSpecialistEvalBehavioral (1, skipif)
- `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` — seeded fixture: verify state self-loops via on_no (ambiguous-output failure mode)

**Files modified:**
- `scripts/tests/test_builtin_loops.py` — added `"loop-specialist-eval"` to expected set in test_expected_loops_exist
- `scripts/little_loops/loops/README.md` — added row in Harness/Templates section

All 25 structural tests pass in CI (0 live LLM required). Behavioral class is gated by @pytest.mark.skipif(shutil.which("claude") is None).

## Session Log
- `/ll:ready-issue` - 2026-05-17T06:56:27 - `51a66358-79c9-4b90-a353-1ad5d5387149.jsonl`
- `/ll:confidence-check` - 2026-05-17T07:00:00Z - `ef9ca494-2be9-4304-94ae-01645da1598c.jsonl`
- `/ll:decide-issue` - 2026-05-17T06:51:37 - `0ad726dc-f84b-4588-b026-51f74db04434.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `03e36d1b-d310-479e-800b-33f687338d1c.jsonl`
- `/ll:wire-issue` - 2026-05-17T06:42:54 - `87a7c4bc-9a32-4209-86b1-fe1931bcd7b6.jsonl`
- `/ll:refine-issue` - 2026-05-17T06:37:08 - `c15321a7-dce4-49df-a764-c95bf09bf56f.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `1f2aa363-89b4-48fb-b7e2-882be8ac2cc8.jsonl`
- `/ll:manage-issue` - 2026-05-17T06:59:43Z - implementation complete

---

**Done** | Created: 2026-05-17 | Completed: 2026-05-17 | Priority: P3
