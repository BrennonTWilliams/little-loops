---
discovered_date: "2026-04-08"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
- `scripts/little_loops/fsm/fsm-loop-schema.json:63` — `input_key` description says "Context key populated by the positional input arg at runtime"; incomplete after JSON unpacking — keys are distributed across matching context fields in the non-fallback case [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:98-103` — argparse positional `input` arg; `nargs="?"` still passes raw string (no structural change needed), BUT line 102 help string `"Optional input string injected as context['input'] (or the key declared in input_key)"` must be updated to reflect JSON auto-unpack behavior [Wiring pass added by `/ll:wire-issue`]
- `scripts/little_loops/cli/loop/lifecycle.py:220-224` — `cmd_resume` has an identical `--context KEY=VALUE` parsing block; if similar JSON unpacking is ever added there, follow the same pattern
- Any loop YAML that defines a `context:` block — behavior improves automatically

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py:61-65` — `--context KEY=VALUE` parsing in the same function; the JSON unpacking block must sit at lines 59-60 so `--context` still wins on conflict
- `scripts/little_loops/cli/loop/lifecycle.py:220-224` — duplicate `kv.partition("=")` pattern in `cmd_resume`
- `scripts/little_loops/cli/sprint/run.py:56-63` — the only existing `try/except (json.JSONDecodeError, ...)` in the CLI layer; use same exception tuple

### Tests
- `scripts/tests/test_ll_loop_commands.py:2038-2152` — `TestCmdRunContextInjection` is the exact class for new JSON unpacking tests; add a `multi_context_loop` fixture and 5 test methods following the existing fixture pattern (write loop YAML to `tmp_path / ".loops"`, use `dry_run=True` args namespace or simulate injection directly via `load_and_validate`)
- `scripts/tests/test_cli_loop_lifecycle.py:683-798` — `_make_args()` helper pattern for building `argparse.Namespace`; reuse or copy for new tests
- `scripts/tests/test_ll_loop_parsing.py:219-243` — existing argparse tests for the `input` positional (`test_positional_input_parsed`, `test_positional_input_default_is_none`, `test_positional_input_quoted_string`, `test_positional_input_with_context_flag`); verify they still pass — non-JSON strings fall through to fallback, no changes to these tests needed [Wiring pass added by `/ll:wire-issue`]

### Documentation
- `docs/guides/LOOPS_GUIDE.md:240` — uses `--context input="..."` pattern; add note that a plain string positional works identically as shorthand (non-JSON fallback) [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/LOOPS_GUIDE.md:1140-1153` — outer-loop-eval invocation example uses two `--context` flags; add JSON shorthand invocation example (`ll-loop run outer-loop-eval '{"loop_name": "...", "input": "..."}'`) enabled by ENH-999 — this is the canonical use case [Wiring pass added by `/ll:wire-issue`]
- `docs/reference/CLI.md:243` — `input` positional row reads "Input string injected as `context['input']` (or the key declared in `input_key`)" — update to reflect JSON auto-unpack and fallback semantics

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/cli/loop/__init__.py:102` — change help string from `"Optional input string injected as context['input'] (or the key declared in input_key)"` to describe JSON auto-unpack behavior (e.g., "If valid JSON object with keys matching defined context variables, unpacks into those keys; otherwise stored as a string in context[input_key]")
7. Update `scripts/little_loops/fsm/fsm-loop-schema.json:63` — revise `input_key` description to reflect that in the JSON-unpack path the positional input populates multiple context keys, and `input_key` only receives the raw string in the fallback case
8. Verify `scripts/tests/test_ll_loop_parsing.py:219-243` — run these existing argparse tests to confirm they still pass unchanged (non-JSON strings, quoted strings, and `--context` coexistence all take the fallback path)

## Impact

- **Priority**: P4 - Quality-of-life improvement; `--context` workaround exists
- **Effort**: Small - ~20 lines of Python + tests
- **Risk**: Low - fallback preserves existing behavior for all non-matching inputs
- **Breaking Change**: No — only activates when input is valid JSON with keys matching the loop's defined context

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `dx`, `captured`

## Resolution

**Resolved**: 2026-04-08
**Implemented by**: `/ll:manage-issue`

### Changes Made
- `scripts/little_loops/cli/loop/run.py`: Added `import json`; replaced 2-line input injection with JSON-detection + unpacking block (~14 lines)
- `scripts/little_loops/cli/loop/__init__.py:102`: Updated `input` positional help string to describe auto-unpack behavior
- `scripts/little_loops/fsm/fsm-loop-schema.json:63`: Revised `input_key` description to reflect fallback-only role
- `scripts/tests/test_ll_loop_commands.py`: Added `multi_context_loop` fixture + 5 test methods to `TestCmdRunContextInjection`
- `docs/guides/LOOPS_GUIDE.md`: Added JSON shorthand examples at lines 240 and 1147
- `docs/reference/CLI.md:243`: Updated `input` positional row description

### Verification
- 4486 tests passed, 0 failures
- `ruff check scripts/` — all checks passed

## Session Log
- `/ll:ready-issue` - 2026-04-08T19:50:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11459c4f-b7c0-41f0-814e-56de3ec06758.jsonl`
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4f9c0d7-0ba1-4b11-a7e6-c52eac77de25.jsonl`
- `/ll:wire-issue` - 2026-04-08T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-08T19:39:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7a7df3b-a5eb-417d-9326-336e8ae6c68c.jsonl`
- `/ll:format-issue` - 2026-04-08T19:35:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52b984e9-5e44-4f2c-b572-5705d6456c10.jsonl`
- `/ll:capture-issue` - 2026-04-08T18:24:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8163e06d-ba51-4c89-ad08-3b2526018e0f.jsonl`
- `/ll:manage-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Status

**Completed** | Created: 2026-04-08 | Resolved: 2026-04-08 | Priority: P4
