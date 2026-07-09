---
captured_at: '2026-07-09T00:35:54Z'
completed_at: 2026-07-09 01:13:42+00:00
discovered_date: 2026-07-09
discovered_by: capture-issue
status: done
confidence_score: 98
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 19
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2553: `ll-loop run rn-refine <plan.md>` falsely reports `:default=` context refs as missing required variables

## Summary

The pre-run validator in `cli/loop/run.py` uses a regex that captures everything between `${context.` and `}`, including the engine-native `:default=value` suffix. As a result, every context reference written in default-guard form (e.g. `${context.dry_run:default=false}`) is extracted as a key like `dry_run:default=false`, found absent from `fsm.context`, and reported as a missing required variable. The validator then exits 1 before the loop runs a single state, even though the FSM engine itself would have handled the missing key via the `:default=` fallback.

`rn-refine` is the most prominent victim (its `preflight_check` and `finalize` actions use `${context.floor_fraction:default=0.5}`, `${context.dry_run:default=false}`, `${context.confirm_overwrite:default=false}`), so the loop can no longer be launched with only the plan file as input:

```
$ ll-loop run rn-refine Tableau-Design-Plan.md
[ERR] Missing required context variable: 'confirm_overwrite:default=false'. Run with: ll-loop run rn-refine --context confirm_overwrite:default=false=VALUE
[ERR] Missing required context variable: 'dry_run:default=false'. Run with: ll-loop run rn-refine --context dry_run:default=false=VALUE
[ERR] Missing required context variable: 'floor_fraction:default=0'. Run with: ll-loop run rn-refine --context floor_fraction:default=0=VALUE
```

The error message's own example (`--context key=VALUE`) confirms the validator sees the suffix as part of the variable name.

## Current Behavior

Any loop whose states reference context vars using the `:default=` engine-native fallback syntax (without also listing them in `fsm.context`) trips this validator. The user is forced to pass every default-guarded ref explicitly on the CLI to satisfy the false-positive, e.g.

```
ll-loop run rn-refine Tableau-Design-Plan.md \
  --context confirm_overwrite=false \
  --context dry_run=false \
  --context floor_fraction=0.5
```

This regresses the documented "input file only" UX for `rn-refine` and silently affects every other loop that uses `:default=` guards.

## Expected Behavior

- `${context.X:default=Y}` and `${context.X?}` references are treated as having a fallback and are NOT reported as missing required context vars. Only "bare" `${context.X}` references (no guard) for keys not in `fsm.context` should be flagged.
- The validator's success/error message matches what the engine will actually do. Today the two disagree: engine resolves the fallback fine, validator claims the var is required.
- `ll-loop run rn-refine Tableau-Design-Plan.md` runs to completion (or hits a real error) without the user having to repeat the engine-default values back through `--context`.

## Motivation

- **User impact**: `rn-refine` and any other loop relying on engine-native `:default=` guards become unrunnable with the documented invocation (`ll-loop run <loop> <input>`). Users hit this on every invocation that previously worked.
- **Engine/validator drift**: The two implementations disagree on what constitutes a "missing" context reference. Engine (`fsm/interpolation.py:230-238`) and validator (`fsm/validation.py:2554` — "Only collect references NOT guarded by `:default=`: a guarded reference is safe even when the capture is missing") both treat `:default=` as authoritative; this single CLI check in `run.py` does not.
- **Discoverability**: The error message surfaces `key:default=value` as if the user must supply that whole string, which has no working overload. Anyone trying to follow the message blindly makes it worse.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Function**: pre-run validation block (lines 252-270)
- **Regex**: `_ctx_var_re = re.compile(r"\$\{context\.([^}.]+)")`
- **Cause**: Group 1 matches greedily up to `}` and does NOT strip a `:default=value` suffix. Combined with the comparison `if key not in fsm.context:` the captured `"dry_run:default=false"` is never going to be present in `fsm.context`, so the guard fails. The engine-side split (`interpolation.py:231`) and the validator's reference-collection (`validation.py:2554`) both explicitly honor `:default=`; this one CLI check is out of sync.

