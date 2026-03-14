---
id: ENH-731
type: ENH
priority: P3
title: Rename FSM transition labels from success/fail to yes/no
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 43
---

# ENH-731: Rename FSM transition labels from success/fail to yes/no

## Summary

FSM loop transition labels currently use "success" and "fail" as the standard outcome names for state transitions. These terms imply that a transition represents task completion or failure, but many FSM states are simply decision points (e.g., "did the check pass?", "is there more work?"). Renaming the labels to "yes" and "no" better reflects the conditional branching nature of FSM transitions without implying failure or completion semantics.

## Current Behavior

FSM loop YAML states use `on_success` and `on_failure` as shorthand routing properties (internal verdict strings are `"success"` and `"failure"`):

```yaml
states:
  check-quality:
    action: "Run /ll:check-code lint,format,types"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: fix-quality
```

The `on_success`/`on_failure` property names carry pass/fail connotations, which is misleading for states that are simply evaluating a condition (e.g., "did the check pass?", "is there more work?"). The internal verdict strings `"success"` and `"failure"` propagate through the evaluators (`scripts/little_loops/fsm/evaluators.py`) and executor (`scripts/little_loops/fsm/executor.py`).

## Expected Behavior

FSM loop YAML states use neutral routing properties (e.g., `on_yes`/`on_no`) that reflect conditional branching rather than task outcome:

```yaml
states:
  check-quality:
    action: "Run /ll:check-code lint,format,types"
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix-quality
```

This language is neutral and works equally well for condition-checking states, decision gates, and terminal states.

## Acceptance Criteria

- [ ] FSM schema (`scripts/little_loops/fsm/schema.py`) accepts `on_yes`/`on_no` as routing properties
- [ ] FSM evaluators (`scripts/little_loops/fsm/evaluators.py`) emit `"yes"`/`"no"` verdict strings instead of `"success"`/`"failure"`
- [ ] FSM executor (`scripts/little_loops/fsm/executor.py`) routes on `"yes"`/`"no"` verdicts
- [ ] All 19 built-in loop YAML files in `loops/` migrated from `on_success`/`on_failure` to `on_yes`/`on_no`
- [ ] `ll-loop` status output and diagrams display `yes`/`no` instead of `success`/`failure`
- [ ] `create-loop` skill generates YAML with `on_yes`/`on_no` properties
- [ ] `review-loop` skill validates `on_yes`/`on_no` and flags `on_success`/`on_failure` as deprecated
- [ ] Documentation and skill examples updated with `on_yes`/`on_no` throughout
- [ ] Backwards compat shim or migration path for any user-authored loops using `on_success`/`on_failure`

## Motivation

The `on_success`/`on_failure` property names (and internal `"success"`/`"failure"` verdict strings) create a conceptual mismatch: a state like `has_more_issues` routing to `process_next` via `on_success` is confusing — it's not that the state succeeded, it's that the answer is "yes". Using `on_yes`/`on_no` maps naturally to how FSM states are described in documentation and conversations, reduces cognitive overhead when authoring loops, and avoids misleading implications in state diagrams and logs.

## Proposed Solution

