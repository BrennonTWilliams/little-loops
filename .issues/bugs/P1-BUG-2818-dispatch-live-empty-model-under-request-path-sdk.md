---
id: BUG-2818
type: BUG
priority: P1
status: open
captured_at: "2026-07-25T22:53:35Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, sdk, host-runner, executor]
relates_to: [BUG-2807, FEAT-2716, ENH-2737, ENH-2738, ENH-2197]
---

# BUG-2818: `_dispatch_live` sends empty `model` when `ll-loop run` omits `--model` under `request_path: sdk`

## Summary

`FSMExecutor._dispatch_live` (`scripts/little_loops/fsm/executor.py:2200`) resolves the request
model as `state.model or self.run_model or ""`. When a loop is started without `ll-loop run
--model` and no state declares a `model:` override, `run_model` is `None` and the SDK receives
`model=""`, which the API rejects:

```
Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error',
 'message': 'model: String should have at least 1 character'}, 'request_id': 'req_011CdPZ...'}
```

Now that `orchestration.request_path` is `"sdk"` (ENH-2720/ENH-2738) and BUG-2807 made SDK
dispatch actually reachable, **every prompt/slash_command state in a top-level loop fails
instantly** unless the operator remembers `--model`. This is a total blocker for `ll-loop run`
on the default configuration.

## Current Behavior

`ll-loop run autodev FEAT-2817` (no `--model`), with `.ll/ll-config.json` carrying
`orchestration.request_path: "sdk"`:

- `run.py:577` sets `run_model=getattr(args, "run_model", None) or None` → `None`.
- `_resolve_request_path()` returns `"sdk"` from `orchestration_config.request_path`.
- `_dispatch_live()` computes `model = state.model or self.run_model or ""` → `""`.
- `host_runner.dispatch_anthropic_request(model="")` → HTTP 400, `ActionResult.exit_code = 1`,
  126–474 ms, no output.

Observed live in run `autodev-20260725T171820`: `deposit_options` and `run_decide` both died
this way, the decision gate could never clear, and FEAT-2817 was deferred as
`decision_unresolved` after 13 iterations / 4m41s having done no real work.

Two things make this hard to see:

1. The `ll-loop run` header prints `model: sonnet`, which is `fsm.llm.model` — used for
   *evaluators* (`executor.py:1927,1974`), never for action dispatch. The header actively
   suggests a model is configured when the action path has none.
2. Sub-loop states still work (see BUG-2819), so a loop that delegates to a child loop shows a
   confusing mix of successful and instantly-400ing LLM calls.

The failure also bypasses the ENH-2737 downgrade safety net: that guard covers a missing
`anthropic` package or credential, not an unresolvable model, so there is no fallback to `cli`.

## Expected Behavior

A prompt/slash_command state dispatched via the SDK always sends a non-empty model:

- `_dispatch_live` falls back past `run_model` to `self.fsm.llm.model` (the same model the
  header advertises and evaluators already use), and only then to a hard default.
- If no model can be resolved at all, the run fails loudly at load/startup with an actionable
  message — never by emitting an unsatisfiable request per state.
- `ll-loop run` with no `--model` behaves identically under `request_path: cli` and
  `request_path: sdk`.

## Motivation

`request_path: sdk` is the default (ENH-2738) and is the substrate for the token-cost work under
EPIC-2456. With this defect every unattended `ll-auto` / `ll-loop run` / `ll-sprint` invocation
that reaches a top-level prompt state burns its full iteration budget doing nothing, while
reporting a normal `done` terminal — the loop "completes successfully" having accomplished
nothing. Cost is not the issue; silent total failure of the automation layer is.

## Root Cause

`scripts/little_loops/fsm/executor.py:2200` in `_dispatch_live`:

```python
model = state.model or self.run_model or ""
```

