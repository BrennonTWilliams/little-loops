# History & Session Guide

Long-term observability for your little-loops project: what ran, what changed, what was corrected, and why.

## Table of Contents

- [What Is history.db?](#what-is-historydb)
- [What Gets Recorded](#what-gets-recorded)
- [Getting Started: Backfill](#getting-started-backfill)
- [Querying Sessions](#querying-sessions)
- [Issue ↔ Session Cross-References](#issue--session-cross-references)
- [Planning Skill Injection](#planning-skill-injection)
- [History Analytics](#history-analytics)
- [Session Log Tooling (ll-logs)](#session-log-tooling-ll-logs)
- [Optional: LCM Compaction](#optional-lcm-compaction)
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
| How long issue BUG-123 took | `ll-history-context BUG-123 --effort` |
| Which sessions worked on issue FEAT-42 | `ll-history sessions FEAT-42` |
| A trend analysis for the last quarter | `ll-history analyze --since 2026-01-01 --format markdown` |
| All tools used across sessions | `ll-session recent --kind tool --limit 20` |
| What the project summary looks like | `ll-history summary` |
| What shipped recently (commits with issue linkage) | `ll-session recent --kind commit` |
| Last pytest run on this branch | `ll-session recent --kind test_run --limit 1` |
| Which skills succeed vs. fail | `ll-session skill-stats` |

---

## What Is history.db?

`.ll/history.db` is a per-project SQLite database that accumulates a long-lived event history across every Claude Code session. Where session JSONL files are ephemeral per-conversation snapshots, history.db is the persistent record: it indexes tool invocations, file modifications, issue state transitions, loop executions, user corrections, and session-to-message content across all sessions that have ever run in this project. Set `LL_HISTORY_DB=/path/to/alt.db` to override the default location (useful for test isolation or CI).

The database is **additive-only** — backfill is idempotent (dedup indexes prevent duplicates on repeated runs) and nothing is deleted unless you explicitly prune. Schema migrations apply automatically on connect. Current schema version: 18. The v15–v18 migrations are driven by EPIC-2457 children (ENH-2458 `commit_events`, ENH-2459 `test_run_events`, ENH-2460 `skill_events` completion columns, ENH-2462 `issue_events.session_id`) and are additive — no user action is required when the schema version advances.

---

## What Gets Recorded

| Table | What it stores |
|-------|---------------|
| `tool_events` | Every tool call (Bash, Read, Write, etc.) with token counts and cache-hit flag |
| `file_events` | File reads and writes with path, operation, and associated issue ID |
| `issue_events` | Issue state transitions: captured, started, completed, deferred. v16 added a `session_id` column (indexed) so the `issue_sessions` view no longer relies on timestamp overlap (ENH-2462). |
| `issue_snapshots` | Point-in-time snapshots of issue content at lifecycle transitions (`open`, `done`, `cancelled`); dedup index on `(issue_id, transition)`; FTS-indexed via the `search_index` with `kind="snapshot"`. Populated live by `set_status` and by `ll-session backfill --snapshots` for historical issues. Used by `ll-history-context` as a last-resort fallback when no corrections or FTS rows match an issue (ENH-2151). |
| `loop_events` | FSM state-machine transitions with loop name and retry count |
| `message_events` | User message content for FTS indexing |
| `assistant_messages` | Assistant response content with tool-use count |
| `user_corrections` | Messages matching correction patterns ("no", "don't", "instead", "remember") |
| `skill_events` | `/ll:` skill invocations with args. v15 added nullable `exit_code`, `success`, and `duration_ms` columns so `ll-session skill-stats` can compute per-skill success rates (ENH-2460). |
| `cli_events` | `ll-*` CLI commands with exit code and duration |
| `sessions` | Maps session IDs to their `.jsonl` file paths |
| `commit_events` | Git commit metadata: `commit_sha` (unique), `parent_sha`, message, author, branch, `issue_id` (linked when known), `files_json`. Populated live by the session-start backfill. Queryable via `ll-session recent --kind commit` (ENH-2458, v17). |
| `test_run_events` | Pytest runs: `total`, `passed`, `failed`, `errored`, `skipped`, `duration_s`, `failing_names_json`, `head_sha`, `branch`, `command`, `env_label`. Queryable via `ll-session recent --kind test_run` (ENH-2459, v18). |
| `summary_nodes` / `summary_spans` | LCM compaction summary tree (`summary_nodes` = nodes, `summary_spans` = message-link table). Populated when `history.compaction.enabled: true`; surface via `ll-history root --expand` and `ll-session expand/describe` (v10 / v12). |
| `correction_retirements` | Records corrections that have been "retired" by a matching decision rule (topic fingerprint → rule id). Lets `ll-history analyze` show how often a past correction is now auto-handled (v13). |

Two captures are opt-in via config (both enabled by default):
- `analytics.capture.file_events` — file reads/writes
- `analytics.capture.corrections` — user correction signals

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

Returns BM25-ranked results across all event tables. Use `--kind` to restrict to one table type: `tool`, `file`, `issue`, `loop`, `correction`, `message`, `skill`, `cli`, `commit`, `test_run`.

### Most recent events

```bash
ll-session recent --kind correction
ll-session recent --kind loop --limit 10
ll-session recent --kind issue --issue BUG-1759
```

`--kind` is required. `--issue` filters to events associated with a specific issue ID.

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
ll-history-context ENH-1708 --effort
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

Shows the top-level condensed summary node when LCM compaction is enabled. `--expand` drills down to the underlying message events. See [LCM Compaction](#optional-lcm-compaction) below.

### Test runs

```bash
ll-session recent --kind test_run --limit 5
ll-session recent --kind test_run --branch main
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
ll-session prune --dry-run   # show what would be deleted
ll-session prune             # apply
```

**When to prune:** If your project is under 1 year old, leave the defaults alone — the guards prevent premature pruning. Only lower `raw_event_max_age_days` if `ll-session` commands feel slow (consistently > 500ms), which indicates the database has grown large.

Pruning is guarded by two minimums to prevent accidental data loss on young or small projects:

- `analytics.retention.min_project_age_days` (default: 365) — don't prune if the project is younger than this
- `analytics.retention.min_db_size_mb` (default: 800) — don't prune if the database is smaller than this

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
| `history.session_digest.enabled` | `true` | Inject project-wide digest block at session start |
| `history.session_digest.days` | `7` | Lookback window for session digest |
| `history.session_digest.char_cap` | `1200` | Max characters in injected context block |
| `history.compaction.enabled` | `false` | LCM summarization during backfill |
| `history.compaction.budget_tokens` | `4096` | Token budget per summary node |
| `history.compaction.cross_session_enabled` | `true` | Build cross-session condensed nodes |
| `analytics.retention.min_project_age_days` | `365` | Min project age before pruning is allowed |
| `analytics.retention.min_db_size_mb` | `800` | Min DB size before pruning is allowed |
| `analytics.retention.raw_event_max_age_days` | `90` | Age threshold for raw event deletion |
| `analytics.capture.file_events` | `true` | Record file reads/writes |
| `analytics.capture.corrections` | `true` | Record user correction messages |
| `analytics.capture.correction_patterns` | `[]` | Additional regex patterns for correction detection |

---

## See Also

- [Session Handoff Guide](SESSION_HANDOFF.md) — context monitoring and session continuation; the session-start hook that triggers incremental backfill
- [Workflow Analysis Guide](WORKFLOW_ANALYSIS_GUIDE.md) — `ll-messages` for extracting and analyzing user message patterns
- [CLI Reference](../reference/CLI.md) — complete flag listings for `ll-session`, `ll-history`, `ll-history-context`, `ll-logs`
