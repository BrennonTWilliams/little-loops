---
id: ENH-1898
title: Add required_inputs guard for loops with input_key
type: enhancement
priority: P3
status: done
captured_at: '2026-06-03T19:12:59Z'
completed_at: '2026-06-03T20:21:53Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
labels:
- fsm
- validation
- dx
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1898: Add `required_inputs` guard for loops with `input_key`

## Summary

The FSM loop runtime has no way to declare that a runtime input is required.
A loop declaring `input_key: description` runs silently with
`context.description: ""` when no input is supplied, producing degraded output
(e.g. a generic brief) with no warning. Add a `required_inputs` declaration and
a pre-flight guard so missing inputs fail fast.

## Current Behavior

`grep -rn "required_inputs" scripts/little_loops/` returns nothing — the concept
does not exist. The `svg-textgrad` audit (§9, "`description` context is empty")
observed that the resolved FSM showed `context.description: ""`, meaning
`ll-loop run svg-textgrad` with no description silently produces a generic brief
from an empty `${context.description}` interpolation.

## Expected Behavior

A loop can declare which injected inputs are mandatory, and the runner refuses
to start (with a clear error) when a required input is absent or empty:

```yaml
input_key: description
required_inputs: ["description"]
```

```
$ ll-loop run svg-textgrad
Error: loop 'svg-textgrad' requires input 'description' but none was provided.
       Pass it via --input or the configured input_key.
```

## Motivation

Silent-empty-input is a footgun: the loop "succeeds" but optimizes against an
empty subject, wasting a full run and masking operator error. A declarative
guard makes the contract explicit and shifts the failure left to start-time.

## Proposed Solution

### Option A — Full Guard (Recommended)

> **Selected:** Option A — Full Guard (Recommended) — shifts failure left to start-time; all sub-components reuse existing codebase patterns directly

Declare intent in the loop YAML and enforce it at start-time:

1. **Schema field**: add `required_inputs: list[str] = field(default_factory=list)` to `FSMLoop` in `schema.py` (Form A list pattern, same as `labels`). Update `from_dict()` (`data.get("required_inputs", [])`) and `to_dict()` (emit when non-empty). Add `"required_inputs"` to `KNOWN_TOP_LEVEL_KEYS` in `validation.py`.
2. **Pre-flight runner guard**: in `cmd_run()` in `run.py`, after the existing `_ctx_var_re` context-variable scan block (~line 232), iterate `fsm.required_inputs`, check each key against `fsm.context` for absence or empty-string value, and `return 1` with `logger.error(...)` on violation. Pattern: same `return 1` + `logger.error` used by the existing missing-context-variable check.
3. **Static validation warning** (bonus): add `_validate_input_key_without_guard(fsm)` to `validation.py` emitting `ValidationSeverity.WARNING` when a loop has `input_key` set but `required_inputs` is empty — nudges authors who forget to declare intent.

### Option B — Static Warning Only (Minimal)

Skip the schema field and runtime abort entirely. Only add the `ll-loop validate` WARNING (step 3 above) to surface the missing declaration at validation time. Does not prevent a silent empty-input run; relies on authors running `ll-loop validate` to catch the omission.

**Tradeoff**: Option B is ~3 lines vs Option A's ~30 lines, but Option A is the only approach that shifts the failure left to start-time for end users. Option B is appropriate if the feature is judged too heavyweight for P3.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-03.

**Selected**: Option A — Full Guard (Recommended)

**Reasoning**: Both options score 11/12 on codebase fit (Consistency 3/3 each), but Option B's warning is discarded with `_` in `cmd_run()` and never printed to stdout during `ll-loop run` — operators who don't run `ll-loop validate` see nothing, so the silent-failure mode the issue targets is not prevented. Option A achieves the stated Expected Behavior (start-time abort with a clear error) and is feasible at P3 given the "Small" effort estimate. All three sub-components reuse existing infrastructure with zero new abstractions.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Full Guard | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B — Static Warning Only | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:
- Option A: `labels` field in `schema.py:944` is the exact form-A list template; `_ctx_var_re` block in `run.py:214–232` is the direct neighbor and model for the runtime guard; `_validate_artifact_isolation` in `validation.py:1153` is the private-validator template; reuse score 3/3
- Option B: Warning-only validators dominate `validate_fsm()` (8 existing); `load_and_validate()` discards the warnings list with `_` in `cmd_run` so warnings are only visible via `ll-loop validate` or Python logging — not on stdout during `ll-loop run`; reuse score 3/3

## Scope Boundaries

