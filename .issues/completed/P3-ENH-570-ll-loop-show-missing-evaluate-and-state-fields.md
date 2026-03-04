---
id: ENH-570
priority: P3
status: completed
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 97
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

## Acceptance Criteria

- [ ] `ll-loop show` displays a truncated evaluate prompt preview (first 2 lines, max 100 chars each) for `llm_structured` evaluators
- [ ] `ll-loop show` displays `min_confidence` only when it differs from the default (0.5)
- [ ] `ll-loop show` displays `operator` and `target` for numeric/threshold evaluators when set
- [ ] `ll-loop show` displays `pattern` when set on an evaluator
- [ ] `ll-loop show` displays state-level `capture`, `timeout`, and `on_maintain` when configured on a state
- [ ] LLM config block shown in metadata section when non-default values are present
- [ ] All existing `ll-loop show` output is preserved (no regressions)

## Success Metrics

- **Before**: `ll-loop show` output omits evaluate prompt, min_confidence, operator/target, pattern, and all state-level fields
- **After**: All configured evaluate and state-level fields visible in `ll-loop show` output without requiring the user to read the YAML file directly
- **Regression**: `ll-loop show` on loops with no evaluate config or no optional state fields produces identical output to current behavior

## Scope Boundaries

- **In scope**: `cmd_show` display logic in `scripts/little_loops/cli/loop/info.py`; evaluate config fields (`prompt` preview, `min_confidence`, `operator`, `target`, `pattern`); state-level fields (`capture`, `timeout`, `on_maintain`); LLM config block in metadata
- **Out of scope**: Full evaluate prompt display (deferred to ENH-569 `--verbose` flag); `ll-loop run` output; other loop commands (`status`, `list`, `history`)

## Implementation Steps

1. **Evaluate config display** — expand block at `info.py:551–552`:
   ```python
   if state.evaluate:
       ev = state.evaluate
       print(f"    evaluate: {ev.type}")
       if ev.prompt:
           lines = ev.prompt.strip().splitlines()
           preview = lines[0][:100] + (" ..." if len(lines) > 1 or len(lines[0]) > 100 else "")
           print(f"      prompt: {preview}")
       if ev.min_confidence != 0.5:  # default is 0.5 per schema.py:70
           print(f"      min_confidence: {ev.min_confidence}")
       if ev.operator:
           print(f"      operator: {ev.operator} {ev.target}")
       if ev.pattern:
           print(f"      pattern: {ev.pattern}")
   ```

2. **State-level fields** — add after the existing transitions block (`info.py:553–562`), before route display:
   ```python
   if state.capture:
       print(f"    capture: {state.capture}")
   if state.timeout:
       print(f"    timeout: {state.timeout}s")
   if state.on_maintain:
       print(f"    on_maintain ──→ {state.on_maintain}")
   ```
   Fields defined at `schema.py:201–203`.

3. **LLM config block** — add to metadata section (`info.py:519–537`), after existing optional fields; `LLMConfig` is at `schema.py:295`, `fsm.llm` at `schema.py:371`. Defaults are `model="sonnet"`, `max_tokens=256`, `timeout=30`, `enabled=True` — show only when non-default:
   ```python
   llm = fsm.llm
   llm_parts = []
   if llm.model != "sonnet":
       llm_parts.append(f"model={llm.model}")
   if llm.max_tokens != 256:
       llm_parts.append(f"max_tokens={llm.max_tokens}")
   if llm.timeout != 30:
       llm_parts.append(f"timeout={llm.timeout}s")
   if llm_parts:
       print(f"LLM config: {', '.join(llm_parts)}")
   ```
   Note: verify whether `LLMConfig` has a `to_dict()` method before using it.

4. **Tests** — add to `scripts/tests/test_ll_loop_display.py` following `TestPrintExecutionPlan` patterns (lines 304–388, the class at those lines — note: `TestCmdShow` is in `test_ll_loop_commands.py` at line 312, not in this file): write YAML with the new fields, assert new lines appear in `capsys.readouterr().out`. Cover: evaluate prompt preview (truncation at 100 chars), non-default `min_confidence`, `operator`/`target`, `pattern`, each of `capture`/`timeout`/`on_maintain`, and absence of LLM block when defaults used.

5. In `--verbose` mode (see ENH-569), print full evaluate prompt without truncation.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` at line 503; evaluate display block at lines 551–552 (expand); state loop at lines 542–568 (add `capture`, `timeout`, `on_maintain`); metadata section at lines 519–537 (add LLM config block)

### Dependent Files (Read-Only Reference)
- `scripts/little_loops/fsm/schema.py` — source of truth for `EvaluateConfig` (line 25, fields: `prompt` at line 68, `min_confidence` at line 70 with default `0.5`, `operator`, `target`, `tolerance`, `pattern`, `path`), `StateConfig` (line 167, `capture` at line 201, `timeout` at line 202, `on_maintain` at line 203), `LLMConfig` (line 295, fields: `enabled`, `model` default `"sonnet"`, `max_tokens` default `256`, `timeout` default `30`), `FSMLoop.llm` field (line 371)
- `scripts/little_loops/cli/loop/_helpers.py` — `print_execution_plan` at line 101 has the same evaluate-type-only display pattern (line 116); out of scope but parallel context

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary test file; add cases for evaluate prompt preview, min_confidence, operator/target, pattern, and state-level fields. Use existing `make_test_state` / `make_test_fsm` factories (lines 24–72) and follow `TestCmdShow` patterns (lines 304–388) — write YAML to `tmp_path`, `monkeypatch.chdir`, patch `sys.argv`, assert on `capsys.readouterr().out`
- `scripts/tests/test_ll_loop_commands.py` — existing `TestCmdShow` at line 312 (3 tests); must not regress

### Documentation
- N/A — `ll-loop show` is a CLI command; behavior is self-documenting

### Configuration
- N/A

## Dependencies

- ENH-569 (adds `--verbose` flag) — this issue should use the same flag for full evaluate prompt display

## Resolution

All acceptance criteria met. Modified `scripts/little_loops/cli/loop/info.py`:
- Expanded evaluate block to show `prompt` preview (first line, max 100 chars, ` ...` if multi-line), `min_confidence` (non-default only), `operator`/`target`, `pattern`
- Verbose mode (`--verbose`) shows full prompt as indented block
- Added state-level `capture`, `timeout`, `on_maintain` display
- Added LLM config metadata block (shown only when non-default values present)

Added 12 new tests to `scripts/tests/test_ll_loop_commands.py::TestCmdShow`. Updated existing verbose evaluate prompt test to match new `prompt:` format. All 3172 tests pass.

## Session Log
- `/ll:confidence-check` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55d7c8e7-ed1c-4f5d-b244-e812f7e7548d.jsonl`
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6597c7fe-9a5f-4855-8b66-52360a144614.jsonl`
- `/ll:refine-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e64419-077a-4419-9450-a8d0a45ee28c.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/89d50802-77c8-4fea-b4d7-e84780aad71a.jsonl`
