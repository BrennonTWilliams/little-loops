---
id: BUG-2769
title: Issue-id ingest trusts malformed frontmatter id, silently mis-keying history
  rows
type: BUG
priority: P3
status: done
discovered_by: manual
discovered_date: 2026-07-24
captured_at: '2026-07-24T22:10:00Z'
completed_at: '2026-07-25T06:01:53Z'
labels:
- history
- session-store
- data-integrity
decision_needed: false
parent: EPIC-2791
confidence_score: 96
outcome_confidence: 84
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2769: Issue-id ingest trusts malformed frontmatter `id`, silently mis-keying history rows

## Summary

Every `.ll/history.db` ingest path takes the issue file's frontmatter `id:` value
verbatim, and only falls back to parsing `TYPE-NNN` out of the **filename** when
`id` is entirely absent. An `id` that is present but malformed — e.g. `id: 2756`
or `id: "1294"` instead of `id: BUG-2756` — sails straight through, and the row
lands under a key no query will ever match. The issue then appears "missing"
from history while actually being present under a bare-numeric key.

## Steps to Reproduce

1. Write an issue file whose frontmatter has `id: 2756` (bare number) but whose
   filename is `P2-BUG-2756-....md`.
2. Transition it: `ll-issues set-status BUG-2756 done` (or let a loop close it).
3. Query history: `sqlite3 .ll/history.db "select * from issue_snapshots where
   issue_id='BUG-2756'"` → **0 rows**.
4. `sqlite3 .ll/history.db "select issue_id from issue_snapshots where issue_id
   not like '%-%'"` → `2756`.

## Current Behavior

Four ingest sites read the id and none validate its shape:

- `scripts/little_loops/session_store.py:3090` (`_backfill_issues`) — `fm.get("id")`,
  `_FILENAME_TYPE_RE` fallback only when falsy.
- `scripts/little_loops/session_store.py:3152` (`_backfill_snapshots`) — same pattern.
- `scripts/little_loops/session_store.py:1383` (`record_issue_snapshot`) — takes
  `issue_id` from its caller with no normalization.
- `scripts/little_loops/session_store.py:2989` (`SQLiteTransport` issue-event
  branch) — passes the event payload's `issue_id` through to both `issue_events`
  and `record_issue_snapshot`.

`_index()` is called with the same unvalidated value as its `ref`, so the FTS5
`search_index` rows are mis-keyed in lockstep.

Observed corruption in the live DB before repair (2026-07-24):

| Table | Key written | Should have been |
|-------|-------------|------------------|
| `issue_snapshots` | `2756` | `BUG-2756` |
| `issue_events` | `1182` | `BUG-1182` |
| `issue_events` | `1294` | `BUG-1294` |
| `issue_events` | `1548` | `ENH-1548` |

Four issue files carried the defect (`BUG-1182`, `BUG-1294`, `BUG-2756`,
`ENH-1548`); `BUG-1294` used the quoted form `id: "1294"`, so a naive
`^id: [0-9]+$` grep misses that variant.

## Expected Behavior

An id that disagrees with the filename's `TYPE-NNN` is normalized to the
filename-derived canonical form before any write, so `issue_events`,
`issue_snapshots`, and `search_index.ref` are always keyed `TYPE-NNN`. A
malformed `id` should additionally be surfaced by `ll-issues format-check`
rather than silently repaired forever.

## Root Cause

- **File**: `scripts/little_loops/session_store.py`
- **Anchors**: `_backfill_issues`, `_backfill_snapshots`, `record_issue_snapshot`,
  `SQLiteTransport._write` (issue branch)
- **Cause**: `_FILENAME_TYPE_RE` (`session_store.py:3045`) is used only as an
  *absence* fallback, never as a *validator*. The frontmatter value is trusted
  whenever it is truthy, and `INSERT OR IGNORE` on the
  `(issue_id, transition)` dedup index means the bad row inserts cleanly with
  no constraint to trip.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Line numbers have drifted since this issue was captured. Current locations
  (verified 2026-07-25):
  - `_FILENAME_TYPE_RE` — `session_store.py:3237` (not 3045)
  - `_backfill_issues` — `session_store.py:3264-3326` (id read 3282-3288,
    insert 3299-3316; `str(issue_id)` and `normalize_issue_id(str(issue_id))`
    both flow from the unvalidated `fm.get("id")`)
  - `_backfill_snapshots` — `session_store.py:3329-3385` (id read 3346-3352,
    insert 3360-3375)
  - `record_issue_snapshot` — `session_store.py:1487-1538` (insert
    1522-1527). This function does **not** re-derive from frontmatter —
    `issue_id` is a caller-supplied parameter (frontmatter is only consulted
    for `title`/`priority`/`issue_type`, lines 1509-1513). Its trust boundary
    is therefore the *caller*, not the frontmatter file — see
    `set_status.py` note below.
  - `SQLiteTransport.send` issue-event branch (not `_write`) —
    `session_store.py:3104-3187`, branch at 3140-3182 (`event.get("issue_id")`
    read at 3141, `normalize_issue_id(issue_id) if issue_id else None` at
    3147, insert 3148-3165, and it forwards to `record_issue_snapshot(...)`
    at line 3181).
