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

> **Architectural Note — live-write only; NOT a raw_events parser
> (ARCHITECTURE-144 scope).** ARCHITECTURE-144 (`.ll/decisions.yaml`,
> ENH-2581) named this issue among those "turned into event_type parser
> tasks over raw_events." That does not apply here: the Claude Code host
> does **not** write hook execution results (exit code, duration, stderr)
> into the session transcript JSONL, so `raw_events` carries no hook
> telemetry to parse. Hook telemetry is genuinely out-of-band, exactly
> like ENH-2507's context-pressure readings. Therefore `hook_events` is a
> **live-write-only** table: `record_hook_event` / `hook_event_context`
> is the only producer, it is **excluded from `rebuild()`'s
> `_REBUILD_TABLES`** (a wipe would be unrecoverable), and there is **no
> `_backfill_hook_events` parser** — the earlier spec's backfill bullet is
> retracted below because its data source does not exist. This is a
> documented, justified pattern deviation.
- **EPIC-1707 deliberately deferred this.** ENH-2495 added lifecycle
  *events* (handoff_needed, compaction, sweep) but not lifecycle
  *telemetry* (the fires that produced them). This issue fills the
  second gap.
- **Adjacent to ENH-2495 (lifecycle_events) and ENH-2504
  (verdict_events).** Different table, complementary signal: 2505 says
  "the handoff_needed event happened"; 2506 says "the hook that
  detected it ran in 12ms with exit code 0."
- **Trivial producer.** Extend the existing `skill_event_context`
  precedent (the best-effort pattern at
  `session_store.py:1109-1182`) to a generic `hook_event_context(...)`
  that wraps any hook handler. Every existing `LLHookResult` producer
  drops in for free.

  > ⚠ Codebase Research Findings (added by `/ll:refine-issue`): The issue
  > originally cited `cli_event_context` at `session_store.py:870-908`,
  > but that function is now at `session_store.py:1055-1091` and is **not**
  > the right precedent — it is **not** best-effort (it raises on a
  > missing DB). `skill_event_context` at `session_store.py:1109-1182`
  > is the right model: it tolerates DB-absent / DB-locked failures
  > (EPIC-1707 graceful-degradation contract — same constraint that
  > applies to hook handlers) and uses a mutable `SkillEventCompletion`
  > handle so the caller can set `exit_code` post-hoc. Use
  > `skill_event_context` as the structural model, not `cli_event_context`.

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
  with the new context manager. Verified handler anchors (as of
  v1.147.0):
  - `scripts/little_loops/hooks/post_tool_use.py:137` — PostToolUse (the
    one whose `with contextlib.suppress(Exception):` block at line 158
    is the canonical inner-swallow pattern)
  - `scripts/little_loops/hooks/user_prompt_submit.py:61` — UserPromptSubmit
  - `scripts/little_loops/hooks/pre_tool_use.py` — PreToolUse (NEW — not
    in the original issue; `hooks/hooks.json` registers PreToolUse for
    `Write|Edit`, `Bash`, and several dedicated matchers)
  - `scripts/little_loops/hooks/pre_compact.py:84` — PreCompact
  - `scripts/little_loops/hooks/sweep_stale_refs.py:141` — SessionStart
    secondary (stale-refs sweep)
  - `scripts/little_loops/hooks/session_start.py:75` — SessionStart primary
  - `scripts/little_loops/hooks/post_commit.py` — PostToolUse (additional
    producer for issue-auto-commit; NEW)
  - `scripts/little_loops/hooks/edit_batch_nudge.py` — PostToolUse
    (`Edit|Write|MultiEdit` matcher — NEW)
  - `scripts/little_loops/hooks/pre_compact_handoff.py` — PreCompact
    secondary (NEW)
  - `scripts/little_loops/hooks/learning_tests_gate.py`,
    `install_learning_gate.py` — PreToolUse / PostToolUse (NEW, gated by
    `analytics.capture.skills`)

  There is **no** `scripts/little_loops/hooks/stop.py` — the `Stop`
  hook is bash-only in this codebase (`hooks/scripts/context-handoff-sentinel.sh`
  and `hooks/scripts/session-cleanup.sh` per `hooks/hooks.json:177-198`).
  Capture Stop/SessionEnd via a small bash wrapper that calls
  `record_hook_event` from a new `hooks/scripts/record-hook-event.sh`
  shim — pattern follows the existing `post-tool-use.sh` adapter
  (`hooks/adapters/claude-code/post-tool-use.sh`). All other bash hooks
  under `hooks/scripts/*.sh` (scratch-pad, scratch-cleanup,
  user-prompt-check, context-monitor, etc.) likewise emit via the shim.