- In scope: declaring and enforcing presence/non-emptiness of injected inputs.
- Out of scope: type validation, format/regex validation, or default-value
  synthesis for inputs (could be a follow-up).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `required_inputs` as optional `array` of `string` at top level (alongside `input_key`)
- `scripts/little_loops/fsm/schema.py` — add `required_inputs: list[str] = field(default_factory=list)` to `FSMLoop` dataclass; update `FSMLoop.from_dict()` (`data.get("required_inputs", [])`) and `FSMLoop.to_dict()` (emit when non-empty)
- `scripts/little_loops/cli/loop/run.py` — add presence/non-empty check after the existing `_ctx_var_re` pre-run validation block (~line 232); follow `return 1` + `logger.error` pattern already used there
- `scripts/little_loops/fsm/validation.py` — add `"required_inputs"` to `KNOWN_TOP_LEVEL_KEYS` frozenset; add `_validate_input_key_without_guard(fsm)` returning `ValidationSeverity.WARNING`; wire via `errors.extend(...)` in `validate_fsm()`
- `scripts/little_loops/loops/svg-textgrad.yaml` — add `required_inputs: ["description"]` as first consumer

### Test Files to Add/Modify
- `scripts/tests/test_fsm_validation.py` — add `TestRequiredInputsValidation` class; use `make_state()` + `validate_fsm()` pattern; test WARNING fires when `input_key` set without `required_inputs`; test WARNING absent when `required_inputs` declared; also add `_validate_input_key_without_guard` to the file's explicit private-validator import block at the top
- `scripts/tests/test_ll_loop_errors.py` — add integration test for missing required input abort, following `TestErrorHandling` (uses `monkeypatch.chdir` + `main_loop()` + `capsys`); assert exit code 1 and error message contains key name
- `scripts/tests/test_ll_loop_commands.py` — extend `TestCmdRunContextInjection` class (~line 2578) with happy-path test: required input present → proceeds normally

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `TestFSMLoopRequiredInputs` class (5 serialization tests: defaults_to_empty, to_dict_omits_when_empty, to_dict_includes_when_set, from_dict_parses, round_trip) following the `TestFSMLoopCommands` pattern; also add `TestLoadAndValidate.test_required_inputs_key_no_warning` following the `test_commands_key_no_warning` pattern already in that file

### Similar Patterns to Follow
- `scripts/little_loops/cli/loop/run.py:214–232` — existing `_ctx_var_re` pre-flight check: same `logger.error` + `return 1` pattern; new `required_inputs` guard follows directly after this block
- `scripts/little_loops/fsm/validation.py` — `_validate_artifact_isolation(fsm)` is the canonical template for a new private validator: returns `list[ValidationError]`, wired via `errors.extend(...)` in `validate_fsm()`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.labels` uses the correct Form A list pattern: `field(default_factory=list)`, emitted in `to_dict()` only when non-empty, deserialized with `.get("labels", [])`

### Documentation
- `docs/reference/loops.md` — add `required_inputs` to the loop schema reference table
- `docs/guides/LOOPS_GUIDE.md` — mention `required_inputs` in the `input_key` section

### 23 Loops Currently Using `input_key` (Candidates for `required_inputs`)
All loops in `scripts/little_loops/loops/` that set `input_key` are potential consumers. Only `svg-textgrad.yaml` is in scope for this issue; others can opt in via follow-up.

## Implementation Steps

1. **JSON Schema**: In `scripts/little_loops/fsm/fsm-loop-schema.json`, add `required_inputs` as an optional array field alongside `input_key`.
2. **Dataclass**: In `scripts/little_loops/fsm/schema.py`, add `required_inputs: list[str] = field(default_factory=list)` to `FSMLoop`; update `FSMLoop.from_dict()` and `FSMLoop.to_dict()` following the `labels` field pattern.
3. **Known keys**: In `scripts/little_loops/fsm/validation.py`, add `"required_inputs"` to `KNOWN_TOP_LEVEL_KEYS` frozenset to suppress the unknown-key warning.
4. **Validation warning**: In `validation.py`, add `_validate_input_key_without_guard(fsm: FSMLoop) -> list[ValidationError]` emitting `ValidationSeverity.WARNING` when `fsm.input_key != "input"` (i.e., explicitly set) and `not fsm.required_inputs`; wire into `validate_fsm()` via `errors.extend(...)`.
5. **Pre-flight runner guard**: In `scripts/little_loops/cli/loop/run.py` `cmd_run()`, after the existing `_ctx_var_re` missing-context-key block (~line 232), add a loop over `fsm.required_inputs` that checks `fsm.context.get(key, "") == ""` and calls `logger.error(f"loop '{loop_name}' requires input '{key}' but none was provided. Pass it via: ll-loop run {loop_name} <value>")` + `return 1`.
6. **First consumer**: In `scripts/little_loops/loops/svg-textgrad.yaml`, add `required_inputs: ["description"]` after `input_key: description`.
7. **Tests**:
   - `test_fsm_validation.py`: `TestRequiredInputsValidation` — WARNING fires when `input_key` set without `required_inputs`; no WARNING when `required_inputs` declared; wired into `validate_fsm()`
   - `test_ll_loop_errors.py`: integration test via `monkeypatch.chdir` + `main_loop()` — missing required input exits with code 1; present input proceeds
   - `test_ll_loop_commands.py`: happy-path test in `TestCmdRunContextInjection` — required input supplied, execution proceeds
8. **Docs**: Update `docs/reference/loops.md` schema table and `docs/guides/LOOPS_GUIDE.md` `input_key` section.
9. Run `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_ll_loop_errors.py scripts/tests/test_ll_loop_commands.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update import block in `scripts/tests/test_fsm_validation.py` — add `_validate_input_key_without_guard` to the explicit private-validator import list (alongside `_validate_artifact_isolation`, `_validate_zero_retry_counter`, etc.)
11. Add `TestFSMLoopRequiredInputs` class to `scripts/tests/test_fsm_schema.py` — 5 serialization tests following `TestFSMLoopCommands` pattern (defaults to empty list, `to_dict` omits when empty, `to_dict` includes key when set, `from_dict` parses correctly, full round-trip); also add `test_required_inputs_key_no_warning` to the existing `TestLoadAndValidate` class in that file, following the `test_commands_key_no_warning` pattern
12. **Behavioral side-effect note**: The 23 builtin loops that set a custom `input_key` (but not `required_inputs`) will begin emitting a WARNING from `_validate_input_key_without_guard()` once this lands. This is intentional — `test_all_validate_as_valid_fsm` in `test_builtin_loops.py` filters only ERROR-severity, so that test passes without changes. Those loops can opt in via a follow-up. No code change needed for this step.

