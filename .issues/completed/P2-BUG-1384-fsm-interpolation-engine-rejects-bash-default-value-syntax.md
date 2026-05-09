---
id: BUG-1384
type: BUG
priority: P2
status: active
captured_at: '2026-05-09T01:55:56Z'
completed_at: '2026-05-09T19:45:06Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
size: Very Large
---

# BUG-1384: FSM interpolation engine rejects bash default-value syntax in escaped variables

## Summary

The FSM interpolation engine incorrectly processes `$${...}` escape sequences — intended to pass through as literal `${...}` for bash — causing an `Invalid variable` error that makes any FSM loop using bash parameter expansion (e.g., `$${DEPTH:-0}`) fail immediately.

## Current Behavior

The FSM loop YAML files use `$${...}` as an escape sequence intended to produce a literal `${...}` for the shell (preventing the interpolation engine from treating it as a variable reference). However, the interpolation engine in `interpolation.py` is incorrectly treating `$${DEPTH:-0}` as a variable reference and failing with:

```
Invalid variable: ${DEPTH:-0} (expected namespace.path)
```

This causes `recursive-refine` to fail on its first state transition, which in the FSM-based sprint mode produces an infinite retry loop (observed: 191 iterations before SIGKILL).

## Root Cause

**File**: `scripts/little_loops/fsm/interpolation.py`

The escape logic works in three steps:
1. Replace `$${` with a placeholder (`\x00ESCAPED\x00`)
2. Match and resolve remaining `${namespace.path}` references via `VARIABLE_PATTERN`
3. Restore the placeholder as `${`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The three-step implementation in `interpolate()` (lines 169–206) has the steps in the correct order:**

```python
# Module-level constants (interpolation.py lines 25–27)
VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")
ESCAPED_PATTERN = re.compile(r"\$\$\{")
ESCAPED_PLACEHOLDER = "\x00ESCAPED\x00"

# Inside interpolate() — steps 1, 2, 3 in correct order
result = ESCAPED_PATTERN.sub(ESCAPED_PLACEHOLDER, template)   # step 1
result = VARIABLE_PATTERN.sub(replace_var, result)             # step 2
result = result.replace(ESCAPED_PLACEHOLDER, "${")             # step 3
```

**The `replace_var()` inner function raises `InterpolationError` when captured content has no `.`:**

```python
def replace_var(match: re.Match[str]) -> str:
    full_path = match.group(1)
    if "." not in full_path:
        raise InterpolationError(
            f"Invalid variable: ${{{full_path}}} (expected namespace.path)"
        )
```

The observed error `Invalid variable: ${DEPTH:-0}` means `VARIABLE_PATTERN` matched `${DEPTH:-0}` — i.e., the `$${` was **not consumed by step 1** before step 2 ran. This can only happen if the string arriving at `interpolate()` already contained `${DEPTH:-0}` (single `$`) rather than `$${DEPTH:-0}` (double `$`).

**The YAML action at line 88 uses a literal block scalar (`action: |`)**, which means YAML passes `$$` through verbatim — no single-`$` collapse at the YAML layer.

