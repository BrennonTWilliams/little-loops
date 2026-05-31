---
id: ENH-1795
type: ENH
title: Action-level loop detection (complement to diff_stall)
priority: P3
status: done
captured_at: '2026-05-29T20:37:23Z'
completed_at: '2026-05-31T22:30:16Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- captured
- fsm
- stall-detector
- loops
- harness
relates_to:
- BUG-1767
- BUG-1766
parent: EPIC-1663
confidence_score: 94
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
decision_needed: false
---

# ENH-1795: Action-level loop detection (complement to `diff_stall`)

## Summary

Add a second stall-detection mode to the harness that fires when the
**same action string** or **same captured output** repeats for N
consecutive iterations, regardless of git diff state. Today `check_stall`
(`diff_stall` evaluator) only catches "no file changes" stalls; it misses
the symmetric failure where a skill *does* mutate files but keeps
executing the identical no-op action (or the same skill invocation
producing the same output text).

## Motivation

This enhancement would:
- Prevent silent exhaustion of `max_iterations` when a loop has converged
  to a fixed point that `diff_stall` can't detect because the skill mutates
  files on each pass
- Reduce wasted LLM token costs from repeated identical action executions
  in loops that have already reached their effective output
- Complement existing `diff_stall` to provide robust stall-detection
  coverage across both "no changes" and "identical changes" failure modes

## Current Behavior

- `check_stall.evaluate.type: diff_stall` records `git diff --stat`
  output and fingerprints `progress_paths`; if the fingerprint changes,
  the deque resets and the stall window restarts (per BUG-1674 / -1767).
- A loop that keeps calling, say, `/ll:refine-issue ${captured.current_item.output}`
  and gets back the identical "already refined" output for 10 cycles
  produces no `diff_stall` signal as long as anything in the working
  tree changes.
- The harness silently exhausts `max_iterations` even though the loop
  has visibly converged to a fixed point.

DeerFlow's `LoopDetectionMiddleware` hard-stops on repeated tool-call
patterns; we have nothing analogous at the action / output level.

## Expected Behavior

A new evaluator (working name `action_stall` or `output_repeat`) that:

1. Records a hash of (state, expanded action string, captured output)
   per iteration.
2. Fires `no` after `max_repeat` consecutive identical hashes (default
   `2`).
3. Composes with `diff_stall` — either evaluator can short-circuit the
   chain; both are cheap.
4. Reports the repeated payload in the `LLEvent` so the operator can
   see *what* repeated.

Example:

```yaml
check_action_stall:
  action_type: shell
  action: "echo 'probe'"
  evaluate:
    type: action_stall
    track: ["action", "captured.execute.output"]
    max_repeat: 2
  on_yes: check_concrete
  on_no: advance
```

## Proposed Solution

Add a new `action_stall` evaluator alongside the existing `diff_stall`
evaluator in `scripts/little_loops/fsm/evaluators.py`, following the same pattern:

- **Function**: Add `evaluate_action_stall(track: list[str], max_repeat: int = 2) -> EvaluationResult` to `scripts/little_loops/fsm/evaluators.py` — hashes tracked capture keys per iteration; maintains a bounded deque; fires `no` when `max_repeat` consecutive identical hashes detected
- **Dispatcher wiring**: Add `elif eval_type == "action_stall"` branch in `evaluate()` in `evaluators.py`; add `"action_stall"` to `_EXIT_CODE_AWARE_EVALUATORS` frozenset
- **Validator**: add `"action_stall": []` to `EVALUATOR_REQUIRED_FIELDS` in `scripts/little_loops/fsm/validation.py`
- **LLEvent payload**: include the repeated payload hash and iteration
  indices so the operator can see *what* repeated

The evaluator composes with `diff_stall` — both sit in the routing chain and
either can short-circuit to `advance` when their respective stall condition
is met.

## Success Metrics

- Loops with output-repeat stalls: detected within `max_repeat` (default 2)
  iterations vs exhausting `max_iterations` (current behavior)
- False positive rate: 0% on loops with genuine iterative progress where
  actions repeat but captured output differs
- Per-iteration overhead: <1ms for hash computation and deque comparison
- Adoption: existing loops can opt in with a 4-line YAML block

## Scope Boundaries

- **In scope**:
  - New `evaluate_action_stall()` function in `scripts/little_loops/fsm/evaluators.py`
  - Dispatcher wiring in the `evaluate()` function in `evaluators.py`
  - Validator support in `ll-loop validate`
  - `LLEvent` payload reporting of repeated content hash and iteration indices
  - Configuration via `track` field (list of capture keys to hash) and
    `max_repeat` threshold (default 2)
  - Composition with existing `diff_stall` evaluator (both in routing chain)
