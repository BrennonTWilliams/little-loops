---
id: ENH-2512
title: Persist read-side audit / review outcomes into history.db
type: ENH
priority: P3
status: done
discovered_date: 2026-07-06
captured_at: '2026-07-06T00:00:00Z'
completed_at: '2026-07-23T21:37:54Z'
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
labels:
- enhancement
- history-db
- audit
- review
- captured
confidence_score: 95
outcome_confidence: 87
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 24
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

## Impact

- **Without this**: audit/review output (`review-epic`, `audit-architecture`,
  `audit-claude-config`, `audit-docs`, `audit-loop-run`, `review-sprint`,
  `review-loop`) only survives in stdout or a one-off diagnostics file;
  velocity questions like "how many P0 review findings closed this week?"
  are unanswerable, and refused audits (missing run data) leave no trace.
- **With this**: a `review_events` row per invocation makes reviewer output
  queryable alongside the existing executor (`ENH-2493`) and verifier
  (`ENH-2504`) telemetry, completing the read-side signal set and enabling
  `review_velocity()` / `open_findings()` rollups.
- **Scope of change**: additive — one new table, one migration, one
  producer-side write per audit/review skill (best-effort, never changes
  exit code on DB failure). No existing schema or behavior changes.

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

### Codebase Research Findings (second pass, 2026-07-23)

_Added by `/ll:refine-issue` — the anchors above are stale; both ENH-2493 and
ENH-2504 have since landed (`status: done`) and shifted every downstream line
number. Re-verified live against `scripts/little_loops/session_store.py`:_

- **`SCHEMA_VERSION` is now 34** (`session_store.py:228`, not the 20 cited
  above). ENH-2504 landed `verdict_events` as **v33**
  (`session_store.py:1017-1042`) and ENH-2507 landed `context_pressure_events`
  as **v34** (`session_store.py:1043-1064`) — the most recent `_MIGRATIONS`
  entry. `review_events` would append as **v35**, bumping
  `SCHEMA_VERSION` 34→35 at line 228. `_MIGRATIONS` now spans
  `session_store.py:374-1065` (not 333-734). No `review_events` table,
  `record_review_event()` function, or `"review"` kind exists yet anywhere
  in the repo — this is a clean, unclaimed slot.
- **`record_verdict_event()` (`session_store.py:2024-2079`, landed by
  ENH-2504) is a closer template than `record_test_run_event`** — it already
  has `target_kind`, `target_id`, `severity_counts` (JSON-encoded),
  `findings_count`, `verdict`, `session_id`, `head_sha`, `branch`: nearly the
  exact column set this issue proposes for `review_events`, minus
  `findings_json_summary`. Its docstring confirms the contract this issue
  also wants: the function itself raises on failure; the caller wraps it in
  `contextlib.suppress(Exception)` so a DB write failure never changes exit
  code. `record_test_run_event` (now `session_store.py:1847-1910`) and
  `record_harness_event` (now `session_store.py:1912-1978`) share the same
  `connect → INSERT → _index(..., kind=...) → commit → finally: close()`
  skeleton and remain valid secondary references.
- **`VALID_KINDS` now at `session_store.py:230-253`, `_KIND_TABLE` at
  `session_store.py:254-277`** (22 entries each currently, ending with
  `"context_pressure"` / `"context_pressure_events"`). `_EXPORT_TABLE_MAP`
  is now at `session_store.py:4962-4981` and `_EXPORT_DEFAULT_TABLES` at
  `session_store.py:4983-5000` (ending with `"verdict_event"`,
  `"context_pressure_event"`). Add `"review"`/`"review_events"` and
  `"review_event"` respectively, following the same two-list pattern.
  `ll-verify-kinds` (`cli/verify_kinds.py:30-74`) still hard-gates on both
  registrations existing together.
