---
captured_at: '2026-05-23T22:07:11Z'
completed_at: '2026-05-24T02:43:12Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
discovered_commit: 24e2afbc0f8543d43869ad4d61e3cdc193239f57
discovered_branch: main
status: done
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- **Line-number corrections** (issue text drifted since capture; use these when navigating):
  - `run_foreground` is defined at `_helpers.py:608-984` (not 335-638).
  - The `display_progress(event)` closure starts at `_helpers.py:678`.
  - `executor.event_bus.register(display_progress)` is at `_helpers.py:945`, guarded by `if not quiet or show_diagrams:` at line 943 and `if hasattr(executor, "event_bus"):` at line 944.
  - The alt-screen enter (`\033[?1049h\033[H`) is at `_helpers.py:954`, inside `if show_diagrams and clear_screen and sys.stdout.isatty():` at line 952; exit (`\033[?1049l`) is at line 966 inside the `finally` block (range 951-967).
  - `executor.run()` is at `_helpers.py:958` (not 617).
- **Fallback path** the issue doesn't mention: when `event_bus` is absent, `_helpers.py:947` sets `executor._on_event = display_progress` directly. `PersistentExecutor` always exposes `event_bus`, so the resume path will always take the `register()` branch — but the fallback must remain intact for non-persistent executors used elsewhere.
- **`PersistentExecutor.resume()` already emits a `loop_resume` event** at `persistence.py:651` *before* calling `self.run(clear_previous=False)` at line 654. Subscribers registered before `executor.resume()` runs will receive this event — useful for the new subscriber-count test (any subscriber will see ≥1 event even if the resumed run does nothing else).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- **Mode-parameter style precedent**: `run_foreground` already accepts a `show_diagrams_mode: str` parameter with `"main"` / `"full"` literals (`_helpers.py:252, 336`). The new `mode: str = "run"` / `"resume"` parameter follows this established string-literal convention — no new style invention required.
- **No existing `mode: str = "run" | "resume"` pattern**: pattern-finder confirmed no function in `scripts/little_loops/` currently branches between run vs. resume via a `mode` string. This is genuinely new ground for that *semantic*, but the style is precedented (see above).
- **`result is None` early-return placement** (critical for not leaking alt-screen mode): the alt-screen enter sequence is at `_helpers.py:954`, *inside* the conditional `if show_diagrams and clear_screen and sys.stdout.isatty():` at line 952. The `result is None` early-return for "nothing to resume" must occur *before* line 952. Concretely: after `if mode == "resume": result = executor.resume()`, check `if result is None: logger.warning("Nothing to resume for: …"); return 1` before falling through to the alt-screen block.
- **Completion-line API mismatch** (decide before implementing): `cmd_run` uses `print(f"Loop completed: {state_colored} ({result.iterations} iterations, {duration_str})")` at `_helpers.py:982` with ANSI-colorized state. `cmd_resume` historically uses `logger.success(f"Resumed and completed: …")` at `lifecycle.py:445-448` with a plain string. Routing resume through `run_foreground` naturally shifts to the `print()` plumbing. Recommended: keep the `print()` API and just swap the prefix ("Loop completed" → "Resumed and completed") so resumed runs gain the same ANSI state coloring `cmd_run` has. The "preserve wording" rule locks only the literal `"Resumed and completed:"` prefix, not the underlying API.
- **Event-bus subscriber registration is the only production call site** (besides the backward-compat `_on_event.setter` at `persistence.py:482`). Confirms `run_foreground` is the canonical single owner — routing resume through it consolidates the wiring rather than spreading it.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — add `mode` parameter, branch on it for `executor.run()` vs `executor.resume()`, adjust completion-line wording, handle `result is None`.
- `scripts/little_loops/cli/loop/lifecycle.py` — replace direct `executor.resume()` call in `cmd_resume` with `run_foreground(..., mode="resume")`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — current sole caller of `run_foreground` at line 352; must continue to work unchanged with default `mode="run"`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()` dispatches to `cmd_resume()` at line 449; this is the actual CLI entry point that routes `ll-loop resume` subcommand invocations. No change needed — `cmd_resume`'s public signature is unchanged.

### Similar Patterns
- `cmd_run` (`run.py:88-363`) is the reference implementation for display wiring — keep `cmd_resume` symmetric with it.

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — update `TestCmdResume` mocks: the resume path now flows through `run_foreground`, so tests that patch `PersistentExecutor.resume` need to ensure the patched `executor.event_bus` is also an `EventBus`-compatible mock so `register()` does not raise. Add one new test asserting the event-bus subscriber count is ≥1 after `cmd_resume` invocation, proving the display is wired.
- Any existing tests for `run_foreground` should grow a parametrized case for `mode="resume"` if such tests exist.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py:403` — `TestCmdResume.test_resume_with_minutes_duration` — **will break**: asserts `"2m" in str(logger.success.call_args)`. After the fix, `logger.success` is no longer called for the completion line (replaced by `print()` inside `run_foreground`). Update assertion to check `builtins.print` output instead — follow the capsys pattern already used in `test_resume_awaiting_continuation` (line 432).
- `scripts/tests/test_ll_loop_state.py` — integration test asserting `"Resumed and completed: done" in captured.out`. Both `logger.success` and `print()` route to stdout, so this test will continue to pass after the fix — but it should be listed here as a test to verify during smoke testing.
- `scripts/tests/test_ll_loop_display.py` — new test needed (no existing coverage): `run_foreground(mode="resume")` where `executor.resume()` returns `None` (the "nothing to resume" early-return path). Expected: function returns exit code `1` without entering the alt-screen sequence. Follow the `_run_with_terminated_by` inline-executor template at line 2565; add a `resume()` method that returns `None`.

#### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- **Existing `TestCmdResume` pattern** (`scripts/tests/test_cli_loop_lifecycle.py`, `TestCmdResume.test_resume_success` at line 377): patches `PersistentExecutor` at the class level via `patch("little_loops.fsm.persistence.PersistentExecutor")`, so `mock_exec_cls.return_value` is the executor instance. The new test's mock surface needs `mock_exec_cls.return_value.event_bus.register` to be a `MagicMock` so call-count assertions work.
- **Structural model for the new subscriber-count test**: `TestCmdResumeCircuitWiring` at `scripts/tests/test_cli_loop_lifecycle.py:1368` already inspects `mock_exec_cls.call_args.kwargs` after `cmd_resume()` returns. An analogous assertion: `assert mock_exec_cls.return_value.event_bus.register.call_count >= 1` (or, to confirm it's the display closure, assert the callable name on `call_args[0][0]`).
- **Existing `run_foreground` parametrized-test template** (`scripts/tests/test_ll_loop_display.py`, `TestExitCodeMapping._run_with_terminated_by` at line 2557): constructs a minimal inline `_Executor` class with `_on_event` and `run()`, then calls `run_foreground` directly. This is the existing template for a `mode="resume"` parametrization — replace the inline `_Executor.run()` call with `_Executor.resume()` and pass `mode="resume"` to `run_foreground`.
- **Real `event_bus.register` usage as test pattern** (`scripts/tests/test_fsm_persistence.py:777`): shows `executor.event_bus.register(lambda e: bus_events.append(e))` — the canonical way to count emitted events on a real (non-mocked) executor, useful for an integration-style assertion that the resumed-run callback actually fires.
- **No existing test** asserts on `event_bus.register` call counts via a mock. This will be the first.

### Documentation
- N/A — user-facing behavior change brings resume in line with run; no doc references to the silent behavior to update.

### Configuration
- N/A

## Implementation Steps

1. Extend `run_foreground` in `_helpers.py` with `mode` parameter and resume/run branch (including `result is None` early return).
2. Refactor `cmd_resume` in `lifecycle.py` to delegate to `run_foreground(..., mode="resume")`, preserving the `try/finally: executor.close_transports()` wrapper and the existing `--instance-id` filter block.
3. Update `TestCmdResume` mocks and add a new test asserting `display_progress` is registered on `executor.event_bus` during resume.
4. Manual smoke: interrupt a short loop, resume with `--show-diagrams`, verify live per-iteration output and final `Resumed and completed: …` line.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Fix `test_cli_loop_lifecycle.py:403` (`TestCmdResume.test_resume_with_minutes_duration`) — update the `logger.success.call_args` assertion to check `builtins.print` output (see `test_resume_awaiting_continuation` at line 432 for the capsys pattern to follow).
6. Add `test_ll_loop_display.py` — new test for `run_foreground(mode="resume")` where `executor.resume()` returns `None`; assert return code is `1` and alt-screen sequences are not emitted. Use the inline `_Executor` template from `TestRunForegroundExitCodes._run_with_terminated_by` (line 2565) — add a `resume()` method that returns `None`.

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

## Resolution

Fixed by routing `cmd_resume` through `run_foreground(..., mode="resume")`, the same display-wiring path `cmd_run` already used. This restores live per-iteration output (FSM diagram, `[N/MAX] state (Xs)` lines, action / verdict / route lines, alt-screen toggle) on resumed loops, replacing the previously silent terminal.

**Files changed**:
- `scripts/little_loops/cli/loop/_helpers.py` — added `mode: str = "run"` parameter to `run_foreground`; branches to `executor.resume()` when `mode == "resume"`; early-returns 1 (with `Logger().warning("Nothing to resume for: …")`) when `executor.resume()` returns `None`, *before* any alt-screen sequence is emitted; completion-line prefix swaps from `"Loop completed"` to `"Resumed and completed"` for `mode="resume"`.
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume` now delegates to `run_foreground(executor, fsm, args, highlight_color=…, edge_label_colors=…, badges=…, mode="resume")`, preserving the `try/finally: executor.close_transports()` wrapper and the existing `--instance-id` filter block. Removed unused `EXIT_CODES` import.
- `scripts/tests/test_cli_loop_lifecycle.py` — updated `TestCmdResume.test_resume_with_minutes_duration` to assert on captured stdout (capsys) instead of `logger.success.call_args`, since the completion line is now printed by `run_foreground` not emitted via the logger; added `test_resume_wires_display_callback_to_event_bus` as a regression guard asserting `executor.event_bus.register.call_count >= 1` after `cmd_resume`.
- `scripts/tests/test_ll_loop_display.py` — added `TestRunForegroundResumeMode` class with four tests: `resume()` returning `None` exits with code 1 and emits no alt-screen sequences; `mode="resume"` calls `executor.resume()` (not `.run()`); completion line uses the `"Resumed and completed"` prefix; an unknown `mode` raises `ValueError`.

**Verification**: `python -m pytest scripts/tests/` → 7476 passed, 5 skipped (was 7472 before; +4 new tests). `ruff check scripts/` → clean. `mypy scripts/little_loops/cli/loop/` → 2 pre-existing errors unchanged (wcwidth stub + LoopState variance; not introduced by this change).

## Session Log
- `/ll:manage-issue` - 2026-05-24T02:43:12Z - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
- `/ll:ready-issue` - 2026-05-24T02:31:31 - `a831c57a-345e-49ef-a2f5-c7cd4051eace.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `a831c57a-345e-49ef-a2f5-c7cd4051eace.jsonl`
- `/ll:wire-issue` - 2026-05-24T02:28:09 - `427c3817-f696-4b84-826d-de8a9874c08a.jsonl`
- `/ll:refine-issue` - 2026-05-24T02:23:05 - `cc45a1c4-242b-4e80-bbab-25524451ce36.jsonl`
- `/ll:format-issue` - 2026-05-23T22:10:57 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:capture-issue` - 2026-05-23T22:07:11Z - `91194a18-41a9-4ea2-aeb1-1b9a20014452.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
