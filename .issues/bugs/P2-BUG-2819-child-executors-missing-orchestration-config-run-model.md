---
id: BUG-2819
type: BUG
priority: P2
status: done
captured_at: '2026-07-25T22:53:35Z'
completed_at: '2026-07-26T05:54:31Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- sdk
- executor
- sub-loops
relates_to:
- BUG-2818
- FEAT-2716
- ENH-2714
- ENH-2073
- ENH-2197
blocked_by: []
confidence_score: 100
outcome_confidence: 91
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 24
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Method name correction**: the code path is `FSMExecutor._execute_sub_loop`
  (`executor.py:801`), not `_run_subloop` as this issue's prose names it. The line numbers cited
  throughout this issue (977-984 for the construction call, 985 for `_depth`) are accurate against
  `_execute_sub_loop` — only the method name in prose is stale.
- **The constructor's own docstring already claims propagation that the code doesn't perform**:
  `FSMExecutor.__init__`'s docstring for `run_model` (`executor.py:200-201`) states *"Inherited by
  nested sub-loop executors"* — but the `_execute_sub_loop` call site never passes
  `run_model=self.run_model`, so the docstring is currently false. Fixing the call site makes the
  docstring accurate rather than adding new documented behavior.
- **Two more run-scoped params silently drop at the same call site, not named in this issue's
  Proposed Solution**: `signal_detector` and `handoff_handler` (both accepted by
  `FSMExecutor.__init__` at `executor.py:180-181`) are likewise absent from the `_execute_sub_loop`
  construction call — children get `None` for both. These aren't mentioned in the original bug
  report; the audit step in Proposed Solution should confirm whether they need the same treatment
  or belong on the intentionally-non-inherited allowlist (unlike `orchestration_config`/`run_model`
  /`compression_config`, no docstring or existing behavior currently claims inheritance for these
  two, so they may be legitimately exempt — worth an explicit decision either way).
- **Why `pruning_profile`/`tools` already work across the boundary despite not being constructor
  params**: `_run_action` resolves `pruning_profile` as `state.pruning_profile or
  self.fsm.pruning_profile` (`executor.py:1663`) and `tools` directly from `state.tools`
  (`executor.py:1677`) — both read from `self.fsm`/`state`, i.e. the *child's own loaded FSM and
  state config*, not from anything threaded through `FSMExecutor.__init__`. Since
  `_execute_sub_loop` always loads a fresh `child_fsm` via `load_and_validate` (`executor.py:841`),
  these two resolve correctly per-executor with no propagation fix needed — confirming they are a
  structurally different mechanism from `orchestration_config`/`run_model`/`compression_config`,
  which are executor-instance fields with no path to the child other than the constructor call.
- **BUG-2818 (the stated blocker) is done**: `.issues/bugs/P1-BUG-2818-*.md` frontmatter shows
  `status: done`, `completed_at: '2026-07-26T03:46:33Z'`. `_resolve_action_model`
  (`executor.py:2184`) now resolves `state.model or self.run_model or self.fsm.llm.model`, never
  emitting an empty model string. `blocked_by` has been cleared in this issue's frontmatter — the
  propagation fix can land without broadening BUG-2818's failure mode.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing manual-mirroring propagation test to extend**:
  `TestSubLoopExecution.test_sub_loop_inherits_parent_circuit`
  (`scripts/tests/test_fsm_executor.py:7365-7384`) hand-constructs a child `FSMExecutor` that
  "mirror[s] the argument list used in `_execute_sub_loop`" (comment at the call site) and asserts
  `child._circuit is parent._circuit`. The same shape extends directly to `run_model` /
  `orchestration_config` / `compression_config` identity/equality assertions.
- **Existing end-to-end sub-loop test to extend for real dispatch-path assertions**:
  `TestSubLoopExecution.test_sub_loop_depth_propagates_to_nested_sub_loops`
  (`scripts/tests/test_fsm_executor.py:5858-5887`) writes real on-disk parent/child/grandchild loop
  YAML under `tmp_path/.loops` and runs the full parent via `.run()`, asserting on emitted event
  metadata rather than internal attributes — the template for a true `loop:`-delegation test rather
  than direct child construction.
