---
id: BUG-2757
title: refine-issue/ready-issue model log shows requested alias, not resolved model
  ID
type: bug
priority: P3
status: done
captured_at: '2026-07-24T00:00:00Z'
completed_at: '2026-07-24T18:50:27Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
labels:
- fsm
- telemetry
- host-runner
confidence_score: 100
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 23
---

# BUG-2757: refine-issue/ready-issue model log shows requested alias, not resolved model ID

## Summary

`process_issue_inplace` callers (the `refine-issue`/`ready-issue` code path in
`issue_manager.py`) log the model as the short alias requested on the CLI
invocation (e.g. `sonnet`) instead of the model the host CLI actually resolved
to and ran (e.g. `claude-sonnet-5`). Meanwhile `autodev.yaml` (via the FSM
executor) logs/records the correctly resolved full model ID for the same kind
of invocation. This is the same class of problem BUG-1897 fixed for FSM loop
`TokenUsage`, but a second, still-unfixed callback in `issue_manager.py` reads
from a different (unresolved) stream-json event.

## Current Behavior

- `scripts/little_loops/issue_manager.py:1426-1431` registers an `on_model`
  callback that logs `f"model: {m}"` using whatever value is passed to it.
- That callback is wired as `on_model_detected` into
  `subprocess_utils.py:467-474`, which fires from the CLI's `system`/`init`
  stream-json event:
  ```python
  if etype == "system" and event.get("subtype") == "init":
      if "model" in event:
          detected_model = event["model"]
          if on_model_detected:
              on_model_detected(event["model"])
  ```
  The `init` event's `model` field echoes back the **requested alias**
  (`"sonnet"`, from `fsm/schema.py:23`'s `DEFAULT_LLM_MODEL = "sonnet"`, or the
  hardcoded `model="sonnet"` passed directly in
  `cli/issues/decisions.py:797`), not the model actually negotiated.
- By contrast, `fsm/executor.py:1692` reads `result.usage_events[-1].model`,
  which is populated in `subprocess_utils.py:509` from the CLI's **`result`**
  event (`event.get("model", detected_model)`). The `result` event's `model`
  field contains the **resolved** model ID the CLI actually ran
  (`claude-sonnet-5`), which is why autodev-driven loops display the correct
  name.

## Expected Behavior

