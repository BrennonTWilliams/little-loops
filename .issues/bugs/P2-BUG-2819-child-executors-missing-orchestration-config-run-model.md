---
id: BUG-2819
type: BUG
priority: P2
status: open
captured_at: "2026-07-25T22:53:35Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, sdk, executor, sub-loops]
relates_to: [BUG-2818, FEAT-2716, ENH-2714, ENH-2073, ENH-2197]
blocked_by: [BUG-2818]
---

# BUG-2819: Child FSM executors are not threaded with `orchestration_config` / `run_model`

## Summary

`FSMExecutor._run_subloop` constructs the child executor at
`scripts/little_loops/fsm/executor.py:977` without passing `orchestration_config` or
`run_model`. Both silently default: `run_model` becomes `None`, and
`_resolve_request_path()` hits its "no `orchestration_config` → `cli`" branch
(`executor.py:2122-2125`). A project configured for `request_path: "sdk"` therefore dispatches
parent states via the SDK and child states via the host CLI, and an `ll-loop run --model X` flag
applies to the parent's states but not to any sub-loop's.

## Current Behavior

Config in `.ll/ll-config.json` sets `orchestration.request_path: "sdk"`. Running
`ll-loop run autodev FEAT-2817`:

- Parent state `deposit_options` (`/ll:refine-issue --auto`) → `_dispatch_live` → SDK.
- Child state `refine_issue` in the delegated `refine-to-ready-issue` sub-loop — a
  byte-for-byte equivalent `/ll:refine-issue ${...} --auto` with the same
  `pruning_profile` shape — → `action_runner.run(...)` → host CLI.

The two states are indistinguishable in YAML, sit one `loop:` boundary apart, and take entirely
different execution paths. In run `autodev-20260725T171820` this manifested as the child refine
succeeding (2609 output tokens, `model: claude-sonnet-5` recorded in `usage.jsonl`) while both
parent-level slash commands 400'd instantly — see BUG-2818 for that failure. This asymmetry is
what made BUG-2818 hard to diagnose: the run *looked* like a partial LLM outage rather than a
config resolution defect.

Divergence is not limited to `request_path`:

- **`run_model`**: `--model` never reaches sub-loop states.
- **`compression_config`**, **`orchestration_config`**-derived behavior, and any future
  executor-level config are likewise dropped (the child gets only `action_runner`, `loops_dir`,
  `event_callback`, `circuit`, `working_dir`).
- Because the child resolves to `cli`, it *does* honor `pruning_profile` and `tools`
  (`executor.py:1662-1678`), which the SDK path ignores entirely — so pruning and tool
  allowlists apply on one side of the boundary and not the other.

MR-12 Check 3 and ENH-2810 reason about `orchestration.request_path` as a project-wide default;
that assumption is false for every state inside a sub-loop.

## Expected Behavior

A sub-loop state executes under the same orchestration contract as an equivalent parent state:

- `orchestration_config`, `run_model`, and `compression_config` propagate to child executors
  (as `_depth` and `circuit` already do at `executor.py:985`).
- A state-level `request_path:` override in the child's own YAML still wins.
- `ll-loop run --model X` applies uniformly across loop boundaries.

## Motivation

Sub-loop delegation is the primary composition mechanism in this codebase — `autodev` alone
delegates to `refine-to-ready-issue`, and the `oracles/` family is delegated into by six wrapper
loops. If half the runtime configuration stops at the `loop:` boundary, then cost controls
(`request_path`, `pruning_profile`), model pinning, and compression are all quietly
partial. Any measurement of SDK-vs-CLI parity or token savings taken on a delegating loop is
measuring a mixture, not the configured path.

## Root Cause

`scripts/little_loops/fsm/executor.py:977-984`:

```python
child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,
    loops_dir=self.loops_dir,
    event_callback=_sub_event_callback,
    circuit=self._circuit,
    working_dir=child_working_dir,
)
child_executor._depth = depth  # propagate depth for further nesting
```

`orchestration_config` (param at `executor.py:188`) and `run_model` (param at
`executor.py:185`) are simply absent from the call. `_resolve_request_path`'s docstring
(`executor.py:2107-2108`) already anticipates this — *"No `orchestration_config` (the default for
executors not threaded with one) resolves to `cli`"* — but treats it as a compatibility default
rather than a gap to close, and nothing flags the sub-loop case.

## Steps to Reproduce

1. Set `orchestration.request_path: "sdk"` in `.ll/ll-config.json`.
2. Run a loop that delegates via `loop:` to a sub-loop containing a prompt state, e.g.
   `ll-loop run autodev <ISSUE-ID>`.
3. In `.loops/.running/<run>.events.jsonl`, compare a parent prompt state's `action_complete`
   with a child prompt state's: the child shows host-CLI behavior (`session_jsonl`, usage events
   with a resolved model), the parent shows SDK dispatch.
4. Add `--model haiku` and confirm the child's recorded model is unchanged.

## Environment

- little-loops @ `main`, 2026-07-25
- `orchestration.request_path: "sdk"`
- Observed in run `.loops/runs/autodev-20260725T171820/`

## Frequency

Deterministic — every `loop:`-delegated state, every run.

## Proposed Solution

Thread the missing config through the child constructor:

```python
child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,
    loops_dir=self.loops_dir,
    event_callback=_sub_event_callback,
    circuit=self._circuit,
    working_dir=child_working_dir,
    orchestration_config=self.orchestration_config,
    run_model=self.run_model,
    compression_config=self.compression_config,
)
```

Audit the full `FSMExecutor.__init__` signature for any other run-scoped parameter that should
propagate, and add a test that fails when a new one is added without propagation (e.g. compare
the child's resolved attributes against an explicit allowlist of intentionally non-inherited
params). Note this change makes BUG-2818 strictly worse until BUG-2818 is fixed — child states
would then also dispatch with an empty model — so land BUG-2818 first.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_run_subloop` child construction (~line 977)
- `scripts/tests/test_fsm_subloop.py` / the sub-loop test module — propagation assertions

### Tests
- Parent with `orchestration_config.request_path="sdk"` → child `_resolve_request_path()` returns
  `"sdk"` for a state with no override.
- Parent with `run_model="haiku"` → child prompt state dispatches with `haiku`.
- Child state with an explicit `request_path: cli` override still resolves to `cli`.
- Signature-drift guard: every `FSMExecutor.__init__` run-scoped param is either propagated or
  named in an explicit non-inherited allowlist.

## Implementation Steps

1. Land BUG-2818 first (empty-model fallback), otherwise propagation broadens the 400.
2. Pass `orchestration_config`, `run_model`, `compression_config` to the child executor.
3. Add the four tests above.
4. Re-run a delegating loop and confirm parent and child states take the same dispatch path.
5. Revisit ENH-2810 / MR-12 Check 3 — its config-default exemption becomes accurate for sub-loop
   states only after this fix.

## Impact

- **Severity**: High — runtime configuration is silently half-applied across loop boundaries.
- **Scope**: All delegating loops (`autodev`, the six `oracles/` wrappers, `rn-*` family).
- **Cost/measurement**: SDK-vs-CLI and pruning parity numbers taken on delegating loops are
  measuring a mixture of both paths.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` § Orchestration Layers | sub-loop delegation model |
| `docs/reference/API.md` | `FSMExecutor` constructor contract |
| `.claude/CLAUDE.md` § Loop Authoring | MR-12 / `pruning_profile` resolution |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:33 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