- **Naming collision**: `normalize_issue_id(issue_id: str | int | None) -> int
  | None` **already exists** at `session_store.py:1189` (backed by
  `_ISSUE_NUM_RE = re.compile(r"(?:BUG|ENH|FEAT|EPIC)-(\d+)", re.IGNORECASE)`
  at line 1186). It is already called at both backfill sites (3298, 3359) and
  in the `SQLiteTransport` branch (3147). It extracts a **numeric** id for DB
  keying and is deliberately permissive — it also accepts bare-digit strings
  (`issue_id.isdigit()`, line 1217) by design, so it cannot double as the
  proposed shape validator; it currently *masks* malformed ids rather than
  rejecting them (a malformed `id: 2756` still produces a non-`None`
  `issue_num`). The Proposed Solution's helper (`str | None`, canonical-form
  return) needs a **different name** to avoid colliding with this existing
  `int | None` helper — e.g. `canonicalize_issue_id`.
- No anchored (`^...$`) `TYPE-NNN` shape validator exists anywhere in the
  codebase today. Related but non-equivalent regexes (all `.search()`-based,
  tolerant of surrounding text): `issue_parser.py:30` `_ISSUE_TYPE_RE`,
  `issue_history/parsing.py:51`, `hooks/post_tool_use.py:37`
  `_ISSUE_ID_RE`, `hooks/sweep_stale_refs.py:37` `_ISSUE_ID_RE`,
  `cli/issues/clusters.py:69` `_ISSUE_ID_RE`, `cli/logs.py:1493`
  `_ISSUE_ID_RE` (looser, matches any uppercase prefix).
- WARN-logging convention in this file (`logger = logging.getLogger(__name__)`
  at line 119): `logger.warning("<function_context>: <what happened> %r/%s",
  value[, exc_info=True])` — e.g. `logger.warning("is_correction: skipping
  invalid extra_pattern %r", p)` (line 359).

## Proposed Solution

1. Add a `normalize_issue_id(raw: object, file_path: str | Path | None) -> str | None`
   helper in `session_store.py` (near `_FILENAME_TYPE_RE`): if `raw` already
   matches `^(BUG|ENH|FEAT|EPIC)-\d+$`, return it; else derive from the filename;
   else, if `raw` is a bare integer/numeric string and the filename gives a type,
   splice them; else fall back to the filename match, then `None`.
2. Route all four ingest sites through it, including the `ref=` passed to
   `_index()`.
3. Log at WARN when normalization changes the value, so the underlying file
   defect is visible rather than papered over.
4. Add a check to `ll-issues format-check` that flags frontmatter `id` not
   matching `TYPE-NNN` or disagreeing with the filename.
5. Tests: `tmp_path` issue file with `id: 2756` / `id: "1294"` / absent `id` /
   correct `id`, each asserted to produce a `TYPE-NNN` key in both
   `issue_snapshots` and `search_index`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Rename the new helper away from `normalize_issue_id` — that name is taken
  (see Root Cause findings above). `canonicalize_issue_id(raw, file_path) ->
  str | None` avoids the collision while staying self-explanatory next to the
  existing numeric `normalize_issue_id`.
- `record_issue_snapshot` (`session_store.py:1487-1538`) is not itself an
  ingest-from-frontmatter site — it trusts whatever `issue_id` its caller
  passes. `set_status.py:141` calls it with `args.issue_id` (the CLI
  argument), not a frontmatter value. To close this call site per item 2, the
  fix must validate/canonicalize at the `set_status.py` call site (or make
  `record_issue_snapshot` accept an optional `file_path` and canonicalize
  internally when one is available) — routing "through" the new helper here
  means adding a `file_path` parameter, not just reusing the frontmatter path.