- **Out of scope**:
  - Replacing or modifying existing `diff_stall` evaluator behavior
  - Auto-detecting which actions to track (user configures via YAML)
  - ML-based or fuzzy detection of "near-repeat" patterns
  - Integration with DeerFlow or other external loop detection systems

## API/Interface

New evaluator class:

```python
class ActionStallEvaluator:
    """Detect repeated action/output patterns that indicate stalled loops."""
    def evaluate(self, track: list[str], max_repeat: int = 2) -> bool: ...
```

YAML configuration interface (per-loop, in loop YAML):

```yaml
evaluate:
  type: action_stall
  track: ["action", "captured.execute.output"]
  max_repeat: 2
```

No changes to existing evaluator interfaces or public CLI surface.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — Add `evaluate_action_stall()` function; add `"action_stall"` branch to `evaluate()` dispatcher (mirrors `elif eval_type == "diff_stall"` pattern); add `"action_stall"` to `_EXIT_CODE_AWARE_EVALUATORS` frozenset
- `scripts/little_loops/fsm/schema.py` — Add `track: list[str]` and `max_repeat: int = 2` fields to `EvaluateConfig`; extend `EvaluateConfig.type` `Literal[...]` with `"action_stall"`; update `from_dict`/`to_dict` following `scope`/`max_stall` pattern
- `scripts/little_loops/fsm/validation.py` — Add `"action_stall": []` to `EVALUATOR_REQUIRED_FIELDS`; add type-specific validation block for `max_repeat >= 1` in `_validate_evaluator()` (mirrors `if evaluate.type == "diff_stall"` block); update MR-1 error prose in `_validate_meta_loop_evaluation()` to include `action_stall` in the human-readable non-LLM evaluator list
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Add `action_stall` entry to § Stall Detection with composition guidance
- `scripts/little_loops/loops/lib/common.yaml` — Add `action_stall_gate` fragment after ENH-1777 adds `diff_stall_gate` (keeps fragment library symmetric)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `"action_stall"` to `definitions.evaluateConfig.properties.type.enum`; add `track` (array of string) and `max_repeat` (integer, minimum 1) to `definitions.evaluateConfig.properties` (required because the schema uses `additionalProperties: false`) [Agent 2 finding]

