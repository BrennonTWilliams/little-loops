---
id: ENH-2932
type: ENH
priority: P3
status: open
discovered_date: 2026-07-30
captured_at: '2026-07-30T23:22:05Z'
discovered_by: capture-issue
relates_to:
- ENH-1833
- ENH-1834
- ENH-1835
- ENH-1841
labels:
- enhancement
- captured
---

# ENH-2932: Wire analytics.capture.skills and cli_commands gates onto skill/CLI event writers

## Summary

`ll-config.json`'s `analytics.capture.skills` and `analytics.capture.cli_commands`
glob-pattern fields are defined in `config-schema.json` and parsed into
`AnalyticsCaptureConfig` (`scripts/little_loops/config/features.py`), but no write
path ever consults them. `record_skill_event()`/`skill_event_context()` and
`cli_event_context()` (`scripts/little_loops/session_store/writers.py`) accept a
`config` parameter documented as a "forward-compatibility stub ... accepted but not
yet used," and the two call sites (`hooks/post_tool_use.py:246`,
`hooks/user_prompt_submit.py:130`) still carry
`# TODO(ENH-1835): wire ... gate when ENH-1833/ENH-1834 lands` comments. Both
prerequisite issues (ENH-1833 skill events, ENH-1834 CLI events) have since shipped,
but the follow-up wiring was never done.

## Current Behavior

Setting `analytics.capture.skills` or `analytics.capture.cli_commands` to anything
other than `["*"]` (e.g. narrowing to specific skill/binary names) has no effect —
every `/ll:`-prefixed skill invocation and every `ll-*` CLI invocation that calls
`cli_event_context()` is written to `skill_events`/`cli_events` unconditionally. The
config keys are documented in `config-schema.json` and covered by unit tests for the
`feature_enabled_for()` glob-matching helper itself, but nothing threads that helper
into the two live write paths.

## Expected Behavior

`record_skill_event()`/`skill_event_context()` and `cli_event_context()` consult
`AnalyticsCaptureConfig.skills` / `.cli_commands` (via `feature_enabled_for()`) before
writing a row, using the same pattern ENH-1841 already established for
`analytics.capture.file_events` and `analytics.capture.corrections`. A skill/binary
name that doesn't match any configured glob pattern is silently skipped; the default
`["*"]` preserves today's unconditional-capture behavior.

## Motivation

This closes a real, currently-misleading gap: the config schema and `ll-doctor`
capture-state reporting present `analytics.capture.skills`/`cli_commands` as live
controls, but they are inert scaffolding. High-volume projects that set these to
narrow the DB growth get no effect and no error — a silent no-op is worse than an
unsupported key. The fix is small and low-risk: the pattern was already proven twice
in ENH-1841 for the other two capture categories.

## Proposed Solution

Follow the exact ENH-1841 pattern:

```python
from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled_for

capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
if not feature_enabled_for({"skills": capture.skills}, "skills", skill_name):
    return
```

Thread this gate inside `record_skill_event()`/`skill_event_context()` (using
`capture.skills`) and inside `cli_event_context()` (using `capture.cli_commands`),
not only at the hook call sites — matching ENH-1841's Wiring Phase note #6 that
gating must live in the write-path functions themselves so it also applies to
non-hook callers (e.g. `ll-*` CLI entry points calling `cli_event_context()`
directly). Remove the two now-stale `TODO(ENH-1835)` comments once wired.

## Scope Boundaries

- **In scope**: Threading `analytics.capture.skills` into `record_skill_event()` /
  `skill_event_context()`; threading `analytics.capture.cli_commands` into
  `cli_event_context()`; removing the two stale TODO comments; tests mirroring
  ENH-1841's gating tests for the new categories.
- **Out of scope**: Capturing project-local (non-`/ll:`-prefixed) skill invocations —
  `user_prompt_submit.py`'s regex only recognizes `^/ll:[a-z][a-z0-9-]*`, a separate
  capture-surface limitation, not a gating bug. Capturing arbitrary non-`ll-*` CLI
  invocations (e.g. `python3 tools/*.py`) — `cli_event_context()` is only called from
  inside `ll-*` entry points by design (ENH-1834 explicitly scoped non-`ll-` tools as
  out of scope). Both are legitimate follow-ups but distinct from finishing this
  gating wire-in.

## Implementation Steps

1. Add the `capture.skills` gate inside `record_skill_event()` and
   `skill_event_context()` in `scripts/little_loops/session_store/writers.py`.
2. Add the `capture.cli_commands` gate inside `cli_event_context()` in the same file.
3. Remove the two stale `TODO(ENH-1835)` comments in `hooks/post_tool_use.py` and
   `hooks/user_prompt_submit.py` (or replace with a short note that gating now lives
   in the writer, if the hook call sites don't already pass `config` through).
4. Add gating tests mirroring `TestRecordCorrection`'s
   `test_record_correction_gate_disabled` pattern for both new categories.
5. Verify `ll-doctor`'s existing capture-state reporting block (added by ENH-1842)
   still reads correctly now that the flags are live.

## Impact

- **Priority**: P3 — matches sibling capture-config issues (ENH-1833/1834/1835/1841);
  not urgent, but closes a documented-but-inert config surface.
- **Effort**: Small — the exact pattern is already implemented twice (ENH-1841); this
  is the same threading applied to two more write paths.
- **Risk**: Low — safe default (`["*"]`) preserves current unconditional-capture
  behavior; no behavior change unless a user narrows the glob list.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-30T23:22:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4be5df0-3d5b-4e4c-86d2-f958207fe7cb.jsonl`

---

## Status

**Open** | Created: 2026-07-30 | Priority: P3
