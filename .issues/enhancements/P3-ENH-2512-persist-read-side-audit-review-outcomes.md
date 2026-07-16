---
id: ENH-2512
title: Persist read-side audit / review outcomes into history.db
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
  - audit
  - review
  - captured
---

# ENH-2512: Persist read-side audit / review outcomes into history.db

## Summary

`/ll:review-epic`, `/ll:review-sprint`, `/ll:review-loop`,
`/ll:audit-architecture`, `/ll:audit-claude-config`, `/ll:audit-docs`,
`/ll:audit-loop-run`, and the `--comment` / `--fix` modes of the
built-in `code-review` / `simplify` commands each produce a structured
review with severity counts and findings. Today those reviews only
survive in stdout or, at best, in `.loops/diagnostics/<loop>-<ts>.md`.
So the velocity-tracking question "how many P0 review findings closed
this week?" is unanswerable. Add a `review_events` table with
`(reviewer_skill, target_kind, target_id, severity_counts,
findings_json_summary, ts)` so opinion-bearing audits become queryable.
Adjacent to ENH-2493 (which captures executors, not audits).

## Motivation

- **Reviews are the third read-side signal.** ENH-2493 captures
  *executor* outcomes (test runs, harness runs). ENH-2504 captures
  *verifier* outcomes (readiness checks, confidence checks). This
  issue captures *reviewer* outcomes (architecture audits, sprint
  reviews, loop audits) — the third leg of the read-side stool.
- **Velocity-tracking needs the row.** A weekly review of "P0 findings
  closed" requires: (a) the review event when the finding was raised,
  (b) the issue that addressed the finding, (c) the issue's
  `status=done` event. The first row doesn't exist; the second and
  third do (ENH-2462, `issue_events`). One new table completes the
  join.
- **Different shape than ENH-2493.** ENH-2493 captures `runner` /
  `target` / `semantic_verdict` (binary-ish). This issue captures
  `severity_counts` (a multi-bucket histogram) and
  `findings_json_summary` (a JSON summary, not the full findings list —
  full list lives in the diagnosis artifact at the path captured in the
  row).
- **Reuses producer patterns.** The audit skills already write to
  `.loops/diagnostics/<target>-<ts>.md` (per the
  `loop-specialist`/`audit-loop-run` precedent). Adding a sibling
  DB write is one line per producer.

## Current Behavior

- `/ll:review-epic EPIC-2457` produces a structured health report to
  stdout; no DB row.
- `/ll:audit-architecture` produces findings to stdout; no DB row.
- `/ll:audit-loop-run rn-implement` produces a verdict-and-recommendations
  block; the killed-run analysis at `autodev-bug2501-kill-analysis.md`
  (2026-07-07) is exactly this kind of artifact, and it's only
  available as a one-off file.
- `/ll:simplify` and `/code-review --fix` produce change proposals;
  findings aren't captured.

## Expected Behavior

- A `review_events` table records one row per audit/review invocation
  with `reviewer_skill` (`review-epic` | `audit-architecture` |
  `audit-claude-config` | `audit-docs` | `audit-loop-run` | `review-sprint`
  | `review-loop` | `code-review` | `simplify`),
  `target_kind` (`epic` | `sprint` | `loop` | `repo` | `pr` | `config`),
  `target_id`, `severity_counts` (JSON: `{"p0": 1, "p1": 3, "p2": 7,
  "info": 12}`), `findings_json_summary` (JSON: top-N findings with
  file:line and short title), `findings_count`, plus `session_id`,
  `ts`, `head_sha`, `branch`.
- Each audit skill calls `record_review_event(...)` before returning
  (best-effort).
- The diagnosis artifact path (`.loops/diagnostics/<loop>-<ts>.md` or
  `.ll/reviews/<target>-<ts>.md`) is captured in `findings_json_summary
  .artifact_path` so the DB row points to the full report.
