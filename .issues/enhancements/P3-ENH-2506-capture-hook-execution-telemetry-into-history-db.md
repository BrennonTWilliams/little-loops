---
id: ENH-2506
title: Capture hook execution telemetry into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - hooks
  - telemetry
  - captured
---

# ENH-2506: Capture hook execution telemetry into history.db

## Summary

The `post-tool-use`, `session-end`, `pre-compact`, `user-prompt-submit`,
and `stop` hook scripts exit non-zero silently all the time — the outer
`try/except Exception: return LLHookResult(exit_code=0)` wrappers in the
hook handlers swallow the failure, and nothing persists. So when a user
hits "the hook didn't fire" or "the context-monitor is broken", there is
no record of whether the hook ran, what it returned, or how long it
took. Add a `hook_events` table capturing `(session_id, event_name,
matcher, script, exit_code, duration_ms, stderr_preview)` for every hook
fire. Most "the hook didn't fire" debug threads start with no data; this
ends that.

## Motivation

- **Hook telemetry is the largest dark area.** Today, hooks can fail,
  time out, or never fire, and the only signal is "the agent behaves
  strangely." With per-fire rows, every hook invocation becomes a
  queryable point: which matcher matched, which script ran, what exit
  code it returned, how long it took, what stderr it produced.
- **EPIC-1707 deliberately deferred this.** ENH-2495 added lifecycle
  *events* (handoff_needed, compaction, sweep) but not lifecycle
  *telemetry* (the fires that produced them). This issue fills the
  second gap.
- **Adjacent to ENH-2495 (lifecycle_events) and ENH-2504
  (verdict_events).** Different table, complementary signal: 2505 says
  "the handoff_needed event happened"; 2506 says "the hook that
  detected it ran in 12ms with exit code 0."
- **Trivial producer.** Extend the existing `cli_event_context`
  precedent (the post-tool-use wrap pattern at
  `session_store.py:870-908`) to a generic `hook_event_context(...)`
  that wraps any hook handler. Every existing `LLHookResult` producer
  drops in for free.

## Current Behavior

- `post_tool_use.py:158` (and the matching patterns in
  `user_prompt_submit.py`, `pre_compact.py`, `sweep_stale_refs.py`,
  `session_start.py`) wraps the body in
  `with contextlib.suppress(Exception):` and the dispatcher wraps that
  in another `try/except Exception: return LLHookResult(exit_code=0)`.
  A failed hook returns success.
- The only durable artifact of a hook fire is `tool_events` for
  `post_tool-use` writes that succeeded. For other hooks, nothing.
- The dispatch table (`scripts/little_loops/hooks/__init__.py:_dispatch_table`)
  registers every hook but doesn't record the fire.

## Expected Behavior

- A `hook_events` table records one row per hook fire with
  `event_name`, `matcher` (the selector from `hooks/hooks.json`),
  `script` (the bash command or Python entry point), `exit_code`,
  `duration_ms`, `stderr_preview` (truncated first N bytes), and
  `session_id`.
- A `hook_event_context(db_path, event_name, matcher, script)`
  context manager measures elapsed time, captures exit code on exit,
  reads stderr if available, and writes the row (best-effort).
- Existing hook handlers adopt the context manager; no other producer
  changes required.
- `ll-session recent --kind hook_event` returns rows; aggregate
  queries (failure rate by event_name, p95 duration) become
  straightforward.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS hook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    event_name TEXT NOT NULL,     -- "PostToolUse" | "UserPromptSubmit" | "PreCompact" | "Stop" | "SessionStart" | "SessionEnd"
    matcher TEXT,                 -- the `matcher` field from hooks/hooks.json (e.g., "Write|Edit|MultiEdit")
    script TEXT,                  -- bash command or python module path
    exit_code INTEGER,
    duration_ms INTEGER,
    stderr_preview TEXT,          -- truncated first 512 bytes of stderr (if any)
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_hook_event_name ON hook_events(event_name);
CREATE INDEX IF NOT EXISTS idx_hook_session ON hook_events(session_id);
CREATE INDEX IF NOT EXISTS idx_hook_exit ON hook_events(exit_code);
```

Bump `SCHEMA_VERSION`. Add `"hook_event"` to `_VALID_KINDS` and
`"hook_event": "hook_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_hook_event(db_path, *, ts, session_id, event_name, matcher,
  script, exit_code, duration_ms, stderr_preview=None, head_sha=None,
  branch=None)` to `session_store.py`, best-effort, FTS-indexing
  `event_name + matcher`.
- Add `hook_event_context(db_path, session_id, event_name, matcher,
  script)` to `session_store.py` modeled on `cli_event_context`
  (`session_store.py:870-908`): a `@contextmanager` that
  records `started_at = time.monotonic()`, yields, and on exit writes
  the row with `duration_ms = int((monotonic() - started_at) * 1000)`,
  `exit_code=<caller's exit code>`, and stderr from a captured buffer.
- Wrap each existing `handle()` in the host-agnostic Python handlers
  (`scripts/little_loops/hooks/post_tool_use.py:handle`,
  `user_prompt_submit.py:handle`, `pre_compact.py:handle`,
  `sweep_stale_refs.py:handle`, `session_start.py:handle`,
  `stop.py:handle` if present) with the new context manager. Bash hooks
  (`hooks/scripts/*.sh`) shell out to a one-liner that calls
  `record_hook_event` after the bash script runs.
- Backfill: a `_backfill_hook_events` (sibling to
  `_backfill_tool_events` at `session_store.py:1620`) walks JSONL for
  hook events emitted by Claude Code host and reconstructs rows.

### Read API

- `history_reader.recent_hook_events(event_name=None, exit_code=None,
  since=None, limit=50)`.
- `history_reader.hook_failure_rate(event_name, since=None)` — exit
  code != 0 rate per event.
- `history_reader.hook_latency_p95(event_name, since=None)` — the
  "is this hook getting slow" signal.

### CLI surface

- `ll-session recent --kind hook_event`.
- `ll-session hook-health [--since 7d]` (optional follow-on) — rollup
  of fires / failures / p95 duration per event_name.

## Acceptance Criteria

- Schema migration lands; `hook_events` exists; `SCHEMA_VERSION` bumped.
- Every `PostToolUse` fire writes one row with `event_name="PostToolUse"`,
  `matcher`, `script`, `exit_code`, `duration_ms`.
- A hook that returns non-zero writes `exit_code=<that code>` and the
  outer wrapper still swallows the failure (preserving EPIC-1707
  contract).
- A hook that produces stderr writes the first 512 bytes to
  `stderr_preview`.
- DB-absent/locked does not change hook exit code.
- `ll-session recent --kind hook_event` returns rows; failure-rate
  rollup works.
- Tests cover: success/failure/timeout paths, stderr truncation, DB
  absent graceful degradation.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — "the missing
  events.jsonl is what would distinguish Modes A/B/C" — the hooks that
  should have fired during the killed run left no trace
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` (lines 74-99)
  — registers every hook; this issue extends the registration with a
  recording wrap
- ENH-2495 — sibling lifecycle *events* (handoff_needed, etc.); this
  issue captures the *fires* that produced them
- ENH-2496 — sibling config-snapshot work; same `analytics.capture`
  gate applies

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; hook write-paths note |
| `docs/reference/API.md` | `session_store`, `hooks` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |
| `reference_dispatch_table_usage_banner` (memory) | Update hook intent list when adding new intent handlers |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`