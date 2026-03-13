---
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# FEAT-725: ll-loop run positional string input argument

## Summary

Add support for passing a positional string input to `ll-loop run` so that loops with an `init` state can receive a runtime value without requiring `--context key=value` syntax.

Target UX:
```
ll-loop run single-issue-refinement-loop "FEAT-719"
ll-loop run single-issue-refinement-loop FEAT-719
```

## Current Behavior

- `ll-loop run <loop-name>` accepts only the loop name as a positional argument.
- Runtime values must be passed via `--context input=FEAT-719`, which is verbose and requires the user to know the context key name.
- Loop YAML authors have no convention for declaring an "expected input" to document or validate that the loop requires a runtime string.

## Expected Behavior

- `ll-loop run <loop-name> [input]` accepts an optional second positional argument.
- When provided, the input is injected into `fsm.context["input"]` (or a configurable key declared in the loop YAML) before execution begins.
- Loops can declare an `input` key in their top-level `context:` with a placeholder/default (e.g., `null` or empty string) to signal that they accept runtime input.
- The `init` state (or any state) can reference `{{context.input}}` in its action/prompt to consume the value.

### Example loop YAML

```yaml
name: single-issue-refinement-loop
initial: init
context:
  input: null   # populated at runtime via positional arg
states:
  init:
    action: "/ll:refine-issue {{context.input}}"
    on_success: done
    on_failure: done
  done:
    terminal: true
```

### Example invocation

```bash
ll-loop run single-issue-refinement-loop FEAT-719
# equivalent to:
ll-loop run single-issue-refinement-loop --context input=FEAT-719
```

## Motivation

Single-item loops (refine one issue, process one file, run one check) are a natural pattern but are awkward to invoke today — users must know the internal context key name and use the verbose `--context` flag. A positional input arg makes `ll-loop` feel like a natural CLI tool and unlocks reusable parameterized loop templates.

## Implementation Steps

1. **CLI argument**: Add optional positional `input` to the `run` subparser in `scripts/little_loops/cli/loop/__init__.py` (after `loop`).
2. **Injection in `cmd_run`**: In `scripts/little_loops/cli/loop/run.py`, after loading the FSM, inject `args.input` into `fsm.context["input"]` when present (before existing `--context` overrides are applied, so `--context` can still override).
3. **Schema update**: Add optional `input_key` string field to FSM loop schema (`fsm-loop-schema.json`) — defaults to `"input"`. Allows loop authors to name the expected key something other than `input`.
4. **Dry-run display**: Show the resolved input value in the execution plan printed by `print_execution_plan`.
5. **Validation**: If loop YAML declares `context.input: null` and no input is provided at runtime, emit a warning (not an error, to keep loops runnable without input).

## API / Interface Changes

```
ll-loop run <loop-name> [input] [options]
```

- `input` — optional positional string injected as `fsm.context["input"]` (or `fsm.context[fsm.input_key]` if `input_key` is declared)
- No breaking changes; existing invocations without positional input are unaffected

## Acceptance Criteria

- [ ] `ll-loop run my-loop "FEAT-719"` injects `FEAT-719` into `context["input"]` and runs successfully
- [ ] `ll-loop run my-loop` (no input) still works; `context["input"]` defaults to `null`/empty
- [ ] `--context input=X` still works and overrides the positional value
- [ ] `--dry-run` shows the resolved input value in the execution plan
- [ ] Tests cover: positional input injection, `--context` override wins, no-input default

## Related

- `scripts/little_loops/cli/loop/__init__.py` — run subparser argument definitions
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` context injection logic
- `scripts/little_loops/fsm/fsm-loop-schema.json` — schema for `input_key`

---

## Status

**Active** — not yet started

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/582c29ac-d327-46f4-8794-3433874ce5c2.jsonl`
