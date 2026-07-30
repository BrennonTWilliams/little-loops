---
id: BUG-2928
title: ll-queue LOOP entries are killed by the 120s subprocess timeout, discarding
  the FSM's own budget and summary.json
type: BUG
status: done
priority: P2
captured_at: '2026-07-30T20:15:00Z'
completed_at: '2026-07-30T21:44:50Z'
discovered_date: 2026-07-30
discovered_by: capture-issue
relates_to:
- BUG-2929
- FEAT-2930
- ENH-2931
labels:
- queue
- fsm
- feat-2906
confidence_score: 100
outcome_confidence: 95
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2928: ll-queue LOOP entries are killed by the 120s subprocess timeout

## Summary

`ll-queue add <loop> --runner loop` stamps the generic `ActionSpec.timeout`
default of **120 seconds** onto the entry. `_run_loop_entry` passes that value
straight to `subprocess.run(..., timeout=action.timeout)`, so every queued FSM
loop run is hard-killed two minutes in — long before any real loop finishes.
The entry is written back as `timed_out` / `failed`, and the loop's own
graceful-termination path never runs.

The outer timeout is not merely redundant with the FSM's internal budget, it
**destroys** it: `subprocess.TimeoutExpired` kills the child process, so the
executor never reaches `self._finish("timeout")` and therefore never flushes
pending shell state, never writes `summary.json`, and never stamps a
`terminated_by` classification. The queue records an infrastructure kill in
place of the run's actual verdict.

## Current Behavior

A `LOOP` queue entry is enqueued with `timeout: 120` and, on `ll-queue run`, is
hard-killed by `subprocess.TimeoutExpired` roughly two minutes into execution.
`cmd_run` catches the resulting `RunnerResult(timed_out=True)` and writes the
entry back as `failed`. The child `ll-loop` process dies mid-state, so no
`summary.json` is produced and the run's `terminated_by` is never classified.

## Steps to Reproduce

```bash
ll-queue add autodev --runner loop --input "ENH-2924"
ll-queue run
```

1. Observe the `ll-loop run autodev ENH-2924` subprocess is killed at ~120s.
2. `ll-queue status <id> --json` shows `status: failed`, `timed_out: true`.
3. No run summary exists under the loop's run directory.

Stored entry (from `.ll/queue.db`):

```json
{
  "action": {
    "name": "autodev", "runner": "loop", "target": "autodev",
    "args": {"loop_input": "ENH-2924"},
    "timeout": 120
  }
}
```

## Expected Behavior

A `LOOP` entry runs to its own completion under the FSM's budget stack. The
subprocess wrapper imposes no wall clock of its own by default, so the executor
reaches its normal termination path, writes `summary.json`, and the queue
records the loop's real exit status. Non-LOOP runners are unaffected and keep
the 120s default. An explicit `--timeout N` still overrides for any runner.

## Root cause

FEAT-2906 added the `RunnerType.LOOP` dispatch path but left the timeout
default runner-agnostic:

- `scripts/little_loops/runner_spec.py:90` — `timeout: int = 120` on `ActionSpec`
- `scripts/little_loops/cli/queue.py:389` — `add` parser: `--timeout` `default=120`
- `scripts/little_loops/cli/queue.py:257` — `_run_loop_entry` forwards it to `subprocess.run`

120s is a sane bound for a `SKILL`/`CMD`/`MCP`/`PROMPT` one-shot, which has no
internal budget of its own. A `LOOP` target is the opposite case: it already
carries a full budget stack.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Widening `ActionSpec.timeout` to `int | None` is safe** — the only live
  consumer of the field is `_run_loop_entry`'s
  `subprocess.run(..., timeout=action.timeout)` (`cli/queue.py:257`); no other
  site in `cli/queue.py` formats, arithmetically operates on, or logs
  `action.timeout`. `RunnerType.LOOP` is also never routed through
  `runner_spec.py`'s `_DISPATCH` table (`runner_spec.py:300-305`, keyed only on
  `SKILL`/`CMD`/`MCP`/`PROMPT`), so `ActionSpec.timeout` for a `LOOP` entry has
  no other reader.