## Location

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Anchor**: pre-run validation block, lines 252-270 (`_ctx_var_re` definition + missing-key loop)
- **Related (correct) implementations**:
  - `scripts/little_loops/fsm/interpolation.py:230-238` — engine splits on `:default=` before resolving
  - `scripts/little_loops/fsm/validation.py:2554` — explicitly skips default-guarded refs

## Resolution

Mirror the engine's split in the validator: strip a `:default=` suffix from the captured key before the membership check, and (preferred) skip guarded refs entirely so the two implementations stay aligned. Suggested patch shape:

```python
_ctx_var_re = re.compile(r"\$\{context\.([^}.]+)")
missing_keys: set[str] = set()
for state in fsm.states.values():
    templates = [state.action] if state.action else []
    if state.evaluate and state.evaluate.prompt:
        templates.append(state.evaluate.prompt)
    for template in templates:
        for m in _ctx_var_re.finditer(template):
            raw = m.group(1)
            # Default-guarded refs (`${context.x:default=y}` or `${context.x?}`) are
            # safe even when the capture is missing — see fsm/validation.py:2554.
            if ":default=" in raw or raw.endswith("?"):
                continue
            if raw not in fsm.context:
                missing_keys.add(raw)
if missing_keys:
    ...
```

Add a regression test in `scripts/tests/` that asserts a loop whose action uses `${context.x:default=true}` does NOT trip the validator when `x` is absent from `fsm.context`, and that a truly bare `${context.x}` (no guard) still does.

## Integration Map

_Added by `/ll:refine-issue` — codebase-driven research findings._

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — pre-run validator block at lines 252-270; update the `_ctx_var_re` consumer loop to skip guarded refs (mirror `fsm/validation.py:135-156` idiom)

### Related (correct) implementations — do NOT modify, reference for the fix idiom
- `scripts/little_loops/fsm/interpolation.py:230-238` — engine splits `:default=` before resolving; also strips trailing `?` (lines 239-241)
- `scripts/little_loops/fsm/validation.py:135-156` — `_CAPTURED_REF_FULL_RE` + `_unguarded_captured_refs()` show the canonical "skip guarded refs" pattern; consumer comment at `fsm/validation.py:2554`
- `scripts/little_loops/fsm/concurrency.py:32` — `_CONTEXT_VAR_RE` for `${context.X}` in `scope:` paths; same blind spot exists but is harmless because `resolve_scope()` leaves the path as-is literal instead of asserting missing

### Dependent files (callers/importers) — no changes required, but worth noting
- `scripts/little_loops/cli/loop/__init__.py:268-274` — `--context` CLI flag definition (`action="append"`, `metavar="KEY=VALUE"`)
- `scripts/little_loops/cli/loop/run.py:164-168` — `--context KEY=VALUE` parser (`partition("=")`); suffix-blindness is intentional here because the engine defaults are passed via the YAML `context:` block, not via `--context`
- `scripts/little_loops/cli/loop/lifecycle.py:514-518` — `resume` reuses the same `partition("=")` parser

### Affected loops (consumers of the fix; no loop-YAML changes needed)
- `scripts/little_loops/loops/rn-refine.yaml:355` — `FLOOR="${context.floor_fraction:default=0.5}"` (primary victim)
- `scripts/little_loops/loops/rn-refine.yaml:413-414` — `DRY_RUN="${context.dry_run:default=false}"`, `CONFIRM="${context.confirm_overwrite:default=false}"`
- `scripts/little_loops/loops/recursive-refine.yaml:50,70,71,106,275,291` — `order:default=queue`, `commit_every:default=0`, `no_recursion:default=false`, etc.
- `scripts/little_loops/loops/rl-coding-agent.yaml:26` — guarded context ref
- `scripts/little_loops/loops/lib/composer.yaml:32` — `${context.include:default=}`

