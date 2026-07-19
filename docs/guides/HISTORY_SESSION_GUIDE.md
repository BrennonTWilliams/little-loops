# History & Session Guide

Long-term observability for your little-loops project: what ran, what changed, what was corrected, and why.

## Table of Contents

- [When to Use This Guide](#when-to-use-this-guide)
- [Querying Recipes](#querying-recipes)
- [What Is history.db?](#what-is-historydb)
- [What Gets Recorded](#what-gets-recorded)
- [Getting Started: Backfill](#getting-started-backfill)
- [Querying Sessions](#querying-sessions)
- [Issue ↔ Session Cross-References](#issue--session-cross-references)
- [Planning Skill Injection](#planning-skill-injection)
- [History Analytics](#history-analytics)
- [Session Log Tooling (ll-logs)](#session-log-tooling-ll-logs)
- [Advanced: LCM Compaction](#advanced-lcm-compaction)
- [Retention & Pruning](#retention--pruning)
- [Configuration Reference](#configuration-reference)
- [See Also](#see-also)

---

## When to Use This Guide

Use this when you want to query what happened in past sessions, inject historical context into planning, or analyze trends across your project. Start with the **Querying Recipes** table below — most common needs are one command.

## Querying Recipes

| I want to know... | Command |
|------------------|---------|
| Which files I touched in the last week | `ll-session recent --kind file` |
| All times I debugged authentication | `ll-session search --fts "authentication"` |
| Every correction Claude received about a topic | `ll-session search --fts "rate limit" --kind correction` |
| How long issue BUG-1759 took | `ll-history-context BUG-1759 --effort` |
| Which sessions worked on issue FEAT-42 | `ll-history sessions FEAT-42` |
| A trend analysis for the last quarter | `ll-history analyze --since 2026-01-01 --format markdown` |
| All tools used across sessions | `ll-session recent --kind tool --limit 20` |
| What the project summary looks like | `ll-history summary` |
| What shipped recently (commits with issue linkage) | `ll-session recent --kind commit` |
| Last pytest run on this branch | `ll-session recent --kind test_run --limit 1` |
| Recent LLM token usage / cost by model | `ll-session recent --kind usage` |
| Per-issue outcomes from the latest automation batches | `ll-session recent --kind orchestration_run` |
| How often context handoff triggers / recent compaction events | `ll-session recent --kind session_lifecycle` |
| Which skills succeed vs. fail | `ll-session skill-stats` |

---

## What Is history.db?

`.ll/history.db` is a per-project SQLite database that accumulates a long-lived event history across every Claude Code session. Where session JSONL files are ephemeral per-conversation snapshots, history.db is the persistent record: it indexes tool invocations, file modifications, issue state transitions, loop executions, user corrections, and session-to-message content across all sessions that have ever run in this project. Set `LL_HISTORY_DB=/path/to/alt.db` to override the default location (useful for test isolation or CI).

The database is **additive-only** — backfill is idempotent (dedup indexes prevent duplicates on repeated runs) and nothing is deleted unless you explicitly prune. Schema migrations apply automatically on connect. Current schema version: 27, defined in `scripts/little_loops/session_store.py` (`_MIGRATIONS`). Each version maps to the ENH/FEAT that introduced it:

| Version | Issue | Adds |
|---------|-------|------|
| v1 | — | Initial bootstrap: `tool_events`, `file_events`, `issue_events`, `loop_events`, `user_corrections`, `search_index`, `meta` |
| v2 | ENH-1621 | Issue completion-summary columns on `issue_events`; `message_events` table |
| v3 | ENH-1690 | Dedup index on `issue_events(issue_id, transition)` |
| v4 | ENH-1710 | `sessions` table (session ID → JSONL path) |
| v5 | ENH-1711 | `issue_sessions` view (timestamp-overlap join) |
| v6 | ENH-1830 | `last_backfill_ts` meta key for incremental backfill |
| v7 | ENH-1833 | `skill_events` table |
| v8 | ENH-1848 | `cli_events` table |
| v9 | ENH-1904 | Dedup index on `user_corrections` |
| v10 | FEAT-1712 | `summary_nodes` / `summary_spans` (LCM compaction DAG) |
| v11 | ENH-1942 | `assistant_messages` table |
| v12 | ENH-1953 | `level` column on `summary_nodes` for N-level DAG |
| v13 | ENH-2046 | `correction_retirements` table |
| v14 | ENH-2151 | `issue_snapshots` table |
| v15 | ENH-2460 | `skill_events` completion columns (`exit_code`, `success`, `duration_ms`) |
| v16 | ENH-2462 | Authoritative `issue_events.session_id` column |
| v17 | ENH-2458 | `commit_events` table |
| v18 | ENH-2459 | `test_run_events` table |
| v19 | ENH-2581 | `raw_events` source-of-truth table |
| v20 | ENH-2461 | `usage_events` table (real LLM token counts + cost) |
| v21 | FEAT-2478 | OTel `invocation_id` / `provider_vendor` attribution on `usage_events` |
| v22 | ENH-2492 | `orchestration_runs` table (per-issue batch outcomes) |
| v23 | ENH-2463 | `loop_runs` table (per-run FSM loop summaries) |
| v24 | ENH-2497 | `agent_type` discriminator column on `tool_events` |
| v25 | ENH-2511 | `mcp_server`/`mcp_tool`/`mcp_outcome`/`latency_ms` columns on `tool_events` |
| v26 | ENH-2466 | `learning_test_events` table (Learning Test Registry mirror) |
| v27 | ENH-2495 | `session_lifecycle_events` table (handoff/compaction/sweep transitions) |

v15–v18 and v20–v27 are EPIC-2457 coverage expansions and related observability migrations; all migrations are additive — no user action is required when the schema version advances.

---

## What Gets Recorded

| Table | What it stores |
|-------|---------------|
| `tool_events` | Every tool call (Bash, Read, Write, etc.) with byte counts (`bytes_in`, `bytes_out`, `result_size`), `cache_hit` flag, and `agent_type` (nullable; populated with the dispatched subagent name for `tool_name="Task"` rows, `NULL` otherwise — ENH-2497) |
| `file_events` | File reads and writes with path, operation, and associated issue ID |
| `issue_events` | Issue state transitions: captured, started, completed, deferred. v16 added a `session_id` column (indexed) so the `issue_sessions` view no longer relies on timestamp overlap (ENH-2462). |
| `issue_snapshots` | Point-in-time snapshots of issue content at lifecycle transitions (`open`, `done`, `cancelled`); dedup index on `(issue_id, transition)`; indexed for full-text search (FTS) via the `search_index` with `kind="snapshot"`. Populated live by `set_status` and by `ll-session backfill --snapshots` for historical issues. Used by `ll-history-context` as a last-resort fallback when no corrections or FTS rows match an issue (ENH-2151). |
| `loop_events` | FSM (finite-state machine) loop transitions with loop name and retry count |
| `message_events` | User message content for FTS indexing |
| `assistant_messages` | Assistant response content with tool-use count |
| `user_corrections` | Messages matching correction patterns: message-start signals (`no,`/`no!`, `don't`, `stop`, `revert`, `that's wrong`, `not like that`, `!remember`) and anywhere-in-message phrases (`instead`, `actually that/this/it`, `you missed`, `should be` (excluding `should be fine/ok/good/great/...`), `wrong approach`, `remember that`, `always use`, `never use`, `from now on`, `I meant...not`, `not...use`); extend with `analytics.capture.correction_patterns` (see [Configuration Reference](#configuration-reference)) |
| `skill_events` | `/ll:` skill invocations with args. v15 added nullable `exit_code`, `success`, and `duration_ms` columns so `ll-session skill-stats` can compute per-skill success rates (ENH-2460). |
| `cli_events` | `ll-*` CLI commands with exit code and duration |
| `sessions` | Maps session IDs to their `.jsonl` file paths |
| `commit_events` | Git commit metadata: `commit_sha` (unique), `parent_sha`, message, author, branch, `issue_id` (linked when known), `files_json`. Populated live by the session-start backfill. Queryable via `ll-session recent --kind commit` (ENH-2458, v17). |
| `test_run_events` | Pytest runs: `total`, `passed`, `failed`, `errored`, `skipped`, `duration_s`, `failing_names_json`, `head_sha`, `branch`, `command`, `env_label`. Queryable via `ll-session recent --kind test_run` (ENH-2459, v18). |
| `usage_events` | Real LLM token counts per assistant turn: `model`, `state` (always NULL from the parser path), `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cost_usd` (NULL for unpriced models). Derived from `raw_events` by `_backfill_usage_events()` (parses `message.usage` on `type == "assistant"` records). Queryable via `ll-session recent --kind usage` and `history_reader.recent_usage_events()`/`aggregate_usage()` (ENH-2461, v20; OTel attribution columns added in v21). |
| `orchestration_runs` | Final per-issue outcomes from `ll-auto`, `ll-parallel`, and `ll-sprint`: invocation-scoped `run_id`, driver, status, duration, failure reason, sprint wave label, optional PR URL, timestamps, and git context. Retries UPSERT the same `(run_id, issue_id)` and refresh FTS. Queryable via `ll-session recent --kind orchestration_run`, FTS search, export, and `history_reader.recent_orchestration_runs()`/`aggregate_orchestration_runs()` (ENH-2492, v22). |
| `summary_nodes` / `summary_spans` | LCM compaction summary tree (`summary_nodes` = nodes, `summary_spans` = message-link table). Populated when `history.compaction.enabled: true`; surface via `ll-history root --expand` and `ll-session expand/describe` (v10 / v12). |
| `correction_retirements` | Records corrections that have been "retired" by a matching decision rule (topic fingerprint → rule id). Lets `ll-history analyze` show how often a past correction is now auto-handled (v13). |
| `loop_runs` | One row per completed FSM loop run: `run_id` (archive-time identifier, unique), `loop_name`, `started_at`/`ended_at`, `final_state`, `iterations`, `terminated_by`, `error`, nullable `evaluator_score`/`diagnostics_path`, and git context. Written best-effort by `FSMExecutor._finish()`. Queryable via `ll-session recent --kind loop_run` and `history_reader.recent_loop_runs()`/`find_loop_run()`/`aggregate_loop_runs()` (ENH-2463, v23). |
| `learning_test_events` | Mirror of the Learning Test Registry (`.ll/learning-tests/*.md`): `record_id` (slugified target, unique), `target`, `status`, `assertions_json`, `date`, `raw_output_path`. Written best-effort by `ll-learning-tests prove`/`mark-stale`/`orphans --mark-stale` (UPSERT — re-proves overwrite in place); reconciled from disk for out-of-band edits by `ll-session backfill`. Queryable via `ll-session recent --kind learning_test`, FTS search, and `history_reader.recent_learning_tests()`/`find_learning_test()` (ENH-2466, v26). |
| `session_lifecycle_events` | Session-lifecycle/handoff transitions: `session_id`, `event` (`handoff_needed`/`compaction`/`stale_ref_sweep`, open TEXT — no CHECK constraint), `detail` (JSON), `head_sha`, `branch`. Written best-effort by `record_session_lifecycle_event()` from `context-monitor.sh` (80%-threshold crossing), `pre_compact.handle()` (after state persistence), and `sweep_stale_refs.handle()` (once per invocation, including zero findings). First-write-only — no historical backfill. Queryable via `ll-session recent --kind session_lifecycle`, FTS search, and `history_reader.recent_lifecycle_events()`/`handoff_frequency()` (ENH-2495, v27). |

Capture is controlled per-signal via `analytics.capture.*` config (`scripts/little_loops/config-schema.json`):
- `analytics.capture.file_events` (bool, default `true`) — gate `file_events` recording
- `analytics.capture.corrections` (bool, default `true`) — gate `user_corrections` recording
- `analytics.capture.skills` (array of glob patterns, default `["*"]`) — which skill names get recorded to `skill_events`; e.g. `["create-sprint", "manage-issue"]` records only those skills
- `analytics.capture.cli_commands` (array of glob patterns, default `["*"]`) — which `ll-*` CLI command names get recorded to `cli_events`
- `analytics.capture.correction_patterns` (array of regex strings, default `[]`) — additional patterns appended to the built-in correction detector (built-ins always remain active; see [What Gets Recorded](#what-gets-recorded) for the full built-in list)

---

## Getting Started: Backfill

The database starts empty. Populate it by backfilling from your existing session JSONL files and issue directory.

### Full backfill

```bash
ll-session backfill
```

Reads three sources sequentially:

1. **Issues directory** (`.issues/*/`) → `issue_events`
2. **Loop state** (`.loops/.running/`, `.loops/.history/`) → `loop_events`
3. **Session JSONL files** (discovered from your project folder) → `tool_events`, `message_events`, `assistant_messages`, `sessions`, `user_corrections`

Output shows counts per table:

```
{
  "issues": 42,
  "loops": 8,
  "tools": 1204,
  "messages": 389,
  "assistant_messages": 401,
  "sessions": 23,
  "corrections": 17,
  "summaries": 0,
  "snapshots": 0
}
```

### Incremental backfill

```bash
ll-session backfill --since 2026-05-01
```

Processes only session JSONL files modified after the given date. Faster than a full backfill and safe to run frequently. The session-start hook runs this automatically at the start of each session (ENH-1830), so the database stays current without manual intervention.

You can specify which host's session files to scan if you use multiple Claude Code hosts:

```bash
ll-session backfill --host claude-code   # default
ll-session backfill --host codex
ll-session backfill --host opencode
```

---

## Querying Sessions

### Full-text search

```bash
ll-session search --fts "authentication middleware"
ll-session search --fts "rate limit" --kind correction
ll-session search --fts "worktree" --kind tool --limit 5
```

Returns BM25-ranked results across all event tables. Use `--kind` to restrict to one table type: `tool`, `file`, `issue`, `loop`, `correction`, `message`, `skill`, `cli`, `snapshot`, `commit`, `test_run`, `usage`, `orchestration_run`, `loop_run`, `learning_test`, `session_lifecycle` (the full list is sourced from `VALID_KINDS`).

### Most recent events

```bash
ll-session recent --kind correction
ll-session recent --kind loop --limit 10
ll-session recent --kind issue --issue BUG-1759
```

`--kind` is required unless `--issue` is given (in which case sessions for that issue are listed instead). `--kind` + `--issue` together filters events of that kind to the issue.

### All events for an issue

```bash
ll-session related BUG-1759
```

Returns every event (tools, files, corrections, loop transitions) linked to that issue ID, chronologically ordered.

### Resolve a session's JSONL file

```bash
ll-session path abc123-def456
# → /Users/you/.claude/projects/my-project/abc123-def456.jsonl
```

Useful when you want to open the raw session transcript.

### Export tables as JSONL

```bash
ll-session export                                    # all non-message tables, to stdout
ll-session export --tables issue_event correction     # only these types
ll-session export --since 2026-06-01 -o export.jsonl  # date-filtered, to a file
ll-session export --include-messages                  # also include message_events (~46K rows)
```

Dumps selected tables as newline-delimited JSON (one record per line, each tagged with a `"type"` field) for visualization or external tooling. `--tables` accepts one or more of: `session`, `issue_event`, `issue_snapshot`, `skill_event`, `loop_event`, `correction`, `summary_node`, `commit_event`, `test_run_event`, `usage_event`, `orchestration_run`, `message_event`. When `--tables` is omitted, the default set is every type except `message_event` (pass `--include-messages` to add it back, or select it explicitly via `--tables`). `--since` filters each table by its own timestamp column (`started_at` for `session`, `created_at` for `summary_node`, `ended_at` for `orchestration_run`, `ts` for the rest) and accepts an ISO 8601 date or datetime. `-o FILE` / `--output FILE` writes to a file instead of stdout and prints a summary count on success; without it, records stream to stdout with no trailing summary (so output stays pipeable).

---

## Issue ↔ Session Cross-References

The `issue_sessions` view joins issue lifecycle events with session messages. Since v16 (ENH-2462), the join is **authoritative**: every `issue_events` row carries a `session_id` column (indexed) recorded at write time, so the view no longer infers association from timestamp overlap. A legacy view `legacy_issue_sessions_ts_overlap` is retained as a backward-compat fallback for sessions recorded before the v16 migration — new code should use `issue_sessions` directly.

**List sessions that worked on an issue:**

```bash
ll-history sessions BUG-1759
```

**Event stream for an issue filtered to one session:**

```bash
ll-session recent --kind tool --issue BUG-1759
```

**Navigate within a session:**

```bash
ll-session expand 42       # message_events under summary node 42 (if compaction enabled)
ll-session describe 42     # metadata for summary node 42
```

---

## Planning Skill Injection

When you invoke a planning skill (`/ll:create-sprint`, `/ll:manage-issue`, `/ll:scope-epic`, `/ll:review-epic`), little-loops automatically injects a `## Historical Context` block drawn from history.db. This surfaces past corrections, recently touched files, and completed issues relevant to what you're planning — so the agent doesn't repeat mistakes from prior sessions.

**What the injected block looks like:**

```markdown
## Historical Context

- don't use HTTP-only cookies for refresh tokens (correction, 3 occurrences)
- authentication middleware needs CORS credentials flag (correction, 2 occurrences)
- file:src/middleware/auth.ts:write (7 days ago)
- file:src/utils/tokens.ts:write (7 days ago)
- completed: BUG-1759 — fix refresh token expiry (12 days ago)
```

**How injection is gated:**

The `history.planning_skills` config key controls which skills trigger injection. Default:

```json
{
  "history": {
    "planning_skills": ["create-sprint", "scope-epic", "manage-issue", "review-epic"]
  }
}
```

To add a skill or disable injection entirely:

```json
{
  "history": {
    "planning_skills": ["create-sprint", "scope-epic", "manage-issue", "review-epic", "my-skill"]
  }
}
```

```json
{
  "history": {
    "planning_skills": []
  }
}
```

**Effort and velocity context:**

Add `--effort` to get session count and cycle-time context for an issue:

```bash
ll-history-context BUG-1759 --effort
```

**How automation calls it:**

Skills call `ll-history-context --for-skill <name>`, which exits 0 with no output if the skill is not in `planning_skills`. This makes the gate cheap: no DB query if the skill isn't configured for injection.

---

## History Analytics

### Project summary

```bash
ll-history summary
ll-history summary --json
```

Issue counts, completion rate, and age distribution. Quick health check.

### Trend analysis

```bash
ll-history analyze
ll-history analyze --format markdown --period monthly
ll-history analyze --since 2026-01-01 --until 2026-06-01
```

Produces trend analysis: velocity, subsystem breakdown, tech debt signals. Useful for sprint retrospectives and capacity planning.

### Export documentation from issue history

```bash
ll-history export "authentication"
ll-history export "rate limiting" --format narrative --output docs/rate-limiting-context.md
ll-history export "API design" --type FEAT --since 2026-01-01 --scoring hybrid
```

Generates prose documentation from completed issues matching the topic. The `hybrid` scoring mode combines BM25 keyword matching with semantic overlap. Useful for onboarding docs and ADRs.

### Project root summary (requires compaction)

```bash
ll-history root
ll-history root --expand
```

Shows the top-level condensed summary node when LCM compaction is enabled. `--expand` drills down to the underlying message events. See [LCM Compaction](#advanced-lcm-compaction) below.

### Test runs

```bash
ll-session recent --kind test_run --limit 5
# Filtering by branch is not supported on `recent`; use `ll-session backfill --branch main --since ...` for branch-scoped queries.
```

Each row is a pytest invocation captured live during a session or by `ll-session backfill` from a recorded run: `total`, `passed`, `failed`, `errored`, `skipped`, `duration_s`, `failing_names_json`, `head_sha`, `branch`, `command`, `env_label`. Use this to spot a branch where tests started failing, or to find the commit that flipped a passing run red. (ENH-2459.)

### Skill success signal

```bash
ll-session skill-stats
ll-session skill-stats --skill /ll:manage-issue --window-days 30
```

Per-skill invocation count, completion count, and success rate, derived from the `exit_code` / `success` / `duration_ms` columns on `skill_events` (added in v15, ENH-2460). Use this to surface skills that users are pushing back on most, or to measure whether a recent change improved a skill's reliability.

## Session Log Tooling (`ll-logs`)

`ll-logs` operates directly on the host's session JSONL files rather than history.db. Use it for analysis that needs raw session-level data.

### Invocation frequency and corrections

```bash
ll-logs stats --project .
ll-logs stats --project . --sort corrections --window-days 30
```

Skill invocation frequency ranked by usage or correction rate. Tells you which skills users are pushing back on most.

### Mine failed commands for bugs

```bash
ll-logs scan-failures --project .
ll-logs scan-failures --project . --capture --window-days 14
```

Finds failed `ll-*` CLI invocations in session logs, clusters by error signature, and optionally creates BUG issue files (`--capture`).

### Identify unused skills

```bash
ll-logs dead-skills --project .
ll-logs dead-skills --project . --threshold 5 --window-days 90
```

Lists skills from the catalog with zero or few invocations in the given window. Useful for identifying candidates for pruning or deprecation.

### Compare two sessions

```bash
ll-logs diff SESSION_A SESSION_B
```

Behavioral comparison: which skills were used in each session, tool-chain sequences, correction frequency, error rates. Good for understanding why one session solved a problem and another didn't.

### Export eval fixtures

```bash
ll-logs eval-export --skill manage-issue --limit 50 --out fixtures/manage-issue.yaml
ll-logs eval-export --issue FEAT-1933 --out fixtures/feat-1933-turns.yaml
```

Extracts turn-pair fixtures from session logs for SFT training corpus construction. Filtered by skill name or issue ID. Requires schema v11+.

---

## Advanced: LCM Compaction

By default, history.db stores raw events only. Enable LCM-style compaction to additionally generate hierarchical summaries:

```json
{
  "history": {
    "compaction": {
      "enabled": true,
      "budget_tokens": 4096
    }
  }
}
```

When enabled, `ll-session backfill` calls LLM summarization after ingesting session JSONL files. It produces:

- **Per-session leaf nodes** — compressed summaries of individual session content
- **Per-session condensed nodes** — bullet-point distillations when a session exceeds the token budget
- **Cross-session condensed nodes** — recursive summaries when enough per-session nodes accumulate
- **Project root node** — a single top-level summary accessible via `ll-history root`

The compaction algorithm (LCM Algorithm 3) uses a three-level escalation: normal LLM → aggressive bullet-point → deterministic truncation.

Three optional keys tune the pass (see [Configuration Reference](#configuration-reference)): `model` and `timeout` control the summarization LLM calls, and `max_level` caps cross-session recursion depth (default: unbounded — recurses until a single root node remains).

> Compaction is disabled by default because it makes background LLM calls during backfill. Enable it when you want `ll-history root` and `ll-session expand/describe` to be useful.

Navigate the summary DAG:

```bash
ll-session describe 42     # show metadata for node 42
ll-session expand 42       # show original messages under node 42
ll-session grep "auth" --summary-id 42   # search within a node's scope
```

---

## Retention & Pruning

history.db grows over time. The `prune` command deletes raw events older than a configured age and VACUUMs the database:

```bash
ll-session prune --dry-run   # show what would be deleted, without deleting
ll-session prune             # apply
ll-session prune --json      # machine-readable result
```

`--dry-run` counts eligible rows per table without deleting them (`vacuumed` is always `false` in this mode). `--json` prints the result dict instead of a human-readable summary.

**Tables pruned** (age-based, by `ts` column): `tool_events`, `cli_events`, `file_events`, `message_events`. **Never pruned**, regardless of age: `issue_events`, `user_corrections` (and all other tables not in the prunable list) — these are considered high-value and are excluded by design.

**Gating:** both minimums below must be exceeded before *any* row is deleted (dual-gated, not either/or):

- `analytics.retention.min_project_age_days` (default: 365) — project age is measured as `MIN(started_at)` from the `sessions` table, not wall-clock repo age
- `analytics.retention.min_db_size_mb` (default: 800) — measured as the `.ll/history.db` file size on disk

If either gate is unmet, `prune` returns a `gate_unmet` list explaining why and deletes nothing. If both gates pass but `raw_event_max_age_days` is `null`, pruning is considered to have "run" but no age cutoff is applied (no rows deleted). Otherwise, rows in the prunable tables older than the cutoff are deleted, the transaction is committed, and a `VACUUM` runs afterward on a separate connection (avoids transaction conflicts) to reclaim disk space.

**Result shape** (both human and `--json` output derive from this dict): `pruned` (bool, whether pruning executed), `gate_unmet` (list of human-readable reasons), `project_age_days`, `db_size_mb`, `deleted` (dict of table → row count, actual or dry-run-projected), `vacuumed` (bool).

**When to prune:** If your project is under 1 year old, leave the defaults alone — the guards prevent premature pruning. Only lower `raw_event_max_age_days` if `ll-session` commands feel slow (consistently > 500ms), which indicates the database has grown large.

The raw event max age:

```json
{
  "analytics": {
    "retention": {
      "raw_event_max_age_days": 90
    }
  }
}
```

---

## Configuration Reference

All keys live under `history.*` and `analytics.*` in `.ll/ll-config.json`.

| Key | Default | Description |
|-----|---------|-------------|
| `history.planning_skills` | `["create-sprint", "scope-epic", "manage-issue", "review-epic"]` | Skills that trigger `## Historical Context` injection |
| `history.velocity_window` | `10` | Issue count window for velocity calculations |
| `history.max_age_days` | `null` | Global max age for all history queries (null = no limit) |
| `history.db_path` | `null` | Override the default `.ll/history.db` location; relative paths resolve against the project root. The `LL_HISTORY_DB` env var takes precedence over this |
| `history.effort_fields` | `["session_count", "cycle_time_days"]` | Fields extracted from history.db for `ll-history-context --effort` reporting |
| `history.session_digest.enabled` | `true` | Inject project-wide digest block at session start |
| `history.session_digest.days` | `7` | Lookback window for session digest |
| `history.session_digest.char_cap` | `1200` | Max characters in injected context block |
| `history.session_digest.sections` | `[]` | Ordered list of digest section providers to include; empty = all v1 providers |
| `history.compaction.enabled` | `false` | LCM summarization during backfill |
| `history.compaction.budget_tokens` | `4096` | Token budget per summary node |
| `history.compaction.cross_session_enabled` | `true` | Build cross-session condensed nodes |
| `history.compaction.model` | `null` | Model override for compaction LLM calls (null = host default) |
| `history.compaction.timeout` | `60` | Timeout (seconds) per compaction LLM call; on timeout, escalation falls through to deterministic truncation |
| `history.compaction.max_level` | `null` | Max cross-session condensation depth (null = recurse until one root node remains) |
| `history.evolution.feedback_min_recurrence` | `2` | Min recurrence count for a correction to surface in evolution analysis |
| `history.evolution.bypass_min_count` | `2` | Min bypass count threshold for evolution signal suppression |
| `history.go_no_go.correction_penalty` | `-0.2` | Score penalty applied per correction event in go/no-go scoring |
| `history.capture_issue.dup_overlap_threshold` | `0.7` | Overlap ratio above which a new captured issue is considered a duplicate |
| `analytics.retention.min_project_age_days` | `365` | Min project age before pruning is allowed |
| `analytics.retention.min_db_size_mb` | `800` | Min DB size before pruning is allowed |
| `analytics.retention.raw_event_max_age_days` | `90` | Age threshold for raw event deletion |
| `analytics.capture.file_events` | `true` | Record file reads/writes |
| `analytics.capture.corrections` | `true` | Record user correction messages |
| `analytics.capture.skills` | `["*"]` | Glob patterns for skill names to record to `skill_events` |
| `analytics.capture.cli_commands` | `["*"]` | Glob patterns for CLI command names to record to `cli_events` |
| `analytics.capture.correction_patterns` | `[]` | Additional regex patterns for correction detection |

---

## See Also

- [Session Handoff Guide](SESSION_HANDOFF.md) — context monitoring and session continuation; the session-start hook that triggers incremental backfill
- [Workflow Analysis Guide](WORKFLOW_ANALYSIS_GUIDE.md) — `ll-messages` for extracting and analyzing user message patterns
- [CLI Reference](../reference/CLI.md) — complete flag listings for `ll-session`, `ll-history`, `ll-history-context`, `ll-logs`