### Dependent Files (Callers/Importers)
- No existing callers — `action_stall` is opt-in via loop YAML; no built-in loops use it yet
- `scripts/little_loops/fsm/executor.py` — No changes needed; `FSMExecutor._evaluate()` already routes through `evaluate()` dispatcher and emits events via `_emit("evaluate", {"type": ..., "verdict": ..., **result.details})` automatically
- `scripts/little_loops/loops/harness-single-shot.yaml` — Reference loop showing the standalone `check_stall` gate pattern to follow for `action_stall` usage examples
- `scripts/little_loops/loops/harness-multi-item.yaml` — Same reference

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `_EVALUATE_TYPE_DISPLAY` dict can receive `"action_stall": "action stall"` entry for display quality in `ll-loop show`; falls back to raw string if absent (no-break, but add for completeness alongside `diff_stall`) [Agent 2 finding]
- `scripts/little_loops/cli/loop/testing.py` — Calls `evaluate()` dispatcher generically; no changes needed; included for awareness [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:evaluate_diff_stall` — Primary implementation pattern: filesystem-backed state under `.loops/tmp/` with MD5 cache key, `EvaluationResult(verdict, details)` return shape, stall counter + reset-on-progress logic
- `scripts/little_loops/fsm/stall_detector.py:StallDetector` — Sliding-window `deque(maxlen=window)` pattern for tracking repeated values across iterations (analogous shape needed per-evaluator-instance for `action_stall`)

### Tests
- `scripts/tests/test_fsm_evaluators.py:TestDiffStallEvaluator` (line 1062) — Primary test template; add `TestActionStallEvaluator` class in same file using the same fixture pattern (`clean_state_files` autouse with `monkeypatch.chdir(tmp_path)` for state-file isolation)
- `scripts/tests/test_fsm_validation.py:TestHarborScorerEvaluatorValidation` (line 345) — Template for evaluator-type validation tests; add `TestActionStallEvaluatorValidation` covering `max_repeat >= 1` constraint

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py:TestEvaluateDispatcher.test_dispatch_exit_code_124_short_circuits_to_error` (line 551) — **Update**: add `"action_stall"` to the parametrize list (it is in `_EXIT_CODE_AWARE_EVALUATORS` and exempt from exit-code-124 short-circuit, like `diff_stall`) [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py:TestEvaluateDispatcher.test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` (line 621) — **Update**: add `"action_stall"` to parametrize list (same BUG-1815 exemption rationale) [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — **New tests**: add `test_action_stall_evaluator_type_is_valid`, `test_action_stall_round_trips_through_dict` (including `track`/`max_repeat` fields), `test_action_stall_to_dict_omits_defaults`; follow pattern at lines 1859–1883 (`test_mcp_result_evaluator_type_is_valid` and `test_harbor_scorer_evaluator_type_is_valid`) [Agent 3 finding]
- `scripts/tests/test_fsm_schema_fuzz.py:malformed_evaluate_config` (line 44) — **Update**: add `"action_stall"` to the `valid_types` hard-coded list (currently missing `diff_stall` and `mcp_result` too) [Agent 3 finding]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Add `action_stall` entry to § Stall Detection
- `docs/reference/EVENT-SCHEMA.md` — Document the new evaluate event payload keys emitted when `type: action_stall` fires

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Add new row for `action_stall` in the evaluators table (§ Evaluators); update exit-code exempt list prose (~line 1635) which explicitly names exempt evaluator types [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — Append `action_stall` to the inline YAML comment enumerating evaluator types (~line 305); also the § `diff_stall` reference section [Agent 2 finding]
- `docs/reference/API.md` — Add `action_stall` to the comment block listing known evaluator types (~line 4224) [Agent 2 finding]
- `docs/reference/CLI.md` — Add `action_stall` to the MR-1 description paragraph's explicit list of non-LLM evaluator types (~line 460) [Agent 2 finding]

### Configuration
- N/A — Evaluator is configured per-loop in loop YAML; no global config changes needed

## Implementation Steps

1. Study existing `diff_stall` evaluator as reference pattern
2. Implement `ActionStallEvaluator` class with hash tracking, bounded
   deque, and `max_repeat` threshold
3. Register evaluator in runner routing chain alongside `diff_stall`
4. Add validator support in `ll-loop validate` (known evaluator types list)
5. Wire `action_stall` result into `LLEvent` payload for operator visibility
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Stall Detection
   with action_stall entry and composition guidance
7. Write tests for hash tracking, reset-on-change behavior, and composition
   with `diff_stall`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Read the reference**: `evaluate_diff_stall()` in `scripts/little_loops/fsm/evaluators.py` — study the `.loops/tmp/` file-backed state pattern; `evaluate_action_stall` needs the same persistence shape (state files survive process-per-iteration spawning)
2. **Implement function**: Add `evaluate_action_stall(track: list[str], max_repeat: int = 2) -> EvaluationResult` to `scripts/little_loops/fsm/evaluators.py`; hash the tracked capture keys' values each iteration; compare against stored deque; fire `verdict="no"` when `max_repeat` consecutive identical hashes are seen
3. **Wire dispatcher**: In `evaluate()` in `evaluators.py`, add `elif eval_type == "action_stall": return evaluate_action_stall(track=config.track, max_repeat=config.max_repeat)` (immediately after the `diff_stall` branch)
4. **Exempt from exit-code guard**: Add `"action_stall"` to `_EXIT_CODE_AWARE_EVALUATORS` frozenset in `evaluators.py` (same rationale as `diff_stall` — the probe action exit code is irrelevant)
5. **Schema**: In `scripts/little_loops/fsm/schema.py:EvaluateConfig`, add `track: list[str] = field(default_factory=list)` and `max_repeat: int = 2`; extend `type` `Literal[...]` with `"action_stall"`; update `from_dict`/`to_dict` following `scope`/`max_stall` patterns
6. **Validator**: In `scripts/little_loops/fsm/validation.py`, add `"action_stall": []` to `EVALUATOR_REQUIRED_FIELDS` (auto-enrolls as `NON_LLM_EVALUATOR_TYPES`); add `max_repeat >= 1` check in `_validate_evaluator()`
7. **Tests**: Add `TestActionStallEvaluator` class to `scripts/tests/test_fsm_evaluators.py` after `TestDiffStallEvaluator`; use `monkeypatch.chdir(tmp_path)` autouse fixture for state-file isolation; add validation tests to `scripts/tests/test_fsm_validation.py` following `TestHarborScorerEvaluatorValidation` at line 345
8. **Verify**: `python -m pytest scripts/tests/test_fsm_evaluators.py scripts/tests/test_fsm_validation.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/fsm/fsm-loop-schema.json` — add `"action_stall"` to `definitions.evaluateConfig.properties.type.enum`; add `track` (array-of-string) and `max_repeat` (integer, min 1) to `definitions.evaluateConfig.properties` (schema uses `additionalProperties: false` — new fields must be declared or loop YAML will fail JSON Schema validation)
10. Update `scripts/tests/test_fsm_evaluators.py` — add `"action_stall"` to parametrize list in `test_dispatch_exit_code_124_short_circuits_to_error` (line 551) and `test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` (line 621)
11. Add schema tests to `scripts/tests/test_fsm_schema.py` — `test_action_stall_evaluator_type_is_valid`, `test_action_stall_round_trips_through_dict` (with `track`/`max_repeat` fields), `test_action_stall_to_dict_omits_defaults`; follow pattern at lines 1859–1883
12. Update `scripts/tests/test_fsm_schema_fuzz.py:malformed_evaluate_config` (line 44) — add `"action_stall"` to `valid_types` list
13. Update `docs/guides/LOOPS_GUIDE.md` — add row for `action_stall` in evaluators table; add `action_stall` to exit-code exempt prose (~line 1635)
14. Update `docs/generalized-fsm-loop.md` and `docs/reference/API.md` and `docs/reference/CLI.md` — add `action_stall` to evaluator type enumerations in inline comments / prose

## Impact

- **Priority**: P3 — high-utility second guard; doesn't block existing
  loops but materially improves cost behavior of prompt-based skills.
- **Effort**: Small-to-Medium — new evaluator class, runner wiring,
  validator entry, docs.
- **Risk**: Low — opt-in; default behavior unchanged.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Stall Detection | Phase ordering and decision guide need a second entry |
| `BUG-1767` | Documents the related blind spot in progress_paths fingerprinting |

## Labels

`captured`, `fsm`, `harness`, `loops`, `stall-detector`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-31_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- **Wrong integration map throughout**: The issue specifies `scripts/little_loops/evaluators/action_stall.py` (no such directory), `scripts/little_loops/runner.py` (doesn't exist), and `scripts/little_loops/validators/loop_validator.py` (doesn't exist). All implementation lives under `scripts/little_loops/fsm/`: add to `fsm/evaluators.py`, `fsm/validation.py`, `fsm/schema.py`, `fsm/__init__.py`.
- **Dependent Files are TBD**: Run `grep -r "diff_stall" scripts/` and `grep -r "check_stall" loops/` before implementing to confirm no additional wiring points.

## Resolution

Implemented `evaluate_action_stall()` in `scripts/little_loops/fsm/evaluators.py` using file-backed
state (matching `diff_stall` pattern). Hashes tracked context values per iteration; fires `no` after
`max_repeat` consecutive identical hashes.

Changes:
- `fsm/evaluators.py`: new `evaluate_action_stall()` function + dispatcher wiring + `_EXIT_CODE_AWARE_EVALUATORS` entry
- `fsm/schema.py`: `"action_stall"` type + `track`/`max_repeat` fields
- `fsm/validation.py`: `EVALUATOR_REQUIRED_FIELDS` entry + `max_repeat >= 1` constraint + MR-1 prose update
- `fsm/fsm-loop-schema.json`: new type enum entry + `track`/`max_repeat`/`scope`/`max_stall` properties
- `cli/loop/info.py`: display name entries for `diff_stall` and `action_stall`
- 4 test files: `TestActionStallEvaluator` (8 tests), `TestActionStallEvaluatorValidation` (4 tests), 3 schema tests, fuzz valid_types update
- 6 doc files: AUTOMATIC_HARNESSING_GUIDE, LOOPS_GUIDE, generalized-fsm-loop, API.md, CLI.md, EVENT-SCHEMA.md

509 tests pass, lint clean.

## Status

**Done** | Created: 2026-05-29 | Completed: 2026-05-31 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-31T22:18:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9a2bb36-dbbb-4420-a5a0-0029bcd82e36.jsonl`
- `/ll:confidence-check` - 2026-05-31T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ea265ad-1402-4546-a112-a466fe729689.jsonl`
- `/ll:wire-issue` - 2026-05-31T22:11:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2f45ba3-0f67-402a-81ca-f5ae24fec63d.jsonl`
- `/ll:refine-issue` - 2026-05-31T22:05:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9893e753-0bc1-49e0-b62b-fa1db5abda47.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3598727d-c1b2-449b-bcac-1ffd3f832915.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-29T21:13:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04006cb6-ee11-466d-86cf-3f1e99cff482.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
- `/ll:manage-issue` - 2026-05-31T22:30:16Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9cf4f767-248b-41af-b43a-2a81cea4b8df.jsonl`
