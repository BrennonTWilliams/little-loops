---
id: FEAT-2906
title: '`ll-queue run`: dispatch RunnerType.LOOP entries via PersistentExecutor'
type: FEAT
priority: P2
status: open
captured_at: '2026-07-29T00:47:13Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- FEAT-2682
- FEAT-2683
- EPIC-2670
- EPIC-2616
labels:
- queue
- cli
- fsm
- scheduling
decision_needed: false
confidence_score: 98
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# FEAT-2906: `ll-queue run` — dispatch `RunnerType.LOOP` entries via `PersistentExecutor`

## Summary

`ll-queue add <loop-name>` classifies its target as `RunnerType.LOOP`
(`cli/queue.py:62-67`), but `ll-queue run` dispatches every dequeued entry
through `run_action()` (`cli/queue.py:243`), which explicitly refuses `LOOP`
(`runner_spec.py:12-19`, `308-319`). Queued loops are therefore accepted at
enqueue time and guaranteed to fail at dequeue time. Wire a real `LOOP` branch
in `cmd_run` that drives the FSM through `PersistentExecutor`/`run_foreground`,
and give the entry a place to carry the loop's input.

## Current Behavior

1. `ll-queue add rn-implement` → `_classify_action` calls `resolve_loop_path`,
   succeeds, and builds an `ActionSpec(runner=RunnerType.LOOP, ...)`. The entry
   persists as `pending` with no warning.
2. `ll-queue run` pops it (`cli/queue.py:236-239`), marks it `running`, and
   calls `run_action(entry.action)`.
3. `run_action` finds no handler in `_DISPATCH` for `RunnerType.LOOP` and raises
   `ValueError: run_action() does not dispatch runner type: RunnerType.LOOP`.
4. The `except Exception` at `cli/queue.py:244` swallows it into
   `{"exit_code": None, "timed_out": False, "error": "..."}` and the entry is
   written back as `failed`.

There is also no way to pass loop input. `--arg KEY=VALUE` folds into
`ActionSpec.args`, which is not a context bag — it is a fixed set of runner
knobs consumed by the skill/cmd/mcp/prompt handlers (`runner_args`,
`stream_callback`, `trace_mode`, `automation_profile`, `workspace_root`,
`tools`, `mcp_params`, `model`; `runner_spec.py:112-283`). Unrecognized keys are
stored and silently ignored.

## Expected Behavior

- `ll-queue run` executes a queued FSM loop to completion, serially, and writes
  back a real `status`/`result` reflecting the run's terminal verdict.
- An `ll-queue add` entry can carry loop input, interpreted with the same
  semantics as `ll-loop run <loop> [input]`.
- The `RunnerType.LOOP`-is-not-dispatchable contract in `runner_spec.py` stays
  intact — the queue reaches the executor directly, it does not smuggle loops
  through `run_action()`.

## Motivation

EPIC-2670's stated goal was a queue for *heterogeneous* work items, with FSM
loops as the motivating case (the EPIC exists because `ll-loop queue`'s
liveness-marker mechanism never dequeues-and-executes anything). FEAT-2683
delivered the worker loop for `SKILL`/`CMD`/`MCP`/`PROMPT` and deferred `LOOP`,
which leaves the EPIC's headline use case not just unimplemented but actively
misleading: the CLI accepts the enqueue and reports `failed` later, so the
failure surfaces at dequeue time with a stack-trace-flavored error string rather
than at the point of user error.

## Use Case

A maintainer wants three FSM loops to run back-to-back overnight without holding
a terminal open per loop or hand-rolling a shell `&&` chain:

```bash
ll-queue add rn-refine --input '{"issue_id": "FEAT-2900"}' --priority P1
ll-queue add rn-implement --input '{"issue_id": "FEAT-2900"}' --priority P2
ll-queue add audit-loop-run --priority P3
ll-queue run
```

Each loop runs to completion in priority order; `ll-queue list` afterwards shows
per-entry terminal status. Today all three enqueue cleanly and all three fail at
dequeue.

