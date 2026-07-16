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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current `SCHEMA_VERSION` is 20** (verified live at `scripts/little_loops/session_store.py:207`). The actual next-version slot is whatever is open at implementation time per the EPIC-2457 "no coordinated release" convention noted in the Scope Boundary section.
- **No local implementation exists for `/code-review` or `/simplify`** — these are host-provided Claude Code slash commands with no `scripts/little_loops/` Python entry point. Wiring them requires either a future local CLI wrapper (e.g. `scripts/little_loops/cli/code_review.py`) or accepting that they remain un-persisted. The issue should call this gap out explicitly rather than silently skipping them.
- **Severity-bucket mismatch** — the proposed `severity_counts = {p0, p1, p2, info}` does not match any existing producer's taxonomy. Current outputs use Error/Warning/Suggestion (`skills/review-loop/SKILL.md:236-246`), Critical/High/Medium/Low mapped to P1–P5 (`commands/audit-architecture.md:169-182`), Critical/Warning/Suggestion + Info (`skills/audit-claude-config/SKILL.md:191-215`), high/med/low (`skills/audit-docs/SKILL.md:95-103`), and a verdict-only family of `met | phantom | honest-failure | partial | degraded` (`skills/audit-loop-run/SKILL.md:295-306`). Each producer needs an explicit mapping into the new p0/p1/p2/info schema (see Implementation Step 5).
- **Best-effort guard lives at the call site**, not inside `record_review_event`. The producer raises on `sqlite3.Error`; the caller wraps in `contextlib.suppress(Exception)` (canonical pattern at `scripts/little_loops/pytest_history_plugin.py:118-121`). The `skill_event_context` helper at `session_store.py:1108-1182` is an alternative internal-swallow pattern (per EPIC-1707) — use the former for new wiring.
- **Producers are markdown-driven** — none of the 9 audit/review skills has a Python `main()`. Wiring is a markdown directive at each skill's "Final Report" / "Phase 7" / "Summary" section, e.g. "After producing the final report, call `review_events.record(...)`."
- **Refused-path precedent** — the pre-flight gate at `skills/audit-loop-run/SKILL.md:81-94` checks for `events.jsonl`/`state.json` and emits "Run '<id>-<name>' not found or empty — refusing to audit." (`SKILL.md:96-108`). The existing `autodev-bug2501-kill-analysis.md` (2026-07-07) is exactly the kind of refused audit this issue would persist with `verdict="refused"`, `severity_counts={"p0":0,...}`, `findings_count=0`.
- **`head_sha`/`branch` capture** — use `_git_output(*args)` at `scripts/little_loops/pytest_history_plugin.py:61-74` (or the `_git(*args)` precedent at `scripts/little_loops/hooks/post_commit.py:27-41`). The `git_utils.py:get_head_sha()` referenced in older issue docs does NOT exist (per ENH-2493 anchor refresh).
- **ll-verify-kinds gate** — `scripts/little_loops/cli/verify_kinds.py:38-47` exits 1 if `review_events` is created in `_MIGRATIONS` but missing from `_KIND_TABLE`. Both registrations are mandatory, not optional.
- **Sibling prior art**: ENH-2493 (`.issues/enhancements/P3-ENH-2493-persist-harness-eval-outcomes-into-history-db.md`) for `harness_events` (executor side); ENH-2504 (`.issues/enhancements/P3-ENH-2504-persist-verification-verdict-outcomes-into-history-db.md`) for `verdict_events` (verifier side). `review_events` is the reviewer-side third leg.

## Implementation Steps

