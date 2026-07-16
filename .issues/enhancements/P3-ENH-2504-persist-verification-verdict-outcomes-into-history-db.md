---
id: ENH-2504
title: Persist verification / readiness-review verdict outcomes into history.db
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
  - verification
  - audit
  - captured
---

# ENH-2504: Persist verification / readiness-review verdict outcomes into history.db

## Summary

`ll-ready-issue`, `ll-tradeoff-review`, `ll-confidence-check`, `ll-go-no-go`,
`ll-refine-issue`, `ll-format-issue`, `ll-verify-issues`, `ll-prioritize-issues`,
`ll-align-issues`, and `/ll:verify-issue-loop` each compute a pass/fail
verdict with a severity count and a findings list. Today the verdict only
survives in the CLI's stdout — once the terminal scrolls, there's no record of
"the confidence-check on BUG-2501 ran at 2026-07-07T02:55:00 and scored 97
with 0 P0 findings" or "the tradeoff review recommended `implement` over
`defer`." Add a `verdict_events` table capturing every verifier's structured
outcome so issue-readiness trends are queryable alongside the executor
events ENH-2493 already persists.

## Motivation

- **The read-side is completely dark.** ENH-2493 (`harness_events`) and
  ENH-2459 (`test_run_events`) cover the executor side (pytest, ll-harness,
  dsl evals). The verifier side — the commands an agent invokes to *decide*
  whether to implement — leaves no trace, so the velocity story
  ("how many issues passed readiness this week?") is unreachable.
- **`/ll:verify-issue-loop` outputs are already structured but throwaway.**
  The same harness runner that ENH-2493 captures produces the rows this issue
  would store; nothing currently distinguishes "executor verdict" from
  "verifier verdict."
- **Adjacent to but distinct from ENH-2493.** ENH-2493 captures
  *executor* outcomes (`runner`, `target`, `semantic_verdict`). This issue
  captures *verifier* outcomes — the readiness/confidence/refine side that
  feeds the executor. Different producers (readiness-review vs. harness
  runners), same shape. Either a sibling table (`verdict_events`) or a
  shared table with a `verdict_kind` discriminator works; this issue
  proposes a sibling table for clearer provenance.

## Current Behavior

- `ll-ready-issue`, `ll-tradeoff-review`, `ll-confidence-check`,
  `ll-go-no-go`, `ll-refine-issue`, `ll-format-issue`, `ll-verify-issues`,
  `ll-prioritize-issues`, `ll-align-issues` each print a verdict and exit
  code, then exit; nothing persists.
- `/ll:verify-issue-loop` produces the same shape via `ll-harness`; ENH-2493
  would capture those rows (they're harness invocations), but the verifier
  ones (`ll-ready-issue --json` etc.) bypass `ll-harness` entirely.
- No `--kind verdict` in `ll-session recent`.

## Expected Behavior

- A `verdict_events` table records one row per verifier invocation with
  `verdict_kind` (the command/skill name), `target_kind` (`issue` | `epic` |
  `sprint` | `loop`), `target_id`, `verdict` (`pass` | `fail` | `warn` |
  `defer` | `implement` | `close`), `severity_counts` (JSON: `{p0: 0, p1: 2,
  ...}`), `findings_count`, plus `session_id`, `ts`, `head_sha`, `branch`.
- Each verifier calls `record_verdict_event(...)` before returning (best-
  effort guarded).
- `ll-session recent --kind verdict` returns rows; FTS matches
  `target_id` / findings text.
- Same shape is reachable from `/ll:verify-issue-loop` outputs (no double-
  write; the harness table gets the executor row, this table gets the
  verifier row when the skill is invoked standalone).

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS verdict_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    verdict_kind TEXT NOT NULL,   -- "ll-ready-issue" | "ll-confidence-check" | "/ll:tradeoff-review-issues" | ...
    target_kind TEXT,             -- "issue" | "epic" | "sprint" | "loop"
    target_id TEXT,               -- "BUG-2501" | "EPIC-2457" | ...
    verdict TEXT NOT NULL,        -- "pass" | "fail" | "warn" | "implement" | "defer" | "close"
    severity_counts TEXT,         -- JSON: {"p0": 0, "p1": 2, ...}
    findings_count INTEGER,
    confidence INTEGER,           -- numeric confidence when produced (e.g., 97)
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_verdict_kind ON verdict_events(verdict_kind);
CREATE INDEX IF NOT EXISTS idx_verdict_target ON verdict_events(target_id);
CREATE INDEX IF NOT EXISTS idx_verdict_session ON verdict_events(session_id);
```

Bump `SCHEMA_VERSION`. Add `"verdict"` to `_VALID_KINDS` and
`"verdict": "verdict_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_verdict_event(db_path, *, ts, session_id, verdict_kind,
  target_kind, target_id, verdict, severity_counts=None, findings_count=None,
  confidence=None, head_sha=None, branch=None)` to `session_store.py`,
  best-effort, FTS-indexing `target_id` + `verdict_kind`.
- Wire into the terminal-return point of each verifier's main(): each
  command already builds the structured result it prints; capture that
  same dict into `record_verdict_event(...)` before the final return.
- A small helper module (e.g. `scripts/little_loops/verdict_events.py`)
  exporting a `record(command, target, verdict, ...)` shortcut would
  centralize the call sites and reduce duplication across the nine
  verifier entry points.

### Read API

- `history_reader.recent_verdict_events(verdict_kind=None, target_id=None,
  since=None, limit=50)`.
- `history_reader.verdict_pass_rate(verdict_kind=None, target_id=None,
  since=None)` — pass rate over a window, the readiness-trend rollup.

### CLI surface

- `ll-session recent --kind verdict`.
- `ll-history issue-readiness <ISSUE_ID>` (optional follow-on) — surfaces
  the most recent verifier scores for an issue across readiness/confidence/
  tradeoff/go-no-go.

## Acceptance Criteria

- Schema migration lands; `verdict_events` exists; `SCHEMA_VERSION` bumped.
- An `ll-ready-issue BUG-2501` invocation writes one row with
  `verdict_kind="ll-ready-issue"`, `target_id="BUG-2501"`, the computed
  verdict, and severity counts.
- An `/ll:verify-issue-loop` invocation produces the verifier row from
  this table (alongside, not instead of, the executor row in
  `harness_events`).
- `ll-session recent --kind verdict` returns rows; FTS matches
  `target_id`.
- Writes are best-effort: DB absent/locked does not change the verifier
  exit code.
- Tests cover: each verifier producer, DB-absent graceful degradation,
  severity_counts JSON round-trip.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — "the missing `events.jsonl`
  is what would distinguish Modes A/B/C" — the analysis couldn't run because
  no verifier-event trail existed for the killed run
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- ENH-2493 — sibling structured-result table for executors
- ENH-2497 / `post_tool_use.py` — `subagent_type` already shows what
  agent invoked the verifier
- `scripts/little_loops/cli/{ready_issue,confidence_check,go_no_go,
  tradeoff_review,refine_issue,format_issue,verify_issues,
  prioritize_issues,align_issues}.py` — nine producer entry points

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
ENH-2496, ENH-2497, ENH-2498, ENH-2506, ENH-2511, and others) independently
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
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:55 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`