## Acceptance Criteria

- `ll-loop run <loop-with-required-inputs>` with no `--input` exits with code 1 and prints a message containing the loop name and missing key name.
- `ll-loop run <loop-with-required-inputs> --input ""` (empty string) also exits with code 1.
- `ll-loop run <loop-with-required-inputs> <value>` proceeds normally when the required input is supplied.
- `ll-loop run <loop-without-required-inputs>` continues to run without change (additive field, fully optional).
- `ll-loop validate svg-textgrad` emits no WARNING about missing `required_inputs` (because it will be declared).
- `ll-loop validate <loop-with-input_key-but-no-required_inputs>` emits a WARNING.
- All existing loops without `required_inputs` pass `test_builtin_loops.py:test_all_validate_as_valid_fsm` unchanged.

## Impact

- **Priority**: P3 — Non-blocking footgun; loops degrade silently rather than fail, so discovery is delayed but not catastrophic.
- **Effort**: Small — Schema field addition, ~10-line runner guard, and unit tests; no architectural changes.
- **Risk**: Low — Additive only; `required_inputs` is optional so all existing loops are unaffected.
- **Breaking Change**: No — loops omitting `required_inputs` behave identically to today.

## Status

- **Created**: 2026-06-03 via `/ll:capture-issue` (from `svg-textgrad` audit)
- **State**: open

## Session Log
- `/ll:ready-issue` - 2026-06-03T20:08:49 - `a68d5975-0f85-438b-bc3e-cd6b1c904e3a.jsonl`
- `/ll:confidence-check` - 2026-06-03T20:30:00Z - `1922c502-9ec1-4e9c-bac8-cfd10be314b4.jsonl`
- `/ll:decide-issue` - 2026-06-03T20:03:45 - `a1f6b779-08f3-4224-8886-3f8107947977.jsonl`
- `/ll:wire-issue` - 2026-06-03T19:54:53 - `0c2c4ec0-fdc3-40a0-acba-bc5944f0532e.jsonl`
- `/ll:refine-issue` - 2026-06-03T19:49:16 - `26cefa79-6ddc-4aec-98ad-a322190d9134.jsonl`
- `/ll:format-issue` - 2026-06-03T19:21:49 - `9e65eaa3-eac1-4a28-8cdf-0b883be5b699.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cba1a69-7a53-425f-8c5d-4f1ba61f51bb.jsonl`
