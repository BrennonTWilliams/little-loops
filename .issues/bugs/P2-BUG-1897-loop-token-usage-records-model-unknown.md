---
id: BUG-1897
title: Loop token usage always records model "unknown"
type: bug
priority: P2
status: done
captured_at: '2026-06-03T19:12:59Z'
completed_at: '2026-06-03T19:40:45Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
labels:
- fsm
- telemetry
- host-runner
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-1897: Loop token usage always records `model: "unknown"`

## Summary

Every prompt action across every FSM loop records `"model": "unknown"` in its
`action_complete` event payload. The model name is available at runtime but is
never threaded into the `TokenUsage` record, so per-loop cost/token attribution
is unusable. Surfaced by the `svg-textgrad` audit (2026-06-03), which found
`"model": "unknown"` on all prompt actions across two independent runs.

## Current Behavior

`scripts/little_loops/subprocess_utils.py:402` constructs the `TokenUsage`
dataclass from the stream-json **`result`** event:

```python
on_usage_detailed(
    TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        ...
        model=event.get("model", "unknown"),  # result event has no "model"
    )
)
```

The Claude Code stream-json `result` event does **not** carry a `model` field —
the model is only emitted in the `system`/`init` event, which is handled
separately at `subprocess_utils.py:365` via the `on_model_detected` callback:

```python
if etype == "system" and event.get("subtype") == "init":
    if on_model_detected and "model" in event:
        on_model_detected(event["model"])
    continue
```

The executor's prompt path (`scripts/little_loops/fsm/runners.py:122`,
`run_claude_command(...)`) does not pass `on_model_detected` at all, and the
init-event model is never captured into a local variable. Result: the
`model=event.get("model", "unknown")` lookup at the `result` event always falls
back to `"unknown"`.

## Expected Behavior

`TokenUsage.model` reflects the actual model that served the request (e.g.
`claude-opus-4-8`), so that `action_complete` payloads, `usage.jsonl`, and
the `ll-loop run` cost summary (via `_print_usage_summary()` in
`cli/loop/_helpers.py`) are accurate per loop and per state. Currently that
summary shows `"n/a"` for cost because `estimate_cost_usd("unknown", ...)` returns
`None` — the fix restores real dollar figures. (`ll-ctx-stats` is a separate
analytics tool that reads only tool-call byte metrics from SQLite and is not
affected by this bug.)

## Motivation

The audit's §9 ("No token attribution available") flagged this as "likely a
runtime instrumentation gap rather than a loop definition issue" — confirmed.
The blast radius is every loop, not just `svg-textgrad`: any cost analysis,
per-model accounting, or token reporting built on `usage_events[].model` is
silently wrong.

## Root Cause

`subprocess_utils.py` reads `model` from the wrong stream-json event. The model
is present only in the `system`/`init` event but the `TokenUsage` is built from
the `result` event, where the field is absent — so the `"unknown"` default
always wins.

## Proposed Solution

Capture the init-event model into a closure variable inside
`run_claude_command` and use it when constructing `TokenUsage` at the `result`
event — independent of whether the caller supplied an `on_model_detected`
callback:

```python
detected_model = "unknown"
...
if etype == "system" and event.get("subtype") == "init":
    if "model" in event:
        detected_model = event["model"]
        if on_model_detected:
            on_model_detected(event["model"])
    continue
...
# result event:
on_usage_detailed(
    TokenUsage(
        ...
        model=event.get("model", detected_model),
    )
)
```

This keeps the existing `on_model_detected` contract intact while fixing the
attribution for all callers (including the FSM executor, which doesn't pass the
callback).

## Integration Map

### Files to Modify

- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` event
  dispatch loop (lines ~360–413): add `detected_model: str = "unknown"` before
  the loop; assign it from the `system`/`init` branch (line 364); use as
  fallback in the `result` branch's `TokenUsage` constructor (line 402).

### Callers That Benefit Automatically (No Changes Needed)

- `scripts/little_loops/fsm/runners.py:122` — `DefaultActionRunner.run()`:
  calls `run_claude_command()` without `on_model_detected`; receives corrected
  `TokenUsage.model` once the fix lands.
- `scripts/little_loops/cli/action.py` — `ll-action` CLI: calls
  `run_claude_command()`; also benefits automatically.
- `scripts/little_loops/parallel/worker_pool.py` — parallel execution worker;
  benefits automatically.
- `scripts/little_loops/cli/generate_skill_descriptions.py` — benefits
  automatically.
- `scripts/little_loops/workflow_sequence/__init__.py` — benefits automatically.
- `scripts/little_loops/issue_manager.py` — already passes `on_model_detected`;
  fix is additive/no-op for this caller.

### Downstream Consumers of `TokenUsage.model` (Fix Improves These)

- `scripts/little_loops/fsm/executor.py:1097` — `FSMExecutor._run_action()`:
  reads `result.usage_events[-1].model` → writes into `action_complete` payload
  as `payload["model"]`.
- `scripts/little_loops/fsm/persistence.py:634` — `PersistentExecutor._on_event()`:
  writes `{"model": event.get("model", "unknown"), ...}` to per-run `usage.jsonl`.
- `scripts/little_loops/cli/loop/_helpers.py:1324` — `_print_usage_summary()`:
  calls `estimate_cost_usd(model, inp, out, cr, cc)`; when `model="unknown"` the
  call returns `None` and the cost column shows `"n/a"`. Fix restores real dollar
  figures.

### Tests

- `scripts/tests/test_subprocess_utils.py` — `TestRunClaudeCommandModelDetection`
  class (line ~1349): primary location for the new test. Use the two-event
  `io.StringIO` pattern (see `TestRunClaudeCommandOutputCapture.test_captures_stdout_lines`
  at line 393 for the `call_count <= N` selector trick) feeding a `system`/`init`
  event with `"model"` followed by a `result` event without `"model"`, then
  assert `detailed_calls[0].model == "claude-sonnet-4-6"` (not `"unknown"`).
- `scripts/tests/test_usage_reporter.py` — `TestPrintUsageSummary.test_na_shown_for_unknown_model`
  writes `"model": "unknown"` as fixture data directly into a `usage.jsonl` and
  asserts `"n/a"` appears in output. Not broken by the fix (it bypasses
  `run_claude_command`), but after the fix this test documents the edge-case
  fallback rather than the normal behavior.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_usage_reporter.py` — see above.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### run_claude_command` section: the documented
  signature omits `on_usage_detailed`; after the fix the cross-event model
  capture (init → closure → result) behavior should be noted under
  `on_usage_detailed` / `on_model_detected`.