- Backfill: **none** (retracted). An earlier draft proposed a
  `_backfill_hook_events` parser walking JSONL, but the Claude Code host
  does not emit hook execution results into the transcript, so there is
  nothing to parse — see the Architectural Note above. `hook_events` is
  live-write-only and must be **excluded from `rebuild()`'s
  `_REBUILD_TABLES`** (mirroring `context_pressure_events`/ENH-2507 and
  the `test_run_events`/`cli_events` live-only tables ENH-2581's
  `rebuild()` deliberately leaves untouched).

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

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Modify

- `scripts/little_loops/session_store.py` — append v21 migration block
  to `_MIGRATIONS` (line 333 onward) creating `hook_events` + 3 indexes;
  add `"hook_event": "hook_events"` to `_KIND_TABLE` (line 223);
  add `record_hook_event(...)` and `hook_event_context(...)` next to
  `skill_event_context` (line 1109) so they share the same best-effort
  pattern; **do not add a `_backfill_hook_events`** (no transcript source
  — see Architectural Note) and ensure `hook_events` is left out of
  `rebuild()`'s `_REBUILD_TABLES`
- `scripts/little_loops/hooks/post_tool_use.py:137` — wrap `handle()` in
  `hook_event_context` (preserve the existing `contextlib.suppress` at
  line 158; the new context is best-effort outer wrap)
- `scripts/little_loops/hooks/user_prompt_submit.py:61` — wrap `handle()`
- `scripts/little_loops/hooks/pre_compact.py:84` — wrap `handle()`
- `scripts/little_loops/hooks/sweep_stale_refs.py:141` — wrap `handle()`
- `scripts/little_loops/hooks/session_start.py:75` — wrap `handle()`
- `scripts/little_loops/hooks/pre_tool_use.py` — wrap `handle()`
- `scripts/little_loops/hooks/post_commit.py` — wrap `handle()`
- `scripts/little_loops/hooks/edit_batch_nudge.py` — wrap `handle()`
- `scripts/little_loops/hooks/pre_compact_handoff.py` — wrap `handle()`
- `scripts/little_loops/hooks/learning_tests_gate.py`,
  `install_learning_gate.py` — wrap `handle()`
- `scripts/little_loops/hooks/__init__.py` (`_dispatch_table`,
  lines 74-99) — add a single outer wrap around each registered handler
  so the same context manager applies to every host-agnostic Python
  handler (alternative: wrap each module's `handle()` individually — see
  Implementation Steps for the trade-off)
- `scripts/little_loops/history_reader.py` — add `recent_hook_events`,
  `hook_failure_rate`, `hook_latency_p95` next to existing
  `recent_*` helpers (look for `recent_tool_events` /
  `recent_skill_events` as precedent)
- `scripts/little_loops/cli/session.py` — register `"hook_event"` in
  the `--kind` argument's `choices=` list so `ll-session recent
  --kind hook_event` works
- `scripts/little_loops/cli/session.py` — add `hook-health`
  subcommand (optional follow-on, gated by `--since`)
- `scripts/little_loops/templates/API.md` — add entry to
  `ll-history-context`, `ll-session` for the new `--kind` and
  subcommand
- `hooks/scripts/record-hook-event.sh` (NEW) — bash shim that calls
  `python -m little_loops.cli.session record-hook-event "$@"` so bash
  hooks (Stop, SessionEnd, scratch-cleanup, etc.) can emit rows; the
  shim is invoked from each existing bash hook after its main body
  exits, capturing `$?` as `exit_code`
- `hooks/adapters/claude-code/{stop,session-end}-adapter.sh` (NEW) —
  bash wrappers for the adapter layer, mirroring the
  `post-tool-use.sh` pattern

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py` — dispatcher for `ll-session`
  recent / hook-health (the new `--kind hook_event` and aggregate
  subcommand land here)
- `scripts/little_loops/cli/__init__.py`, `cli/history.py` — register
  any new commands if the subcommand split is reused
- `scripts/little_loops/cli/backfill_worker.py` — **no change** (no
  `_backfill_hook_events` to wire; hook telemetry is live-write-only, see
  Architectural Note)

### Similar Patterns

- `session_store.py:1109` `skill_event_context` — best-effort
  `@contextmanager` with mutable `SkillEventCompletion` handle (the
  right structural model for `hook_event_context`)
- `session_store.py:1055` `cli_event_context` — eager
  `@contextmanager` (NOT best-effort; do NOT mirror)
- `session_store.py:1878` `_backfill_usage_events` — useful only for the
  precise live-`INSERT` shape (column list, `_index()` FTS call shape);
  **not** as a backfill template — `hook_events` has no backfill path
  (see Architectural Note). Contrast the live-only recorders
  `record_test_run_event` / `record_context_pressure_event` (ENH-2507),
  which are the correct structural model here.