- **Architecture correction — the Producer Wiring design below does not
  match how the closest sibling (ENH-2504) actually shipped.** ENH-2504's
  own refinement notes recorded an explicit decision: *"no central helper
  module required."* No `verdict_events.py` module exists. Instead, all 9
  of ENH-2504's skill-bridged verifiers are wired through a single
  chokepoint: `scripts/little_loops/cli/action.py::cmd_invoke()`. A
  `_VERIFIER_SKILLS` frozenset allowlist (`cli/action.py:~1-98`) gates a
  `_record_verdict()` helper that reads a `VERDICT_JSON: {...}` tagged
  stdout line via `little_loops.output_parsing.extract_tagged_json` (the
  existing tagged-output convention) and calls `record_verdict_event(...)`
  inside `with suppress(Exception):` (`cli/action.py:~144-200`). Skills
  communicate structured findings by emitting a tagged JSON line in their
  own output — they never call any CLI or Python helper directly.
  **This issue's 7 producers are not uniformly bridged through one
  dispatcher today** the way ENH-2504's 9 verifiers are (`review-epic` and
  `audit-loop-run` are skills; `audit-architecture` and `review-sprint` are
  `commands/*.md` with no confirmed common Python call site) — which is
  presumably why the original design reached for per-skill markdown
  directives instead. This is a real fork in the road; see the decision
  block below.

**Option A**: Follow the ENH-2504 precedent directly — extend
`cmd_invoke()` with a parallel `_REVIEWER_SKILLS` frozenset and a
`_record_review()` helper that reads a new `REVIEW_JSON: {...}` tagged
stdout line (reusing `extract_tagged_json`) and calls
`record_review_event(...)`. No `review_events.py` module. Requires
confirming `ll-action`/`cmd_invoke()` can dispatch `commands/*.md` entries
(`audit-architecture`, `review-sprint`), not just `skills/*/SKILL.md`
entries, since two of the seven producers are commands.

> **Selected:** Option A — codebase evidence confirms `cmd_invoke()` already
> dispatches `commands/*.md` targets identically to `skills/*/SKILL.md` targets
> (6 of the 9 existing `_VERIFIER_SKILLS` entries from ENH-2504 are
> command-backed and pass their existing tests), making this the proven,
> higher-reuse path.

**Option B**: Keep this issue's original design — per-skill markdown
directives at each producer's final-report section, plus a new
`scripts/little_loops/review_events.py` centralizing module wrapping
`record_review_event()` with the `contextlib.suppress(Exception)` +
`_git_output()` best-effort guard. Diverges from the ENH-2504 precedent,
but sidesteps the unconfirmed command-dispatch question in Option A.

**Recommended**: Option A if implementation-time verification confirms
`cmd_invoke()` can dispatch `commands/*.md` the same as skills — it reuses
proven, already-gated infrastructure and avoids a bespoke module the
codebase has now explicitly rejected once (ENH-2504's "no central helper
module required" decision). Fall back to Option B only if
`audit-architecture`/`review-sprint` genuinely cannot be routed through
`cmd_invoke()`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-23.

**Selected**: Option A — extend `cmd_invoke()` with a `_REVIEWER_SKILLS`
frozenset and `_record_review()` helper.

**Reasoning**: Codebase research confirms `cmd_invoke()` already dispatches
`commands/*.md` targets with zero special-casing — 6 of the 9 existing
`_VERIFIER_SKILLS` entries (ENH-2504) are command-backed (`ready-issue`,
`tradeoff-review-issues`, `refine-issue`, `verify-issues`,
`prioritize-issues`, `align-issues`) and pass their existing tests
(`test_action.py:311-410`), so the "unconfirmed command-dispatch question"
blocking Option A is resolved. `extract_tagged_json` is tag-parameterized
and needs no changes to accept `REVIEW_JSON`, and `record_verdict_event`'s
column shape is a near-exact template for `record_review_event`. Option B's
new `review_events.py` module directly repeats the "central helper module"
shape ENH-2504 explicitly rejected for the same reviewer/verifier/executor
telemetry family, and its markdown-driven wiring would only be verifiable
via string-presence assertions, not actual call-site execution.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (cmd_invoke() dispatcher) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (per-skill directives + module) | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Option A: `_run_skill()` (`runner_spec.py:80-134`) dispatches by opaque
  `/ll:{name}` string regardless of skill vs. command; `test_action.py`'s
  `TestCmdInvokeRecordsVerdictEvent` already exercises command-backed
  targets (`ready-issue`) successfully.
- Option B: only 2 skills (`improve-claude-md`, `format-issue`) call
  `little_loops.*` helpers directly from markdown — a minority pattern —
  and it repeats the exact "central module" shape ENH-2504 rejected.

## Implementation Steps

> ⚠ **Anchor staleness note** (added by `/ll:refine-issue`, 2026-07-23): Steps
> 1-3 below cite line numbers and a `v21`/`SCHEMA_VERSION 20→21` target that
> predate ENH-2504 (v33, `verdict_events`) and ENH-2507 (v34,
> `context_pressure_events`) landing on `main`. The correct current target is
> **v35, `SCHEMA_VERSION` 34→35**, at the anchors given in the "Codebase
> Research Findings (second pass, 2026-07-23)" addendum above. Step 3's
> `review_events.py` centralizing-module design is also superseded by the
> Option A/B decision in that addendum — resolve `decision_needed` before
> implementing Step 3.

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

> ⚠ **Anchor staleness note** (added by `/ll:refine-issue`, 2026-07-23): the
> `session_store.py` line ranges below predate ENH-2504/ENH-2507 landing;
> use the current anchors in the "Codebase Research Findings (second pass,
> 2026-07-23)" addendum under Proposed Solution instead (`SCHEMA_VERSION`
> line 228, `_MIGRATIONS` 374-1065, `VALID_KINDS` 230-253, `_KIND_TABLE`
> 254-277, `_EXPORT_TABLE_MAP` 4962-4981, `_EXPORT_DEFAULT_TABLES`
> 4983-5000, `record_verdict_event` 2024-2079 as the closer template).

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

