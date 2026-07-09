---
captured_at: "2026-07-09T00:35:54Z"
discovered_date: 2026-07-09
discovered_by: capture-issue
status: open
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

## Session Log

- `/ll:capture-issue` - 2026-07-09T00:35:54Z