1. **Schema migration** — Append a v21 entry to `_MIGRATIONS` in `scripts/little_loops/session_store.py:333-734` (model after `usage_events` v20 at lines 709-733). Bump `SCHEMA_VERSION = 20 → 21` (line 207). Add `"review"` to `VALID_KINDS` (lines 209-222) and `"review": "review_events"` to `_KIND_TABLE` (lines 223-236) so `ll-session recent --kind review` works and `ll-verify-kinds` (`cli/verify_kinds.py:38-47`) does not fail.
2. **Producer helper** — Implement `record_review_event(db_path, *, ts, reviewer_skill, target_kind=None, target_id=None, severity_counts=None, findings_count=0, findings_json_summary=None, verdict=None, session_id=None, head_sha=None, branch=None, config=None) -> None` at `scripts/little_loops/session_store.py` (mirror `record_test_run_event` lines 1352-1414). Use plain `INSERT` (each review is a distinct row), JSON-encode `severity_counts` + `findings_json_summary`, write an FTS5 summary of `reviewer_skill + target_id + verdict`.
3. **Centralized call helper** — Add `scripts/little_loops/review_events.py` exporting `record(skill, target, severity_counts, findings, verdict, *, artifact_path=None)` wrapping `record_review_event` with `contextlib.suppress(Exception)` best-effort guard (canonical pattern from `scripts/little_loops/pytest_history_plugin.py:118-121`). Capture `head_sha`/`branch` via `_git_output(*args)` from `pytest_history_plugin.py:61-74` (note: `git_utils.py:get_head_sha()` referenced in older issues does NOT exist).
4. **Read API** — In `scripts/little_loops/history_reader.py`: add `ReviewEvent` dataclass (mirror `RunEvent` lines 138-161), add `recent_review_events(reviewer_skill=None, target_id=None, since=None, limit=50)` (mirror `recent_test_runs` lines 689-725), add `review_velocity(since=None)` weekly rollup (mirror `aggregate_usage` lines 596-648). Wrap in `_connect_readonly` + `try/except sqlite3.Error: return []` for graceful degradation.
5. **Wire producers** — Add a markdown directive at the final-report injection point of each skill, calling `review_events.record(...)`. Concrete anchors:
   - `skills/review-epic/SKILL.md:207-277` (final report) + early-exit gates (`:42-59`, `:69-97`)
   - `skills/review-loop/SKILL.md:368-382` (summary) + `:386-403` (artifact path)
   - `commands/audit-architecture.md:93-163` (recommendations) — map Critical/High/Medium/Low → p0/p1/p2/info per the existing priority table at `:169-182`
   - `skills/audit-claude-config/SKILL.md:419-422` (Phase 7 report) — map Critical/Warning/Suggestion → p0/p1/p2; map exit code 0/1/2 → verdict pass/warn/fail (`:425-432`)
   - `skills/audit-docs/SKILL.md:125-127` (Phase 4 report) — map high/med/low → p1/p2/info (subagent contract at `:95-103`)
   - `skills/audit-loop-run/SKILL.md:81-108` (refused path: `verdict="refused"`, all-zero counts) + `:418-428` (normal completion)
   - `commands/review-sprint.md:304-345` (final output); derive verdict from health-check counts (`:311-316`)
   - **Skip `code-review` and `simplify`** — built-in Claude Code slash commands with NO local implementation under `scripts/little_loops/`. Document this gap; wire only if a local CLI wrapper is added.
6. **JSONL export parity** — Add `("review_events", "ts")` to `_EXPORT_TABLE_MAP` and `"review_event"` to `_EXPORT_DEFAULT_TABLES` in `session_store.py:3303-3329` so `ll-session export --tables review_event` works.
7. **Tests** — Add `TestRecordReviewEvent` to `scripts/tests/test_session_store.py` (mirror `TestRecordTestRunEvent` lines 4362-4415) covering round-trip, severity_counts JSON round-trip, refused verdict path, DB-absent graceful degradation. Add `test_recent_kind_review_outputs_row` to `test_ll_session.py:1086-1097`. Add parameterized-filter test in `test_history_reader.py:1459`. Update `SCHEMA_VERSION` assertions at `test_session_store.py:1372, 1817` and `test_assistant_messages.py:88`.
8. **Verification** — Run `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py scripts/tests/test_ll_session.py scripts/tests/test_verify_kinds.py -v`, then `python -m pytest scripts/tests/` for the full suite. Confirm `ll-verify-kinds` exits 0.
9. **Documentation** — Append v21 row to `docs/ARCHITECTURE.md:670-678`. Add `ReviewEvent` + `record_review_event` to Public API list in `docs/reference/API.md:6847-6848, 7286-7287, 7346+`. Add `ll-session recent --kind review` example to `docs/reference/CLI.md:2507-2519`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — append v21 migration block to `_MIGRATIONS` (lines 333-734), bump `SCHEMA_VERSION` 20→21 (line 207), register `"review"` in `VALID_KINDS` (lines 209-222) and `_KIND_TABLE` (lines 223-236), implement `record_review_event()` modeled after `record_test_run_event` (lines 1352-1414), update `_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES` (lines 3303-3329)
- `scripts/little_loops/history_reader.py` — add `ReviewEvent` dataclass (model after `RunEvent` lines 138-161), `recent_review_events()` (model after `recent_test_runs` lines 689-725), `review_velocity()` weekly rollup (model after `aggregate_usage` lines 596-648)
- `scripts/little_loops/review_events.py` (new) — centralize `record(skill, target, severity_counts, findings, verdict, *, artifact_path=None)` wrapping `session_store.record_review_event` + head_sha/branch capture via `_git_output(*args)`
- `scripts/little_loops/cli/session.py` — extend `--kind` choices (auto via `VALID_KINDS`), add `review_event` to `--tables` choices (lines 218-245)