- **Existing `request_path`/`model` dispatch-kwarg assertion pattern (BUG-2818's own regression
  tests) — the closest ready-made template**: `TestRequestPathDispatchWiring`
  (`scripts/tests/test_fsm_executor.py:9567`), e.g. `test_request_path_sdk_calls_dispatch_not_cli`
  (line 9585) constructs `FSMExecutor(fsm, orchestration_config=OrchestrationConfig(request_path=
  "sdk"))`, patches `little_loops.host_runner.dispatch_anthropic_request`, calls `.run()`, and
  asserts `mock_dispatch.call_args.kwargs["model"]`. The four tests this issue's Integration Map
  requires should nest a minimal `ask`-shaped child loop under a `loop:` state and reuse this exact
  patch-and-assert shape from inside the child's execution, rather than inventing a new pattern.
- **No existing signature-drift-guard pattern in this repo**: searched for
  `inspect.signature`/`inspect.getfullargspec`/`__code__.co_varnames` usage against a class
  `__init__` — none found. The closest analog (`test_verify_cli_allowlist.py`) cross-checks a
  static config allowlist against `pyproject.toml` entry points, a different mechanism. The
  signature-drift guard this issue proposes is new-pattern work; base it on
  `inspect.signature(FSMExecutor.__init__)` enumerated against an explicit propagated/exempt
  allowlist, generalizing the "mirror the argument list" comment convention from
  `test_sub_loop_inherits_parent_circuit` above.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` child construction (`executor.py:977-984`, method defined at `executor.py:801`)
- `scripts/tests/test_fsm_executor.py` — propagation assertions; existing sub-loop coverage lives
  in `TestSubLoopExecution` (`test_fsm_executor.py:5470+`) and dispatch-kwarg coverage in
  `TestRequestPathDispatchWiring` (`test_fsm_executor.py:9567+`) — no separate `test_fsm_subloop.py`
  module exists in this codebase, all sub-loop tests live in `test_fsm_executor.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **CLI-to-executor threading, for context on the top-level pattern being extended to children**:
  `scripts/little_loops/cli/loop/run.py:571-580` passes `run_model`, `compression_config`, and
  `orchestration_config` from resolved project config into `PersistentExecutor`, which forwards
  `**executor_kwargs` to `FSMExecutor.__init__` (`scripts/little_loops/fsm/persistence.py:678-720`).
  This is the parent-level threading already working correctly; the bug is specifically that
  `_execute_sub_loop`'s child construction doesn't repeat this same forwarding one level down.
- **`OrchestrationConfig` dataclass location**: `scripts/little_loops/config/orchestration.py:63-103`
  (fields: `host_cli`, `request_path`, `composer`, `cluster`).

### Tests
- Parent with `orchestration_config.request_path="sdk"` → child `_resolve_request_path()` returns
  `"sdk"` for a state with no override.
- Parent with `run_model="haiku"` → child prompt state dispatches with `haiku`.
- Child state with an explicit `request_path: cli` override still resolves to `cli`.
- Signature-drift guard: every `FSMExecutor.__init__` run-scoped param is either propagated or
  named in an explicit non-inherited allowlist.

### Wiring Pass Findings

_Wiring pass added by `/ll:wire-issue`:_

- **No existing test exercises this gap end-to-end.** `TestRequestPathDispatchWiring`
  (`test_fsm_executor.py:9567+`) only builds flat (non-sub-loop) FSMs — none combine
  `orchestration_config`/`run_model` with a `loop:` state. `TestSubLoopExecution::test_sub_loop_inherits_parent_circuit`
  (`test_fsm_executor.py:7365-7384`) hand-mirrors the `_execute_sub_loop` constructor call rather
  than exercising the real method, so it gives no coverage of the fix and can silently drift out of
  sync with `executor.py:977-984` after this change — worth noting so the new tests call the real
  `_execute_sub_loop` path (via `.run()` on a parent with a `loop:` state) rather than adding a
  second hand-mirrored copy.
