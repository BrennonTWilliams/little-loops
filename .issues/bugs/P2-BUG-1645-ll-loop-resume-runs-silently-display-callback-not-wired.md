---
captured_at: "2026-05-23T22:07:11Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
discovered_commit: 24e2afbc0f8543d43869ad4d61e3cdc193239f57
discovered_branch: main
status: open
---

# BUG-1645: `ll-loop resume` runs silently — display callback not wired in `cmd_resume`

## Summary

`cmd_resume` (`scripts/little_loops/cli/loop/lifecycle.py:307-451`) calls `executor.resume()` directly without registering the per-event display callback that `cmd_run` wires through `run_foreground`. The loop runs normally and emits `state_enter`/`action_start`/`action_complete`/`evaluate`/`route` events on its event bus, but no subscriber is attached on the resume path, so every event evaporates. The terminal stays completely silent until the run terminates (or Ctrl+C triggers graceful shutdown), at which point a single `Resumed and completed: <state> (N iterations, Xs)` line is printed. From the user's seat this is indistinguishable from a hang.

Observed in practice: a user ran `ll-loop resume general-task --show-diagrams --clear --delay 0.8 --instance-id general-task-20260523T151748` and saw zero output for 88 minutes; the loop was actually completing 56 iterations of `diagnose` normally, but `--show-diagrams` rendered nothing and no per-iteration progress lines appeared.

