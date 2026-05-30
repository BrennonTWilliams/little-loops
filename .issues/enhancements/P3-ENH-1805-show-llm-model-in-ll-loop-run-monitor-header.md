---
id: ENH-1805
status: open
priority: P3
type: ENH
captured_at: '2026-05-30T04:12:22Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
---

# ENH-1805: Show LLM model in `ll-loop run` and `ll-loop monitor` header

## Summary

Extend the artifact-paths header section introduced in ENH-1701 to also display the LLM model being used in the current turn, when available. This gives users visibility into which model is executing their loop without consulting configuration files or CLI flags.

## Current Behavior

The pinned pane and startup header show:

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
────────────────────────────────────────────────────────────
[FSM diagram]
```

The LLM model is not displayed anywhere in the run or monitor output. Users must check the loop YAML's `model:` field, `.ll/ll-config.json`, or CLI flags to determine the active model.

## Expected Behavior

The model appears alongside artifact paths in the header:

```
== loop: rn-refine =========================================
  loop:       loops/rn-refine.yaml
  output_dir: .loops/plans/
  model:      claude-opus-4-7
────────────────────────────────────────────────────────────
[FSM diagram]
```

When the model is not available (not yet resolved, or running with the default), the model line is omitted. The model line uses the same 2-space indent and dim colorization as the artifact path lines.

## Motivation

Users running loops need to know which model is executing their work. A loop configured with `claude-haiku-4-5` behaves very differently from one using `claude-opus-4-7`, and surfacing the model in the header helps users:
- Correlate loop behavior and output quality with model capabilities
- Catch misconfigurations (e.g., an expensive model accidentally left on a frequent loop)
- Understand cost implications at a glance

## Proposed Solution

The model can be sourced from `fsm.context` if loops inject it there, or from the resolved FSM's `model` field. The `_artifact_lines` helper from ENH-1701 already extracts path-like values from `fsm.context`; the model should be handled similarly — either as an additional entry in `_artifact_lines` or as a separate `_model_line` helper. The model value should be dim-colorized matching the artifact path style (`colorize(value, '2')`).

## Scope Boundaries

- **In scope**: Pinned pane header (`_build_pinned_pane`), non-pinned startup block in `run_foreground`, and `ll-loop monitor` attach display (via shared `StateFeedRenderer`). Model sourced from resolved FSM configuration or context.
- **Out of scope**: Displaying model changes mid-run (if the loop switches models); displaying token usage or cost estimates; model display in `ll-loop run --json` output or `ll-loop info`.

## Success Metrics

- Users can identify the active LLM model from the header without consulting config files
- Both `ll-loop run` and `ll-loop monitor` display the model consistently
- No regressions in artifact path display or header formatting

## Implementation Steps

1. Identify the canonical source of the resolved model in the FSM/runner pipeline
2. Thread the model value through `_build_pinned_pane`, `_render_pinned_pane`, `StateFeedRenderer`, and `run_foreground` (following the ENH-1701 pattern)
3. Render the model line with 2-space indent and dim colorization between the artifact paths and the separator line, or after the last artifact path line
4. Add tests for model display in pinned and non-pinned modes
5. Verify no regressions in existing header rendering tests

## API/Interface

N/A — No public API changes. Internal threading of a `model: str | None` value through display helpers, following the same pattern as `loop_path: Path | None` from ENH-1701.

## Impact

- **Priority**: P3 — UX improvement; loops are fully functional without this, but model visibility reduces debugging friction
- **Effort**: Small — follows the established ENH-1701 threading pattern; primarily adding a `model` parameter alongside the existing `loop_path` parameter
- **Risk**: Low — output-only change; `model` defaults to `None` so all existing callers are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ux`, `ll-loop`

## Session Log
- `/ll:capture-issue` - 2026-05-30T04:12:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3dadd8e3-fc7a-4acb-bcd9-75794404ebd6.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
