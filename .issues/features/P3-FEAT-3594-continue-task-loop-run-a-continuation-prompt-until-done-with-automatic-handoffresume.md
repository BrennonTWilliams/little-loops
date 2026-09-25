---
id: FEAT-3594
type: FEAT
title: 'continue-task loop: run a continuation prompt until done with automatic handoff/resume'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T04:27:08Z'
---

# FEAT-3594: continue-task loop: run a continuation prompt until done with automatic handoff/resume

## Summary

Add a built-in, general-purpose FSM loop `continue-task` that takes a continuation prompt and keeps working it until done, handling context exhaustion with automatic `/ll:handoff` → spawned `/ll:resume` sessions. Input is optional: with no input, the loop starts from the newest `.ll/ll-continue-prompt.md`.

## Current Behavior

Continuing a handed-off session is manual: open a new session, run `/ll:resume`, repeat at every handoff. `general-task` automates handoff/resume but only inside its own plan/DoD pipeline and requires an explicit task input.

## Expected Behavior

`ll-loop run continue-task [prompt]` works a continuation prompt (explicit, or the newest non-stale `.ll/ll-continue-prompt.md`) across as many automatic handoffs as needed, stopping when an independent done-check against the pinned starting goal passes, or at the iteration cap with a partial summary.

## Motivation

No built-in loop defaults its input to the handoff prompt. `general-task` is the only loop that reads `.ll/ll-continue-prompt.md`, and only to re-enter a pass mid-step (`do_work`). It is the wrong shape for this job: it always runs `define_done` and `plan`, then the DoD verification / final-tests / step-abandonment machinery. A continuation prompt already carries the plan and current state, so re-planning discards or duplicates it.

## Proposed Solution

A thin loop (~5 states), decoupled from the Issue system:

1. `load_prompt` (shell) — write `${context.input}` via quoted heredoc (BUG-2622 pattern from `prompt-across-issues.yaml` `init`). If empty, fall back to `.ll/ll-continue-prompt.md`, rejecting it when older than `continuation.prompt_expiry_hours` (default 24, same key `/ll:resume` reads). Print the source, mtime and first line for provenance. Fail clearly if neither is available. Snapshot the starting prompt to `${context.run_dir}/goal.md` — this pins the goal so repeated handoff summaries cannot drift it.
2. `work` (prompt) — mark the pass start; run `/ll:resume` if the handoff file is newer than the pass marker (general-task's `pass-started.txt` freshness pattern), else work from `goal.md`. Keep `${context.run_dir}/progress.md` current (done / remaining / evidence). On the context-monitor threshold, update progress and run `/ll:handoff`.
3. `run_tests` (shell, non-LLM signal) — run the resolved test command (explicit `context.test_cmd`, else `ll-config get project.test_cmd`); record exit code. Skip cleanly when none is configured.
4. `check_done` (prompt + `llm_structured`) — judge `progress.md` evidence and the test exit code against the pinned `goal.md`, re-verifying claims by reading files / running commands. The worker's own "done" claim is never sufficient. A test *regression* (passed at baseline, fails now) forces NO mechanically in `run_tests`, before the LLM check; a suite already failing at baseline is advisory, so a pre-existing failure cannot pin the loop open.
5. `stall_check` (`diff_stall_gate`, max_stall 3) after `work` — working tree unchanged across 3 passes routes to a partial summary.
6. Terminals `done` / `partial` (summary via `on_max_steps` or stall) / `failed`.

Top level: `on_handoff: spawn`, `max_steps` + `on_max_steps` cap, input NOT in `required_inputs` (otherwise `ll-loop run` rejects the empty-input fallback case before `load_prompt` runs).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/continue-task.yaml` (new)

### Dependent Files (Callers/Importers)
- N/A — standalone built-in loop, discovered by the loop loader

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — handoff wiring, `check_baseline_tests` test-cmd resolution
- `scripts/little_loops/loops/prompt-across-issues.yaml` — quoted-heredoc input capture

### Tests
- `scripts/tests/test_builtin_loops.py` — expected built-in loop list

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `README.md` loop count

### Configuration
- Reads `continuation.prompt_expiry_hours`, `project.test_cmd` (no new keys)

## Implementation Steps

1. Add `scripts/little_loops/loops/continue-task.yaml` (states above).
2. Register it: expected-loop list in `scripts/tests/test_builtin_loops.py`, the table in `scripts/little_loops/loops/README.md`, the General-purpose row in `docs/guides/LOOPS_GUIDE.md`, and the README loop count if it changes.
3. Tests: `ll-loop validate continue-task` passes; `load_prompt` fallback / staleness / missing-both cases (shell-level, tmp project dir); input absent from `required_inputs`.
4. Document that `on_handoff: spawn` is detached (`HandoffHandler._spawn_continuation` in `little_loops.fsm.handoff_handler` discards stdout), so the foreground view ends at the first handoff — follow along with `ll-loop status` / run logs.

## Impact

- **Priority**: P3 - Workflow convenience; manual `/ll:resume` works today
- **Effort**: Small - one thin YAML reusing existing handoff machinery, plus registration
- **Risk**: Low - additive new loop; no changes to executor or existing loops
- **Breaking Change**: No

## Use Case

A developer's interactive session hits the context threshold mid-task and runs `/ll:handoff`. Instead of manually opening a new session and running `/ll:resume` (repeatedly, for a long task), they run `ll-loop run continue-task` with no argument. The loop picks up the handoff prompt, pins its goal, and keeps working across as many handoffs as needed, stopping only when an independent done-check (plus the test command, when one exists) confirms the goal is met, or when the iteration cap is hit.

## API/Interface

```
ll-loop run continue-task                 # resume newest .ll/ll-continue-prompt.md
ll-loop run continue-task "<prompt>"      # explicit continuation prompt / task
ll-loop run continue-task --context test_cmd="pytest -x" --context max_passes=20
```

## Acceptance Criteria

- `ll-loop run continue-task` with no input and a fresh handoff file starts from that file and writes `goal.md`.
- With no input and no (or stale) handoff file, the run fails at `load_prompt` with an actionable message.
- `check_done` cannot pass on the worker's self-report alone; a failing test command forces NO.
- Loop validates cleanly and appears in the built-in loop listings/tests.
- Loop contains no Issue-system coupling.

## Risks

- `.ll/ll-continue-prompt.md` is a single shared file, overwritten by any session's `/ll:handoff` and by the PreCompact hook (`little_loops.hooks.pre_compact_handoff`). Mitigated by the staleness check, provenance printing, and the pinned `goal.md`.

## References

- `general-task.yaml` — `on_handoff: spawn`, `pass-started.txt` freshness check in `select_step` / `do_work`
- `little_loops.fsm.handoff_handler` — spawn = detached `ll-loop resume <loop>`
- `little_loops.issue_manager.run_with_continuation` — Issue-coupled Python equivalent used by ll-auto

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-25T04:27:15 - `a8472ba4-4c46-48b4-8f68-409c6b4973fa.jsonl`
