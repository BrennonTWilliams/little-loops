---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1080
size: Small
confidence_score: 95
outcome_confidence: 88
score_complexity: 3
score_test_coverage: 4
score_ambiguity: 4
score_change_surface: 3
---

# FEAT-1228: Deprecate ll-parallel in Favor of FSM Parallel States

## Summary

Emit a deprecation warning from `ll-parallel` on every invocation directing users to FSM loops with `parallel:` states, and add an inline comment to `ll-auto` explaining why no multiplication concern exists there.

## Parent Issue

Decomposed from FEAT-1080: Parallel State FSM API Exports and Config Wiring

## Use Case

**Who**: A developer currently using `ll-parallel` to run issues concurrently

**Context**: `ll-parallel` is a legacy mechanism for outer-level parallelism. FSM loops with `parallel:` states are the intended replacement — they express parallelism inside the loop definition itself, eliminating the silent N×M worker multiplication that arises when combining `ll-parallel` with `parallel:` states. Users should be directed to the loop-based approach.

**Goal**: Every `ll-parallel` invocation prints a deprecation notice pointing to the loop-based alternative. No behavior change — the tool continues to work.

**Outcome**: Users discover the FSM-native path without needing to read changelogs or docs.

## Motivation

`ll-parallel` and the FSM `parallel:` state are two separate concurrency layers that compose silently and multiplicatively. The architecturally clean solution is to consolidate on one layer — FSM loops — and deprecate `ll-parallel` rather than patching the symptom with a per-run warning. The deprecation warning is the first visible step toward that consolidation.

## Current Behavior

- `ll-parallel` runs N issues in N parallel worktrees with no deprecation notice
- Users have no signal that loop-based parallelism is the preferred path
- `ll-auto` has no comment explaining that sequential outer execution means inner `parallel:` states are free to use their full `max_workers` budget

## Expected Behavior

- `ll-parallel` prints exactly one deprecation notice to stderr on every invocation:
  ```
  ⚠ ll-parallel is deprecated. Use ll-loop with a parallel: state instead — loop-based parallelism avoids the silent N×M worker multiplication from combining ll-parallel with parallel: states.
  ```
- `ll-auto` gains an inline comment (no stderr output) explaining sequential outer behavior
- `ll-sprint` is unchanged — sprint manages curated issue sets with dependency ordering and is a distinct feature; no deprecation applies

## Proposed Solution

### `scripts/little_loops/cli/parallel.py`

Add a single `print(...)` call near the top of `main_parallel()` (before argument parsing side-effects, after the function entry):

```python
print(
    "⚠ ll-parallel is deprecated. Use ll-loop with a parallel: state instead — "
    "loop-based parallelism avoids the silent N×M worker multiplication from "
    "combining ll-parallel with parallel: states.",
    file=sys.stderr,
)
```

No loop loading, no `--loop` argument, no `load_loop_with_spec`.

### `scripts/little_loops/cli/auto.py`

Insert inline comment before `manager = AutoManager(...)` (line 90):

```python
# ll-auto processes issues sequentially — inner parallel: states use their own
# max_workers budget without multiplying outer concurrency.
```

### Modules MUST NOT be touched

- `scripts/little_loops/fsm/executor.py`
- `scripts/little_loops/fsm/parallel_runner.py`
- `scripts/little_loops/parallel/worker_pool.py`
- `scripts/little_loops/cli/sprint/run.py`

### Tests

- `scripts/tests/test_ll_parallel.py` (new file):
  - Assert deprecation warning is printed to stderr on every `main_parallel()` invocation
  - Assert warning text includes `"deprecated"` and `"ll-loop"`