- `format_check.py`'s `cmd_format_check` (line 35) delegates entirely to
  `check_format_gaps()` in `issue_parser.py:185-229` (`FormatGaps` dataclass,
  `issue_parser.py:135-159`, categories: `missing`/`renamed`/`empty`/
  `boilerplate`). `check_format_gaps` derives `issue_type` from the
  **filename** only (line 219) and never inspects frontmatter today. Item 4
  requires adding a new `FormatGaps` category (e.g. `malformed_id: list[str]`)
  — none of the four existing categories fit "field present, wrong shape" —
  plus updating `to_dict()` and the CLI's print loop in `format_check.py` to
  surface it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. `record_issue_snapshot`'s only external caller (`set_status.py:141`)
   already passes `str(path)` as `file_path` positionally — no new parameter
   is needed; canonicalize internally using the `file_path` already in scope.
7. Update `docs/reference/API.md`'s `check_format_gaps` doc (~lines 847-851)
   and its `ll-issues format-check --format json` example to add the fifth
   `malformed_id` category.
8. Update `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckJsonOutput::test_clean_issue_json_output`
   (lines 220-243) to include `"malformed_id": []` — this assertion breaks
   once the new field exists if left unchanged.
9. Add `TestFormatCheckMalformedId` to `test_ll_issues_format_check.py`
   mirroring the existing per-category test classes.
10. Add a malformed-id case to `test_session_store.py::TestSQLiteTransportIssueEvents`
    and extend `test_set_status_cli.py::TestSetStatusRecordsIssueEvent` with
    an end-to-end malformed-`id:` → canonical-key assertion.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — the four ingest sites + new
  `canonicalize_issue_id` helper (near `_FILENAME_TYPE_RE` at line 3237, not
  the existing `normalize_issue_id` at line 1189)
- `scripts/little_loops/cli/issues/format_check.py` — new frontmatter-id
  check (CLI print loop)
- `scripts/little_loops/issue_parser.py` — `FormatGaps` dataclass (line
  135-159, new `malformed_id` category) and `check_format_gaps` (line
  185-229, the actual check logic)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_status.py:133-141` — passes
  `args.issue_id` straight to `record_issue_snapshot` (verified range;
  originally cited as 134-137)
- `scripts/little_loops/observability/schema.py:504` — documents
  `record_issue_snapshot` as an `issue_snapshots` writer

### Tests
- `scripts/tests/test_session_store.py` — backfill and snapshot round-trips.
  Existing patterns to follow: `TestBackfillIssuesV2Columns` (line 875,
  `test_v2_columns_populated_from_frontmatter` /
  `test_v2_columns_derived_from_filename_when_fm_absent`) and
  `TestBackfillSnapshots...` (line ~4099, `test_backfill_snapshots_hydrates_table`
  at 4116-4155). Both call the public `backfill(db, issues_dir=..., loops_dir=...)`
  entry point (not the private `_backfill_*` functions directly) against a
  `tmp_path / ".issues" / <type-dir>` fixture, then assert via `recent(db,
  kind="issue")` or a raw `conn.execute(...)` SELECT.
- `scripts/tests/test_ll_issues_format_check.py` — confirmed existing file
  (the issue's guess of `test_issues_format_check.py` was close but not
  exact); add the new `malformed_id` case here.

_Wiring pass added by `/ll:wire-issue` (additional dependent files):_
- `scripts/little_loops/cli/issues/format_check.py:43,51` — imports and calls
  `check_format_gaps`; its print loop and JSON output must add a
  `malformed_id` line/key alongside `missing`/`renamed`/`empty`/`boilerplate`
  [Agent 1/3 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` (`ensure_formatted` gate,
  ~lines 100-108, 282) — shells out to `ll-issues format-check "$ID"` as a
  pass/fail gate only (does not parse individual category names), so no
  routing change is required, but it will now also catch malformed-id issues
  it previously passed through [Agent 2 finding, confirmed no update needed]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:847-851` — `check_format_gaps` doc enumerates the
  four gap classes (`missing`, `renamed`, `empty`, `boilerplate`); needs a
  fifth `malformed_id` bullet when the category is added [Agent 2 finding]
- `docs/reference/API.md` (`ll-issues format-check --format json` example,
  ~line 1598, exact line drifted — verify at edit time) — the literal JSON
  shape example `{"missing": [...], "renamed": [...], "empty": [...],
  "boilerplate": [...]}` needs `"malformed_id": [...]` added [Agent 2 finding]
- `docs/reference/CLI.md` — documents `ll-issues format-check`; check for the
  same four-category enumeration and update if present [Agent 1 finding,
  unconfirmed — verify during implementation]

### Tests (additional gaps found by wiring pass)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckJsonOutput::test_clean_issue_json_output`
  (lines 220-243) — asserts the exact dict shape
  `{"missing": [], "renamed": [], "empty": [], "boilerplate": []}`; this is
  load-bearing on `FormatGaps.to_dict()` and **must be updated** (not just
  extended by a new test) to include `"malformed_id": []`, or it fails once
  the new field exists [Agent 3 finding — confirmed breaking]