- `scripts/little_loops/hooks/post_tool_use.py:158` — the canonical
  inner `with contextlib.suppress(Exception):`; preserve it inside the
  new outer `hook_event_context`

### Tests

- `scripts/tests/test_session_store.py` — extend
  `TestEnsureDb.test_all_tables_created` to assert `"hook_events"` is
  in the table list (currently asserts 8 tables at line 96-106);
  bump that assertion to include `"hook_events"`
- `scripts/tests/test_session_store.py` — add a `TestHookEvents`
  class covering: (a) migration adds the table, (b) `record_hook_event`
  inserts a row, (c) `hook_event_context` writes `exit_code`/`duration_ms`
  on clean exit and on raised exception, (d) DB-absent /
  DB-locked does NOT raise (best-effort contract)
- `scripts/tests/test_hook_post_tool_use.py` — add a fixture that
  captures `hook_events` rows around a `handle()` call and asserts
  one row is inserted
- `scripts/tests/test_hook_user_prompt_submit.py`,
  `test_hook_session_start.py` — same fixture pattern
- `scripts/tests/test_hooks_integration.py` — extend with a
  multi-event rollup test: trigger 3 fires, 1 failure → assert
  `hook_failure_rate("PostToolUse")` returns ≈0.33
- (NEW) `scripts/tests/test_history_reader_hook.py` — direct tests
  for `recent_hook_events`, `hook_failure_rate`, `hook_latency_p95`
  using an in-memory or temp SQLite fixture

### Documentation

- `docs/ARCHITECTURE.md` — schema versions table; bump v20→v21 entry
  to mention `hook_events` (ENH-2506)
- `docs/reference/API.md` — `session_store` section: add
  `record_hook_event` / `hook_event_context` / `_backfill_hook_events`;
  `hooks` section: note the new telemetry wrap on every `handle()`
- `docs/reference/CLI.md` — `ll-session recent --kind` values table;
  `ll-session hook-health` subcommand entry
- `docs/claude-code/hooks-reference.md` — update the hook-intent
  banner per the `reference_dispatch_table_usage_banner` memory
  (`scripts/little_loops/hooks/__init__.py:_USAGE` line 50-54)
- `docs/development/TROUBLESHOOTING.md` — add the "hook didn't fire"
  debug section pointing to `ll-session recent --kind hook_event`

### Configuration

- `.ll/ll-config.json` → `analytics.capture` keys: gate the new
  producer on a new `analytics.capture.hooks` flag (parallel to
  `analytics.capture.file_events` / `analytics.capture.skills`),
  defaulting to `true`. The `skill_event_context` config parameter is
  a forward-compat stub; reuse the same `config: dict | None` shape.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete step ordering that mirrors the
existing migration / wrap pattern._