### Dependent Files (Producer Skills to Wire)
- `skills/review-epic/SKILL.md` — emit row at final report (`:207-277`) and at early-exit gates (`:42-59`, `:69-97`)
- `skills/review-loop/SKILL.md` — emit row at summary (`:368-382`) with artifact path (`:386-403`)
- `commands/audit-architecture.md` — emit row after final report (`:93-163`); map Critical/High/Medium/Low → p0/p1/p2/info per existing priority table (`:169-182`)
- `skills/audit-claude-config/SKILL.md` — emit row after Phase 7 final report (`:419-422`); map Critical/Warning/Suggestion → p0/p1/p2; map exit code 0/1/2 → verdict pass/warn/fail (`:425-432`)
- `skills/audit-docs/SKILL.md` — emit row after Phase 4 final report (`:125-127`); map high/med/low → p1/p2/info (subagent contract: `:95-103`)
- `skills/audit-loop-run/SKILL.md` — two paths: refused pre-flight gate (`:81-108` → `verdict="refused"`, all-zero counts) and normal completion (`:418-428`)
- `commands/review-sprint.md` — emit row after final output (`:304-345`); derive verdict from health-check counts (`:311-316`)
- `code-review` / `simplify` — NO local implementation exists under `scripts/little_loops/`; built-in Claude Code slash commands. Skip wiring unless a local wrapper is added.

### Tests
- `scripts/tests/test_session_store.py:4362-4415` — `TestRecordTestRunEvent` round-trip + JSON + FTS template
- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at(db, version)` helper for v20→v21 upgrade test
- `scripts/tests/test_history_reader.py:1459` — `test_recent_test_runs_and_pass_rate` parameterized-filter template
- `scripts/tests/test_ll_session.py:1086-1097` — `test_recent_kind_test_run_outputs_row` CLI smoke template
- `scripts/tests/test_verify_kinds.py:21` — `test_clean_state_returns_zero` (fails if `review_events` table is created without `_KIND_TABLE` entry)
- `scripts/tests/test_assistant_messages.py:88` — second `SCHEMA_VERSION` assertion site

### Documentation
- `docs/ARCHITECTURE.md:670-678` — schema-versions table (add v21 row)
- `docs/reference/API.md:6847-6848, 7286-7287, 7346+` — Public API list (add `ReviewEvent` + `record_review_event`)
- `docs/reference/CLI.md:2507-2519` — expand `--kind` examples to include `review`

### Configuration (Optional)
- `scripts/little_loops/config-schema.json` — `analytics.capture.review_events` toggle (parity only; ENH-2459 `test_run_events` shipped ungated)

### Similar Patterns
- `scripts/little_loops/session_store.py:1352` — `record_test_run_event` is the closest prior-art template (kwarg-only, non-idempotent, FTS summary)
- `scripts/little_loops/pytest_history_plugin.py:61-74` — `_git_output(*args)` helper for head_sha/branch (canonical replacement for nonexistent `git_utils.py`)
- `scripts/little_loops/pytest_history_plugin.py:118-121` — `contextlib.suppress(Exception)` best-effort wrap pattern at the producer call site
- `scripts/little_loops/session_store.py:1108-1182` — `skill_event_context` alternative internal-swallow pattern (per EPIC-1707)
- `skills/audit-loop-run/SKILL.md:295-306` — explicit verdict family table to mirror in `verdict` column
- `autodev-bug2501-kill-analysis.md` (2026-07-07) — concrete audit artifact this issue would persist as a row

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
- `/ll:refine-issue` - 2026-07-16T17:24:12 - `87fa8022-e8fb-4ea8-b84d-6b3b28ffb434.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`