This is a latent bug that has existed since `cmd_resume` was added — `cmd_run` was wired through `run_foreground` (and benefited from ENH-442's `display_progress` fix), but the resume path was never migrated.

## Steps to Reproduce

1. Start any FSM loop and interrupt it mid-run so it's left in `interrupted` state. E.g. `ll-loop run loops/oracles/<short-loop>.yaml --max-iterations 5` then `Ctrl+C` after a couple of iterations.
2. Resume it with display flags: `ll-loop resume <loop> --show-diagrams --delay 0.5`.
3. Observe: the terminal prints nothing while the loop iterates. No FSM diagram renders. No `[N/MAX] <state> (Xs)` lines. No verdict/transition lines.
4. Either let it finish or `Ctrl+C` — only then does a single closing line appear.

## Current Behavior

- `cmd_resume` builds a `PersistentExecutor`, wires extensions and transports, then calls `executor.resume()` directly at `lifecycle.py:431`.
- `PersistentExecutor.resume()` (`scripts/little_loops/fsm/persistence.py:598-654`) restores state and calls `self.run(clear_previous=False)` → `self._executor.run()`, which emits events on `executor.event_bus` via `emit(...)`.
- No subscriber is registered, so events go nowhere.
- The only visible output is `logger.success(...)` at `lifecycle.py:445-448`, printed after the run terminates.
- `--show-diagrams`, `--clear`, and per-iteration progress are all effectively no-ops on the resume path.

## Expected Behavior

Resumed runs should produce live per-iteration output identical to a fresh `ll-loop run`:

- FSM diagram on each `state_enter` (when `--show-diagrams` is set).
- Per-iteration `[N/MAX] <state> (Xs)` lines.
- Action preview, verdict, and transition lines.
- Alt-screen-buffer toggle behavior for `--show-diagrams --clear`.
- Final summary worded as `Resumed and completed: <state> (N iterations, Xs)` (preserving the existing wording difference from `Loop completed: …`).

## Motivation

`ll-loop resume` is the second-most-used loop entry point — it's how users recover from interrupted long-horizon runs, which are common in this project's automation workflows. The silent terminal makes a resumed loop indistinguishable from a hang: users can't tell whether the FSM is making progress, stuck in one state, or about to terminate, and `Ctrl+C` becomes a guess rather than an informed decision. The captured incident demonstrates the cost: a user watched zero output for 88 minutes while the loop was in fact completing 56 iterations of `diagnose` normally. Wiring the display callback restores parity with the `cmd_run` UX, makes resumed runs observable, and removes a friction point in the most common recovery workflow.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `in function cmd_resume()` (lines 307-451)
- **Cause**: `cmd_resume` calls `executor.resume()` directly at line 431 instead of delegating to `run_foreground(executor, fsm, args, ...)` the way `cmd_run` does at `run.py:352`. `run_foreground` (`_helpers.py:335-638`) is the single place that builds the `display_progress(event)` closure, registers it via `executor.event_bus.register(display_progress)` (lines 603-607), and handles the alt-screen toggle for `--show-diagrams --clear` (lines 612-614, 619-621). Bypassing it means none of that wiring runs.

## Proposed Solution

Make `cmd_resume` go through the same display-wiring path as `cmd_run`. Teach `run_foreground` to drive `executor.resume()` instead of `executor.run()` so the single code path that owns the display callback also owns both run modes.

### 1. `scripts/little_loops/cli/loop/_helpers.py` — extend `run_foreground`

- Add a `mode: str = "run"` parameter (values: `"run"` or `"resume"`).
- Replace `result = executor.run()` (around line 617) with a branch that calls `executor.resume()` when `mode == "resume"`.
- Handle the `result is None` "nothing to resume" case: return early with a warning and exit code 1 *before* entering the alt-screen toggle, so the terminal isn't left in alt-screen mode. Reuse the existing `logger.warning("Nothing to resume for: …")` wording from `cmd_resume`.
- Adjust the final completion line: when `mode == "resume"`, print `"Resumed and completed: …"` (matching historical wording from `cmd_resume`) instead of `"Loop completed: …"`. Keep iteration count / duration formatting identical.

### 2. `scripts/little_loops/cli/loop/lifecycle.py` — refactor `cmd_resume`

Replace the direct `executor.resume()` call (line 431) and the manual duration formatting + `logger.success(...)` block (lines 432-449) with:

```python
from little_loops.cli.loop._helpers import run_foreground
_edge_label_colors = config.cli.colors.fsm_edge_labels.to_dict()
_highlight_color = config.cli.colors.fsm_active_state
_badges = config.loops.glyphs.to_dict()
return run_foreground(
    executor, fsm, args,
    highlight_color=_highlight_color,
    edge_label_colors=_edge_label_colors,
    badges=_badges,
    mode="resume",
)
```

Keep the existing `try / finally: executor.close_transports()` wrapper. Keep the existing `--instance-id` filtering block already in the unstaged diff (unrelated to this bug but must remain).

### Reused utilities (no new code paths)

- `run_foreground` (`_helpers.py:335`) — the display-wiring host.
- `display_progress` closure (`_helpers.py:375-600`) — already handles every event the FSM emits during a resumed run.
- `BRConfig(Path.cwd())` (already used by both `cmd_run` and `cmd_resume`) — supplies highlight color, edge label colors, and badge glyphs.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — add `mode` parameter, branch on it for `executor.run()` vs `executor.resume()`, adjust completion-line wording, handle `result is None`.
- `scripts/little_loops/cli/loop/lifecycle.py` — replace direct `executor.resume()` call in `cmd_resume` with `run_foreground(..., mode="resume")`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — current sole caller of `run_foreground` at line 352; must continue to work unchanged with default `mode="run"`.

### Similar Patterns
- `cmd_run` (`run.py:88-363`) is the reference implementation for display wiring — keep `cmd_resume` symmetric with it.

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — update `TestCmdResume` mocks: the resume path now flows through `run_foreground`, so tests that patch `PersistentExecutor.resume` need to ensure the patched `executor.event_bus` is also an `EventBus`-compatible mock so `register()` does not raise. Add one new test asserting the event-bus subscriber count is ≥1 after `cmd_resume` invocation, proving the display is wired.
- Any existing tests for `run_foreground` should grow a parametrized case for `mode="resume"` if such tests exist.

### Documentation
- N/A — user-facing behavior change brings resume in line with run; no doc references to the silent behavior to update.

### Configuration
- N/A

## Implementation Steps

1. Extend `run_foreground` in `_helpers.py` with `mode` parameter and resume/run branch (including `result is None` early return).
2. Refactor `cmd_resume` in `lifecycle.py` to delegate to `run_foreground(..., mode="resume")`, preserving the `try/finally: executor.close_transports()` wrapper and the existing `--instance-id` filter block.
3. Update `TestCmdResume` mocks and add a new test asserting `display_progress` is registered on `executor.event_bus` during resume.
4. Manual smoke: interrupt a short loop, resume with `--show-diagrams`, verify live per-iteration output and final `Resumed and completed: …` line.

## Impact

- **Priority**: P2 — Significant UX bug: long-horizon resumed loops are common (this is the second-most-used loop entry point), and the silent terminal makes them impossible to monitor or intelligently `Ctrl+C` out of. Not data-loss or correctness — the loop itself runs fine.
- **Effort**: Small — one new parameter on an existing function, one call-site refactor, ~3 test updates. All wiring already exists in `run_foreground`; this just routes resume through it.
- **Risk**: Low — `run_foreground` is well-tested on the `cmd_run` path. The `result is None` early-return is the only new edge case. Risk is bounded to the display wiring; the executor's resume logic is untouched.
- **Breaking Change**: No — output becomes richer (matches `cmd_run`); only the closing line wording is preserved (`Resumed and completed: …`).

## Verification

1. **Unit tests**: `python -m pytest scripts/tests/test_cli_loop_lifecycle.py -v` — existing `TestCmdResume` cases must still pass; new test confirms `display_progress` is registered on `executor.event_bus` during resume.
2. **Manual smoke (clean instance)**: Run `ll-loop run <short-loop> --max-iterations 2`, send `SIGTERM` mid-run to mark it `interrupted`, then `ll-loop resume <loop> --show-diagrams --delay 0.5`. Expect (a) FSM diagram on each `state_enter`, (b) per-iteration `[N/MAX] <state> (Xs)` lines, (c) action verdict/transition lines, (d) final `Resumed and completed: <state> (N iterations, Xs)` summary.
3. **Original failing command**: After fix, `ll-loop resume general-task --show-diagrams --clear --delay 0.8 --instance-id general-task-<id>` should produce live per-iteration output identical to a fresh `ll-loop run`.
4. **Lint/types**: `ruff check scripts/ && python -m mypy scripts/little_loops/cli/loop/`.

## Out of Scope

- Building the FSM stall detector (FEAT-1637) — separate issue, separate PR. That feature would have helped *notice* the 56-iteration repetition but is unrelated to this output-wiring bug.
- Changing what `general-task`'s `diagnose` state does or why it iterated 56 times — loop-design concern, not a runtime bug in `ll-loop` (covered by ENH-1644).
- The unstaged `--instance-id` filtering changes already in `lifecycle.py` — leave intact.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM executor and event bus architecture |
| `docs/reference/API.md` | `PersistentExecutor.resume()` and event bus API surface |

## Labels

`bug`, `cli`, `ll-loop`, `display`, `resume`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-23T22:10:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:capture-issue` - 2026-05-23T22:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91194a18-41a9-4ea2-aeb1-1b9a20014452.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