- **Docstring inconsistency to fix alongside the code change**: `FSMExecutor.__init__`'s docstring
  for `working_dir` (`executor.py:202-206`) already states *"Inherited by nested sub-loop
  executors..."*, but the `run_model` (`executor.py:200-201`), `compression_config`
  (`executor.py:207-211`), and `orchestration_config` (`executor.py:212-217`) docstrings are silent
  on sub-loop inheritance. Once the fix threads these three through, update their docstrings to
  match `working_dir`'s existing "Inherited by nested sub-loop executors" language for consistency.
- **Related but explicitly out-of-scope sibling gap (FYI only, no action required by this issue)**:
  `scripts/little_loops/cli/loop/testing.py:261-266` (`ll-loop simulate`'s `FSMExecutor(...)`
  construction) also omits `orchestration_config`, `run_model`, and `compression_config` — but this
  is a separate top-level construction, not a parent→child `_execute_sub_loop` call, so it is out of
  this issue's stated scope.
- **New behavioral surface post-fix**: once a child executor can have a non-`None`
  `orchestration_config`, it becomes newly eligible to emit the `request_path_downgrade` event
  (`docs/reference/API.md:8871-8882`, ENH-2737) from within a sub-loop, which it could never do
  before (nothing to downgrade from). No existing test asserts on the absence of this event from
  sub-loop runs, but anything asserting exact event-stream equality on a delegating loop should
  account for this.
- Confirmed no config-schema.json / `docs/reference/CONFIGURATION.md` changes are needed — the
  propagation gap is purely in Python object construction (`_execute_sub_loop`), not in config
  authoring or schema validation; `docs/reference/API.md` and `docs/ARCHITECTURE.md`'s existing
  descriptions of `orchestration_config` already read as project-wide and require no textual
  correction — they become accurate rather than needing a caveat removed.

## Implementation Steps

1. ~~Land BUG-2818 first (empty-model fallback), otherwise propagation broadens the 400.~~ Done —
   BUG-2818 landed 2026-07-26T03:46:33Z (`status: done`); `blocked_by` cleared in this issue's
   frontmatter.
2. Pass `orchestration_config`, `run_model`, `compression_config` to the child executor. Update the
   three params' `__init__` docstrings to match `working_dir`'s existing "Inherited by nested
   sub-loop executors" language (see Wiring Pass Findings).
3. Add the four tests above via the real `_execute_sub_loop` path (a parent `.run()` with a `loop:`
   state), not a hand-mirrored constructor call, per the Wiring Pass Findings note on
   `test_sub_loop_inherits_parent_circuit`.
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

## Resolution

Threaded `orchestration_config`, `run_model`, and `compression_config` into the
`_execute_sub_loop` child `FSMExecutor(...)` construction
(`executor.py:977-986`), matching the existing `working_dir`/`circuit`/`_depth`
propagation. Updated the three params' constructor docstrings to state
"Inherited by nested sub-loop executors" for consistency with `working_dir`'s
existing language. Added four tests to `TestRateLimitCircuitIntegration` in
`test_fsm_executor.py`: request_path inheritance through a real `loop:`
delegation, `run_model` inheritance, state-level `request_path` override still
winning, and an AST-based signature-drift guard that fails if a future
run-scoped `FSMExecutor.__init__` param is added without an explicit
propagate/exempt decision.

## Session Log
- `/ll:manage-issue` - 2026-07-26T05:54:02 - `90b87ebc-d7e6-4d37-94c2-91f39a9a4edb.jsonl`
- `/ll:wire-issue` - 2026-07-26T05:46:45 - `6997caf1-1731-41bf-b4f7-a9923b77bd58.jsonl`
- `/ll:refine-issue` - 2026-07-26T05:40:06 - `4dc7c363-1948-440a-b979-f08b345e3374.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:33 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
