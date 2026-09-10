---
id: FEAT-3445
type: FEAT
title: 'Workspace activity reader: cross-repo per-repo and union activity counts over
  a since window'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:04Z'
---

# FEAT-3445: Workspace activity reader: cross-repo per-repo and union activity counts over a since window

## Summary

New reusable cross-repo reader `aggregate_workspace_activity()` that returns per-repo and workspace-total activity counts — loops run, loops completed, issues completed, issues deferred, plus an `instrumented` flag per member — over a `since` window. A **sibling** to `aggregate_history_dbs()` in a new module, not a generalization of it.

## Context

Identified from a design review of a little-loops-hermes task. 1.162.0 shipped cross-repo history.db aggregation (FEAT-3399/3409/3410/3418) scoped exclusively to agent-quality regression detection (`ll-history quality --workspace`). A downstream consumer (hermes' `ll_briefing` / `ll_portfolio`) needs a single cross-repo activity/event read; today it shells out per project (`ll-loop list --running --json`, `ll-issues list --json`) and opens each project's `.ll/history.db` with its own sqlite3, once per project, every sync.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

- Per-project shelling + per-project sqlite is O(members) subprocess/connection cost every sync, and hermes re-implements discovery and skip semantics that already exist here.
- `aggregate_history_dbs()` cannot serve this: its kwargs are quality-shaped (`min_sample`, `sensitivity`, `baseline_windows`, `latest_only`) and it runs `find_issues(BRConfig(member.repo_path))` per member, which activity counts don't need.
- Quality's `skipped: list[tuple[str, str]]` string pairs can't distinguish "no history" (uninstrumented) from "history present but unreadable" (schema skew) — the exact distinction a briefing consumer needs.

## Proposed Solution

New module `scripts/little_loops/issue_history/workspace_activity.py`:

```python
aggregate_workspace_activity(members: list[WorkspaceMember], *, since: str | None) -> WorkspaceActivityResult
```

**Metric definitions** (single-db read-only SQL per `ok` member):

| Metric | Source | Predicate |
|---|---|---|
| `loops_run` | `loop_runs` | `started_at >= since` |
| `loops_completed` | `loop_runs` | `ended_at IS NOT NULL AND ended_at >= since` (running loops have NULL `ended_at` — schema.py:577-578 — and must not count) |
| `issues_completed` | `issue_events` | `transition = 'done' AND ts >= since` |
| `issues_deferred` | `issue_events` | `transition = 'deferred' AND ts >= since` |
| `instrumented` | — | member status is `ok` (db present, readable, schema current); NOT a count — absence stays distinguishable from zero |

`since is None` = unbounded (all history).

**Timestamp caveat (must handle, not ignore):** timestamp formats are mixed — `loop_runs.started_at` is written as `2026-09-10T22:48:17.151663+00:00`, while `ended_at` and `issue_events.ts` are `2026-09-10T22:51:08Z`. Naive ISO string comparison is correct for date-granularity windows but wrong at sub-second/datetime granularity (`Z` vs `+00:00` suffix ordering). Wrap both sides in SQLite `datetime()` (which normalizes both forms) rather than raw string compare; existing `ts >= ?` sites (evolution.py:115, history_reader/events.py:245) get away with raw compare only because `ts` is uniformly `Z`-formatted.

**Counting semantics (decision, resolved):** an issue counts **once per repo it appears in** — workspace totals are the sum of per-repo counts. Do NOT dedupe on bare `issue_id` across repos: every little-loops repo numbers issues from 1, so same-ID issues in different repos are usually *different* logical issues colliding (this is FEAT-3418's own rationale for the `#r{i}` discriminator). If a future consumer truly has mirrored issues needing cross-repo merge, that requires a workspace-canonical id, not bare `issue_id` — explicitly out of scope.

**No ATTACH union (decision, resolved):** under per-(repo, issue) counting every metric is exactly sum-decomposable — run_ids are UUIDs unique to one member db, and `idx_issue_events_dedup` (unique on `(issue_id, transition)`, schema.py:198-199) already guarantees one `done`/`deferred` row per issue per db. The ATTACH/union machinery (`_open_union`, `_union_view_sql`, `_attach_limit`) earns its keep only for SQL-level joins/analytics over combined rows; for counts it adds a `SQLITE_LIMIT_ATTACHED` member ceiling and discriminator bookkeeping for zero semantic gain. Sum in Python instead.

**Member gating:** extract the per-member gate from `aggregate_history_dbs()` (workspace_quality.py:217-252: missing db → open `file:...?mode=ro` → `read_schema_version` check → skip-and-report) into a shared private helper used by both callers. The activity reader upgrades the skip record from a reason string to a structured status.

**Known limitation (document, do not solve):** FSM signals (stalls, cycles, rate-limits) are webhook-only and not stored in history.db; a history.db read cannot cover them.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Extract the member gate from `workspace_quality.aggregate_history_dbs()` into a shared helper; re-run the quality test suite unchanged.
2. Create `workspace_activity.py` with the enums/dataclasses above.
3. Implement per-member count SQL + Python-side totals.
4. Unit tests: mixed timestamp formats, NULL `ended_at`, missing/skewed/unreadable members, zero-ok workspace, unbounded `since`.

## Impact

- New public module (goes in `docs/reference/API.md`); no changes to existing behavior beyond the gate-helper extraction in `workspace_quality.py`.
- Unblocks the CLI surface issue (`ll-history activity`) and the hermes consumer.

## API/Interface

```python
class MemberActivityStatus(str, Enum):
    OK = "ok"                      # counts present (possibly zero)
    DB_MISSING = "db_missing"      # no history.db -> instrumented: False
    SCHEMA_SKEW = "schema_skew"    # version mismatch -> instrumented: True, counts unreadable
    UNREADABLE = "unreadable"      # sqlite3.Error on open/read -> instrumented: True

@dataclass(frozen=True)
class RepoActivity:
    status: MemberActivityStatus
    instrumented: bool
    reason: str | None = None                    # human detail for non-ok statuses
    loops_run: int | None = None                 # None iff status != OK (not 0)
    loops_completed: int | None = None
    issues_completed: int | None = None
    issues_deferred: int | None = None

@dataclass(frozen=True)
class WorkspaceActivityResult:
    since: str | None
    per_repo: dict[str, RepoActivity]            # key: "{repo_path.name} ({role})", matches quality
    totals: WorkspaceTotals | None               # None iff no ok members
    def to_dict(self) -> dict[str, Any]: ...
```

`WorkspaceTotals` sums each count over `ok` members only, plus `members: int` and `instrumented_members: int`. Schema-skewed/unreadable members are excluded from totals (matching quality's gate) — stated so an implementer doesn't have to re-derive it.

## Acceptance Criteria

1. `aggregate_workspace_activity(members, since=...)` returns one `RepoActivity` per member; non-ok members carry `None` counts, never `0`.
2. `instrumented` is False only for `db_missing`; True for `schema_skew`/`unreadable` (both report `reason`).
3. Totals equal the sum of `ok` members' counts; zero `ok` members yields `totals=None`, no exception.
4. Running loops (NULL `ended_at`) never count as completed; loops started before `since` but ended after do.
5. Timestamp comparison is format-safe across `+00:00`-micros and `Z` forms (via `datetime()` normalization or equivalent).
6. Member databases are opened read-only (`file:...?mode=ro`, `PRAGMA query_only`), never migrated — same contract as workspace_quality.
7. The shared member-gate helper is used by both `aggregate_history_dbs()` and the new reader; quality's behavior is byte-identical after extraction (existing tests pass unmodified).
8. The module docstring documents the FSM-signals limitation verbatim.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design; where the workspace aggregation layer sits |
| architecture | docs/reference/API.md | Python module reference — new public module + `workspace_quality` gate extraction land here |

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-10T23:53:43 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
