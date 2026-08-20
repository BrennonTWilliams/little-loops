---
id: BUG-3266
type: BUG
title: ll-loop resume ignores the use_design_tokens opt-out
priority: P2
status: open
relates_to:
- ENH-3264
- ENH-3267
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T21:10:34Z'
labels:
- bug
- design-tokens
- loops
---

# BUG-3266: ll-loop resume ignores the use_design_tokens opt-out

## Summary

`ll-loop resume` ignores the per-loop `use_design_tokens: false` opt-out that ENH-3099 added. `cmd_resume` re-implements design-token context injection as a parallel copy of `cmd_run`'s block, but without the opt-out gate — so a loop that explicitly disables token injection still gets `design_tokens_context` populated when resumed.

Fix by extracting the gate into a shared helper called from both sites, so the two injection paths cannot diverge again.

## Current Behavior

Two independent injection blocks, structurally *similar* but not identical:

`scripts/little_loops/cli/loop/run.py:242-254` (`cmd_run`) computes the gate, including the string-coercion branch for `--context use_design_tokens=false`:

```python
_use_tokens = fsm.context.get("use_design_tokens", True)
if isinstance(_use_tokens, str):
    _use_tokens = _use_tokens.strip().lower() not in ("", "0", "false", "no", "off")
if _use_tokens and not fsm.context.get("design_tokens_context"):
    _tokens = load_design_tokens(_config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
else:
    fsm.context.setdefault("design_tokens_context", "")
```

`scripts/little_loops/cli/loop/lifecycle.py:715-717` (`cmd_resume`) has **no gate at all**:

```python
if not fsm.context.get("design_tokens_context"):
    _tokens = load_design_tokens(config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
```

So `use_design_tokens: false` is honored on `ll-loop run` and silently ignored on `ll-loop resume`.

## Expected Behavior

`use_design_tokens: false` suppresses `design_tokens_context` identically on both `ll-loop run` and `ll-loop resume`, including via `--context use_design_tokens=false` (string coercion). The key still exists as `""` in both paths so `${context.design_tokens_context}` interpolates without error.

## Motivation

A per-loop opt-out that works on one entry point and silently no-ops on another is worse than no opt-out: the loop author sets `use_design_tokens: false`, sees it honored on `ll-loop run`, and reasonably assumes it holds. Long-running loops are exactly the ones most likely to be resumed, so the path where the setting is ignored is the path where it matters most.

It also blocks ENH-3264's follow-on work: `design_guidance_context` needs a second variable injected under the same gate, and adding it to two divergent parallel blocks would double the defect rather than fix it. Extracting the shared helper here is what makes the follow-on safe.

## Proposed Solution

Extract the gate + injection into a single shared helper — for example `inject_design_context(fsm, config)` in a module both call sites already import from — and call it from `cmd_run` and `cmd_resume`. Do not copy the block a second time; the parallel-maintenance pattern is what produced this defect.

The helper owns: reading `use_design_tokens` (bool or string form), the string coercion, the `load_design_tokens()` call, `render_as_prompt_context()`, and the `setdefault(..., "")` fallback.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py:242-254` — replace the inline block with a call to the shared helper
- `scripts/little_loops/cli/loop/lifecycle.py:707-717` — replace the ungated block with the same call

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` (`test_design_tokens_context_injected_via_cmd_resume`) — existing coverage of the resume injection path
- `scripts/tests/test_cli_loop_lifecycle.py:1397-1480` (`TestUseDesignTokensOptOut`, ENH-3099) — currently exercises `cmd_run` only; add the `cmd_resume` counterpart, which fails before the fix

## Implementation Steps

1. Add the `cmd_resume` opt-out test to `TestUseDesignTokensOptOut` (`test_cli_loop_lifecycle.py:1397-1480`) and confirm it fails against current `main` — this is the regression proof.
2. Extract `run.py:242-254`'s gate + injection wholesale into a shared helper, preserving the string-coercion branch and the `setdefault(..., "")` fallback exactly.
3. Call the helper from `cmd_run` (`run.py:242-254`) and `cmd_resume` (`lifecycle.py:707-717`), deleting both inline blocks.
4. Verify: the new test passes, `test_design_tokens_context_injected_via_cmd_resume` (`:921-948`) still passes, and `python -m pytest scripts/tests/` exits 0.

## Impact

- **Scope**: two call sites plus one new helper. ~30 LOC net.
- **Compatibility**: behavior change only for loops that set `use_design_tokens: false` *and* are resumed — currently a silent no-op, which is the bug.
- **Risk**: low. Isolated, fully covered by existing test classes once the resume counterpart is added.

## Scope Boundaries

**In scope**
- The shared-helper extraction and the `cmd_resume` gate fix, for the existing `design_tokens_context` variable only.

**Out of scope**
- Any new context variable. `design_guidance_context` is ENH-3264's follow-on and consumes this helper once it exists.
- Any change to `load_design_tokens()` or the design-token model.

## Acceptance Criteria

1. `use_design_tokens: false` on a loop suppresses `design_tokens_context` on `ll-loop resume`, not just `ll-loop run`. *(Fails on current `main`.)*
2. `--context use_design_tokens=false` (string form) is honored on both paths — the string-coercion branch lives in the shared helper.
3. When suppressed, `design_tokens_context` is still present as `""` on both paths, so `${context.design_tokens_context}` never hard-fails interpolation.
4. Exactly one implementation of the gate exists; `cmd_run` and `cmd_resume` both call it.
5. `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of ENH-3264, where it was pulled into scope because that issue's acceptance criteria could not pass against current `main` without it. It is an independent defect that exists today and does not depend on any DESIGN.md work, so it ships on its own.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2