- `scripts/tests/test_ll_issues_format_check.py` — add a new
  `TestFormatCheckMalformedId::test_malformed_id_section_exits_one` class
  mirroring the existing per-category pattern (`TestFormatCheckMissing` /
  `TestFormatCheckRenamed` / `TestFormatCheckEmpty` / `TestFormatCheckBoilerplate`,
  lines 110-209): write an issue whose frontmatter `id:` disagrees with its
  filename's `TYPE-NNN`, invoke `format-check`, assert exit 1 and a
  `"malformed_id: ..."` line in output (read `format_check.py`'s print loop
  first to match its exact label format) [Agent 3 finding]
- `scripts/tests/test_session_store.py::TestSQLiteTransportIssueEvents`
  (lines 934-1026) — no existing case sends a bare-numeric `issue_id`; add a
  case asserting the event-branch canonicalizes it before writing
  `issue_events`/`search_index` [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py::TestSetStatusRecordsIssueEvent::test_set_status_writes_issue_events_row`
  (lines 1079-1124, from BUG-2770) — closest existing end-to-end template;
  extend or add a sibling case that writes an issue file with a malformed
  `id:`, runs `ll-issues set-status`, and asserts the `history.db` row landed
  under the canonical `TYPE-NNN` key, not the bare-numeric one [Agent 3
  finding]
- `scripts/tests/integration/test_issue_lifecycle_e2e.py` — check whether
  this broader end-to-end suite also asserts `history.db` row shape after a
  full lifecycle run; add coverage if the malformed-id path isn't exercised
  [Agent 3 finding, unconfirmed — verify during implementation]

## Impact

- **Priority**: P3 — silent, low-frequency history-data loss. No user-visible
  runtime failure; the issue simply vanishes from `ll-session` / `ll-history`
  queries and from any FTS lookup by id.
- **Effort**: Small — one helper, four call sites, one lint check.
- **Risk**: Low — normalization is strictly narrowing toward the canonical form.
- **Breaking Change**: No

## Notes

The four affected files' frontmatter and the corresponding DB rows were repaired
by hand on 2026-07-24 (`UPDATE issue_snapshots/issue_events/search_index` to the
canonical `TYPE-NNN` keys; verified 0 remaining bare-numeric keys and
`INSERT INTO search_index VALUES('integrity-check')` clean). This issue covers
preventing recurrence, not the one-time cleanup.

Separately observed while investigating and **not** covered here: `issue_events`
has recorded nothing since `FEAT-2711` on 2026-07-23, while `issue_snapshots`
kept receiving rows through 2026-07-24 (`BUG-2755`, `-2757`…`-2767`). That is an
independent gap in the event-write path and may warrant its own issue.

## Resolution

Added `canonicalize_issue_id(raw, file_path)` in `session_store.py` (distinct
from the existing numeric `normalize_issue_id`) and routed all four ingest
sites (`_backfill_issues`, `_backfill_snapshots`, `record_issue_snapshot`,
`SQLiteTransport.send`'s issue-event branch) through it, including the `ref=`
passed to `_index()`. Normalization changes are WARN-logged. Added a
`malformed_id` category to `FormatGaps`/`check_format_gaps()` in
`issue_parser.py`, wired into `format_check.py`'s CLI output, and documented
in `docs/reference/API.md`/`CLI.md`. Added regression tests covering
bare-int, quoted-numeric, absent, and correct `id` values across backfill,
snapshot, event, and format-check paths.

## Session Log
- `/ll:manage-issue` - 2026-07-25T06:01:22 - `ae2f8a5d-e817-493e-b5c1-7433393e73d9.jsonl`
- `/ll:ready-issue` - 2026-07-25T05:44:49 - `122bccb1-7560-4934-9b55-90d484f133b1.jsonl`
- `/ll:wire-issue` - 2026-07-25T05:42:44 - `bda9e9c9-bdfb-4966-b8c9-a393fd208696.jsonl`
- `/ll:refine-issue` - 2026-07-25T05:37:19 - `2b56a55a-e243-41d8-b821-e27485905f84.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