1. **Schema migration (session_store.py)**:
   1.1. Append a new entry to `_MIGRATIONS` (after the v20 usage_events
   block at line 718) with the `hook_events` CREATE TABLE + 3 CREATE
   INDEX statements from the Proposed Solution. Comment it `# v21
   (ENH-2506): hook_events — …` following the v18/v19/v20 convention
   (note: `SCHEMA_VERSION = 20` at line 207 — the issue's "Bump
   `SCHEMA_VERSION`" instruction lands this at v21).
   1.2. Add `"hook_event": "hook_events"` to `_KIND_TABLE` (line 223).
   1.3. Verify `ll-verify-kinds` passes (gates unregistered CREATE
   TABLE statements per ENH-2581).

2. **Producer (session_store.py)**:
   2.1. Add `record_hook_event(db_path, *, ts, session_id, event_name,
   matcher, script, exit_code, duration_ms, stderr_preview=None,
   head_sha=None, branch=None)` modeled on `record_tool_event` /
   `record_skill_event` — single-row INSERT with FTS5 `_index()` call.
   2.2. Add `@contextmanager def hook_event_context(db_path, session_id,
   event_name, matcher, script)` modeled on `skill_event_context`
   (lines 1109-1182) — best-effort, mutable completion handle so the
   caller can set `exit_code` and `stderr_preview` post-hoc. Use
   `time.monotonic()` for the duration (the existing
   `cli_event_context` / `skill_event_context` use `time.time()` —
   monotonic is the correct choice for "elapsed time of this hook fire"
   and matches the issue's specification).

3. **Bash shim** (NEW):
   3.1. Write `hooks/scripts/record-hook-event.sh` — captures `$?`,
   `$STDERR_PREVIEW` (first 512 bytes), `$MATCHER`,
   `$EVENT_NAME`, calls the Python entry point. Mirrors the existing
   `post-tool-use.sh` adapter pattern (no new adapter is needed — the
   shim is invoked from each bash hook directly).
   3.2. Wrap each bash hook entry point in `hooks/hooks.json` to
   invoke the shim after the existing body. Specifically: add a second
   command after each existing bash hook under `PostToolUse`, `Stop`,
   `SessionEnd`, `PreCompact`, `UserPromptSubmit`, `SessionStart`
   that invokes the shim with the right `event_name` and `matcher`.
   (Trade-off — see the Decision-Point below.)

4. **Python wrap (each handler)**:
   4.1. Edit each `handle()` function listed in the Integration Map to
   wrap its body in `with hook_event_context(...):` at the outermost
   level (so the context still records `exit_code` even when the
   handler raises). Where a handler is itself gated by
   `analytics.enabled` (e.g. `post_tool_use.py:151`), the wrap goes
   *outside* the gate so a no-config run still produces telemetry.

5. **Read API (history_reader.py)**:
   5.1. `recent_hook_events(event_name=None, exit_code=None, since=None,
   limit=50)` — copy the shape of `recent_tool_events` /
   `recent_skill_events`. Use `_connect_readonly` (line ~220) and
   `_stale_cutoff` (line ~1397) for consistency with peer functions.
   5.2. `hook_failure_rate(event_name, since=None)` — single SQL with
   `AVG(CASE WHEN exit_code != 0 THEN 1.0 ELSE 0.0 END)`.
   5.3. `hook_latency_p95(event_name, since=None)` — SQL aggregate.

6. **CLI surface (cli/session.py)**:
   6.1. Add `"hook_event"` to the `--kind` argument's `choices=` tuple
   in `recent` subcommand.
   6.2. Add `hook-health` subcommand with `--since` argument
   (default 7d), printing per-event_name fires / failures / p95.

7. **Tests** (per Integration Map → Tests):
   7.1. Bump `test_session_store.py::TestEnsureDb::test_all_tables_created`
   to include `"hook_events"` in the expected table set.
   7.2. Add `TestHookEvents` class with the 4 cases listed.
   7.3. Add the `hook_events` capture fixture to each existing
   `test_hook_*.py` file.
   7.4. (NEW) `test_history_reader_hook.py`.
   7.5. Run `python -m pytest scripts/tests/ -v --tb=short` and
   confirm all green.

8. **Backfill (session_store.py)**:
   8.1. Add `_backfill_hook_events(conn, source)` mirroring
   `_backfill_usage_events` (line 1878). Iterate `_iter_events(source)`,
   filter on `record.get("type") == "hook_fire"` (the synthetic shape
   — verify against the live JSONL shape during implementation), and
   INSERT into `hook_events`.
   8.2. Wire `_backfill_hook_events` into the backfill orchestrator
   in `cli/backfill_worker.py` so `rebuild()` invokes it.

9. **Verification**: `ruff check scripts/`, `ruff format scripts/`,
   `python -m mypy scripts/little_loops/`, and `python -m pytest
   scripts/tests/`. Per `.claude/CLAUDE.md`, the pytest suite is the
   project's only CI gate — do not add GitHub Actions workflows.

### Decision-Point (Implementation Steps §3)

The bash shim wiring has two viable shapes:

**Option A** — add a second command per `hooks/hooks.json` entry that
invokes the shim. Pros: zero changes to existing bash bodies (no
behavioral risk to shipped hooks); a single `hooks.json` edit is the
only required change per hook. Cons: every entry now has two
commands (visual noise); bash hooks that exit early (e.g. on missing
config) still emit a row, so the "fires / failures" rollup includes
early-exit hooks.

**Option B** — modify each bash script to call the shim inline at the
end (or via a trap). Pros: only fires that actually reached the shim
get recorded (cleaner signal); one edit per script. Cons: every bash
script needs a behavioural review; trap placement must respect
existing exit-code semantics in scripts that already set `exit $?` at
the end.

**Recommended**: Option A for v1 (lower risk, matches the existing
"two commands" shape under PostToolUse for `context-monitor.sh` +
`session-capture.sh`); revisit with Option B in a follow-on if
"fires that reached the shim" becomes the preferred signal.

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("Bump
`SCHEMA_VERSION`"). Several other active EPIC-2457 siblings (ENH-2492,
ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2493, ENH-2494, ENH-2495,
ENH-2496, ENH-2497, ENH-2498, ENH-2504, ENH-2511, and others) independently
make the same schema-slot claim in their own Integration Maps — they cannot
all land at the same version number. Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's implied slot;
each child lands its own migration at whatever version is open when it is
implemented (no coordinated release; per EPIC-2457's own "no shared helper
module is required" scope note).

## Session Log
- `/ll:refine-issue` - 2026-07-16T16:16:11 - `a12fca84-5e71-48ec-aff1-8ea85e8c0067.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`