- `scripts/tests/test_ll_auto.py` (new file):
  - Assert no warning is emitted to stderr when `main_auto()` runs (comment-only change; belt-and-suspenders regression test)

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/parallel.py` — add deprecation print at `main_parallel()` entry (`main_parallel()` at line 31)
- `scripts/little_loops/cli/auto.py` — inline comment only (`main_auto()` at line 21, `AutoManager` constructed at line 90)

### New Test Files

- `scripts/tests/test_ll_parallel.py` — deprecation warning assertions
- `scripts/tests/test_ll_auto.py` — no-warning regression

### Files NOT affected (previously at-risk)

Adding a `print()` at `main_parallel()` entry requires no `load_loop_with_spec` call, so the following previously-at-risk test groups need **no changes**:
- `scripts/tests/test_cli.py:495–568` (`TestMainParallelIntegration`)
- `scripts/tests/test_cli.py:1601–1724` (`TestMainParallelAdditionalCoverage`)
- `scripts/tests/test_sprint_integration.py`
- `scripts/tests/test_sprint.py`

### Similar Patterns

- **Warning-assertion template**: `scripts/tests/test_ll_loop_commands.py:75-107` — asserts `"⚠" in captured.out` via `capsys.readouterr()`; adapt to `captured.err` since this warning targets stderr
- **CLI entry-point test pattern**: `scripts/tests/test_cli.py:1561-1566` — `patch.object(sys, "argv", [...])` + direct function call

### Documentation

- `docs/reference/CLI.md:140–165` — `ll-parallel` flag table; add a deprecation note at the top of the `ll-parallel` section pointing to `ll-loop`

## Acceptance Criteria

- Every `ll-parallel` invocation emits exactly one deprecation notice to stderr containing `"deprecated"` and `"ll-loop"`
- `ll-auto` has the inline comment; no stderr output from `ll-auto`
- `ll-sprint` is unmodified
- New tests confirm warning fires and no new warnings appear under `ll-auto`

## Impact

- **Priority**: P2
- **Effort**: XSmall — 2 CLI file changes (1 one-liner + 1 comment) + 2 small test files + 1 doc note
- **Risk**: Very Low — deprecation notice only; no behavior change to loop execution
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `cli`, `observability`, `deprecation`

---

**Open** | Created: 2026-04-21 | Priority: P2

## Design Decisions

### 1. Deprecation over warning: rationale

The original issue body proposed a per-run N×M multiplication warning requiring `ll-parallel` to load the loop definition (via a new `--loop` argument). This approach was rejected because:

- Adding `--loop` to `ll-parallel` is a band-aid: the tool itself is the architectural problem
- The N×M multiplication problem dissolves when `ll-parallel` is replaced by loop-based parallelism — there is only one concurrency layer
- A deprecation notice is simpler, requires no new arguments, has no test blast radius, and communicates the correct migration path

### 2. Warning mechanism: `print(..., file=sys.stderr)`

Consistent with the existing codebase approach (`config_cmds.py:27`). `warnings.warn` is absent from `scripts/little_loops/` and is unnecessary here.

### 3. `ll-sprint` scope exclusion

Sprint manages curated issue sets with dependency-aware ordering — a distinct feature from raw parallel worktree execution. No deprecation applies to sprint. If sprint's internal parallel dispatch (the `ParallelOrchestrator` path in `run.py:389–410`) is ever reconsidered, that is a separate issue.

## Session Log
- Direction change: 2026-04-21 — scope narrowed from N×M multiplication warning to ll-parallel deprecation notice; `--loop` argument design discarded
- `/ll:confidence-check` - 2026-04-21T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed37497f-849a-4b7b-be30-d51876e9ed94.jsonl`
- `/ll:wire-issue` - 2026-04-21T19:09:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36a8767f-2730-435d-ac77-be8642d21476.jsonl`
- `/ll:refine-issue` - 2026-04-21T19:03:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e249e1c1-8792-41dc-a575-86d270039932.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644812c0-533a-4e26-96b6-038b38467391.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:26:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/444f6307-f957-4298-afd7-8110637a61ba.jsonl`
- `/ll:wire-issue` - 2026-04-21T16:19:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e62948-0099-497f-bfc8-c00efc10983d.jsonl`
- `/ll:refine-issue` - 2026-04-21T16:11:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7a2ae01-e999-4e1d-b35a-80cc743b6a7d.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c25b41ad-2e86-4d04-bea4-6daf251405e7.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e62948-0099-497f-bfc8-c00efc10983d.jsonl`