- `docs/reference/loops.md` — `Output Artifacts` section documents the
  `usage.jsonl` schema including the `model` field; worth adding a note that
  the field now reflects the actual model from the `init` event rather than
  `"unknown"`.
- `docs/reference/CLI.md` — `Per-State Token/Cost Summary (ENH-1797)` section:
  description of the `est_cost` column (`"n/a"` for unknown model) changes
  meaning after fix — `"n/a"` now only fires for genuinely unpriced models, not
  for all loop runs.

### Related Files

- `scripts/little_loops/fsm/types.py` — `ActionResult` dataclass containing
  `usage_events: list[TokenUsage]`.
- `scripts/tests/test_usage_journal.py` — `TokenUsage` construction fixtures and
  `MockActionRunner` pattern to reference when building test fixtures.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/pricing.py` — defines `estimate_cost_usd()` and
  `MODEL_PRICING`; no change needed, but the function is the gate between
  `TokenUsage.model` and the cost display — confirms why `"n/a"` appeared.
- `CHANGELOG.md` — needs a `Fixed` entry for BUG-1897 under the next release
  section (clarifying that `est_cost` was always `n/a` before this fix).

## Implementation Steps

1. In `scripts/little_loops/subprocess_utils.py`, inside `run_claude_command()`
   before the event dispatch loop (~line 360), add `detected_model: str = "unknown"`.
   In the `system`/`init` branch (lines 364–367), add
   `detected_model = event["model"]` when the key is present (alongside the
   existing `on_model_detected` callback, which is unchanged). In the `result`
   branch (line 402), change `model=event.get("model", "unknown")` →
   `model=event.get("model", detected_model)`.
2. Add a test method `test_model_falls_back_to_init_event_when_result_has_no_model`
   to `TestRunClaudeCommandModelDetection` in
   `scripts/tests/test_subprocess_utils.py`. Build a two-line `io.StringIO` with a
   `system`/`init` event (`"model": "claude-sonnet-4-6"`) followed by a `result`
   event (no `"model"` key), using the `call_count <= 2` selector pattern from
   `TestRunClaudeCommandOutputCapture.test_captures_stdout_lines` (line 393).
   Assert `detailed_calls[0].model == "claude-sonnet-4-6"`. Also add a
   complementary test verifying that an explicit `"model"` field in the `result`
   event still takes priority over the init-captured value.
3. Run `python -m pytest scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandModelDetection -v`
   to confirm new tests pass and no existing tests regress.

## Steps to Reproduce

1. Run any prompt-based loop, e.g. `ll-loop run svg-textgrad`.
2. Inspect the run's event history (`action_complete` payloads).
3. Observe every prompt action shows `"model": "unknown"`.

## Impact

- **Priority**: P2 - Silent corruption of all per-loop token attribution; every cost analysis built on `usage_events[].model` is silently wrong across every loop
- **Effort**: Small - Single closure variable capture in `run_claude_command`; no API or behavioral changes
- **Risk**: Low - Telemetry-only fix; no change to loop execution behavior
- **Breaking Change**: No

## Status

- **Created**: 2026-06-03 via `/ll:capture-issue` (from `svg-textgrad` audit)
- **State**: open

## Session Log
- `/ll:ready-issue` - 2026-06-03T19:36:28 - `b7bc99a4-988e-45a6-a626-858b519d131f.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:00:00 - auto
- `/ll:refine-issue` - 2026-06-03T19:27:02 - `1799b73a-5176-4319-8725-041f9b9a2b19.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00 - `f884175c-3193-4824-87ce-2accac59c385.jsonl`
- `/ll:format-issue` - 2026-06-03T19:21:10 - `1489a8f1-014d-4d2b-9f62-365c703f374a.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cba1a69-7a53-425f-8c5d-4f1ba61f51bb.jsonl`