- **`None` round-trips through queue persistence correctly** —
  `queue_store.py`'s `_serialize_action`/`_deserialize_action`
  (`queue_store.py:188-208`) pass `timeout` through `json.dumps`/`json.loads`
  verbatim; an explicit `None` serializes to JSON `null` and deserializes back
  to `None` (the `data.get("timeout", 120)` fallback only applies when the key
  is *absent*, not when it's explicitly `null`). `QueueEntry.to_dict()`
  (`queue_store.py:222-236`) likewise emits `"timeout": null` with no
  int-only formatting assumption — confirms AC 1's `timeout: null` claim.
- **Other `ActionSpec(...)` construction sites already pass explicit
  timeouts** (confirms the "other call sites depend on it" note below):
  `cli/harness.py:398-404,424-429`, `cli/action.py:239-245,292-298`, and
  `cli/loop/run.py:132-137` (the latter's `ActionSpec` is documentary-only —
  its own comment notes it's "not dispatched through
  `runner_spec.run_action()`"). None of these rely on the dataclass default
  itself, but none should be touched by this fix either.
- **Precedent for `int | None` timeout fields already exists** in this
  codebase: `fsm/schema.py`'s `StateConfig.timeout` and `LoopFSM.timeout` /
  `default_timeout` are already `int | None = None`, consumed via the
  falsy-check idiom `if self.fsm.timeout: ...` (`fsm/executor.py:541`) —
  the same "`None` means unbounded" semantics this fix adopts.

## Why LOOP entries need no outer timeout

The FSM enforces its own bounds, and does so gracefully:

- **Loop-level wall clock** — `timeout:` (`fsm-loop-schema.json:61`), enforced
  at `fsm/executor.py:561` via `self._finish("timeout")`, which flushes pending
  shell state, writes `summary.json`, and sets `terminated_by: "timeout"`.
  `autodev.yaml:19` sets `timeout: 28800`.
- **Step cap** — `max_steps`, defaulting to `50` (`fsm/schema.py:1267`) even
  when a loop declares no wall clock, so a LOOP entry is never unbounded.
  `autodev.yaml:18` sets `max_steps: 500`.
- **Per-state and per-action timeouts** — `default_timeout`
  (`fsm-loop-schema.json:92`) and action-level `timeout`
  (`fsm-loop-schema.json:472`).

Two budgets where the outer one is 240× shorter means the outer one always
fires first and always loses the diagnostic value of the inner one.

## Proposed fix

1. **`LOOP` entries default to no subprocess timeout** (`timeout: None`), letting
   the FSM's own budget terminate the run. `_run_loop_entry` already handles
   `timeout=None` correctly — `subprocess.run` treats it as "wait forever".
2. **Non-LOOP runners keep the 120s default**, unchanged.
3. An explicit `--timeout` on `ll-queue add` still overrides for any runner, so
   an operator-imposed outer bound remains available.

Surfacing `args.loop_input`/`timeout` in `ll-queue list` output — whose absence
made this entry class look input-less during triage — is split out as
**ENH-2931** and is not in scope here.

Implementation note: the default must be resolved per-runner *after*
classification in `cmd_add` (`cli/queue.py:91`), not by changing
`ActionSpec.timeout`'s dataclass default, which other call sites depend on.

**Correctness constraint on `_default_timeout_for` (found by `/ll:wire-issue`):**
`None` is only safe for runner kinds whose dispatch handler forwards `timeout`
straight to `subprocess.run(..., timeout=...)`, which tolerates `None`
natively. Two of the four non-LOOP runner handlers in `runner_spec.py` instead
do raw deadline arithmetic on the timeout value and will raise `TypeError` on
`None`:
- `runner_spec.py`'s `_run_cmd()` (~line 186-212) — `deadline = time.time() +
  spec.timeout`, reachable for `ll-queue add ... --runner cmd`.
- `mcp_call.py`'s `call_mcp_tool()` (~line 103), called from `runner_spec.py`'s
  `_run_mcp()` (~line 277) — `deadline = time.monotonic() + timeout`;
  `call_mcp_tool`'s own signature types `timeout: int` (not `int | None`).

`_run_skill()`/`_run_prompt()` forward `spec.timeout` straight to
`subprocess.run(...)` and are `None`-safe. So `_default_timeout_for` must
return a concrete `int` (120, unchanged) for `RunnerType.CMD` and
`RunnerType.MCP` specifically — not just "120 for everything except LOOP" by
accident of the current runner set. Add a test asserting
`_default_timeout_for` never returns `None` for `CMD`/`MCP`/`SKILL`/`PROMPT`,
only for `LOOP`, so a future runner addition can't silently reintroduce this.

**Pre-existing rows are unaffected but not backfilled:** `queue_store.py`'s
`_deserialize_action()` uses `data.get("timeout", 120)`, which only falls back
when the `"timeout"` key is absent — any `.ll/queue.db` row written before
this fix already has a literal `"timeout": 120` baked into its JSON and stays
at 120 forever (no migration needed or planned; new adds get the corrected
default).

## Program Design

### Types

- `ActionSpec.timeout: int | None` — widen from `int` to admit "no outer bound"

### Signatures

- `_default_timeout_for(runner: RunnerType) -> int | None` — `None` for
  `RunnerType.LOOP`, `120` otherwise
- `_classify_action(target: str, runner: str | None, args_dict: dict, timeout: int | None) -> ActionSpec`
- `_run_loop_entry(action: ActionSpec) -> RunnerResult` — unchanged; already
  forwards `action.timeout` to `subprocess.run`, which accepts `None`

### Call Path

`cmd_add` -> `_classify_action` -> `_default_timeout_for` -> `ActionSpec`
then `cmd_run` -> `_run_loop_entry` -> `subprocess.run(timeout=None)`

The `--timeout` argparse default changes from `120` to `None` so `cmd_add` can
distinguish "operator supplied a bound" from "fall back to the per-runner
default".

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Documentation

- `docs/reference/CLI.md` (`ll-queue add` flags table, ~line 2795) — documents
  `--timeout N | Timeout in seconds (default: 120)`; goes stale once the
  default is per-runner. Update to note LOOP entries default to unbounded
  (no subprocess deadline) while SKILL/CMD/MCP/PROMPT keep 120. [Agent 2/1
  finding]
- `.claude/CLAUDE.md`'s `ll-queue` CLI-tools bullet — optional one-line note
  that timeout now defaults per-runner, for consistency with the CLI.md fix.
  [Agent 2 finding]

### Tests

- `scripts/tests/test_cli_queue.py::TestClassifyAction` — add a case modeled
  on `test_runner_override_skips_classification` (lines 64-67): LOOP-runner
  add-with-no-`--timeout` resolves `spec.timeout is None`; non-LOOP runner
  (skill/cmd) resolves to `120`. All existing cases in this class pass
  `timeout=120` explicitly, so none break. [Agent 3 finding]
- `scripts/tests/test_cli_queue.py::TestCmdAdd` (lines 102-161) — add
  `add --runner loop` (no `--timeout`) asserting `entries[0].action.timeout
  is None`, and `add --runner loop --timeout 30` asserting the explicit
  override survives (`== 30`). [Agent 3 finding]
- `scripts/tests/test_cli_queue_run.py::TestCmdRunLoopDispatch` (lines
  235-334) — extend `test_loop_entry_intercepted_before_run_action`'s pattern
  (it already mocks `little_loops.cli.queue.subprocess.run` and inspects
  `call_args`) to assert `mock_subproc.call_args.kwargs["timeout"] is None`
  for a default `self._add_loop(...)` entry, plus an override-honored variant
  passing `--timeout 30` through `_add_loop` (extend its signature with an
  optional `timeout` kwarg). No existing test in this file currently asserts
  on the `timeout` kwarg passed to `subprocess.run` — only on `cmd` and
  `returncode`. [Agent 3 finding]
- `scripts/tests/test_runner_spec.py` — add a dataclass-level test that
  `ActionSpec(timeout=None)` is constructible and round-trips
  (`spec.timeout is None`), covering the `int` → `int | None` widening
  directly. Also add (per the correctness constraint above) a test that
  `_default_timeout_for` returns a concrete `int` for `CMD`/`MCP`, not just
  "not LOOP". [Agent 3 finding]
- `scripts/tests/test_queue_store.py` — no existing test references
  `timeout` at all (confirmed via grep). Add a round-trip test:
  `add_entry(ActionSpec(..., timeout=None), ...)` then `get_entry(...)
  .action.timeout is None`, since `None` was previously type-unreachable for
  this field and is now a real value flowing through JSON `null`
  serialize/deserialize (`queue_store.py` lines ~195, ~207). [Agent 3
  finding]

No new callers, importers, or registration/manifest files were found beyond
what the issue's own `/ll:refine-issue` pass already identified
(`cli/harness.py`, `cli/action.py`, `cli/loop/run.py` — all pass explicit
timeouts or are documentary-only, unaffected either way).

## Acceptance criteria

- [x] `ll-queue add <loop> --runner loop` stores `timeout: null` by default;
      `ll-queue status <id> --json` shows it.
- [x] `ll-queue add <skill> --runner skill` still stores `timeout: 120`.
- [x] An explicit `--timeout N` is honored for both runner kinds.
- [x] A queued LOOP entry whose loop exceeds its own `timeout:` is written back
      with the loop's real exit status, and its `summary.json` exists on disk.
      (`_run_loop_entry` already forwarded `action.timeout` to
      `subprocess.run`; with `None` it no longer imposes an outer deadline, so
      the FSM's own `self._finish("timeout")` path — which writes
      `summary.json` — is what terminates the run instead of
      `subprocess.TimeoutExpired`.)
- [x] Regression test in `scripts/tests/` covering the per-runner default split
      and the `timeout=None` pass-through in `_run_loop_entry`. See
      Integration Map → Tests for the specific files/classes to extend.
- [x] `_default_timeout_for` returns a concrete `int` (not `None`) for every
      runner kind except `LOOP` — specifically covering `CMD` and `MCP`,
      whose dispatch handlers (`runner_spec.py`'s `_run_cmd()`,
      `mcp_call.py`'s `call_mcp_tool()`) do raw deadline arithmetic on
      `timeout` and would raise `TypeError` on `None`.
- [x] `python -m pytest scripts/tests/` exits 0.

## Resolution

Implemented per the Program Design:

- `ActionSpec.timeout` widened to `int | None` (`runner_spec.py`).
- New `_default_timeout_for(runner) -> int | None` in `cli/queue.py`: `None`
  for `RunnerType.LOOP`, `120` for every other runner kind.
- `_classify_action` now takes `timeout: int | None` and resolves the
  per-runner default *after* the runner is known (at each of the four
  `ActionSpec(...)` construction sites — override, loop, skill, cmd
  fallback), only when the caller passed no explicit `--timeout`.
- `ll-queue add --timeout` argparse default changed from `120` to `None` so
  `cmd_add` can distinguish "operator supplied a bound" from "fall back to
  the per-runner default".
- `_run_skill`/`_run_cmd`/`_run_mcp` each gained a leading
  `assert spec.timeout is not None` (mypy narrowing + a fail-fast guard) since
  those three runner kinds are guaranteed a concrete int by
  `_default_timeout_for`'s contract, but the field itself is now nullable at
  the type level.
- Docs: `docs/reference/CLI.md`'s `ll-queue add` flags table and
  `.claude/CLAUDE.md`'s `ll-queue` bullet updated to describe the per-runner
  default.
- Tests added: `test_cli_queue.py` (`TestClassifyAction`, `TestCmdAdd`),
  `test_cli_queue_run.py` (`TestCmdRunLoopDispatch`, extended `_add_loop` with
  a `timeout` kwarg), `test_runner_spec.py` (`ActionSpec(timeout=None)`
  round-trip + new `TestDefaultTimeoutFor`), `test_queue_store.py`
  (`timeout=None` JSON `null` round-trip through `add_entry`/`get_entry`).

No deviations from the Program Design.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete test targets to extend rather than write from scratch:

- `scripts/tests/test_cli_queue.py::TestClassifyAction` (lines 41-99) — model
  the per-runner default-split assertion after
  `test_runner_override_skips_classification`: call `_classify_action` (or
  `cmd_add` via `main_queue()`, see `TestCmdAdd`, lines 102-161) with
  `--runner loop` and no `--timeout`, assert `spec.timeout is None`; repeat
  with `--runner skill`/`cmd` and assert `spec.timeout == 120`.
- `scripts/tests/test_cli_queue_run.py::TestCmdRunLoopDispatch::test_loop_entry_intercepted_before_run_action`
  (lines 252-270) — model the `timeout=None` pass-through assertion after this
  test: it already patches `little_loops.cli.queue.subprocess.run` and
  inspects `mock_subproc.call_args`; extend to assert
  `mock_subproc.call_args.kwargs["timeout"] is None` for a loop entry added
  without `--timeout`. `self._add_loop` (lines 238-250) is the existing
  helper for adding a `--runner loop` entry, ready to extend with a
  `--timeout` param for the "explicit override still honored" case.

## Impact

Any `ll-queue`-driven loop is currently unrunnable — the queue is effectively
broken for its most valuable target type. Discovered while queueing four
`autodev` runs behind a foreground run (ENH-2924/2925/2926/2927); all four
would have been killed at 120s had the queue been drained.

**Effort**: Small — a per-runner default resolved in `cmd_add`, a widened type,
and a regression test. **Risk**: Low — non-LOOP behavior is unchanged, and the
removed bound is redundant with budgets the FSM already enforces.

## Status

**Open** | Created: 2026-07-30 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-07-30T21:44:05 - `b3c9de44-6d9c-4099-9f92-17cf82854bca.jsonl`
- `/ll:ready-issue` - 2026-07-30T21:32:57 - `740a88d8-1ae8-4f57-8426-d566c01d1cab.jsonl`
- `/ll:wire-issue` - 2026-07-30T21:29:59 - `307f37c1-e6b1-44d4-9957-bb321f5094d3.jsonl`
- `/ll:refine-issue` - 2026-07-30T21:23:36 - `9727f339-34c8-42ec-bbfb-eafae362c41c.jsonl`