- `ll-session recent --kind review_event` returns rows;
  `history_reader.review_velocity(since=None)` rolls up
  severity-count totals per week.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    reviewer_skill TEXT NOT NULL, -- "review-epic" | "audit-architecture" | ...
    target_kind TEXT,             -- "epic" | "sprint" | "loop" | "repo" | "pr" | "config"
    target_id TEXT,               -- "EPIC-2457" | "rn-implement" | ...
    severity_counts TEXT,         -- JSON: {"p0": 1, "p1": 3, "p2": 7, "info": 12}
    findings_count INTEGER,
    findings_json_summary TEXT,   -- JSON: top-N findings; includes artifact_path key
    verdict TEXT,                 -- "pass" | "warn" | "fail" | "degraded" | "refused"
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_skill ON review_events(reviewer_skill);
CREATE INDEX IF NOT EXISTS idx_review_target ON review_events(target_id);
CREATE INDEX IF NOT EXISTS idx_review_session ON review_events(session_id);
```

Bump `SCHEMA_VERSION`. Add `"review_event"` to `_VALID_KINDS` and
`"review_event": "review_events"` to `_KIND_TABLE`.

### Producer wiring

- Each audit/review skill's `main()` already builds a structured
  result dict before printing. Capture that dict and call
  `record_review_event(...)` before returning.
- For `/ll:audit-loop-run` (which produces a per-loop verdict), the
  pre-flight gate in the kill-analysis (`/ll:audit-loop-run`'s refusal
  on missing events.jsonl) becomes an entry — a refused audit emits a
  row with `verdict="refused"` and `severity_counts={"p0":0,...}` so
  the velocity query can count refused audits separately.
- A small helper module (e.g.
  `scripts/little_loops/review_events.py`) exporting a
  `record(skill, target, severity_counts, findings, verdict, ...)`
  shortcut would centralize the call sites.

### Read API

- `history_reader.recent_review_events(reviewer_skill=None,
  target_id=None, since=None, limit=50)`.
- `history_reader.review_velocity(since=None)` — weekly rollup of
  severity-count totals.
- `history_reader.open_findings(severity='p0')` — list of P0 findings
  across all reviews that haven't been closed (joins review_events →
  issue_events.status=done to determine closure).
- `history_reader.audit_refusal_rate(skill=None, since=None)` —
  fraction of audits that returned `verdict='refused'` (the
  kill-analysis gate).

### CLI surface

- `ll-session recent --kind review_event`.
- `ll-history audit-velocity [--since 30d]` (optional follow-on) —
  rollup of P0/P1/P2 findings per week per skill.

## Acceptance Criteria

- Schema migration lands; `review_events` exists; `SCHEMA_VERSION`
  bumped.
- An `/ll:audit-architecture` invocation writes one row with
  `reviewer_skill="audit-architecture"`, `target_kind="repo"`,
  `target_id=NULL` (or the repo name), `severity_counts`, and
  `findings_count`.
- An `/ll:audit-loop-run rn-implement` invocation writes one row with
  the verdict and severity counts.
- An `/ll:audit-loop-run` that returns `verdict="refused"` (pre-flight
  gate refusal, per the kill-analysis pattern) writes the row with
  `verdict="refused"` and `findings_count=0`.
- `ll-session recent --kind review_event` returns rows;
  `review_velocity()` returns weekly buckets.
- Writes are best-effort: DB absent/locked does not change the audit
  exit code.
- Tests cover: each reviewer_skill, severity_counts JSON round-trip,
  refused verdict path, DB-absent graceful degradation.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — the audit produced
  here is exactly the kind of artifact this issue would persist
- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list
- ENH-2493 — sibling executor telemetry work (different table)
- ENH-2504 — sibling verifier telemetry work (different table)
- `scripts/little_loops/skills/{review-epic,review-sprint,review-loop,
  audit-architecture,audit-claude-config,audit-docs,audit-loop-run}/`
  — producer entry points

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("Bump
`SCHEMA_VERSION`"). Several other active EPIC-2457 siblings (ENH-2492,
ENH-2463, ENH-2464, ENH-2465, ENH-2466, ENH-2493, ENH-2494, ENH-2495,
ENH-2496, ENH-2497, ENH-2498, ENH-2504, ENH-2506, ENH-2511, and others)
independently make the same schema-slot claim in their own Integration Maps
— they cannot all land at the same version number. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now
**20** (v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459
done, v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's implied slot;
each child lands its own migration at whatever version is open when it is
implemented (no coordinated release; per EPIC-2457's own "no shared helper
module is required" scope note).

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`