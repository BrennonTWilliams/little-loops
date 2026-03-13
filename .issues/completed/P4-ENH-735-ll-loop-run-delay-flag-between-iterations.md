---
id: ENH-735
type: ENH
priority: P4
status: completed
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-735: Add `--delay` flag to `ll-loop run` for inter-iteration pause

## Summary

Add an optional `--delay SECONDS` CLI flag to `ll-loop run` and `ll-loop resume` that inserts an interruptible pause between FSM iterations by overriding `fsm.backoff`. Reuses the existing backoff sleep infrastructure in `executor.py` — no new sleep logic required.

## Current Behavior

Inter-iteration delay can only be set via the `backoff` field in the loop's YAML config. There is no way to inject or override a delay at runtime from the CLI without editing the config file.

## Expected Behavior

- `ll-loop run my-loop --delay 0.5` pauses 0.5 seconds between each iteration
- `ll-loop resume my-loop --delay 0.5` also respects the flag
- `--delay 0` explicitly resets a YAML-configured backoff to zero
- Flag is documented in `ll-loop run --help` and `ll-loop resume --help`

## Scope Boundaries

- Does NOT add delay within a single state execution — only between full iterations
- Does NOT persist the delay value to YAML config or state files
- Does NOT modify the backoff behavior for YAML-configured loops when `--delay` is not passed

## Motivation

When watching FSM box diagram progression in the terminal (e.g. via a CLI recorder like Asciinema), states that execute almost instantaneously are not visually captured between redraws. A small configurable delay (e.g. `0.5s`) between iterations ensures every state transition is recorded and visible.

## Description

Add an optional `--delay SECONDS` flag to `ll-loop run` (and `ll-loop resume`) that inserts a `time.sleep(delay)` pause between FSM iterations. The flag accepts a float value in seconds (e.g. `0.5`, `1.0`).

## Implementation Steps

1. **Add `--delay` to `run_parser`** (`cli/loop/__init__.py:95`, after `--max-iterations`):
   ```python
   run_parser.add_argument("--delay", type=float, default=None, metavar="SECONDS",
                           help="Sleep N seconds between iterations (useful for recording)")
   ```
   Add the same argument to `resume_parser` (`__init__.py:160-189`).
   Use `default=None` (not `0.0`) so `is not None` can distinguish "not set" from `0.0`.

2. **Override `fsm.backoff` in `cmd_run`** (`cli/loop/run.py:41-47`, after the existing `if args.max_iterations` block):
   ```python
   if args.delay is not None:
       fsm.backoff = args.delay
   ```
   Use `is not None` guard (not truthy) so `--delay 0` can explicitly reset a YAML-configured backoff.
   This reuses the **existing** interruptible backoff sleep at `executor.py:480-486` — no new `time.sleep` needed.

3. **Override `fsm.backoff` in `cmd_resume`** (`cli/loop/lifecycle.py:134-216`):
   `cmd_resume` calls `executor.resume()` directly (it does **not** go through `run_foreground`). Apply the same override before the executor is constructed, following the same `if args.delay is not None: fsm.backoff = args.delay` pattern.

4. **Forward `--delay` in `run_background`** (`cli/loop/_helpers.py:225-244`, where existing overrides like `--max-iterations` are forwarded to the subprocess re-exec):
   ```python
   delay = getattr(args, "delay", None)
   if delay is not None:
       cmd.extend(["--delay", str(delay)])
   ```

5. **Tests**: Add to `scripts/tests/test_ll_loop_parsing.py` (CLI arg parsing) and follow the backoff sleep pattern at `scripts/tests/test_fsm_executor.py:2492-2549` (`patch("little_loops.fsm.executor.time.sleep")`). Resume path should be covered in `scripts/tests/test_cli_loop_lifecycle.py`.

## Acceptance Criteria

- `ll-loop run my-loop --delay 0.5` pauses 0.5 seconds between each FSM state execution
- `ll-loop resume my-loop --delay 0.5` also respects the flag
- `--delay 0` (default) preserves existing behavior with no sleep
- Flag is documented in `ll-loop run --help`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py:95` — add `--delay` to `run_parser` (after `--max-iterations`) and `resume_parser` (lines 160-189)
- `scripts/little_loops/cli/loop/run.py:41-47` — override `fsm.backoff = args.delay` in `cmd_run`, alongside existing `max_iterations`/`no_llm` overrides
- `scripts/little_loops/cli/loop/lifecycle.py:134-216` — override `fsm.backoff = args.delay` in `cmd_resume` (resume bypasses `run_foreground` entirely)
- `scripts/little_loops/cli/loop/_helpers.py:225-244` — forward `--delay` in `run_background` subprocess re-exec args

### No Changes Needed
- `scripts/little_loops/fsm/executor.py:480-486` — the interruptible backoff sleep already exists and will be reused as-is
- `scripts/little_loops/fsm/schema.py:365` — `FSMLoop.backoff: float | None = None` already exists

### Tests
- `scripts/tests/test_ll_loop_parsing.py` — add `--delay` arg parsing tests (default=None, accepts float, accepts 0)
- `scripts/tests/test_fsm_executor.py:2492-2549` — existing backoff sleep tests; add test for CLI-set backoff path
- `scripts/tests/test_cli_loop_lifecycle.py` — resume path with `--delay`

### Documentation
- `docs/reference/CLI.md` — `ll-loop run` and `ll-loop resume` sections

## Impact

- **Priority**: P4 - Nice-to-have UX improvement for terminal recording workflows; not blocking any other work
- **Effort**: Small - Reuses existing `fsm.backoff` + interruptible sleep; 4 small edits + tests
- **Risk**: Low - Additive flag with `default=None`; no change to existing behavior when flag is omitted
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `backlog`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Resolution

- Added `--delay SECONDS` to `run_parser` and `resume_parser` in `cli/loop/__init__.py`
- Applied `fsm.backoff = args.delay` override in `cmd_run` (`run.py`) and `cmd_resume` (`lifecycle.py`)
- Forwarded `--delay` in `run_background` subprocess re-exec (`_helpers.py`)
- Added 3 parser tests to `test_ll_loop_parsing.py`
- Updated `docs/reference/CLI.md` for both `ll-loop run` and `ll-loop resume`

## Session Log
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/760c2e2a-8649-4964-a069-7e744eeb271c.jsonl`
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1676ba6e-6a32-48f6-a1fe-7092be9a5865.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19587ea4-3831-489e-b94e-b2174f2233b6.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f817503-3165-4b3d-837d-240a40c0bccd.jsonl`
