# ENH-999: JSON Context Unpacking in ll-loop run

**Date**: 2026-04-08
**Issue**: ENH-999 — ll-loop run should auto-unpack JSON input into named context variables
**Action**: improve

---

## Problem

When `ll-loop run <loop> '{"key": "val"}'` is invoked, the JSON string lands verbatim in `context[input_key]`. Loops with structured `context:` blocks require verbose `--context KEY=VALUE` flags instead.

## Solution

In `run.py`, when `args.input` is valid JSON and the top-level keys overlap with `fsm.context` keys, unpack matching keys directly. Fall back to string storage otherwise.

---

## Phases

### Phase 1: Modify `run.py`
- Add `import json` to stdlib imports (lines 5-8)
- Replace lines 59-60 with JSON-detection + unpacking block

### Phase 2: Update argparse help string (`__init__.py:102`)
- Change help string to describe JSON auto-unpack + fallback behavior

### Phase 3: Update schema description (`fsm-loop-schema.json:63`)
- Revise `input_key` description to reflect fallback-only role in JSON-unpack path

### Phase 4: Add tests (`test_ll_loop_commands.py`)
- Add `multi_context_loop` fixture inside `TestCmdRunContextInjection`
- Add 5 test methods: all-match, no-match, partial-match, non-JSON, JSON-array

### Phase 5: Update docs
- `docs/guides/LOOPS_GUIDE.md`: two locations
- `docs/reference/CLI.md`: `input` positional row

### Phase 6: Verify
- `python -m pytest scripts/tests/`
- `ruff check scripts/`

---

## Success Criteria

- [x] `ll-loop run outer-loop-eval '{"loop_name": "general-task", "input": "foo"}'` populates both context keys
- [x] Non-JSON strings still work as before (stored in `context[input_key]`)
- [x] `--context` flags still override JSON-unpacked values
- [x] All existing tests pass unchanged
- [x] 5 new tests cover all branches
- [x] Documentation reflects new behavior
