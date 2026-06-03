---
id: ENH-1898
title: Add required_inputs guard for loops with input_key
type: enhancement
priority: P3
status: open
captured_at: "2026-06-03T19:12:59Z"
discovered_date: 2026-06-03
discovered_by: capture-issue
labels: [fsm, validation, dx]
---

# ENH-1898: Add `required_inputs` guard for loops with `input_key`

## Summary

The FSM loop runtime has no way to declare that a runtime input is required.
A loop declaring `input_key: description` runs silently with
`context.description: ""` when no input is supplied, producing degraded output
(e.g. a generic brief) with no warning. Add a `required_inputs` declaration and
a pre-flight guard so missing inputs fail fast.

## Current Behavior

`grep -rn "required_inputs" scripts/little_loops/` returns nothing — the concept
does not exist. The `svg-textgrad` audit (§9, "`description` context is empty")
observed that the resolved FSM showed `context.description: ""`, meaning
`ll-loop run svg-textgrad` with no description silently produces a generic brief
from an empty `${context.description}` interpolation.

## Expected Behavior

A loop can declare which injected inputs are mandatory, and the runner refuses
to start (with a clear error) when a required input is absent or empty:

```yaml
input_key: description
required_inputs: ["description"]
```

```
$ ll-loop run svg-textgrad
Error: loop 'svg-textgrad' requires input 'description' but none was provided.
       Pass it via --input or the configured input_key.
```

## Motivation

Silent-empty-input is a footgun: the loop "succeeds" but optimizes against an
empty subject, wasting a full run and masking operator error. A declarative
guard makes the contract explicit and shifts the failure left to start-time.

## Current Pain Point

Operators must remember out-of-band that a loop needs an input. There is no
schema affordance, no validation warning, and no runtime check — the only
symptom is low-quality output discovered after the fact.

## Proposed Solution

1. **Schema**: add an optional `required_inputs: [str]` top-level field to
   `scripts/little_loops/fsm/fsm-loop-schema.json` and the corresponding
   dataclass in `scripts/little_loops/fsm/schema.py`.
2. **Pre-flight check**: in the loop runner (`scripts/little_loops/cli/loop/run.py`),
   after input injection and before executing the first state, verify each name
   in `required_inputs` resolves to a non-empty context value; abort with a
   clear error otherwise.
3. **Validation (optional, lighter alternative)**: at minimum, have
   `ll-loop validate` (`scripts/little_loops/fsm/validation.py`) emit a WARNING
   when a loop has `input_key` but no `required_inputs`, nudging authors to
   declare intent.

## Scope Boundaries

- In scope: declaring and enforcing presence/non-emptiness of injected inputs.
- Out of scope: type validation, format/regex validation, or default-value
  synthesis for inputs (could be a follow-up).

## Backwards Compatibility

Fully backward compatible: `required_inputs` is optional. Loops that omit it
behave exactly as today. No existing loop sets the field.

## Integration Map

- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `required_inputs`.
- `scripts/little_loops/fsm/schema.py` — parse the field onto the loop model.
- `scripts/little_loops/cli/loop/run.py` — pre-flight presence check.
- `scripts/little_loops/fsm/validation.py` — optional `input_key`-without-guard
  warning.
- `scripts/little_loops/loops/svg-textgrad.yaml` — first consumer (`description`).

## Implementation Steps

1. Add `required_inputs` to schema + dataclass.
2. Implement the start-time presence/non-empty check in the runner.
3. Wire the guard into `svg-textgrad.yaml` as the first real consumer.
4. Add tests covering: missing input aborts, empty input aborts, present input
   proceeds, absent `required_inputs` is a no-op.

## Impact

Prevents silent low-quality runs for input-driven loops; makes the input
contract self-documenting in the YAML.

## Status

- **Created**: 2026-06-03 via `/ll:capture-issue` (from `svg-textgrad` audit)
- **State**: open

## Session Log
- `/ll:capture-issue` - 2026-06-03T19:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cba1a69-7a53-425f-8c5d-4f1ba61f51bb.jsonl`
