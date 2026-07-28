---
id: ENH-2885
type: ENH
priority: P3
status: open
captured_at: "2026-07-28T04:08:05Z"
discovered_date: 2026-07-28
discovered_by: capture-issue
---

# ENH-2885: Read actual effort from session JSONL instead of resolved config value

## Summary

`_resolve_action_effort()` (`scripts/little_loops/fsm/executor.py:2278`) resolves the
displayed `effort` value purely from loop/state config precedence
(`state.effort or self.run_effort or self.fsm.llm.effort`), per a comment at
`executor.py:1713-1717` claiming "No host surface reports an 'actual' effort value
back". That comment is stale: the Claude Code host CLI's raw session JSONL does
report the actual effort applied, as a top-level `"effort"` field on every
`type: "assistant"` line (verified directly against a live session JSONL —
11/11 assistant lines carried `"effort": "low"`). The executor already opens this
file post-run for other purposes (`get_current_session_jsonl()` at
`executor.py:1732`, right next to the effort-resolution call), so the plumbing to
read it is already present.

## Current Behavior

`ll-loop run` only displays an effort level when the loop/state explicitly sets
`llm.effort` or a per-state `effort:` override. A loop like `autodev.yaml`, which
sets neither, shows no effort in its header/log output at all — even though the
host CLI is still applying some default effort level under the hood and reporting
it in the session JSONL.

## Expected Behavior

`action_complete`'s `effort` payload field reflects the actual effort the host CLI
applied for that call (read from `session_jsonl`'s assistant-line `"effort"`
field), falling back to the resolved config value only when the host doesn't
report one (e.g. non-Claude-Code hosts, or shell/mcp actions with no effort
concept). This makes the effort display meaningful even for loops that never set
an explicit effort override.

## Motivation

Surfaced while investigating why the currently-running `autodev` loop showed no
effort level in its output (ENH-2869's original feature). The proximate cause is
that autodev has no `llm.effort` configured, but the deeper gap is that the
CLI's effort display can never show anything beyond what the loop author
explicitly configured — it can't reveal what the host actually did by default,
even though that information already exists in the session log little-loops is
already reading.

## Proposed Solution

- In `_resolve_action_effort()` (or the call site at `executor.py:1718`), after
  action execution, parse the `session_jsonl` path already resolved at
  `executor.py:1732` for the most recent `type: "assistant"` line's top-level
  `"effort"` field.
- If found, prefer it over the config-resolved value for the `payload["effort"]`
  written into the `action_complete` event.
- Keep the config-resolved value as the fallback for hosts/action modes where no
  JSONL effort field is available (matches the existing `model` fallback
  pattern already used nearby).
- Update/remove the stale "No host surface reports an actual effort value back"
  comment at `executor.py:1713-1717`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_resolve_action_effort()` and the
  `action_complete` payload construction around line 1718-1735

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:1094` — already consumes
  `event.get("effort")` from `action_complete`; no change needed if the payload
  contract (a string effort level) stays the same

### Tests
- `scripts/tests/` — add/extend a test covering effort resolution when a
  session JSONL with an `"effort"` field is present but no config-level effort
  is set

### Documentation
- N/A

## Session Log
- `/ll:capture-issue` - 2026-07-28T04:08:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f9bac15-2758-49a3-9cff-cf5c0c7f07ff.jsonl`

---

## Status

**Current State**: Open
