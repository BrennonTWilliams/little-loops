---
id: BUG-2305
type: BUG
priority: P2
title: 'FSM validator silently passes unresolvable loop: references, deferring failure
  to runtime'
status: open
captured_at: '2026-06-26T02:05:38Z'
discovered_date: 2026-06-26
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2305: validator silently passes unresolvable `loop:` references

## Summary

`load_and_validate()` never verifies that a state's `loop:` reference resolves
to an actual loop file. An unresolvable reference (typo, missing file, renamed
loop) passes validation cleanly and only raises `FileNotFoundError` at runtime,
deep inside a sub-sub-loop, after the parent has already passed pre-flight
checks and done expensive setup work.

Surfaced by an audit of `qa-pipeline` run `2026-06-26T014210` (cards repo):
`cua-fix-verify.yaml` referenced `loop: cua-agent-desktop`, which did not exist.
The runner only discovered this at `cua_observe` runtime after a 27-second
pipeline run + post-mortem; a definition-time check would have made it a
0-second fix.

## Current Behavior

The only validation that touches `state.loop` is `_validate_with_bindings()` in
`scripts/little_loops/fsm/validation.py`, and it does **not** catch missing
files:

1. It only runs for states that have **both** `state.loop` and `state.with_`
   set (`if state.loop is None or not state.with_: continue`). A bare `loop:`
   reference with no `with:` block — exactly the `cua-agent-desktop` case — is
   never examined.
2. Even when it does run, it wraps `resolve_loop_path()` + `load_and_validate()`
   in `except Exception: continue`, so a `FileNotFoundError` for a missing child
   loop is silently swallowed.

A second, display-time site at `cli/loop/_helpers.py` (~line 572, inside the
FSM diagram renderer) also catches `FileNotFoundError` / `ValueError` with a
bare `pass`, suppressing the missing-loop signal during rendering.

```python
# validation.py — _validate_with_bindings
for state_name, state in fsm.states.items():
    if state.loop is None or not state.with_:
        continue                      # ← bare loop: refs skipped entirely
    try:
        loop_path = resolve_loop_path(state.loop, loop_dir)
        child_fsm, _ = load_and_validate(loop_path)
    except Exception:
        continue                      # ← missing-file error swallowed
```

## Expected Behavior

`load_and_validate()` should resolve every state's `loop:` reference at
definition time and emit a validation warning (e.g.
`LOOP_REFERENCE_UNRESOLVABLE`) when `resolve_loop_path()` raises
`FileNotFoundError`, independent of whether the state has a `with:` block.
The FSM diagram renderer should log (not silently `pass`) when it cannot load a
referenced child loop.

## Motivation

Unresolvable `loop:` references are the most common cause of non-obvious runtime failures in the FSM executor: the parent loop passes pre-flight checks and begins expensive setup (tool calls, CUA sessions), then crashes deep in sub-loop dispatch with a bare `FileNotFoundError`. Moving the check to definition time collapses the feedback loop from minutes to zero seconds and avoids wasted setup work. The `qa-pipeline` incident (27-second run + post-mortem for a one-line typo fix) is a concrete cost this change eliminates.

## Steps to Reproduce

1. Create or edit any loop YAML with a state containing `loop: some-nonexistent-loop` (no `with:` block needed)
2. Run `ll-loop validate <loop-file>`
3. Observe: validation exits 0 with no warnings about the unresolvable reference
4. Run `ll-loop run <loop-file>`
5. Observe: `FileNotFoundError` raised at runtime inside sub-loop dispatch, after the parent loop's setup work has completed

## Root Cause

**File**: `scripts/little_loops/fsm/validation.py`
**Anchor**: `_validate_with_bindings()` (line 364) and `load_and_validate()` (line 2072)

- **Guard at line 380**: `if state.loop is None or not state.with_: continue` — the `or not state.with_` clause exits early for states with `loop:` but no `with:` block. Only states with both `loop:` *and* a non-empty `with:` dict enter the validation body.
- **Exception handler at lines 384–389**: `except Exception: continue` — even for states that pass the guard, any `FileNotFoundError` from `resolve_loop_path()` is silently discarded.
- **`load_and_validate()` at line 2157–2158** calls `_validate_with_bindings(fsm, path.parent)` and `_validate_fragment_bindings(fsm, path.parent)` but has no third call that resolves `state.loop` file references independently of `with:`.

`resolve_loop_path()` (`cli/loop/_helpers.py:849`) raises `FileNotFoundError(f"Loop not found: {name_or_path}")` when none of its four probe paths match. This exception is only reached at runtime — never during static validation for bare `loop:` states.

## Proposed Solution

1. Add `_validate_loop_references()` to `validation.py`, called from
   `load_and_validate()` alongside the existing `_validate_with_bindings()` call at line 2157.
   For every state where `state.loop is not None`, call `resolve_loop_path(state.loop, loop_dir)`
   and emit a `ValidationError(severity=ValidationSeverity.WARNING, path=f"states.{state_name}.loop")`
   on `FileNotFoundError`. This must run regardless of whether the state declares `with:`.