1. Update `schema.py`: rename `on_success`/`on_failure` fields to `on_yes`/`on_no`; update evaluators to emit `"yes"`/`"no"` verdicts; update executor routing logic
2. Update all 19 loop YAML files in `loops/` from `on_success`/`on_failure` to `on_yes`/`on_no`
3. Update `ll-loop` display/rendering (status output, diagrams, history) to show `yes`/`no`
4. Update `create-loop` skill and `review-loop` skill to generate/validate `on_yes`/`on_no` properties
5. Update documentation (loop authoring guides, examples)
6. Consider deprecation path for `on_success`/`on_failure` if backwards compatibility needed (user-authored loops)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig.on_success`/`on_failure` fields (lines 195–196); `to_dict` keys (lines 217–220); `from_dict` lookups (lines 254–255); `get_referenced_states` checks (lines 273–276). **Note**: no Pydantic — plain `@dataclass` with hand-written `from_dict`/`to_dict`, no alias machinery exists.
- `scripts/little_loops/fsm/evaluators.py` — `DEFAULT_LLM_SCHEMA` `enum` at line 54 lists `"success"/"failure"`; `evaluate_exit_code` returns at lines 92/94; `evaluate_output_numeric` line 144; `_compare_values` line 211; `evaluate_output_json` lines 258/260; `evaluate_output_contains` lines 302/304
- `scripts/little_loops/fsm/executor.py` — default verdict `"success"` at line 535; `_route` method shorthand dispatch at lines 722/724 (`verdict == "success"` / `verdict == "failure"`)
- `scripts/little_loops/fsm/validation.py` — `has_shorthand` field checks at lines 178–182; warning message string at line 189 that names `on_success`/`on_failure` literally
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema property definitions for `on_success`/`on_failure` at lines ~87–93
- `scripts/little_loops/cli/loop/layout.py` — `_EDGE_LABEL_COLORS` dict (`"success"` at line 23, `"fail"` at line 24); edge collection labels at lines 139/141; `_colorize_label` checks at lines 37/43; happy-path tracer reads `on_success` at line 187
- `scripts/little_loops/cli/loop/info.py` — event log `verdict == "success"` at line 199; compact transition table uses `"success"`/`"fail"` at lines 272–273; verbose transition table uses `"success"`/`"failure"` at lines 531–532 (**inconsistency**: compact uses `"fail"`, verbose uses `"failure"` — both need to become `"no"`); stats counter at lines 398–399
- `scripts/little_loops/cli/loop/_helpers.py` — `print_execution_plan` prints `on_success`/`on_failure` labels verbatim at lines 174–178; evaluate verdict check at line 382 uses `verdict in ("success", "target", "progress")`
- `scripts/little_loops/cli/loop/testing.py` — verdict routing `verdict == "success"` / `verdict == "failure"` with `state_config.on_success`/`on_failure` at lines 148–153
- `loops/*.yaml` — 18 of 19 loop files (81 occurrences) use `on_success:`/`on_failure:` YAML keys; **additionally, LLM `evaluate.prompt` text inside many loops instructs the model to `Return "success"` / `Return "failure"` — these string literals also need updating to `"yes"`/`"no"`** (e.g., `fix-quality-and-tests.yaml:15-16`, `issue-staleness-review.yaml:41-43`, `plugin-health-check.yaml:76-77`, etc.)
- `skills/create-loop/reference.md`, `skills/create-loop/templates.md`, `skills/create-loop/loop-types.md` — YAML examples and prose descriptions
- `skills/review-loop/SKILL.md` — references `on_success`/`on_failure` in QC check logic at lines 155/186
- `skills/review-loop/reference.md` — references at line 469 in `--auto` mode restriction list
- `docs/generalized-fsm-loop.md` — 30+ occurrences in YAML examples and prose
- `docs/guides/LOOPS_GUIDE.md` — user-facing guide examples

### Dependent Files (Callers/Importers)
- `scripts/tests/test_fsm_schema.py` — `make_state` helper uses `on_success`/`on_failure` as kwargs; direct property assertions; roundtrip `from_dict`/`to_dict` assertions; `test_dangling_state_reference` docstring
- `scripts/tests/test_fsm_executor.py` — every FSM fixture + `EvaluationResult(verdict="success")` mocks
- `scripts/tests/test_fsm_evaluators.py` — parametrized verdict assertions `(0, "success")`, `(1, "failure")`; `EvaluationResult(verdict="success"/"failure")` direct assertions; LLM mock stdout uses `"success"`/`"failure"` verdict values
- `scripts/tests/test_fsm_persistence.py` — `StateConfig` fixture construction with `on_success`/`on_failure` kwargs
- `scripts/tests/test_ll_loop_commands.py`, `test_ll_loop_display.py`, `test_ll_loop_execution.py`, `test_ll_loop_errors.py`, `test_ll_loop_integration.py`, `test_ll_loop_state.py`, `test_ll_loop_parsing.py`
- `scripts/tests/test_builtin_loops.py`, `test_create_loop.py`, `test_review_loop.py`
- `scripts/tests/conftest.py` — shared YAML fixtures at lines 244, 262 use `on_success`/`on_failure`
- `scripts/tests/fixtures/fsm/valid-loop.yaml` — uses `on_success: done`, `on_failure: done` at lines 6–7
- `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml` — uses `on_success`/`on_failure` at lines 6–7

### Parallel Task YAMLs (Confirmed Out of Scope)
- `scripts/little_loops/parallel/tasks/*.yaml` (4 files) use `on_failure: continue` as a **subtask error directive** (continue vs stop behavior), not an FSM state routing property. These are a completely separate schema and do **not** need to be updated as part of this rename.

### Tests
- All `test_fsm_*.py` files assert on verdict string values and routing property names — all will need updates

### Documentation
- `docs/generalized-fsm-loop.md` — primary architecture doc, 30+ occurrences
- `docs/guides/LOOPS_GUIDE.md` — user-facing guide
- `docs/reference/API.md` — `StateConfig` examples and evaluator output comments (~10 occurrences; lines 3464–3465, 3487–3488, 3552, 3668, 3672, 3675, 3713, 3880, 4005)
- `docs/development/TESTING.md` — `StateConfig` constructor examples with `on_success`/`on_failure` (~5 occurrences; lines 447, 673–674, 701–702)

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for loop YAML validation

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No aliasing mechanism exists**: `StateConfig.from_dict` calls `data.get("on_success")` with no fallback. Backwards-compat shim requires adding `data.get("on_yes") or data.get("on_success")` pattern in `from_dict` (lines 254–255).
- **Display label inconsistency**: `info.py` compact view uses `"fail"` (line 273) but verbose view uses `"failure"` (line 532). `layout.py` uses `"fail"` (line 141). After rename, all should standardize to `"no"`.
- **LLM prompt text in loop YAMLs**: Many loops contain `evaluate.prompt` text like `Return "success" only if...` / `Return "failure" if...`. These are separate from the YAML routing keys and must also be updated to `"yes"`/`"no"`.
- **`DEFAULT_LLM_SCHEMA` in evaluators.py:52–58**: The JSON schema enum sent to Claude for LLM-structured evaluation hardcodes `["success", "failure", "blocked", "partial"]` — needs updating to `["yes", "no", "blocked", "partial"]`.
- **`_helpers.py:393` additional `"fail"` string**: Beyond the `("success", "target", "progress")` tuple at line 385, the else-branch at line 393 checks `verdict in ("fail", "error")` for orange colorization. After rename, `"fail"` must become `"no"` here as well. The full display colorization update for `_helpers.py` therefore touches lines 385 AND 393.
- **`docs/reference/API.md` and `docs/development/TESTING.md` untracked**: Both contain `on_success`/`on_failure` in `StateConfig` code examples and need updating — now documented in the Integration Map.
- **`info.py:248` hardcoded width calculation**: `len("\u2713 success")` is used as a terminal column width anchor. "success" (7 chars) vs "yes" (3 chars) — this width difference may affect terminal alignment in the info display; must be updated to `len("\u2713 yes")` or recalculated.
- **Persistence backwards compat**: Stored `.loops/.running/<name>.events.jsonl` and `.state.json` files written by prior runs will contain old `"success"`/`"failure"` verdict strings. This is cosmetically inconsistent but **not functionally broken** — `LoopState.from_dict` only round-trips `last_result` for display; on resume the executor re-enters at `current_state` and re-runs the action (stored verdict is not fed back into routing). No migration of existing history files is needed.
- **Additional missing test files**: `scripts/tests/test_fsm_persistence.py` (StateConfig fixture construction), `scripts/tests/test_ll_loop_errors.py` (inline YAML and StateConfig usage), and `scripts/tests/conftest.py` (shared YAML fixtures at lines 244, 262) were not listed in the Integration Map but require updates.
- **Additional missing skills/commands files**: `skills/analyze-loop/SKILL.md:234` (references `on_failure` in signal type descriptions), `skills/workflow-automation-proposer/SKILL.md:145–155` (example YAML snippets), and `commands/loop-suggester.md:128–226` (example YAML output templates) all need updating and were not in the Integration Map.

## Implementation Steps

1. **Audit scope** — run `grep -rn "on_success\|on_failure\|\"success\"\|\"failure\"" scripts/little_loops/fsm/ scripts/little_loops/cli/loop/ loops/ skills/ docs/` to confirm all touch points
2. **Update FSM schema** (`schema.py:195–196, 217–220, 254–255, 273–276`) — rename fields to `on_yes`/`on_no`; in `from_dict` add backwards-compat: `on_yes=data.get("on_yes") or data.get("on_success")` (and same for `on_no`/`on_failure`)
3. **Update JSON Schema** (`fsm-loop-schema.json:~87–93`) — rename `on_success`/`on_failure` properties to `on_yes`/`on_no`
4. **Update evaluators** (`evaluators.py:54, 92, 94, 144, 211, 258, 260, 302, 304`) — change all `"success"`/`"failure"` verdict returns to `"yes"`/`"no"`; update `DEFAULT_LLM_SCHEMA` enum from `["success", "failure", "blocked", "partial"]` to `["yes", "no", "blocked", "partial"]`
5. **Update executor** (`executor.py:535, 722, 724`) — change default verdict `"success"` → `"yes"`; change `verdict == "success"` → `"yes"` and `verdict == "failure"` → `"no"` in `_route`
6. **Update validation** (`validation.py:178–182, 189`) — update `has_shorthand` field checks and warning message string
7. **Update CLI rendering** (all in `cli/loop/`):
   - `layout.py:22–43, 139–141, 187` — update `_EDGE_LABEL_COLORS` keys, edge labels `"success"`→`"yes"` / `"fail"`→`"no"`, colorize checks, path tracer
   - `info.py:199, 272–273, 398–399, 531–532` — update all display labels, standardizing compact (`"fail"`→`"no"`) and verbose (`"failure"`→`"no"`)
   - `_helpers.py:174–178, 385, 393` — update `print_execution_plan` output strings; update `("success", "target", "progress")` tuple to `("yes", "target", "progress")`; update `"fail"` in colorize conditional to `"no"`
   - `testing.py:148–153` — update `verdict == "success"`/`"failure"` routing comparisons
8. **Migrate loop YAMLs** (`loops/*.yaml`, 18 files) — rename `on_success:`→`on_yes:` and `on_failure:`→`on_no:` YAML keys; also update LLM evaluate prompt text (`Return "success"` → `Return "yes"`, `Return "failure"` → `Return "no"`)
9. **Migrate test fixtures** (`scripts/tests/fixtures/fsm/valid-loop.yaml`, `loop-with-unreachable-state.yaml`)
10. **Update skills and commands** (`create-loop/reference.md`, `create-loop/templates.md`, `create-loop/loop-types.md`, `review-loop/SKILL.md`, `review-loop/reference.md`, `skills/analyze-loop/SKILL.md:234`, `skills/workflow-automation-proposer/SKILL.md:145–155`, `commands/loop-suggester.md:128–226`)
11. **Update docs** (`docs/generalized-fsm-loop.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/reference/API.md`, `docs/development/TESTING.md`)
12. **Update all tests** — `test_fsm_schema.py`, `test_fsm_evaluators.py`, `test_fsm_executor.py`, and all `test_ll_loop_*.py` files
13. **Verify** — run `python -m pytest scripts/tests/ -v` and `ll-loop run loops/fix-quality-and-tests.yaml --dry-run`

## Impact

- **Priority**: P3 - Naming improvement, not blocking but affects authoring clarity and diagram readability
- **Effort**: Medium - Requires finding all uses of success/fail across engine, YAMLs, skills, docs, and tests
- **Risk**: Low - Rename with potential backwards compat shim; no logic changes
- **Breaking Change**: Yes (if `success`/`fail` removed without migration period)

## Success Metrics

- **YAML authoring clarity**: `on_yes`/`on_no` properties used in 100% of built-in loop configs after migration
- **Zero regressions**: All existing loops execute correctly after rename (pass existing test suite)
- **Terminology consistency**: No remaining `on_success`/`on_failure`/`"success"`/`"failure"` in engine, skills, or docs (or all behind deprecation shim)

## Scope Boundaries

- Out of scope: changing other transition label names beyond success/fail → yes/no
- Out of scope: changing the FSM state machine semantics or execution logic
- Out of scope: adding new transition types

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `loops`, `captured`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/fsm/schema.py` has `on_success`/`on_failure` fields at lines 195–196, 217–220, 254–255, 273–276 — no `on_yes`/`on_no` fields exist. `evaluators.py` still returns `"success"`/`"failure"` verdict strings at lines 54, 92, 94, 144, 211, 258, 260, 302, 304. All built-in loop YAMLs in `loops/` use `on_success:`/`on_failure:` YAML keys. Feature not yet implemented.

## Session Log

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2acb782e-c208-43f1-8534-96bfd95ced6e.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f511c85-9ee7-4764-8b06-753e10552cf2.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f511c85-9ee7-4764-8b06-753e10552cf2.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6421f7c-9303-4c44-9f2e-e1b31accf453.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c48b158-3a38-42ea-9974-fb89dfaa60bc.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c48b158-3a38-42ea-9974-fb89dfaa60bc.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c96e34f-66f6-47a9-8e06-75aea65c7264.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c96e34f-66f6-47a9-8e06-75aea65c7264.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad3c78eb-1f87-4a98-8d6f-f869076e256b.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad3c78eb-1f87-4a98-8d6f-f869076e256b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