## Proposed Solution

Add a `LOOP` branch in `cmd_run` before the `run_action()` call. Two viable
approaches:

**Option A — in-process, reuse `cmd_run_loop`.** Build an `argparse.Namespace`
matching `ll-loop run`'s parsed args and call the existing entry point. Keeps
one execution path, but `cmd_run_loop` owns a large amount of setup —
worktree creation and `os.chdir` (`cli/loop/run.py:560-563`), `atexit` cleanup,
`RateLimitCircuit`, `register_loop_signal_handlers` (`:584`), `wire_extensions`
/ `wire_transports` (`:589-590`) — all of which mutate global process state.
Running several queued loops in one `ll-queue run` process would compound those
mutations across iterations.

**Option B — subprocess per entry (recommended).**

> **Selected:** Option B — subprocess per entry, matching the existing
> `ll-loop run` shell-out precedent in `worker_pool.py` and
> `cli/sprint/run.py`; Option A's `cmd_run_loop` reinstalls process-global
> signal handlers on every call, making it unsafe to invoke repeatedly in one
> `ll-queue run` process.

Shell out to
`ll-loop run <target> [input]` per entry and map the exit code onto the
`RunnerResult` shape already used at `cli/queue.py:248-259`. Process isolation
matches the serial semantics FEAT-2669 Q1 settled on, sidesteps the `os.chdir`
and signal-handler reentrancy problems entirely, and gives each loop its own
teardown. Cost: the queue can no longer observe the FSM event bus directly.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected: Option B — subprocess per entry.** Two independent codebase-pattern
agents verified the evidence cited in Proposed Solution and Codebase Research
Findings. Option B has direct, working precedent (`worker_pool.py:87-120`,
`cli/sprint/run.py:219-236`) shelling out to `ll-loop run` with the exact
`subprocess.run` + exit-code verdict mapping (`0`/`FAILURE_TERMINAL_EXIT_CODE`/
other-nonzero) this issue's Implementation Steps call for, plus a matching
positional-input + `--context` construction pattern in
`cli/loop/next_loop.py:_build_command`. Option A's `cmd_run_loop` was found to
unconditionally reinstall signal handlers via shared module-level globals
(`register_loop_signal_handlers`, `cli/loop/run.py:584`) on every invocation —
serial dispatch of N queued loop entries in one process would reinstall and
overwrite the prior executor reference N times, a live process-wide hazard
with no teardown between iterations. `run_foreground` (a lower-level entry
point under Option A) doesn't eliminate this: it still requires a pre-built
`argparse.Namespace` and doesn't remove the duplicated setup/lock-acquisition
work.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 1 | 3 |
| Simplicity | 1 | 3 |
| Testability | 1 | 2 |
| Risk | 1 | 3 |
| **Total** | **4/12** | **11/12** |