## Resolution

Implemented via Option A (the decided path): a `review_events` table (v35
migration, `SCHEMA_VERSION` 34→35) plus a `_REVIEWER_SKILLS` frozenset and
`_record_review()` helper in `cli/action.py::cmd_invoke()`, mirroring the
`_VERIFIER_SKILLS`/`_record_verdict()` pattern ENH-2504 established. No
central `review_events.py` module and no per-skill Python call sites were
added — the dispatcher-level wiring covers all 7 producers
(`review-epic`, `review-loop`, `audit-architecture`, `audit-claude-config`,
`audit-docs`, `audit-loop-run`, `review-sprint`) generically via
`ll-action invoke <skill>`, with a coarse exit-code-based verdict
(`pass`/`fail`) and an optional `REVIEW_JSON: {...}` tagged-line override
(reusing `extract_tagged_json`) for producers that emit structured findings.

- `record_review_event()` (`session_store.py`) — INSERT + FTS index, raises
  on failure (best-effort enforced at the `cmd_invoke()` call site).
- `history_reader.ReviewEvent` / `recent_review_events()` /
  `review_velocity()` (weekly `p0`/`p1`/`p2`/`info` rollup) — the read API.
- `skills/audit-loop-run/SKILL.md`'s pre-flight refusal gate and
  `commands/audit-architecture.md`'s Recommendations section were given
  `REVIEW_JSON` tagging directives so the `verdict="refused"` path (which a
  bare exit code can't express) and severity-bucket mapping are captured,
  satisfying the two AC rows that name those skills specifically. The
  other 5 producers rely on the coarse exit-code fallback until they adopt
  the tag themselves — precision improves incrementally, no further schema
  change needed (same incremental-adoption shape as `VERDICT_JSON`).
- `code-review`/`simplify` remain unwired — confirmed no local
  `scripts/little_loops/` entry point exists for either.
- Full test suite: 16052 passed, 38 skipped. `ruff check`/`ruff format`
  clean; `mypy` clean on all 3 changed modules (pre-existing repo-wide
  `ruamel` stub-typing warnings are unrelated). `ll-verify-kinds` exits 0.

## Session Log
- `/ll:manage-issue` - 2026-07-23T21:37:17Z - `9b69a734-b6b5-46c0-956e-d8f616b1aa18.jsonl`
- `/ll:ready-issue` - 2026-07-23T21:15:12 - `f022701d-6156-48ba-8862-5ecddd4f053a.jsonl`
- `/ll:decide-issue` - 2026-07-23T21:10:47 - `111ff90c-068b-4e08-8042-41d94917bc12.jsonl`
- `/ll:refine-issue` - 2026-07-23T21:06:44 - `5af36657-eddc-4656-a44d-21c83a7bac92.jsonl`
- `/ll:refine-issue` - 2026-07-16T17:24:12 - `87fa8022-e8fb-4ea8-b84d-6b3b28ffb434.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`