---
id: ENH-2668
title: "Extract shared runner abstraction (RunnerType enum + ActionSpec) from ll-harness/ll-action/ll-loop"
type: ENH
priority: P2
status: open
captured_at: "2026-07-18T00:00:00Z"
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2670
relates_to: [FEAT-2669]
labels:
  - refactor
  - runners
  - cli
decision_needed: false
---

# ENH-2668: Extract shared runner abstraction (RunnerType/ActionSpec)

## Summary

Extract `ll-harness`'s five-way dispatch (`skill`/`cmd`/`mcp`/`prompt`/`dsl`)
plus FSM loop execution into a real `RunnerType` enum + `ActionSpec`
dataclass (name, runner type, invocation args, timeout, etc.) with a single
dispatch function returning `RunnerResult`. `ll-action`, `ll-harness`, and
`ll-loop run` become thin callers of this shared primitive instead of each
owning their own if/elif dispatch. This is Phase 1 of
`thoughts/plans/2026-07-17-generic-ll-queue-design.md` and the prerequisite
for FEAT-2669 (generic `ll-queue`).

## Motivation

- No shared runner abstraction exists today. `ll-action` (`cli/action.py`)
  dispatches via if/elif over skill-name strings calling
  `run_claude_command()`; `ll-harness` (`cli/harness.py:119-170, 450-469`)
  dispatches via argparse subparsers over five runner kinds — also if/elif,
  not an enum/protocol.
- The only shared type between them is `RunnerResult` (`harness.py:25-33`) —
  an output shape, not a dispatch abstraction.
- A generic queue (FEAT-2669) needs a "run this generic work item" primitive;
  this extraction provides it. It is independently useful even if the queue
  never ships: it removes the `ll-action`/`ll-harness` dispatch duplication.

## Current Behavior

- Three CLIs (`ll-action`, `ll-harness`, `ll-loop run`) each own their own
  dispatch logic over overlapping runner kinds; adding a runner type means
  touching each in a different way.

## Expected Behavior

- A `RunnerType` enum covering at least `skill`/`cmd`/`mcp`/`prompt`/`dsl`
  plus FSM loop execution.
- An `ActionSpec` dataclass (name, runner type, invocation args, timeout,
  etc.) and a single dispatch function `run(spec: ActionSpec) -> RunnerResult`.
- `ll-action`, `ll-harness`, and `ll-loop run` call the shared primitive;
  their existing CLI UX and flags are unchanged (no new scheduling behavior).

## Proposed Solution

1. New module (e.g. `scripts/little_loops/runners/` or
   `scripts/little_loops/runner_spec.py`) holding `RunnerType`, `ActionSpec`,
   `RunnerResult` (moved from `harness.py`), and the dispatch function.
2. Port `ll-harness`'s five subparser paths onto the dispatch function.
3. Port `ll-action`'s skill-name if/elif onto `ActionSpec(runner=skill, ...)`.
4. Wrap FSM loop execution (`PersistentExecutor`/`run_foreground` path in
   `cli/loop/run.py`) as a `RunnerType.LOOP` spec. Watch for impedance
   mismatch here — long-running/persistent execution vs. one-shot runners is
   the riskiest part of the extraction; if it doesn't fit cleanly, keep loop
   execution as a thin adapter rather than forcing it into the one-shot shape.
5. Keep `RunnerResult` importable from its old location (re-export) to avoid
   breaking existing importers.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/harness.py` — dispatch extracted; becomes caller
- `scripts/little_loops/cli/action.py` — becomes caller
- `scripts/little_loops/cli/loop/run.py` — loop execution exposed via spec
- New runner module (see Proposed Solution)

### Dependent Files (Callers/Importers)

- Any importers of `RunnerResult` from `harness.py` (re-export preserves them)

### Similar Patterns

- `harness.py` five-way subparser dispatch is the closest existing template

### Tests

- New unit tests for `ActionSpec` normalization + dispatch per runner type
- Existing `ll-action`/`ll-harness`/`ll-loop` test suites must stay green
  unchanged (behavior-preserving refactor)

### Documentation

- `docs/reference/API.md` — document the new runner module

## Acceptance Criteria

- `RunnerType` + `ActionSpec` + single dispatch function exist and cover all
  five harness runner kinds plus FSM loop execution.
- `ll-action`, `ll-harness`, and `ll-loop run` route through the shared
  primitive; their CLI UX is byte-for-byte unchanged (flags, output, exit
  codes).
- No duplicated runner dispatch if/elif remains in `action.py`/`harness.py`.
- `python -m pytest scripts/tests/` exits 0 with no test modifications other
  than import-path updates.

## Scope Boundaries

- **In**: mechanical extraction, re-exports, unit tests for the new module.
- **Out**: any queueing/scheduling behavior (FEAT-2669); changing runner
  semantics, timeouts, or CLI UX; touching `ll-parallel`/`ll-sprint`.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | Source design doc — Phase 1 |
| FEAT-2669 | Consumer of this abstraction (generic `ll-queue`) |

## Impact

- **Priority**: P2 — prerequisite for FEAT-2669; independently reduces
  duplication across three CLIs.
- **Effort**: Small-Medium — mostly mechanical, but touches three CLIs with
  existing test surfaces; FSM-loop fit is the main risk.
- **Risk**: Low — behavior-preserving refactor with existing tests as a net.
- **Breaking Change**: No — additive module + internal rewiring.

## Status

**Open** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-18T00:00:00Z - filed from `thoughts/plans/2026-07-17-generic-ll-queue-design.md` Phase 1 (runner abstraction extraction).
