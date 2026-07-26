---
id: BUG-2818
type: BUG
priority: P1
status: done
captured_at: '2026-07-25T22:53:35Z'
completed_at: '2026-07-26T03:46:33Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- sdk
- host-runner
- executor
relates_to:
- BUG-2807
- FEAT-2716
- ENH-2737
- ENH-2738
- ENH-2197
learning_tests_required:
- anthropic
confidence_score: 96
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 24
score_ambiguity: 25
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- A ready-made non-empty default already exists: `DEFAULT_LLM_MODEL: str = "sonnet"`
  (`scripts/little_loops/fsm/schema.py:23`), used by `LLMConfig.model` (`schema.py:881`) so
  `self.fsm.llm.model` is *always* populated (never `None`/`""`) — the Proposed Solution's
  `DEFAULT_MODEL` should reuse this constant rather than introducing a new one.
- `host_runner.dispatch_anthropic_request` (`host_runner.py:1519-1576`) and
  `dispatch_batch_request` (`host_runner.py:1579-1599`) do **not** validate `model` themselves —
  both forward it verbatim into `client.messages.create(**request)`. An empty string is only ever
  caught downstream as a generic `anthropic.APIError`, which is why the failure currently surfaces
  as an opaque 400 instead of a clear local error.
- `_dispatch_live`'s own `batch` branch already has a precedent for the "hard requirement, no safe
  fallback" early-return shape the Proposed Solution recommends — the `run_dir` guard at
  `executor.py:2216-2221`: `return ActionResult(output="", stderr="request_path 'batch' requires a
  run_dir context value", exit_code=1, duration_ms=0)`. The batch-submission `except Exception`
  handler at `executor.py:2238-2240` also already converts `dispatch_batch_request` failures into a
  routed `ActionResult` — only the `sdk` branch has no local `try/except` around its dispatch call
  at all.
- `_resolve_request_path` / `_warn_request_path_downgrade` (`executor.py:2102-2181`, immediately
  above `_dispatch_live`) is the closest existing "state override → run-level fallback → hard
  default, with one-shot logging" pattern in this file, and its own docstring
  (`executor.py:2105-2106`) already cross-references `state.model or self.run_model` — making it
  the natural sibling location for the proposed shared `_resolve_action_model()` helper.
- The CLI path's harmlessness is structural, not incidental: `executor.py:1678` passes `model=None`
  (no `or ""` terminator) into `ActionRunner.run()`, and the host-CLI runners
  (`scripts/little_loops/fsm/runners.py`, `model: str | None = None` params) simply omit any
  `--model` flag when `None`, letting the host CLI binary apply its own default. The SDK/batch API
  call has no such downstream default — a concrete non-empty string is a hard requirement.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Use `DEFAULT_LLM_MODEL` from `scripts/little_loops/fsm/schema.py:23` (`"sonnet"`) as the hard
  default in the fallback chain — it is already the codebase's single canonical "default model
  string" constant (imported via `scripts/little_loops/fsm/__init__.py:136,184`), and
  `evaluators.py:1967` already uses the identical `model=model or DEFAULT_LLM_MODEL` shape as
  precedent.
