---
discovered_date: "2026-04-08"
discovered_by: capture-issue
---

# ENH-999: ll-loop run should auto-unpack JSON input into named context variables

## Summary

When `ll-loop run <loop> <input>` receives a JSON object as the positional `input` argument, and the loop defines named context keys that match the JSON keys, the runner should unpack the JSON into the context rather than storing it as a raw string in `context.input`. This makes multi-context loops ergonomic to invoke without requiring `--context KEY=VALUE` pairs.

## Current Behavior

```bash
ll-loop run outer-loop-eval '{"loop_name": "general-task", "input": "some task"}'
# Result: context.input = '{"loop_name": "general-task", "input": "some task"}'
#         context.loop_name = "" (default, never populated)
```

The JSON string is treated as opaque text. Any loop with multiple named context variables requires verbose `--context` flags.

## Expected Behavior

```bash
ll-loop run outer-loop-eval '{"loop_name": "general-task", "input": "some task"}'
# Result: context.loop_name = "general-task"
#         context.input = "some task"
```

When the positional input is valid JSON and the top-level keys match context variable names defined in the loop's YAML, unpack them automatically. Fall back to the current behavior (store as `context.input`) when the JSON keys don't match any defined context keys or when the input isn't valid JSON.

## Motivation

Loops with structured context blocks (multiple named variables) are hard to invoke ergonomically from the command line. The natural mental model when you have `context: {loop_name: "", input: ""}` is to pass a JSON dict. The mismatch causes silent failures that are difficult to diagnose (see BUG-998).

## API/Interface

```python
# scripts/little_loops/cli/loop/run.py  (lines 49-65, context population)

# Current
if getattr(args, "input", None) is not None:
    fsm.context[fsm.input_key] = args.input

# Proposed
if getattr(args, "input", None) is not None:
    raw = args.input
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            # Unpack keys that exist in the loop's defined context
            matched = {k: v for k, v in parsed.items() if k in fsm.context}
            if matched:
                fsm.context.update(matched)
            else:
                fsm.context[fsm.input_key] = raw  # no key overlap, treat as string
        else:
            fsm.context[fsm.input_key] = raw
    except (json.JSONDecodeError, ValueError):
        fsm.context[fsm.input_key] = raw  # not JSON, treat as string
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py:49-65` — context population logic

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — argparse setup (no change needed)
- Any loop YAML that defines a context block — behavior improves automatically

### Similar Patterns
- `--context KEY=VALUE` parsing at lines 60-65 of `run.py` — same file, adjacent logic

### Tests
- `scripts/tests/` — add unit tests for JSON unpacking: matching keys, non-matching keys, non-JSON input, partial key overlap, nested JSON (should not unpack)

## Implementation Steps

1. Add `import json` to `run.py` if not already imported
2. Replace the simple `fsm.context[fsm.input_key] = args.input` assignment with the JSON-detection logic
3. Only unpack if at least one key matches a defined context key (prevents spurious unpacking of arbitrary JSON strings passed as task input)
4. Add unit tests covering: valid JSON with all keys matching, valid JSON with no keys matching, valid JSON with partial match, non-JSON string, JSON array (not a dict)
5. Update `ll-loop run --help` or docs to describe the auto-unpack behavior

## Impact

- **Priority**: P4 - Quality-of-life improvement; `--context` workaround exists
- **Effort**: Small - ~20 lines of Python + tests
- **Risk**: Low - fallback preserves existing behavior for all non-matching inputs
- **Breaking Change**: No — only activates when input is valid JSON with keys matching the loop's defined context

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `dx`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-08T18:24:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8163e06d-ba51-4c89-ad08-3b2526018e0f.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
