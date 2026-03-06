---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# BUG-601: `cmd_compile` drops `llm`, `scope`, and `on_handoff` fields from YAML output

## Summary

When `cmd_compile` serializes a compiled paradigm to `.fsm.yaml`, it omits the `llm`, `scope`, and `on_handoff` fields from the output dict. If a paradigm specifies a custom LLM model, scope restriction, or handoff configuration, those values are present on the in-memory `FSMLoop` but silently dropped during serialization. Loading the compiled `.fsm.yaml` later uses default settings, diverging from the author's intent.

## Location

- **File**: `scripts/little_loops/cli/loop/config_cmds.py`
- **Line(s)**: 43-60 (at scan commit: c010880)
- **Anchor**: `in function cmd_compile()`, "Convert FSMLoop to dict for YAML output" block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/config_cmds.py#L43-L60)
- **Code**:
```python
fsm_dict: dict[str, Any] = {
    "name": fsm.name,
    "paradigm": fsm.paradigm,
    "initial": fsm.initial,
    "states": {name: state.to_dict() for name, state in fsm.states.items()},
    "max_iterations": fsm.max_iterations,
}
if fsm.context:
    fsm_dict["context"] = fsm.context
if fsm.maintain:
    fsm_dict["maintain"] = fsm.maintain
if fsm.backoff:
    fsm_dict["backoff"] = fsm.backoff
if fsm.timeout:
    fsm_dict["timeout"] = fsm.timeout
```

## Current Behavior

`cmd_compile` serializes `name`, `paradigm`, `initial`, `states`, `max_iterations`, `context`, `maintain`, `backoff`, and `timeout` — but never serializes `fsm.llm` (the `LLMConfig` object), `fsm.scope`, or `fsm.on_handoff`.

## Expected Behavior

All non-default fields on the `FSMLoop` should be serialized, including `llm`, `scope`, and `on_handoff`, so that running the compiled `.fsm.yaml` produces identical behavior to running the paradigm file directly.

## Steps to Reproduce

1. Create a paradigm file with custom LLM settings:
   ```yaml
   paradigm: goal
   name: my-loop
   goal: Tests pass
   tools: [pytest]
   llm:
     model: claude-opus-4
     max_tokens: 1024
   scope: [src/]
   ```
2. Run `ll-loop compile my-loop.yaml`
3. Open `my-loop.fsm.yaml` — `llm` and `scope` entries are absent
4. Run `ll-loop run my-loop.fsm.yaml` — uses default LLM model and no scope lock

## Root Cause

- **File**: `scripts/little_loops/cli/loop/config_cmds.py`
- **Anchor**: `in function cmd_compile()`
- **Cause**: The serialization dict construction manually enumerates fields to include. The `llm`, `scope`, and `on_handoff` fields were never added to the enumeration.

## Motivation

Silent data loss during compilation means users who customize `llm`, `scope`, or `on_handoff` get unexpected behavior when running compiled `.fsm.yaml` files. The compiled output appears valid but silently reverts to defaults, making debugging difficult and eroding trust in the compile workflow.

## Proposed Solution

Add conditional serialization for the missing fields after the existing `if fsm.timeout:` block:

```python
if fsm.llm:
    fsm_dict["llm"] = fsm.llm.to_dict()  # or dataclasses.asdict(fsm.llm)
if fsm.scope:
    fsm_dict["scope"] = fsm.scope
if fsm.on_handoff:
    fsm_dict["on_handoff"] = fsm.on_handoff
```

Verify that `LLMConfig` has a `to_dict()` method or use `dataclasses.asdict()`.

## Implementation Steps

1. Add `llm`, `scope`, and `on_handoff` to the serialization block in `cmd_compile`
2. Add a round-trip test: compile a paradigm with custom llm/scope, load the output, verify fields match
3. Verify `LLMConfig` serialization produces valid YAML

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/config_cmds.py` — add `llm`, `scope`, `on_handoff` to serialization dict in `cmd_compile()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run_cmds.py` — loads compiled `.fsm.yaml`; will now receive complete config
- `scripts/little_loops/cli/loop/loader.py` — YAML loader that parses FSMLoop from dict

### Similar Patterns
- N/A — serialization is centralized in `cmd_compile()`

### Tests
- `scripts/tests/` — add round-trip compile test verifying `llm`, `scope`, `on_handoff` survive serialization

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - Silent data loss during compilation; compiled output behaves differently from source
- **Effort**: Small - Adding 3 conditional lines to existing serialization block
- **Risk**: Low - Additive change, existing fields unaffected
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `config`

## Session Log
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/30c0642f-bc3d-4a06-8802-42e5b1e42a67.jsonl` — readiness: 100/100 PROCEED, outcome: 86/100 HIGH CONFIDENCE
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/30c0642f-bc3d-4a06-8802-42e5b1e42a67.jsonl` — Added Motivation, Integration Map sections (v2.0 alignment)
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: serialization dict at `config_cmds.py:43-57` confirmed; `llm`, `scope`, `on_handoff` absent; `context`, `maintain`, `backoff`, `timeout` present
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — Added missing `## Status` heading (v2.0 structural alignment)

---

## Status

**Open** | Created: 2026-03-06 | Priority: P2