- The header's current `model:` line is sourced from `run.py:600` (`model=fsm.llm.model`), rendered
  by `_render_artifact_header_lines` in `scripts/little_loops/cli/loop/_helpers.py:1292-1326`
  (line 1322/1325 prints it) — this is the exact call site to extend if the action model is
  surfaced separately.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_dispatch_live` (~line 2200, both the `sdk` and
  `batch` branches); optionally a shared `_resolve_action_model()` used by line 1678 too
- `scripts/tests/test_fsm_executor.py` (or the FEAT-2716 dispatch test module) — regression test
- `scripts/little_loops/cli/loop/_helpers.py` — header rendering, if the action model is surfaced

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:577` — `run_model=getattr(args, "run_model", None) or None`,
  the origin of `self.run_model` being `None` when `--model` is omitted; the new fallback chain
  must treat this as an expected, legitimate input, not an error condition [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/run.py:600` — `model=fsm.llm.model` passed into
  `_render_artifact_header_lines` for the `ll-loop run` header; the exact value the Proposed
  Solution recommends reusing as the SDK-path fallback, and the call site to extend with a second
  `action_model=` argument if the header is changed to show the action-dispatch model separately
  [Agent 1/2 finding]

### Tests
- Unit: executor with `run_model=None`, `fsm.llm.model="sonnet"`, `request_path="sdk"` →
  `dispatch_anthropic_request` called with a non-empty model.
- Unit: no model resolvable anywhere → non-zero `ActionResult` with an actionable `stderr`, not a
  400 round-trip.
- Guard the `batch` branch with the same assertions.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` `TestRequestPathDispatchWiring` (line 9511) — none of the
  four existing tests in this class (`test_request_path_sdk_calls_dispatch_not_cli`,
  `test_state_level_request_path_overrides_orchestration_default`,
  `test_request_path_cli_default_unaffected`, `test_request_path_batch_submits_polls_and_clears_tracker`)
  inspect the `model=` kwarg on the mocked `dispatch_anthropic_request`/`dispatch_batch_request`
  call — add that assertion to the sdk and batch tests rather than only adding new tests
  [Agent 3 finding]
- `scripts/tests/test_host_runner_dispatch.py` `TestDispatchAnthropicRequest` (line 48) — every
  existing test supplies an explicit non-empty `model=` kwarg; none exercise `model=""`. Not
  required to change if the guard stays in `_dispatch_live` (upstream of these functions), but
  add an empty-model case here instead if the fix is implemented as validation inside
  `dispatch_anthropic_request`/`dispatch_batch_request` [Agent 2/3 finding]
- `scripts/tests/test_batch_request_path.py` — batch dispatch tests; mirror the same model-kwarg
  assertion for the `batch` branch fix [Agent 1 finding]
- No test currently exercises `_dispatch_live`'s existing `run_dir` guard (`executor.py:2214-2221`)
  missing-`run_dir` failure branch, the closest in-function precedent for the new model guard's
  shape — worth adding alongside the new tests since the pattern being copied is itself untested
  on its failure path [Agent 3 finding]
- If the header is extended to show the action-dispatch model, `_render_artifact_header_lines`
  (`_helpers.py:1292`) has no dedicated existing test — `scripts/tests/test_cli_loop_layout.py`
  only has one incidental `"model": None` reference (line 138); this would be a new test, not an
  update [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `little_loops.host_runner` (~lines 8860-8871) — documents
  `_resolve_request_path()`/`_dispatch_live()` as "the sole production call sites" and the
  ENH-2737 downgrade behavior, but says nothing about model resolution/fallback; natural place to
  add the new `state.model → run_model → fsm.llm.model → DEFAULT_LLM_MODEL → hard-fail` chain
  [Agent 2 finding]
- `docs/ARCHITECTURE.md` § "SDK/Batches Dispatch Path (`orchestration.request_path`)" (~line 883)
  — documents `_resolve_request_path` selection logic and the ENH-2737 downgrade but is silent on
  model resolution; same gap as API.md [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` § `orchestration` (~lines 1161-1197) — documents
  `request_path` including the downgrade-to-cli safety net in detail, but never mentions that
  model resolution becomes load-bearing under `"sdk"`/`"batch"` in a way it structurally isn't
  under `"cli"`; the natural place a user configuring `request_path: "sdk"` would look for this
  requirement [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Model regression tests after `TestRequestPathDispatchWiring` in
  `scripts/tests/test_fsm_executor.py:9511`. `test_request_path_sdk_calls_dispatch_not_cli`
  (`test_fsm_executor.py:9529-9560`) is the closest existing fixture — it already patches
  `little_loops.host_runner.dispatch_anthropic_request` and constructs a minimal SDK-mode
  `FSMExecutor` via the `self._sdk_fsm()` helper (`test_fsm_executor.py:9514-9527`). **None of the
  existing tests in this class assert on the `model=` kwarg value passed to the mocked dispatch
  call** — that assertion (`mock_dispatch.call_args.kwargs["model"]` is non-empty when
  `run_model`/`state.model` are both unset) is the new coverage this issue needs.
- Sibling tests to model the `cli`-path-unaffected assertion after:
  `test_request_path_cli_default_unaffected` (`test_fsm_executor.py:9606-9625`).
- `dispatch_batch_request` tests live in `scripts/tests/test_host_runner_dispatch.py:48-87`
  (`TestDispatchAnthropicRequest`); mirror for a batch-path model-kwarg assertion.

## Implementation Steps

1. Add the `fsm.llm.model` fallback (plus hard default) in `_dispatch_live` for both branches.
2. Extract the chain into a shared helper so the CLI path at line 1678 uses the same resolution.
3. Add the two regression tests above, plus a `batch`-path variant.
4. Re-run `ll-loop run autodev <issue>` with no `--model` and confirm the prompt states dispatch.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add the missing `model=` kwarg assertions to the four existing
   `TestRequestPathDispatchWiring` tests in `test_fsm_executor.py` (not just new tests) and mirror
   the batch-path assertion in `test_batch_request_path.py`.
6. If the header is extended to surface the action-dispatch model, update `run.py:600`'s call into
   `_render_artifact_header_lines` and add a new dedicated test (none exists today).
7. Update `docs/reference/API.md` § `little_loops.host_runner`, `docs/ARCHITECTURE.md` § SDK/Batches
   Dispatch Path, and `docs/reference/CONFIGURATION.md` § `orchestration` to document the model
   resolution requirement under `request_path: "sdk"`/`"batch"`.

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

## Resolution

Added `FSMExecutor._resolve_action_model()` (`scripts/little_loops/fsm/executor.py`), which
resolves `state.model or self.run_model or self.fsm.llm.model` — `fsm.llm.model` is never empty
since `LLMConfig.model` defaults to `DEFAULT_LLM_MODEL` ("sonnet"), so the empty-string case is
now structurally unreachable and no separate hard-fail branch is needed. `_dispatch_live`'s `sdk`
and `batch` branches both call the new helper instead of the old `state.model or self.run_model or
""` expression. Added model-kwarg assertions to all four `TestRequestPathDispatchWiring` tests
plus the batch-submit test in `test_fsm_executor.py`. Full suite: 16311 passed, 38 skipped.

## Session Log
- `/ll:manage-issue` - 2026-07-26T03:45:59Z - `8e7d2c8e-89fd-4b78-a923-3530d55d8695.jsonl`
- `/ll:ready-issue` - 2026-07-26T03:37:03 - `b5d7bc4f-0d45-436a-8c76-0fb0a5d1b34f.jsonl`
- `/ll:wire-issue` - 2026-07-26T03:34:52 - `13b6e0b1-6b88-4666-9247-671dec60b882.jsonl`
- `/ll:refine-issue` - 2026-07-26T03:29:53 - `c6a7ac3b-9ddd-40a8-abc5-8bd6e0dd640b.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:53:35Z - `ae9c212c-ff4e-4576-a5c4-7457be6284e5.jsonl`

---

## Status

open
