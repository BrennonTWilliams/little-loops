---
id: ENH-1542
title: "outer-loop-eval: use input as positional context key"
type: ENH
priority: P4
status: done
captured_at: "2026-05-17T05:35:08Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
---

# ENH-1542: outer-loop-eval: use input as positional context key

## Summary

Renamed the `loop_name` context variable to `input` in `outer-loop-eval.yaml` so the target loop name is accepted as a CLI positional argument. Also renamed the secondary `input` variable to `loop_input` to avoid collision. Updated all context references in the YAML and tests.

## Motivation

The loop previously required `--context loop_name=<name>` to identify the target loop, and callers had to supply full absolute paths. After this change:

- The target loop name maps to `context.input` (the FSM runner's default `input_key`), so it can be passed as a bare positional argument: `ll-loop run outer-loop-eval <name>`.
- Name resolution already handles bare names via `resolve_loop_path` (checks `.loops/<name>.yaml` then built-ins), so full paths are no longer needed.
- Data forwarded into the sub-loop moves to `context.loop_input`, keeping the two concerns separate.

## Changes

- `scripts/little_loops/loops/outer-loop-eval.yaml` — renamed `loop_name` → `input`, `input` → `loop_input`; updated all `${context.*}` interpolations and error message
- `scripts/tests/test_outer_loop_eval.py` — updated all assertions to match new context key names

## Usage (after)

```bash
# bare name (resolves from .loops/ or built-ins)
ll-loop run outer-loop-eval eval-specfile-gold

# absolute path still works
ll-loop run outer-loop-eval /path/to/some-loop.yaml

# optionally forward data into the sub-loop
ll-loop run outer-loop-eval eval-specfile-gold --context loop_input="some value"
```

## Session Log
- `hook:posttooluse-status-done` - 2026-05-17T05:35:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76ac37c3-b42c-4f32-8ffb-dec49dee3945.jsonl`
- `/ll:capture-issue` - 2026-05-17T05:35:08Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f83462fc-6ed8-4bc4-b54c-c8a7368feb83.jsonl`