Key evidence: `cli/loop/run.py:584` (`register_loop_signal_handlers` global
reassignment, Option A disqualifier); `worker_pool.py:87-120` and
`cli/sprint/run.py:219-236` (Option B's working precedent);
`little_loops/fsm/types.py:25` (`FAILURE_TERMINAL_EXIT_CODE = 2`, confirmed
importable).

Either way, add a dedicated `--input` on `ll-queue add`, stored verbatim on the
entry (as `ActionSpec.args["loop_input"]` or a first-class column) and applied
at dequeue time. It must **not** be re-interpreted at enqueue time: `ll-loop
run`'s positional does `json.loads`, and on a dict intersects its keys against
the *already-loaded* `fsm.context`, falling back to `fsm.input_key`
(`cli/loop/run.py:161-175`). `ll-queue add` never loads the FSM — it only calls
`resolve_loop_path` for existence — so the coercion has to happen where the FSM
is parsed.

Do not add a bare second positional to `ll-queue add`: it would collide with
`target`, which under `--runner cmd` is already a full command line.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Option B already has direct codebase precedent**, which should raise
  confidence in recommending it over Option A. `worker_pool.py` (proof-first-task
  gate, ~line 87-120) and `cli/sprint/run.py:219-236`
  (`ready-to-implement-gate` pre-flight) both already shell out to
  `["ll-loop", "run", <loop-name>, "--context", "key=value", ...]` via
  `subprocess.run(cmd, capture_output=True, text=True, cwd=...)` and derive a
  verdict from `returncode`: `0` → success, `FAILURE_TERMINAL_EXIT_CODE`
  (imported from `little_loops.fsm.types`) → a distinguishable
  "terminal-failure" outcome, any other nonzero → generic failure. This
  three-way exit-code split is a candidate for the `LOOP` branch's
  `result_dict`/`status` mapping in `cmd_run` beyond the current binary
  `done`/`failed` split used for `SKILL`/`CMD`/`MCP`/`PROMPT`.
- **Constructing the positional `input` argument** already has a pattern in
  `cli/loop/next_loop.py:_build_command()` (lines 173-181): `json.dumps(...)`
  of the input dict is appended as a bare positional, and any remaining
  params are passed as `--context KEY=VALUE`. The new `--input` value on a
  queue entry should be threaded through the same way when building the
  subprocess argv for Option B.
- `ll-loop run`'s `input` positional is registered in
  `cli/loop/__init__.py:126-131` (`nargs="?"`, default `None`) — confirms the
  argparse shape the subprocess call needs to match.
- `runner_spec.py`'s `_DISPATCH` table (mapping only `SKILL`/`CMD`/`MCP`/`PROMPT`)
  and `run_action()`'s `handler = _DISPATCH.get(spec.runner); if handler is
  None: raise ValueError(...)` confirm the AC "run_action() still raises for
  RunnerType.LOOP" requires no code change — only the module docstring note
  already scoped in the Integration Map.

## Integration Map

| File | Change |
|------|--------|
| `scripts/little_loops/cli/queue.py` | `cmd_run`: branch on `RunnerType.LOOP` before `run_action()`; `cmd_add`/parser: add `--input`; `_classify_action`: thread input onto the spec |
| `scripts/little_loops/queue_store.py` | Persist/round-trip the loop input field |
| `scripts/little_loops/runner_spec.py` | Docstring only — reaffirm that the queue bypasses `run_action()` for `LOOP` rather than registering a handler |
| `scripts/tests/` | New tests: loop entry executes; input reaches `fsm.context`; non-loop entries unchanged |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/tests/test_cli_queue_run.py`** is the primary target for new
  LOOP-dispatch tests — it already contains
  `TestQueueRunExitCodeVerdict.test_loop_runner_is_not_dispatched_by_run_action`
  (lines 217-229), the existing regression test guarding the exact contract
  this issue's AC re-asserts ("`run_action()` still raises for
  `RunnerType.LOOP`"). The new `LOOP` branch must intercept in `cmd_run`
  *before* `run_action()` is ever called for `RunnerType.LOOP` entries, so
  this test should keep passing unmodified.
- Existing test structure to model new tests after: an autouse
  `_isolate_cwd` fixture (`monkeypatch.chdir(tmp_path)`) isolates
  `.ll/queue.db` per test; `_add()`/`_add_and_get_id()` helpers wrap
  `main_queue()` via `patch("sys.argv", [...])`; assertions read back state
  via `get_entry(entry_id)`/`list_entries()` from `queue_store.py`, checking
  `entry.status` and `entry.result["exit_code"]`/`["timed_out"]`/`["error"]`.
  For LOOP-branch tests, the mock point shifts from `runner_spec.run_action`
  to whatever function the new branch calls (e.g. `subprocess.run`).
- Other queue/loop test files relevant to this change: `test_queue_store.py`
  (entry schema round-trip — where the new `--input`/loop-input field needs
  coverage), `test_priority_queue.py` (priority ordering, unaffected but
  worth a smoke check), `test_fsm_executor.py` (`PersistentExecutor` itself,
  relevant only if Option A is chosen).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `### ll-queue` section (~lines 2728-2769) documents `add`/`list`/`status`/`remove` flags but has no `run` subcommand entry at all today; needs a new `--input` row in the `add` flags table plus a `run` description/example. [Agent 2 finding]
- `.claude/CLAUDE.md` — the `ll-queue` CLI-tools bullet currently states `run` dispatches through `run_action()` "writing back real status/result (SKILL/CMD/MCP/PROMPT kinds only — RunnerType.LOOP stays on PersistentExecutor)". This clause is stale the moment this issue ships: Option B dispatches LOOP via a subprocess shell-out to `ll-loop run`, not literally `PersistentExecutor` in-process. Needs correcting, and should mention `--input`. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_queue.py` — no existing coverage for the new `--input` flag on `ll-queue add` (parsing, and that it's carried onto the persisted `ActionSpec`/entry). This file already imports `_classify_action, main_queue` and is the natural home for enqueue-side `--input` tests, distinct from `test_cli_queue_run.py`'s dequeue-side coverage. [Agent 3 finding]
- `scripts/tests/test_cli_queue_run.py::TestQueueRunExitCodeVerdict.test_loop_runner_is_not_dispatched_by_run_action` (lines 217-229) — its docstring premise ("LOOP entries stay on PersistentExecutor... guards against a future LOOP handler being wired up without revisiting that verdict") is exactly what this issue changes. The issue's own AC says `run_action()` must still raise for `RunnerType.LOOP` when called directly, so this test should stay as a direct unit test on `runner_spec.run_action` — but a **new**, separate integration test is needed asserting `cmd_run()` no longer reaches `run_action()` for LOOP entries at all (intercepts before it), since today nothing distinguishes "run_action still rejects LOOP in isolation" from "cmd_run still routes LOOP into run_action." [Agent 3 finding]
- `scripts/tests/test_queue_store.py` — if the loop input is persisted as a first-class column rather than folded into `ActionSpec.args["loop_input"]`, `queue_store.py`'s `SCHEMA_VERSION`/`_MIGRATIONS` (currently version 1, one migration entry) needs a new versioned migration entry and a test asserting an already-initialized `.ll/queue.db` upgrades cleanly — `_apply_migrations` only re-runs migrations with index ≥ current version, so an in-place edit to the existing migration string would silently no-op for existing DBs. Folding into `ActionSpec.args` avoids this entirely (the arg is already framed as the Decision Rationale's lower-friction option). [Agent 2 finding]
- No existing test covers the Edge Cases section's "SIGTERM to `ll-queue run` while a loop entry is mid-flight — entry must not be orphaned in `running`" scenario. The closest analog is `ll-loop queue remove`'s PID-verify-then-SIGTERM-then-always-delete-entry pattern (`cli/loop/queue.py:cmd_queue_remove`, tested in `test_cli_loop_queue.py` ~lines 438-491) — a cancel-a-waiter flow, not a mid-flight-crash-recovery flow, so it's a shape to mirror rather than reuse directly. [Agent 3 finding]

## Implementation Steps

1. Add `--input` to the `ll-queue add` parser and carry it onto the persisted
   entry (store + `to_dict()` round-trip).
2. In `cmd_run`, branch on `entry.action.runner is RunnerType.LOOP` and dispatch
   via the chosen path (Option B: subprocess `ll-loop run`).
3. Normalize the loop's outcome into the existing `result_dict` shape so
   `status` derivation at `cli/queue.py:255-259` is untouched.
4. Confirm input coercion happens FSM-side, matching `cli/loop/run.py:161-175`.
5. Tests per the Integration Map; ensure `python -m pytest scripts/tests/`
   exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `--input` parsing/persistence tests to `scripts/tests/test_cli_queue.py`
   (enqueue side), separate from the dequeue-side dispatch tests in
   `test_cli_queue_run.py`.
7. Add a new integration test asserting `cmd_run()` intercepts `RunnerType.LOOP`
   entries before `run_action()` is called, without weakening
   `test_loop_runner_is_not_dispatched_by_run_action`'s direct
   `run_action()`-still-raises unit assertion.
8. If the loop input is persisted as a first-class `queue_store.py` column
   (rather than folded into `ActionSpec.args["loop_input"]`), add a versioned
   entry to `_MIGRATIONS`/bump `SCHEMA_VERSION` and test that an
   already-initialized `.ll/queue.db` upgrades cleanly.
9. Update `docs/reference/CLI.md`'s `### ll-queue` section with a `run`
   subcommand entry and the new `--input` flag on `add`.
10. Correct `.claude/CLAUDE.md`'s `ll-queue` bullet — it currently states LOOP
    entries "stay on PersistentExecutor"; update to describe the subprocess
    shell-out to `ll-loop run` and mention `--input`.

## Acceptance Criteria

- [ ] `ll-queue add <loop>` then `ll-queue run` executes the loop and records a
      terminal status derived from the run, never the
      `"run_action() does not dispatch runner type"` error.
- [ ] `ll-queue add <loop> --input '{"issue_id": "BUG-1"}'` results in the loop
      seeing `issue_id` in `fsm.context` when that key exists in the loop's
      declared context, and the raw string under `fsm.input_key` otherwise —
      identical to `ll-loop run <loop> '{"issue_id": "BUG-1"}'`.
- [ ] A loop declaring `required_inputs` that are not supplied fails the queue
      entry with the loop's own pre-run validation message
      (`cli/loop/run.py:311-315`), not a dispatch error.
- [ ] `SKILL`/`CMD`/`MCP`/`PROMPT` entries continue through `run_action()` with
      no behavior change.
- [ ] `run_action()` still raises for `RunnerType.LOOP` — the module contract at
      `runner_spec.py:12-19` is not weakened.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Edge Cases

- Multiple queued loops in one `ll-queue run` pass — each must get clean
  teardown (the core argument for Option B).
- A queued loop that itself calls `ll-loop run --queue` and loses a lock race,
  creating a `.loops/.queue/<uuid>.json` marker — the two queue mechanisms are
  distinct (FEAT-2684 keeps the marker mechanism as a compat shim) and must not
  be conflated.
- `--runner loop` given explicitly for a target that does not resolve to a
  `.yaml`: `_classify_action`'s override path (`cli/queue.py:56-60`) skips
  `resolve_loop_path` entirely, so the failure surfaces only at dequeue.
- SIGTERM to `ll-queue run` while a loop entry is mid-flight — the entry must
  not be orphaned in `running`.

## Impact

- **Affected**: `ll-queue add`, `ll-queue run`, `queue_store` entry schema.
- **Unaffected**: `ll-loop run`, `ll-loop queue`, `run_action()`'s dispatch
  table, all non-LOOP queue entries.
- **Risk**: Medium — new execution path, but additive and gated on a runner type
  that currently has a 100% failure rate.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` § Orchestration Layers | Boundary between the FSM engine and the queue/parallel substrates |
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | EPIC-2670 design doc; original `ll-queue` shape |
| `docs/reference/API.md` | `runner_spec` / `queue_store` module reference |

## Session Log
- `/ll:confidence-check` - 2026-07-29T01:22:45 - `624479d1-605f-4fe4-baf9-e256169e0545.jsonl`
- `/ll:wire-issue` - 2026-07-29T01:01:42 - `ae1640d4-5ac7-48dc-b9b1-559d5c0f88b3.jsonl`
- `/ll:decide-issue` - 2026-07-29T00:56:11 - `785b5229-efbd-49d2-9614-08d648dcdb90.jsonl`
- `/ll:refine-issue` - 2026-07-29T00:53:34 - `f74aa2ac-43ca-4068-bba2-0296d720a971.jsonl`
- `/ll:capture-issue` - 2026-07-29T00:47:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ae4ce3f-5a2d-4d0f-8368-4b7f0b4c415a.jsonl`

---

## Status

- [x] Captured
- [ ] Refined
- [ ] Ready
- [ ] Implemented
- [ ] Verified