### Tests
- `scripts/tests/test_ll_loop_errors.py:248-284` — `test_missing_context_input_clear_error` covers the missing-context error path; uses bare `${context.input}` (unguarded), so will still pass after the fix
- `scripts/tests/test_ll_loop_errors.py:315-359` — `TestRequiredInputsGuard.test_missing_input_exits_1` covers the YAML-declared `required_inputs:` list (a separate validator, NOT the regex scan); unaffected
- `scripts/tests/test_ll_loop_commands.py:4098-4142` — `TestRequiredInputGuard.test_required_input_supplied_proceeds` for the `required_inputs` validator; unaffected
- `scripts/tests/test_fsm_validation.py:2589-2646` — `TestCaptureReachabilityValidation` is the canonical pattern for "guarded ref is safe" assertions (mirror for new regression test)
- `scripts/tests/test_fsm_interpolation.py:553-756` — `TestSafeInterpolation` proves the engine honors `:default=` (lines 558-628) and `?` (lines 707-756) in the `${context.X}` namespace

### Regression test (to add)
Add a `TestPreRunContextValidator` class to `scripts/tests/test_ll_loop_commands.py`, modeled on `TestRequiredInputsGuard` (test_ll_loop_errors.py:315-359). Required cases:
1. Loop whose action uses `${context.x:default=true}` and `x` is NOT in `fsm.context` does NOT trip the validator (returns 0, not 1)
2. Loop whose action uses `${context.x?}` (nullable) and `x` is NOT in `fsm.context` does NOT trip the validator
3. Loop whose action uses bare `${context.x}` (no guard) and `x` is NOT in `fsm.context` STILL trips the validator (returns 1, error message mentions `x` without suffix)
4. Loop whose action mixes guarded and unguarded references to the same key: validator flags only the unguarded form (mirror `test_mixed_guarded_and_unguarded_still_warns` at `test_fsm_validation.py:2630-2646`)

### Documentation
- `docs/generalized-fsm-loop.md:1148-1153` — Safe interpolation docs (`:default=`, `?`, suffix mutual exclusion); no update needed (engine behavior is unchanged)
- `docs/reference/CLI.md:674,694` — MR-7 rule description; no update needed
- `CHANGELOG.md` — append entry under the next `## [X.Y.Z]` section (not `[Unreleased]`) noting BUG-2553 fix; mirror the MR-7 entry style at `CHANGELOG.md:235`

## Implementation Steps

_Added by `/ll:refine-issue` — sequenced steps for the implementer._

1. **Modify `scripts/little_loops/cli/loop/run.py` lines 252-270** — update the pre-run validator block to skip `${context.X:default=Y}` and `${context.X?}` refs. Mirror the `_unguarded_captured_refs()` idiom at `fsm/validation.py:146-156`:
   - Use the suggested patch shape (issue body Resolution section lines 67-87): if captured group contains `:default=` or ends with `?`, `continue`
   - This "skip guarded refs entirely" form is preferred over stripping-and-comparing because it keeps the validator + engine aligned (both treat guarded refs as inherently safe)

2. **Verify the error message integrity** — confirm the `Run with: ll-loop run <loop> --context <key>=VALUE` advice never includes `:default=` (since `_ctx_var_re` now only enters the error path for unguarded refs, the printed `key` is always the bare key)

3. **Add regression tests in `scripts/tests/test_ll_loop_commands.py`** — see "Regression test (to add)" in Integration Map above for the four required cases. Use the `tmp_path/.loops/<loop>.yaml` + `monkeypatch.chdir` + `main_loop()` pattern from `test_ll_loop_errors.py:315-359`

4. **Run the full test suite** — `python -m pytest scripts/tests/` must exit 0. Pay particular attention to:
   - `scripts/tests/test_ll_loop_errors.py` (existing `test_missing_context_input_clear_error` should still pass since its template is bare)
   - `scripts/tests/test_builtin_loops.py` (the 14 loops using `:default=` guards — all should now load without the false-positive)
   - `scripts/tests/test_rn_refine.py` (rn-refine is the primary victim; existing tests use engine interpolation directly via `_render()`, not the pre-run validator, so they should still pass)

5. **Manual smoke test** — verify the documented invocation works:
   ```bash
   ll-loop run rn-refine <plan-file.md>
   ```
   Should no longer exit 1 with `Missing required context variable: 'floor_fraction:default=0.5'`, `'dry_run:default=false'`, or `'confirm_overwrite:default=false'`

