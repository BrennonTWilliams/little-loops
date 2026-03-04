---
id: ENH-570
priority: P3
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# ENH-570: `ll-loop show` missing evaluate prompt and state-level fields

## Summary

`cmd_show` shows only `evaluate: llm_structured` (the type) but omits the actual evaluate prompt and all configuration details. Several `StateConfig` fields (`capture`, `timeout`, `on_maintain`) are also never displayed. Users cannot fully inspect a loop's behavior from `ll-loop show` alone.

## Current Behavior

```
  [evaluate] [INITIAL]
    action: ll-issues refine-status
    type: shell
    evaluate: llm_structured
    on_success ──→ done
    on_failure ──→ fix
    on_error ──→ fix
```

Missing from this output:
- The `evaluate.prompt` (multi-line LLM instruction with thresholds, verdict rules)
- `evaluate.min_confidence` (if non-default)
- `evaluate.uncertain_suffix`, `operator`, `target`, `pattern`, `path` (if set)
- State-level `capture`, `timeout`, `on_maintain` (if set)

## Expected Behavior

```
  [evaluate] [INITIAL]
    action: ll-issues refine-status
    type: shell
    evaluate: llm_structured
      prompt: Examine this ll-issues refine-status table output. ...
    on_success ──→ done
    on_failure ──→ fix
    on_partial ──→ fix
    on_error ──→ fix
```

For `llm_structured`, show a truncated preview of the prompt (first 2 lines). Full content available via `--verbose`. For numeric evaluators, show `operator`, `target`, `tolerance`.

## Motivation

- The evaluate prompt contains critical behavioral logic (thresholds, verdict rules, edge cases). Not showing it makes `ll-loop show` insufficient for debugging why a loop routes incorrectly.
- State-level `capture` tells you what variable an action's output is stored in — important for context-dependent loops.
- `on_maintain` determines restart behavior — invisible without reading the YAML.

## Implementation Steps

1. **Evaluate config display** in `cmd_show` (`scripts/little_loops/cli/loop/info.py`):
   ```python
   if state.evaluate:
       ev = state.evaluate
       print(f"    evaluate: {ev.type}")
       if ev.prompt:
           lines = ev.prompt.strip().splitlines()
           preview = lines[0][:100] + (" ..." if len(lines) > 1 or len(lines[0]) > 100 else "")
           print(f"      prompt: {preview}")
       if ev.min_confidence != 0.5:
           print(f"      min_confidence: {ev.min_confidence}")
       if ev.operator:
           print(f"      operator: {ev.operator} {ev.target}")
       if ev.pattern:
           print(f"      pattern: {ev.pattern}")
   ```

2. **State-level fields** — after transitions, add:
   ```python
   if state.capture:
       print(f"    capture: {state.capture}")
   if state.timeout:
       print(f"    timeout: {state.timeout}s")
   if state.on_maintain:
       print(f"    on_maintain ──→ {state.on_maintain}")
   ```

3. **LLM config block** — in the metadata section, show `fsm.llm` if non-default:
   ```python
   llm_dict = fsm.llm.to_dict()
   if llm_dict:
       print(f"LLM config: {llm_dict}")
   ```

4. In `--verbose` mode (see ENH-569), print full evaluate prompt without truncation.

## Files to Change

- `scripts/little_loops/cli/loop/info.py` — `cmd_show` evaluate and state field display

## Dependencies

- ENH-569 (adds `--verbose` flag) — this issue should use the same flag for full evaluate prompt display

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
