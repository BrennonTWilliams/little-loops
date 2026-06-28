---
id: BUG-2373
type: BUG
title: '`UnboundLocalError: _config` in `ll-loop run` from misordered include injection'
priority: P2
status: done
captured_at: '2026-06-28T18:37:50Z'
completed_at: '2026-06-28T18:37:50Z'
discovered_date: 2026-06-28
discovered_by: user-report
labels:
- cli
- ll-loop
- regression
- run-defaults
relates_to:
- ENH-2371
decision_needed: false
confidence_score: 100
---

# BUG-2373: `UnboundLocalError: _config` in `ll-loop run` from misordered include injection

## Summary

Running `ll-loop run <loop> "..."` crashed before execution with:

```
File ".../scripts/little_loops/cli/loop/run.py", line 184, in cmd_run
    if "include" not in fsm.context and _config.loops.run_defaults.include:
                                        ^^^^^^^
UnboundLocalError: cannot access local variable '_config' where it is not associated with a value
```

This is a classic Python **use-before-assignment** bug introduced by the in-progress
**ENH-2371** work ("add `loops.run_defaults.include` config field"). The new block that
injects the `include` allowlist from config referenced `_config` while it was positioned
*above* the `_config = BRConfig(Path.cwd())` assignment. Because `_config` is assigned
somewhere in `cmd_run`, Python treats it as a function-local for the entire body, so the
earlier reference raised `UnboundLocalError`. Every `ll-loop run` invocation crashed while
the block was misordered.

## Root cause

The include-injection block:

```python
if "include" not in fsm.context and _config.loops.run_defaults.include:
    fsm.context["include"] = _config.loops.run_defaults.include
```

depends on `_config`, which is created at `scripts/little_loops/cli/loop/run.py:197`
(`_config = BRConfig(Path.cwd())`). At crash time the block sat above line 197 (reported as
line 184), so it dereferenced the function-local `_config` before it was assigned.

The misordered version existed in neither `HEAD` nor the git index — only the corrected
ordering is present in the working tree — so the crash was produced by a transient mid-edit
state of the uncommitted ENH-2371 change set.

## Resolution (this session)

Investigation confirmed the defect was **already corrected** in the working tree, and that
the ENH-2371 change set was internally coherent:

1. **Ordering fix in place.** The `include` block now sits *after* the `_config`
   assignment — `scripts/little_loops/cli/loop/run.py:197` (`_config = BRConfig(...)`)
   followed by the injection at lines 199–202. No further code change was required.

2. **Attribute resolves.** `loops.run_defaults.include` resolves cleanly, defaulting to
   `""` (`scripts/little_loops/config/features.py:529` field, `:544` `from_dict`).

3. **Regression tests already present.** `scripts/tests/test_loop_cli_defaults.py` contains
   `TestLoopRunIncludeContextInjection`, which routes through `main_loop` → `cmd_run` past
   the previously-crashing line via a `PersistentExecutor` capture spy:
   - `test_include_injected_into_fsm_context_from_config`
   - `test_cli_context_overrides_config_include`
   - `test_empty_config_include_leaves_context_unset`

   These would fail with `UnboundLocalError` if the block were ever re-misordered, so they
   serve as the regression guard for this bug.

## Verification

- `python -m pytest scripts/tests/test_loop_cli_defaults.py` — 17 passed (incl. the 3
  `TestLoopRunIncludeContextInjection` regression tests).
- `ruff check` clean on `run.py`, `features.py`, `test_loop_cli_defaults.py`.
- `mypy scripts/little_loops/cli/loop/run.py` — no issues.
- `BRConfig(Path.cwd()).loops.run_defaults.include` → `''`.

## Notes

The crash no longer reproduces from current source. The fix and its tests live in the
uncommitted ENH-2371 change set (`run.py`, `features.py`, `config-schema.json`); committing
that change set locks in the fix.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-28T18:38:42 - `27b3e971-0e5b-40bf-a313-0d9139355c8e.jsonl`