## Impact

- **Priority**: P2 — affects every loop that uses engine-native `:default=` guards (14 loops including the primary `rn-refine` victim), but the underlying loop code is correct; only the CLI pre-flight check is out of sync with the engine.
- **Effort**: Small — single regex consumer loop (~10 lines) + 1 regression test class (~80 lines). Mirrors the existing `_unguarded_captured_refs()` idiom in `fsm/validation.py:146-156`.
- **Risk**: Low — the fix only relaxes the validator for already-safe references (`:default=` and `?` guards); unguarded refs continue to be flagged. No behavior change for already-passing invocations.
- **Breaking Change**: No — the validator's success/error message will now match what the engine already does. Invocations that previously worked will continue to work.

## Acceptance Criteria

_Added by `/ll:refine-issue` — testable gates._

- [ ] `ll-loop run rn-refine <plan-file.md>` runs without requiring any `--context` override (the `floor_fraction` / `dry_run` / `confirm_overwrite` refs are guarded by `:default=` and the engine substitutes)
- [ ] `ll-loop run <loop>` for any loop whose actions use `${context.X:default=Y}` does NOT exit 1 when `X` is absent from both `fsm.context` and the YAML `context:` block
- [ ] `ll-loop run <loop>` for any loop whose actions use `${context.X?}` (nullable) does NOT exit 1 when `X` is absent
- [ ] `ll-loop run <loop>` STILL exits 1 when a loop's actions use bare `${context.X}` and `X` is absent — the error message lists `X` without a `:default=` suffix
- [ ] `ll-loop run <loop> --context X=value` still overrides the engine default (i.e. CLI override and `:default=` coexist; the CLI value wins because `_parse_program_md` and the `--context` parser both run before the validator at `cli/loop/run.py:142-168`)
- [ ] New `TestPreRunContextValidator` regression tests cover all four cases listed in Implementation Steps #3 and pass under `python -m pytest scripts/tests/`
- [ ] `python -m pytest scripts/tests/` exits 0 (full suite green)
- [ ] `python -m mypy scripts/little_loops/` and `ruff check scripts/` exit 0 (no type/lint regressions)

## Session Log
- `/ll:confidence-check` - 2026-07-08 - `3cd58548-e8d8-45ad-abb7-51b698ff28bf.jsonl`
- `/ll:refine-issue` - 2026-07-09T00:42:50 - `db5d428e-6214-4eed-8f35-6bb1fbbfb780.jsonl`
- `/ll:ready-issue` - 2026-07-09T01:35:54Z - `<this-session-jsonl>`
- `/ll:manage-issue` - 2026-07-09T01:13:42Z - applied fix per Resolution § patch shape (skip guarded refs entirely); added `TestPreRunContextValidator` (4 cases) to `scripts/tests/test_ll_loop_commands.py`; 14,360 passed / 36 skipped in full suite; mypy + ruff clean

- `/ll:capture-issue` - 2026-07-09T00:35:54Z

## Resolution

Fixed in `scripts/little_loops/cli/loop/run.py:252-275` (pre-run validator block). The regex consumer now mirrors the engine split idiom in `fsm/interpolation.py:230-241` and the `_unguarded_captured_refs` pattern in `fsm/validation.py:135-156`: when the captured group contains `:default=` or ends with `?`, the ref is skipped (the engine supplies a fallback at render time, so the missing context key is provably safe). All previously-failing loops (`rn-refine`, `recursive-refine`, `rl-coding-agent`, `composer.yaml`, and 10 others using engine-native `:default=` guards) are once again runnable with `ll-loop run <loop> <input>` alone. The error message printed for genuinely bare `${context.X}` refs no longer carries a spurious `:default=` suffix. Regression coverage added in `scripts/tests/test_ll_loop_commands.py::TestPreRunContextValidator` (4 cases: default-guard, nullable, bare, mixed guarded+unguarded).

**Status**: Done | Created: 2026-07-09 | Priority: P2