The `or ""` coalesces an unset run-level model into an empty string rather than falling through
to `self.fsm.llm.model`. The docstring at `executor.py:2105` claims the resolution "mirrors
`state.model or self.run_model`" — which is true of the CLI path at `executor.py:1678`, where
passing `model=None` lets the host CLI apply its own default. The SDK path has no such
downstream default, so the same expression that is harmless on the CLI path is fatal here.

The identical expression is used for the `batch` path in the same function, so `request_path:
batch` carries the same defect.

## Error Messages

```
Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error',
 'message': 'model: String should have at least 1 character'}, 'request_id': 'req_011CdPZGwueg8Qt4x2ZTBdKt'}
```

Recorded as `stderr_preview` on the `action_complete` event; `exit_code: 1`, `output_preview: null`.

## Steps to Reproduce

1. Ensure `.ll/ll-config.json` has `orchestration.request_path: "sdk"` and a resolvable
   Anthropic credential.
2. Run any loop with a top-level prompt/slash_command state and **no** `--model` flag:
   `ll-loop run autodev <ISSUE-ID>`
3. Inspect `.loops/.running/<run>.events.jsonl` — the first non-sub-loop prompt state's
   `action_complete` carries `exit_code: 1` and the 400 above.
4. Re-run with `ll-loop run autodev <ISSUE-ID> --model sonnet` — the same state succeeds.

## Environment

- little-loops @ `main` (post-BUG-2807, 2026-07-25)
- `orchestration.request_path: "sdk"`, `orchestration.host_cli: "claude-code"`
- Reproduced in run `.loops/runs/autodev-20260725T171820/`

## Frequency

Deterministic — every top-level prompt/slash_command state, every run, whenever `--model` is
omitted under `request_path: sdk`/`batch`.

## Proposed Solution

In `_dispatch_live`, extend the fallback chain and make the empty case impossible:

```python
model = state.model or self.run_model or self.fsm.llm.model or DEFAULT_MODEL
if not model:
    return ActionResult(output="", stderr="request_path 'sdk' requires a resolvable model ...",
                        exit_code=1, duration_ms=0)
```

Prefer resolving once at executor construction (a `_resolve_action_model()` helper shared by the
CLI, SDK, and batch paths) over repeating the chain, so the CLI and SDK paths cannot drift again.
Consider having `ll-loop run` print the *action* model in its header alongside the evaluator
model, since the current single `model:` line is misleading.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_dispatch_live` (~line 2200, both the `sdk` and
  `batch` branches); optionally a shared `_resolve_action_model()` used by line 1678 too
- `scripts/tests/test_fsm_executor.py` (or the FEAT-2716 dispatch test module) — regression test
- `scripts/little_loops/cli/loop/_helpers.py` — header rendering, if the action model is surfaced

### Tests
- Unit: executor with `run_model=None`, `fsm.llm.model="sonnet"`, `request_path="sdk"` →
  `dispatch_anthropic_request` called with a non-empty model.
- Unit: no model resolvable anywhere → non-zero `ActionResult` with an actionable `stderr`, not a
  400 round-trip.
- Guard the `batch` branch with the same assertions.

## Implementation Steps

1. Add the `fsm.llm.model` fallback (plus hard default) in `_dispatch_live` for both branches.
2. Extract the chain into a shared helper so the CLI path at line 1678 uses the same resolution.
3. Add the two regression tests above, plus a `batch`-path variant.
4. Re-run `ll-loop run autodev <issue>` with no `--model` and confirm the prompt states dispatch.

## Impact

- **Severity**: Critical — silent total failure of all top-level LLM states on the default config.
- **Scope**: Every FSM loop; `ll-auto`, `ll-sprint`, `ll-parallel` all inherit it.
- **Workaround**: pass `--model sonnet` explicitly, or set `orchestration.request_path: "cli"`.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Orchestration Layers — FSM dispatch paths |
| `docs/reference/API.md` | `little_loops.host_runner` — `dispatch_anthropic_request` contract |
| `.claude/CLAUDE.md` § Host CLI Abstraction | host/model resolution rules |

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
