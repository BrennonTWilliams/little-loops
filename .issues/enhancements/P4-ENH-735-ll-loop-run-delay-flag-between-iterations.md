---
id: ENH-735
type: ENH
priority: P4
status: backlog
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-735: Add `--delay` flag to `ll-loop run` for inter-iteration pause

## Motivation

When watching FSM box diagram progression in the terminal (e.g. via a CLI recorder like Asciinema), states that execute almost instantaneously are not visually captured between redraws. A small configurable delay (e.g. `0.5s`) between iterations ensures every state transition is recorded and visible.

## Description

Add an optional `--delay SECONDS` flag to `ll-loop run` (and `ll-loop resume`) that inserts a `time.sleep(delay)` pause between FSM iterations. The flag accepts a float value in seconds (e.g. `0.5`, `1.0`).

## Implementation Steps

1. Add `--delay` argument to `run_parser` and `resume_parser` in `scripts/little_loops/cli/loop/__init__.py`:
   ```python
   run_parser.add_argument("--delay", type=float, default=0.0, metavar="SECONDS",
                           help="Sleep N seconds between iterations (useful for recording)")
   ```
2. Pass `args.delay` through `cmd_run` in `scripts/little_loops/cli/loop/run.py` to `run_foreground` / `run_background`.
3. In the foreground execution path (`scripts/little_loops/cli/loop/_helpers.py` or the FSM executor), insert `time.sleep(delay)` after each iteration if `delay > 0`.

## Acceptance Criteria

- `ll-loop run my-loop --delay 0.5` pauses 0.5 seconds between each FSM state execution
- `ll-loop resume my-loop --delay 0.5` also respects the flag
- `--delay 0` (default) preserves existing behavior with no sleep
- Flag is documented in `ll-loop run --help`

## Related Files

- `scripts/little_loops/cli/loop/__init__.py` — argument definitions
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` implementation
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground` / execution loop

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1676ba6e-6a32-48f6-a1fe-7092be9a5865.jsonl`