`ready-issue`/`refine-issue` (and any other caller of
`process_issue_inplace`'s `on_model_detected`) should log/report the same
resolved model ID autodev shows, not the raw alias that was requested.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `on_model` callback inside `_process_issue` (or the analogous
  callback in `process_issue_inplace`), line ~1431
- **Cause**: The callback is wired to `on_model_detected`, which fires from
  the `system`/`init` stream-json event
  (`subprocess_utils.py:467-474`) carrying the unresolved request alias,
  whereas the FSM executor's model display reads the `result` event's `model`
  field (`subprocess_utils.py:509`, consumed at `fsm/executor.py:1692`), which
  the CLI populates with the resolved model ID. Two different event types are
  used as the source of truth for "current model" in these two code paths.

## Proposed Solution

Have the `refine-issue`/`ready-issue` model-logging path prefer the resolved
model the same way the FSM executor does:

- Add (or reuse) an `on_usage_detailed`-style callback in
  `issue_manager.py`'s `process_issue_inplace` call and log/store
  `usage.model` (from the `result` event) instead of/in addition to the
  `on_model_detected` alias, mirroring `fsm/executor.py:1692`.
- Alternatively, centralize alias→resolved-ID normalization in
  `host_runner.py` so any caller passing a short alias gets the resolved ID
  back consistently, rather than each call site picking a different
  stream-json event to trust.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed the first alternative (mirror the FSM executor) is the correct
  approach; there is **no** existing alias→resolved-ID normalization utility
  anywhere in `host_runner.py` (no `resolve_model`/`normalize_model`/alias
  map) — resolution only happens inside the host CLI process itself and is
  observable in-process solely by reading the `result` stream-json event, so
  the "centralize in host_runner.py" alternative has no existing hook to
  build on and would require inventing new host-process introspection.
  `subprocess_utils.py`'s per-invocation `detected_model` closure variable
  (declared before the event loop) is the only place this resolution is
  currently surfaced.
- The exact fix shape to mirror is `fsm/runners.py:160-188`'s
  `DefaultActionRunner.run()`, which always wires a `_collect_usage` closure
  as `on_usage_detailed=_collect_usage` into `run_claude_command()`:
  ```python
  collected_usage: list[TokenUsage] = []

  def _collect_usage(u: TokenUsage) -> None:
      collected_usage.append(u)
      if on_usage_detailed:
          on_usage_detailed(u)
  ```
  `issue_manager.py` currently wires **no** `on_usage_detailed` callback
  anywhere — grep confirms the parameter appears only in `fsm/executor.py`,
  `fsm/runners.py`, and `subprocess_utils.py`.
- Confirmed `cli/loop/info.py:1540` and `cli/issues/decisions.py:797`
  (flagged in Current Behavior/Impact as related alias references) are
  **not** part of the actual bug surface: `info.py:1540`
  (`if llm.model != "sonnet":`) compares the FSM YAML's *configured* model
  against the schema default for display formatting — a static config
  comparison, not a subprocess model-detection read. `decisions.py:797`
  (`model="sonnet"` in `build_blocking_json(...)`) sets the *requested*
  model for a one-shot call with no subsequent resolved-model logging to
  fix. Neither needs to change for this bug.
- `self._detected_model: list[str] = []` (`issue_manager.py:1191`) and the
  `on_model` closure (`issue_manager.py:1426-1434`) only populate once per
  `AutoManager` lifetime (`if not self._detected_model:` guard) — the fix
  should follow the same once-populated pattern when switching to
  `on_usage_detailed`, since `self._detected_model[0]` also feeds
  `context_window_for()`'s context-limit sizing.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_manager.py:565-850` (`process_issue_inplace()`)
  — currently threads `on_model_detected` straight through to every
  `run_claude_command()` call inside it (lines ~627-635, ~683-691, ~850) but
  never wires `on_usage_detailed`. Add an `on_usage_detailed` parameter and
  forward it the same way.
- `scripts/little_loops/issue_manager.py:1410-1446` (`AutoManager._process_issue()`)
  — replace/augment the alias-only `on_model` closure with a
  `_collect_usage`-style closure (mirroring `fsm/runners.py:160-165`) that
  captures `TokenUsage.model` (the resolved ID) via `on_usage_detailed`, and
  update `self.logger.info(f"model: {m}")` / `self._detected_model` to
  prefer that resolved value.

### Reference Implementation (Already Correct — Pattern to Mirror)

- `scripts/little_loops/fsm/runners.py:160-188` — `DefaultActionRunner.run()`'s
  `_collect_usage` closure, always wired as `on_usage_detailed`.
- `scripts/little_loops/fsm/executor.py:1686-1704` — `FSMExecutor._run_action()`
  reads `result.usage_events[-1].model` for the resolved ID.
- `scripts/little_loops/subprocess_utils.py:407,467-474,490-511` — the
  `detected_model` closure variable and the `system`/`init` vs `result`
  event dispatch that produces the resolved value (the BUG-1897 fix
  pattern).

### Callers That Benefit Automatically (No Changes Needed)

- Any other `process_issue_inplace()` caller — gains the corrected model
  once `on_usage_detailed` is threaded through, without further call-site
  changes.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py:71,783` — the only other production
  caller of `process_issue_inplace()`
  (`_run_issue_with_wall_clock_timeout()` and `_cmd_sprint_run()`'s
  sequential retry branch). Neither call site passes
  `on_model_detected`/`on_usage_detailed` today, so both benefit
  automatically from the new default-wired callback — no call-site edit
  needed. [Agent 1 finding, confirmed by direct grep/read]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/auto.py` — imports `AutoManager` (whose
  `_process_issue()` is being changed); no edit needed, informational only
  [Agent 1 finding]

### Confirmed Out of Scope

- `scripts/little_loops/cli/loop/info.py:1540` — static config comparison,
  not a model-detection read (see Codebase Research Findings above).
- `scripts/little_loops/cli/issues/decisions.py:797` — sets the requested
  model, no resolved-model logging exists here to fix.

### Tests

- `scripts/tests/test_subprocess_utils.py:1437-1845`
  (`TestRunClaudeCommandModelDetection`) — has existing fixture helpers
  (`_make_two_line_selector`) and a test
  (`test_result_event_model_takes_priority_over_init_event_model`)
  demonstrating the alias-vs-resolved divergence; model new tests after this
  fixture shape.
- `scripts/tests/test_issue_manager.py` — existing coverage for
  `process_issue_inplace()`/`on_model_detected` wiring; add a case asserting
  the logged/stored model matches the `result`-event value when `init` and
  `result` events carry different models.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py:3683`
  (`test_auto_manager_logs_detected_model`) — the exact existing test to
  extend per Implementation Step 4; its `mock_process_inplace` fixture
  currently stubs an `on_usage: Any = None` kwarg (not `on_usage_detailed`)
  and asserts only `"model: claude-sonnet-4-6"` in the log — already
  resolved-ID-shaped, so it's the update target rather than a broken/alias
  assertion. [Agent 3 finding]
- `scripts/tests/test_context_window.py` — covers `context_window_for()`
  only as a pure function with literal string args; has **no** coverage of
  it being called via `AutoManager.self._detected_model` (the
  `issue_manager.py:1433-1434` call site the Root Cause section flags as
  fed by the resolved value). Add a case that populates
  `self._detected_model` via the new callback and asserts
  `context_window_for()` sizes correctly from the resolved model. [Agent 3
  finding — test gap]
- `scripts/tests/test_fsm_runners.py:419`
  (`test_on_usage_detailed_forwarded_to_run_claude_command`) — secondary
  reference pattern for asserting `on_usage_detailed` kwarg forwarding
  (shallower than the two-event fixture above: only checks the kwarg is
  passed through, not the resolved value). [Agent 3 finding]
- `scripts/tests/test_cli_sprint.py:623,654,693` — confirmed **safe**, no
  changes needed: these tests patch `process_issue_inplace` as a bare
  callable substitute with no kwarg introspection, so the new
  `on_usage_detailed` parameter (defaulted) doesn't affect them. [Agent 3
  finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2377-2404` — the `run_claude_command`
  signature/parameter doc block documents `on_model_detected`/`on_usage`
  but not `on_usage_detailed`; add a parameter bullet once it's forwarded
  through `issue_manager.py`'s wrapper. [Agent 2 finding]

## Implementation Steps

1. Add an `on_usage_detailed` parameter to `process_issue_inplace()`
   (`issue_manager.py:565-850`), forwarding it to each internal
   `run_claude_command()` call the same way `on_model_detected` is already
   forwarded.
2. In `AutoManager._process_issue()` (`issue_manager.py:1426-1446`), add a
   `_collect_usage`-style closure (mirroring `fsm/runners.py:160-165`) that
   captures `TokenUsage.model`, and pass it as `on_usage_detailed=...` into
   `process_issue_inplace()`.
3. Update the `self.logger.info(f"model: {m}")` log line and the
   `self._detected_model` list feeding `context_window_for()` to prefer the
   resolved model captured via the new callback, falling back to the
   `on_model_detected` alias only if no `result` event fired.
4. Add a regression test in `scripts/tests/test_issue_manager.py`, modeled
   on `test_subprocess_utils.py`'s `TestRunClaudeCommandModelDetection`
   two-event fixture (`_make_two_line_selector`), asserting the
   logged/stored model matches the `result`-event value when `init` and
   `result` events diverge.
5. Verify: `python -m pytest scripts/tests/test_issue_manager.py scripts/tests/test_subprocess_utils.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add a `test_context_window.py` case exercising `context_window_for()`
   through `AutoManager.self._detected_model` end-to-end (currently
   untested in isolation from the pure-function tests).
7. Update `docs/reference/API.md:2377-2404`'s `run_claude_command`
   parameter list to document the new `on_usage_detailed` forwarding.
8. Verify `scripts/little_loops/cli/sprint/run.py`'s two
   `process_issue_inplace()` call sites (lines 71, 783) and their tests
   (`scripts/tests/test_cli_sprint.py:623,654,693`) still pass unchanged —
   confirmed safe (bare-callable mocks, no kwarg introspection), no
   call-site edit required.

## Impact

- **Priority**: P3 — cosmetic/telemetry-accuracy issue (log/display only), not
  a functional break. No user-facing operation fails; a human or the
  `context_window_for()` sizing/model-cost logic could be misled by the
  stale alias, but currently only the log line is user-visible.
- **Effort**: Small — likely a single-callback change in `issue_manager.py`
  plus a couple of call sites (`cli/loop/info.py:1540`,
  `cli/issues/decisions.py:797`) that also compare/pass the raw `"sonnet"`
  alias.
- **Risk**: Low — display-only change; verify via existing
  `test_init_core.py`-style coverage or a new unit test asserting
  `on_model_detected`/logged value matches a `result`-event model when both
  events are present in a fixture stream.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Host CLI Abstraction | All host CLI invocations should resolve model naming consistently through `host_runner.py` |

## Session Log
- `/ll:ready-issue` - 2026-07-24T18:37:41 - `ab99baab-fc83-4236-8693-1801648a70eb.jsonl`
- `/ll:confidence-check` - 2026-07-24T19:00:00 - `26ed09c0-3ff5-4cf6-bac3-4820c61f1ca5.jsonl`
- `/ll:wire-issue` - 2026-07-24T18:34:25 - `28772c11-a1c5-4eb4-b223-9cc4b5db2c03.jsonl`
- `/ll:refine-issue` - 2026-07-24T18:27:53 - `5b4c6af4-d9b0-43f9-a271-37fecf063cb5.jsonl`
- `/ll:capture-issue` - 2026-07-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a14c76a3-31e2-42d3-98f1-9c59fc9295df.jsonl`
- `/ll:manage-issue` - 2026-07-24T18:49:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95598eb-c0fa-4362-baac-940e5ab6d461.jsonl`

## Resolution

Added `on_usage_detailed` (resolved `TokenUsage`, including `TokenUsage.model`)
threading through `issue_manager.py`'s local `run_claude_command()` wrapper and
`process_issue_inplace()`'s three internal `run_claude_command()` calls
(ready-issue, ready-issue fallback retry, decide-issue). `AutoManager._process_issue()`
now wires a `_collect_usage`-style closure as `on_usage_detailed` and prefers the
resolved model it captures for both the `model: ...` log line and
`self._detected_model` (feeding `context_window_for()`), falling back to the
requested alias (from `on_model_detected`) only if no result event ever fires.

- `scripts/little_loops/issue_manager.py` — added `TokenUsage` import,
  `on_usage_detailed` param to `run_claude_command()` and `process_issue_inplace()`,
  forwarded to all 3 internal calls; rewrote `AutoManager._process_issue()`'s
  model-detection closure.
- `scripts/tests/test_issue_manager.py` — updated
  `test_auto_manager_logs_detected_model` to assert the resolved model wins over
  the alias; added `test_auto_manager_falls_back_to_alias_when_no_result_event`,
  `test_forwards_on_usage_detailed` (wrapper), `test_forwards_on_usage_detailed_to_ready_issue_call`
  (`process_issue_inplace`), and `test_context_window_sizes_from_resolved_model_not_alias`.
- `docs/reference/API.md` — documented the new `on_usage_detailed` parameter.

---

## Status

**Current Status**: Done
