---
id: BUG-2757
title: refine-issue/ready-issue model log shows requested alias, not resolved model ID
type: bug
priority: P3
status: open
captured_at: '2026-07-24T00:00:00Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
labels:
- fsm
- telemetry
- host-runner
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
- `/ll:capture-issue` - 2026-07-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a14c76a3-31e2-42d3-98f1-9c59fc9295df.jsonl`

---

## Status

**Current Status**: Open