2. (Optional) In the FSM diagram renderer (`_helpers.py:568–573`), replace the bare `pass`
   with `logger.warning(...)` and set `self.child_fsm_stack[depth] = None` when a referenced
   child loop cannot be loaded.

Severity choice: WARNING (not ERROR), consistent with all other file-system-optional checks in
validation.py. No `LOOP_REFERENCE_UNRESOLVABLE` constant exists or is needed — use a descriptive
message string following the established pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation shape** (modeled after `_validate_with_bindings()` at line 364):
```python
def _validate_loop_references(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.loop is None:
            continue
        try:
            from little_loops.cli.loop._helpers import resolve_loop_path
            resolve_loop_path(state.loop, loop_dir)
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    message=f"Loop reference '{state.loop}' does not resolve to any file.",
                    path=f"states.{state_name}.loop",
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors
```

- Use the same lazy import pattern for `resolve_loop_path` (line 385 in `_validate_with_bindings`)
- Catch `FileNotFoundError` specifically (not bare `except Exception`) — `ValueError` from a malformed child YAML is a separate concern
- Wire into `load_and_validate()` at line ~2158: `errors.extend(_validate_loop_references(fsm, path.parent))`
- `ValidationWarning` and `ValidationResult` do not exist; all diagnostics are `ValidationError` with `severity` field

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py:364–438` — add `_validate_loop_references()` (new function after `_validate_with_bindings()`); wire into `load_and_validate():2157` as a third `errors.extend(...)` call
- `scripts/little_loops/cli/loop/_helpers.py:568–573` — replace bare `pass` with `logger.warning(...)` + `self.child_fsm_stack[depth] = None` in the diagram renderer (optional cleanup)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — add `"loop-reference"` pattern key to `TestValidatorWarningBudget.CATEGORY_PATTERNS` dict
- `scripts/tests/fixtures/fsm/inner-eval.yaml` — add minimal valid loop YAML so `test_fixture_subloop_laundering_validates` fixture resolves cleanly under the new check
- `skills/review-loop/reference.md` — add row to `## First-Pass Checks (from ll-loop validate)` table for the loop-reference warning
- `CHANGELOG.md` — add bullet under active release version

### Dependent Files (Callers/Importers)
All callers of `load_and_validate()` gain the new warning automatically:
- `scripts/little_loops/cli/loop/config_cmds.py:29,43` — `cmd_validate()` (the `ll-loop validate` entry point)
- `scripts/little_loops/cli/loop/run.py:109` — loop run command
- `scripts/little_loops/cli/loop/edit_routes.py:51` — `edit-routes` subcommand
- `scripts/little_loops/cli/loop/info.py:1084` — `ll-loop show` info renderer
- `scripts/little_loops/cli/loop/_helpers.py:883,907` — `load_loop()` and `load_loop_with_spec()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:612-613,641-642` — calls `load_and_validate()` for sub-loops at runtime; gains new warning automatically
- `scripts/little_loops/fsm/fragments.py:209` — calls `resolve_loop_path()` in fragment resolution; no change needed, informational only
- `scripts/little_loops/cli/loop/lifecycle.py:481,632` — calls `resolve_loop_path()` directly; no change needed
- `scripts/little_loops/cli/loop/testing.py` — imports from `_helpers`; no change needed
- `scripts/little_loops/fsm/__init__.py` — re-exports `load_and_validate`, `ValidationError`, `validate_fsm`; public API unaffected
- `scripts/little_loops/analytics/variance.py:224` — imports `load_loop` from `_helpers`; no change needed

### Similar Patterns
- `_validate_with_bindings()` (`validation.py:364`) — same signature `(fsm, loop_dir)`, same lazy import of `resolve_loop_path`, same `errors` list accumulation
- `_validate_fragment_bindings()` (`validation.py:441`) — same signature kept for API symmetry; `loop_dir` unused but present