**Investigation priority for the implementer:** Confirm whether the bug is still reproducible with the current code. If reproducible, add a debug log or test to capture the exact string that arrives at `interpolate()`. Possible causes to investigate in priority order:
1. ~~**Double interpolation**~~ — **RULED OUT** (see research findings below). `_run_action()` is the single and only call site for `interpolate()` on action templates.
2. **Fragment/inheritance merging** — `resolve_fragments()` and `resolve_inheritance()` in `fragments.py` deep-merge YAML dicts but do NOT call `interpolate()`. Safe.
3. **YAML double-quoted string in loop file** — if the action were in a YAML double-quoted string (not a block scalar `|`), `$$` would still be passed through verbatim (YAML uses `\` for escaping, not `$$`). But verify in case the YAML is restructured.
4. **Single-`$` typo present at incident time** — the most likely explanation given the ruling-out of double-interpolation. Check `git log -p scripts/little_loops/loops/recursive-refine.yaml` to see if line 88 ever had `${DEPTH:-0}` (single `$`) rather than `$${DEPTH:-0}`.
5. **Sub-loop `with:` binding collision** — if a calling loop passes a `with:` binding whose *value* itself becomes part of an action template string through some indirect path, that value would be pre-interpolated by `interpolate_dict(state.with_, ctx)` at executor.py:437 before `_run_action()` runs. Very unlikely but investigate if 1–4 don't explain the failure.

### Second Refinement Research Findings (2026-05-09)

_Added by `/ll:refine-issue` — comprehensive executor and evaluator audit:_

**Double-interpolation is mechanically impossible with the current code.** Full executor.py call inventory:

| Line | Call | Argument | Touches action template? |
|------|------|----------|--------------------------|
| 429 | `interpolate(state.loop, ctx)` | sub-loop name string | No |
| 437 | `interpolate_dict(state.with_, ctx)` | `with:` bindings dict | No |
| 510–521 | `interpolate(state.on_yes/on_no/on_error, ctx)` | routing target strings | No |
| 610–640 | `interpolate(state.on_error/state.next, ctx)` | routing target strings | No |
| **732** | **`interpolate(action_template, ctx)`** | **the action string** | **Yes — the sole call** |
| 742 | `interpolate_dict(state.params, ctx)` | MCP params dict only | No |
| 924 | `interpolate(state.evaluate.source, ctx)` | evaluator source string | No |
| 1024 | `interpolate(route, ctx)` | routing target string | No |
| 1091 | `interpolate(state.on_error, ctx)` | routing target string | No |

The YAML load path (`validation.py` → `yaml.safe_load` → `resolve_inheritance` → `resolve_flow` → `resolve_fragments` → `FSMLoop.from_dict`) never calls `interpolate()`. Action strings are stored verbatim from parse time until line 732.

**Evaluators.py confirmed clear.** All 5 `interpolate()` calls are in `evaluate()` and operate exclusively on `EvaluateConfig` fields:
- Line 772: `config.target` (numeric threshold)
- Line 806: `config.previous` (convergence reference)
- Line 824: `config.target` (convergence target)
- Line 840: `config.tolerance` (convergence tolerance)
- Line 864: `config.prompt` (LLM evaluator prompt)

Evaluators are called strictly **after** `_run_action()` completes (executor.py lines 646–656: action first, then evaluate). They receive action `output` (already-captured stdout), not the action template string. `EvaluateConfig` has no `action` field.

**Revised root cause conclusion:** If the error occurred as described, the raw `state.action` string (as written in the YAML) must have contained a single-`$` `${DEPTH:-0}` when `interpolate()` ran at line 732. Since the escape mechanism is correct for `$${...}`, the most likely cause is either (a) the YAML had a single-`$` typo at the time of the incident that has since been corrected, or (b) the bug is still present and the YAML loading/editing path introduced a single-`$` somewhere not yet identified. **Reproducing the bug should be the first implementation step.**

**Affected YAML**: `scripts/little_loops/loops/recursive-refine.yaml` (line 88, inside `action: |`):
```yaml
printf '%s' "$${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
```

## Impact

- `ll-loop run recursive-refine` fails immediately on first state transition
- `ll-sprint` in FSM mode enters an infinite retry loop (191+ iterations, requires SIGKILL)
- Any FSM loop YAML that uses bash default-value syntax (`:-`) or other bash parameter expansions in escaped `$${...}` blocks will fail

## Expected Behavior

`$${DEPTH:-0}` should pass through the interpolation engine unchanged and reach the shell as `${DEPTH:-0}`, which bash then evaluates as "value of DEPTH, or 0 if unset".

## Steps to Reproduce

1. Run `ll-loop run recursive-refine <any-issue-id>`
2. Observe the FSM fails on the first state transition
3. Check the FSM event log for: `Invalid variable: ${DEPTH:-0} (expected namespace.path)`
4. Alternatively, run `ll-sprint` in FSM mode — observe the infinite retry loop (191+ iterations)

## Implementation Steps

1. **Reproduce first** — run `ll-loop run recursive-refine <any-issue-id>` and confirm the `Invalid variable: ${DEPTH:-0}` error still occurs with current code. If it does NOT reproduce, the bug may have been a one-time YAML typo that was later corrected.
2. **Check git history** — run `git log -p scripts/little_loops/loops/recursive-refine.yaml | grep -A2 -B2 'DEPTH'` to see if line 88 ever used `${DEPTH:-0}` (single `$`) instead of `$${DEPTH:-0}` (double `$`). Same check for `autodev.yaml`.
3. **Trace the input if still reproducible** — add a `print(repr(template))` at the top of `interpolate()` in `scripts/little_loops/fsm/interpolation.py:169` to capture the exact string arriving; confirm whether it has single or double `$`. Note: double-interpolation via upstream executor calls has been ruled out (see Root Cause research findings).
4. **If single `$` arrives at interpolate()** — the YAML must contain it; search all loop YAML files for `${[A-Z_][^.}]*:-` (single-`$` bash-operator syntax without dot) to find incorrectly written escape sequences.
5. **Fix the root cause** — if a single-`$` YAML typo is found, correct the YAML; if the escape mechanism itself has a regression, fix it in `interpolation.py`'s three-step logic
5. **Add a unit test** in `scripts/tests/test_fsm_interpolation.py` following the pattern in `TestInterpolateEdgeCases`: `interpolate("printf '$${DEPTH:-0}'", InterpolationContext())` → `"printf '${DEPTH:-0}'"` without raising; also test `interpolate("X=$${VAR:+yes}", InterpolationContext())` → `"X=${VAR:+yes}"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Audit `evaluators.py` for double-interpolation** — confirm that none of the 5 `interpolate()` calls in `scripts/little_loops/fsm/evaluators.py` (`evaluate_output_numeric`, `evaluate_convergence`, `evaluate_llm_structured`) operate on `state.action` templates before `_run_action()` does, which would cause double-interpolation and is the leading root-cause hypothesis
7. **Update `test_invalid_format_no_dot`** (`test_fsm_interpolation.py:185`) if the error message in `replace_var()` is reworded — the `match="expected namespace.path"` assertion will break if the string changes
8. **Verify `test_nested_variable_syntax_raises_interpolation_error`** (`test_fsm_interpolation.py:228`) still passes after the fix — the unescaped nested form `${VAR:-${context.x}}` should continue to raise `InterpolationError`
9. **Review `test_interpolation_error_routes_to_on_error_when_set`** (`test_fsm_executor.py:2666`) — uses `${missing_var}` (no dot) to trigger `replace_var()`'s guard; update if guard logic changes
10. **Add extended escape tests** — beyond the two prescribed in step 5, also add: mixed `$${VAR:-default}` + real `${namespace.path}` in one string; `$${SPEC_LIST[@]}` (array expansion); `$${PASSED_LIST:-none}` + `$${SKIPPED_LIST:-none}` multi-escape in one string (patterns from affected YAML files)
11. **Update three doc sections** — after confirming bash-operator syntax inside `$${...}` works: `docs/generalized-fsm-loop.md` "Resolution Rules" table escaping row; `docs/guides/LOOPS_GUIDE.md` variable interpolation escape sentence; `docs/reference/API.md` interpolation escape code sample
12. **(Optional) Add integration test fixture** — create `scripts/tests/fixtures/fsm/escape_bash_operators.yaml` with a simple FSM loop state whose action uses `$${DEPTH:-0}` and real `${context.x}` in the same string; use it in an executor-level integration test that confirms the shell command receives `${DEPTH:-0}` literally. Currently no end-to-end test exercises the escape engine through the FSM executor — only unit tests of `interpolate()` directly [second wire pass finding]

## Proposed Solution

```python
# In interpolation.py, look for the escape sequence handling
# It should look roughly like:
text = text.replace('$${', PLACEHOLDER)       # step 1
text = VAR_PATTERN.sub(replace_var, text)     # step 2
text = text.replace(PLACEHOLDER, '${')        # step 3

# If step 2 runs before step 1, or if VAR_PATTERN matches PLACEHOLDER,
# that is the bug.
```

Check also whether `replace_var()` itself applies the three-step logic or delegates to a top-level function that does.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/interpolation.py` — fix the root cause once identified (either step ordering, double-interpolation, or regex issue); key anchors: `interpolate()` at line 169, `VARIABLE_PATTERN`/`ESCAPED_PATTERN`/`ESCAPED_PLACEHOLDER` at lines 25–27

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` at line 732 calls `interpolate(action_template, ctx)`; `_run_action_or_route()` at line 1080 is the call site
- `scripts/little_loops/loops/recursive-refine.yaml` — uses `$${DEPTH:-0}` at line 88 (inside `action: |`) and `$${DEPTH:+" (depth: $DEPTH)"}` at line 96; will work after fix without modification
- `scripts/little_loops/loops/autodev.yaml` — uses `$${PASSED_LIST:-none}` and `$${SKIPPED_LIST:-none}` at lines 496–497; affected by same bug
- `scripts/little_loops/loops/prompt-across-issues.yaml` — uses `$${COUNT}` escape
- `scripts/little_loops/loops/greenfield-builder.yaml` — uses `$${SPEC_LIST[@]}` bash array syntax in escape

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `interpolate`, `interpolate_dict`, `InterpolationContext`, `InterpolationError` in `__all__`; if any public symbol is renamed or removed this file must be updated [Agent 1 finding]
- `scripts/little_loops/fsm/evaluators.py` — imports and calls `interpolate()` in 5 places: `evaluate_output_numeric()`, `evaluate_convergence()` (×3), `evaluate_llm_structured()`; confirm none of these perform an upstream interpolation of `state.action` that would cause double-interpolation [Agent 1 finding]
- `scripts/little_loops/cli/loop/testing.py` — imports `InterpolationContext` (TYPE_CHECKING, line 26); constructs a bare `InterpolationContext()` in line 114 for the simulate/test path [Agent 1 finding]
- `scripts/little_loops/fsm/types.py` — TYPE_CHECKING import of `InterpolationContext` used in the `Evaluator` `Callable` type alias; if `InterpolationContext` is renamed or moved, this import and the type alias must be updated [Agent 1 finding — second wire pass]

### Similar Patterns
- Existing escape tests in `scripts/tests/test_fsm_interpolation.py`: `TestInterpolate.test_escape_sequence`, `test_escape_with_real_variable`, `TestInterpolateEdgeCases.test_multiple_escape_sequences` — all pass currently with simple `$${context.var}` patterns but NOT with `$${VAR:-default}` bash-operator syntax
- Related regression from BUG-954 (now documented in `test_nested_variable_syntax_raises_interpolation_error`) — different root cause (nested `${VAR:-${context.x}}`), but shows how bash-operator syntax in `${}` tokens was previously handled

### Tests
- `scripts/tests/test_fsm_interpolation.py` — add unit tests in `TestInterpolateEdgeCases`:
  - `interpolate("printf '$${DEPTH:-0}'", InterpolationContext())` → `"printf '${DEPTH:-0}'"` without raising
  - `interpolate("X=$${VAR:+suffix}", InterpolationContext())` → `"X=${VAR:+suffix}"` without raising

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_interpolation.py:185` — `TestInterpolate.test_invalid_format_no_dot` asserts `match="expected namespace.path"` on the `replace_var()` error; **will break** if error message wording changes; update the `match=` value if the message is reworded [Agent 3 finding]
- `scripts/tests/test_fsm_interpolation.py:228` — `TestInterpolateEdgeCases.test_nested_variable_syntax_raises_interpolation_error` asserts `InterpolationError` is still raised for `${VAR:-${context.x}}` (single-`$` nested form); **may break** depending on fix strategy — verify after applying the fix that unescaped nesting still raises [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:2666` — `TestActionExceptionRouting.test_interpolation_error_routes_to_on_error_when_set` uses `${missing_var}` (no dot) to trigger `replace_var()`'s guard; **may break** if guard behavior changes; update fixture if needed [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:3662` — `TestInterpolationErrorHandling.test_missing_context_variable_produces_friendly_message` tests the executor's error-wrapping of `InterpolationError`; safe unless executor wrapping code changes [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py` — exercises `interpolate()` via evaluator dispatch; safe (no escape syntax) but serves as regression coverage [Agent 3 finding]
- New tests also needed for: `$${VAR:-default}` mixed with a real `${namespace.path}` in one string; `$${SPEC_LIST[@]}` array expansion syntax; `$${PASSED_LIST:-none}` multi-escape (patterns from affected YAML files) [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — constructs bare `InterpolationContext()` in 6 places (lines 895, 934, 975, 1018, 1062, 1620) via `_make_ctx()` helper; safe unless `InterpolationContext.__init__` acquires required positional parameters [Agent 1 finding — second wire pass]
- `scripts/tests/test_loops_recursive_refine.py` — runs bash snippets from `recursive-refine.yaml` post-interpolation (single-`$` form); does **not** call `interpolate()` directly; no integration test currently exercises the FSM escape engine end-to-end with bash-operator syntax [Agent 3 finding — second wire pass]
- **Gap**: No YAML fixture in `scripts/tests/fixtures/fsm/` uses `$${...}` with bash operators (`:-`, `:+`, `[@]`); only unit tests in `test_fsm_interpolation.py` cover the escape path — a fixture YAML enabling FSM executor integration testing is absent [Agent 3 finding — second wire pass]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — `## Variable Interpolation` section, "Resolution Rules" table (lines 1044–1045): the `Escaping` row shows `$${` → literal `${`; if the fix expands supported bash-operator syntax inside escapes, update this row and the adjacent `Nesting` row [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — `### Variable Interpolation` section (line 951): `"Escape literal ${ with $${"` — add a note that bash parameter expansion operators (`:-`, `:+`, `[@]`) inside `$${...}` blocks are supported and pass through unchanged [Agent 2 finding]
- `docs/reference/API.md` — `### little_loops.fsm.interpolation` section (lines 4239–4241): the code sample shows `$${context.var}` (simple identifier); add a companion example demonstrating `$${DEPTH:-0}` → `${DEPTH:-0}` for bash-default-value use [Agent 2 finding]
- `docs/development/TESTING.md` — "Variable Interpolation Testing" section (line 701) and "Exception Message Validation Best Practices" section (line 278): the latter contains illustrative prose examples using `InterpolationError` with hardcoded message substrings (`"No previous state result"`); if `InterpolationContext.resolve()` messages are rewarded, this prose becomes misleading [Agent 2 finding — second wire pass]

### Configuration
- N/A

## Verification

1. Run `ll-loop run recursive-refine BUG-635` after the fix
2. Confirm no `"Invalid variable"` error in the FSM event log
3. Confirm the shell command receives `${DEPTH:-0}` literally and evaluates it correctly

## Related Issues

- BUG-1381, BUG-1382, BUG-1383: parallel sprint error capture (separate failure mode, same sprint run)

## Labels

`bug`, `fsm`, `interpolation`, `loops`, `bash-syntax`

## Resolution

**Root cause**: The `interpolate()` escape mechanism in `scripts/little_loops/fsm/interpolation.py` was always correct — the 3-step placeholder logic handles `$${VAR:-default}` without issue. The original bug was a single-`$` typo in `recursive-refine.yaml` (fixed in BUG-1380). BUG-1384 tracks the absence of tests that would have caught the typo earlier and the missing documentation of bash-operator support inside `$${...}` escapes.

**Changes**:
- Added 6 regression tests to `scripts/tests/test_fsm_interpolation.py` covering `:-`, `:+`, `[@]`, multi-escape, and mixed real+escaped patterns
- Updated `docs/generalized-fsm-loop.md` Resolution Rules table escaping row to note bash operators pass through
- Updated `docs/guides/LOOPS_GUIDE.md` interpolation section with concrete `$${DEPTH:-0}` example
- Updated `docs/reference/API.md` interpolation code sample with bash default-value example

## Status

**Closed** | Created: 2026-05-09 | Resolved: 2026-05-09 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09 · re-run 2026-05-09_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Root cause unconfirmed — implementer must reproduce and trace before the actual fix is known; the double-interpolation hypothesis is well-reasoned but has not been confirmed with a specific upstream call site in executor.py or elsewhere
- Conditional implementation path — the first two steps are diagnostic (reproduce → trace), adding an investigation phase before coding begins; timeline depends on how quickly the upstream culprit is found
- `interpolate()` has 18+ call sites — a targeted fix to escape or guard logic needs careful regression testing across `TestInterpolate`, `TestInterpolateEdgeCases`, `test_fsm_executor.py:2666` (guard behavior), and `test_fsm_interpolation.py:228` (nested form must still raise)

## Session Log
- `/ll:manage-issue` - 2026-05-09T19:45:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c692082b-781f-4e2e-977f-a76a603c7136.jsonl`
- `/ll:ready-issue` - 2026-05-09T19:41:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b297ddb7-801f-4ba1-aabc-68f533f30384.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e2d94c2-4dd3-4a1c-9d22-1d89481f32c1.jsonl`
- `/ll:wire-issue` - 2026-05-09T19:35:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d9b2232-9acc-446c-ba6e-040d61cb879c.jsonl`
- `/ll:refine-issue` - 2026-05-09T19:28:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/241564ad-4686-4af0-b01b-75d414420fcd.jsonl`
- `/ll:confidence-check` - 2026-05-09T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df9ff0e5-b8c7-4575-a5de-ff01bba6e261.jsonl`
- `/ll:confidence-check` - 2026-05-09T18:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de5d1e40-6a58-4476-a0ee-823619a2a018.jsonl`
- `/ll:wire-issue` - 2026-05-09T17:59:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/14997ce5-cb0a-45bf-942d-b61965bfaf30.jsonl`
- `/ll:refine-issue` - 2026-05-09T17:54:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/035279af-5fb1-40ab-8a05-e6bb424273eb.jsonl`
- `/ll:format-issue` - 2026-05-09T16:53:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19555582-4ac3-4961-9f72-7680d5a59791.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
