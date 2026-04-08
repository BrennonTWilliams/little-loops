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

## Scope Boundaries

- Only top-level keys are unpacked — no recursive/nested JSON unpacking
- Does not apply type coercion to unpacked values (string values stay strings)
- Does not affect `--context KEY=VALUE` flag parsing (existing behavior unchanged)
- Does not handle non-dict JSON (arrays, strings, raw numbers fall back to string storage)
- Does not auto-create context variables; only populates keys already defined in the loop's YAML
- Does not modify loop YAML format or add new loop config options

## API/Interface

```python
# scripts/little_loops/cli/loop/run.py  (lines 59-60, input injection; 61-65, --context override)

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
- `scripts/little_loops/cli/loop/run.py:59-60` — input injection block (the two lines being replaced)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:98-103` — argparse positional `input` arg (no change needed; `nargs="?"` already passes raw string)
- `scripts/little_loops/cli/loop/lifecycle.py:220-224` — `cmd_resume` has an identical `--context KEY=VALUE` parsing block; if similar JSON unpacking is ever added there, follow the same pattern
- Any loop YAML that defines a `context:` block — behavior improves automatically

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py:61-65` — `--context KEY=VALUE` parsing in the same function; the JSON unpacking block must sit at lines 59-60 so `--context` still wins on conflict
- `scripts/little_loops/cli/loop/lifecycle.py:220-224` — duplicate `kv.partition("=")` pattern in `cmd_resume`
- `scripts/little_loops/cli/sprint/run.py:56-63` — the only existing `try/except (json.JSONDecodeError, ...)` in the CLI layer; use same exception tuple

### Tests
- `scripts/tests/test_ll_loop_commands.py:2038-2152` — `TestCmdRunContextInjection` is the exact class for new JSON unpacking tests; add a `multi_context_loop` fixture and 5 test methods following the existing fixture pattern (write loop YAML to `tmp_path / ".loops"`, use `dry_run=True` args namespace or simulate injection directly via `load_and_validate`)
- `scripts/tests/test_cli_loop_lifecycle.py:683-798` — `_make_args()` helper pattern for building `argparse.Namespace`; reuse or copy for new tests

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — covers `ll-loop run`, context variables, and `input_key`; add a note on JSON auto-unpacking behavior
- `docs/reference/CLI.md` — CLI reference for `ll-loop run` and `--context` flags; update the `input` arg description

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `fsm.context` is initialized directly from the YAML `context:` block at `scripts/little_loops/fsm/schema.py:558` (`context=data.get("context", {})`); all keys are already populated before `cmd_run` reaches line 59 — so `if k in fsm.context` correctly checks YAML-declared keys
- `fsm.input_key` defaults to `"input"` at `schema.py:487`; overridden per-loop via top-level `input_key:` in YAML (e.g., `greenfield-builder.yaml:3` sets `input_key: spec`)
- `json` is **not** currently imported in `run.py` — `import json` must be added to the stdlib imports at the top of the file
- The `argparse` positional `input` argument is defined at `cli/loop/__init__.py:98-103` with `nargs="?"` and no `type=` conversion — value arrives as a plain `str` or `None`
- 28 built-in loop YAMLs define `context:` blocks and will benefit from this change automatically

## Implementation Steps

1. Add `import json` to `run.py` (stdlib imports block, lines 5-8)
2. Replace lines 59-60 (`fsm.context[fsm.input_key] = args.input`) with the JSON-detection logic from the API/Interface section above
3. Only unpack if at least one key matches a defined context key (prevents spurious unpacking of arbitrary JSON strings passed as task input)
4. Add tests to `TestCmdRunContextInjection` in `scripts/tests/test_ll_loop_commands.py:2038`: add a `multi_context_loop` fixture (loop YAML with `context: {loop_name: "", input: ""}`) and 5 methods: all-keys match, no-keys match, partial match, non-JSON string, JSON array (not a dict)
5. Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/CLI.md` to document the auto-unpack behavior

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
- `/ll:refine-issue` - 2026-04-08T19:39:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7a7df3b-a5eb-417d-9326-336e8ae6c68c.jsonl`
- `/ll:format-issue` - 2026-04-08T19:35:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52b984e9-5e44-4f2c-b572-5705d6456c10.jsonl`

- `/ll:capture-issue` - 2026-04-08T18:24:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8163e06d-ba51-4c89-ad08-3b2526018e0f.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