### Tests
- `scripts/tests/test_fsm_validation.py` — primary target; follows the `_write_yaml(tmp_path, body)` + `load_and_validate(loop_yaml, raise_on_error=False)` pattern used by `TestCircuitValidation` and `TestVisibilityValidation`
- New test class `TestLoopReferenceValidation`: write a YAML with `loop: nonexistent-loop` (no `with:`), call `load_and_validate(..., raise_on_error=False)`, assert one WARNING with `"nonexistent"` in `message` and `path == "states.<state>.loop"`
- Regression: existing-loop reference (e.g., point to a real sibling YAML) emits no warning

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` — add a `TestCmdValidate` integration test: write a YAML with a bare `loop: no-such-loop` state, call `cmd_validate()` with `argparse.Namespace(json=True)`, assert exit 0 and JSON `warnings` list contains the loop-reference message (follows existing `test_validate_json_output_invalid_loop` pattern)
- `scripts/tests/test_builtin_loops.py` — add `"loop-reference"` key to `TestValidatorWarningBudget.CATEGORY_PATTERNS` (maps message substring to category name); without this, loop-reference warnings on built-in loops bypass the ratchet entirely
- `scripts/tests/test_audit_loop_run_skill.py:137` (`test_fixture_subloop_laundering_validates`) — fixture `assess-subloop-laundering.yaml` has `loop: inner-eval` with no sibling file; new check emits one WARNING; test discards warnings with `_` so it won't hard-fail, but add `scripts/tests/fixtures/fsm/inner-eval.yaml` (minimal valid YAML) so the fixture resolves cleanly

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/reference.md` — `## First-Pass Checks (from ll-loop validate)` table is a static catalog used by `/ll:review-loop` to classify `ll-loop validate` output; the new loop-reference warning has no entry and would surface as un-catalogued text; add a row (e.g., under a new check ID or descriptive label) so the skill can classify and display it correctly
- `CHANGELOG.md` — established pattern: one bullet per new validation capability in `### Fixed` (or `### Added`) under the release version; follow the style of `"Sub-loop missing-capture validation downgraded to WARNING"` (ENH-1998) and `"MR-6 generator-fix discipline rule in ll-loop validate"` (ENH-2079)

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/fsm/validation.py`, add `_validate_loop_references(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]` after `_validate_with_bindings()` (line 438). Model it on that function: lazy-import `resolve_loop_path`, iterate all states with `state.loop is not None`, catch `FileNotFoundError` specifically, emit `ValidationError(severity=ValidationSeverity.WARNING, path=f"states.{state_name}.loop")`.
2. Wire into `load_and_validate()` at line 2158 by adding `errors.extend(_validate_loop_references(fsm, path.parent))` after the existing `_validate_with_bindings` call.
3. (Optional) In `scripts/little_loops/cli/loop/_helpers.py:572–573`, replace `pass` with `logger.warning("Could not load child loop for state %s: %s", state, e)` and set `self.child_fsm_stack[depth] = None`.
4. Add `class TestLoopReferenceValidation` in `scripts/tests/test_fsm_validation.py`: write a minimal YAML with `loop: nonexistent-loop` (no `with:`) via `tmp_path`, call `load_and_validate(loop_yaml, raise_on_error=False)`, assert one WARNING with the missing loop name in its message; also test that a resolvable sibling YAML produces no warning.
5. Run `ll-loop validate loops/` against built-in loops to confirm no false positives from the new check.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `"loop-reference"` pattern key to `TestValidatorWarningBudget.CATEGORY_PATTERNS` in `scripts/tests/test_builtin_loops.py` so the ratchet captures loop-reference warnings on built-in loops (currently any such warning is silently ignored by `_classify`).
7. Fix the `test_fixture_subloop_laundering_validates` fixture gap: add `scripts/tests/fixtures/fsm/inner-eval.yaml` (minimal valid loop YAML) so `assess-subloop-laundering.yaml`'s `loop: inner-eval` reference resolves cleanly under the new check; alternatively, update the test to assert on the expected WARNING.
8. Add a row to `skills/review-loop/reference.md`'s `## First-Pass Checks (from ll-loop validate)` table for the new loop-reference warning so `/ll:review-loop` can classify and display it correctly rather than surfacing it as un-catalogued text.
9. Add a `CHANGELOG.md` bullet under the active release version following the established pattern (e.g., `"FSM validator now emits WARNING for unresolvable loop: references at definition time (BUG-2305)"`).
10. Add a `TestCmdValidate` integration test to `scripts/tests/test_ll_loop_commands.py`: write a YAML with a bare `loop: no-such-loop` state, call `cmd_validate()` with JSON mode, assert exit 0 and that `warnings` contains the loop-reference message.

## Impact

- **Priority**: P2 - Shifts a class of runtime crashes left to definition time; cheap to add, prevents expensive post-mortems.
- **Effort**: Small - One new validation function mirroring existing ones, plus tests.
- **Risk**: Low/Medium - Risk is false positives on intentionally-optional references; mitigated by choosing warning severity and running against built-in loops.
- **Breaking Change**: No (warning); would be Yes if implemented as a hard error.

## Labels

`bug`, `captured`, `fsm`, `validation`

## Session Log
- `/ll:confidence-check` - 2026-06-25T00:00:00Z - `25233932-f705-4de6-93cd-6045765792e0.jsonl`
- `/ll:wire-issue` - 2026-06-26T02:28:26 - `e9efdfbd-319c-4d2b-9c38-0a9e63fc8643.jsonl`
- `/ll:refine-issue` - 2026-06-26T02:17:16 - `80518754-bc0a-4778-a1c1-8bedfb026b8a.jsonl`
- `/ll:format-issue` - 2026-06-26T02:10:30 - `6a879ef6-fde0-4367-b70f-158714386389.jsonl`
- `/ll:capture-issue` - 2026-06-26T02:05:38Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47212e05-8450-445f-aa2c-7353511e59fa.jsonl`

---

## Status

open
