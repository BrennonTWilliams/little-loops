---
id: ENH-3242
type: ENH
title: Detect history.db structural drift instead of trusting the recorded schema_version
priority: P2
status: open
testable: true
discovered_by: bug-3236-pre-implementation-review
discovered_date: '2026-08-17'
labels:
- history-db
- session-store
- schema-drift
- silent-failure
relates_to:
- BUG-3236
- BUG-3241
---

# ENH-3242: Detect `history.db` structural drift instead of trusting `schema_version`

## Summary

`meta.schema_version` is treated as proof of structure. `_apply_migrations()`
short-circuits on `_current_version(conn) >= len(_MIGRATIONS)`
(`session_store/schema.py:1065`), so a database whose recorded version is current is never
re-examined regardless of what it actually contains. There is no structural verification
anywhere in the codebase and no repair path.

BUG-3236 and BUG-3241 are both instances of this: five databases carrying a drifted
`issue_sessions` view, and roughly two dozen missing indexes their recorded version says
they must have. Each was found by hand, months after the fact, and only because an
unrelated feature happened to depend on the drifted object. This issue is about making the
*next* one loud instead of silent.

## Motivation

The drift mechanism is structural to how this project is developed, not a one-off. Every
little-loops project on this machine is `local-editable` against the source checkout, so
any `ll-*` invocation during in-progress migration work runs the **working-tree** migration
body against real databases. There is no commit, no artifact, and no signal. The affected
databases then record a version they do not structurally match, permanently, because the
version check never fires again.

Both known instances failed silently: every affected reader catches `sqlite3.Error` and
returns `[]` or `None`, which is indistinguishable from "no data." BUG-3236 sat undetected
long enough that its root cause could only be established by proving a negative
(`git log -S` returning no commits).

## Proposed Solution

Three pieces, roughly in order of cost and value. The first is worth doing alone.

**1. A structural assertion in the test suite.** For the current `SCHEMA_VERSION`, assert
that a freshly built database's PRAGMA-derived column sets and index names match an
expected manifest. This is what would have caught both known instances at authoring time,
costs nothing at runtime, and needs no decision about self-healing. Generating the manifest
from `ensure_db()` on a fresh temp database and comparing it against a checked-in snapshot
keeps it maintainable — the snapshot diff becomes a required, reviewable part of any
migration PR.

**2. A cheap structural check in `ensure_db()`'s fast path.** The version-current path
already returns without taking the write lock. A single `PRAGMA table_info` on one sentinel
view (`issue_sessions`) would make view drift self-healing rather than permanent. Weigh
against startup cost — `ensure_db()` is on every `ll-*` invocation's critical path. If the
per-call cost is unacceptable, an opt-in `ll-history doctor` command carrying the full
manifest check is the fallback, and is more useful for the index drift in BUG-3241 anyway.

**3. A log-level convention for reader query failures.** BUG-3236 raises
`history_reader.py:2107` and `:2136` to `logger.error` as a point fix. There are 60+
`except sqlite3.Error:` sites in `history_reader.py` with no distinction anywhere between
"database missing" (expected, `warning`) and "query failed against a present, readable
database" (a defect, `error`). Establishing that distinction file-wide is the durable
version of BUG-3236's item 2. `sessions_for_issue`'s own docstring
(`history_reader.py:2092-2093`) already concedes that its empty-list return conflates three
distinct causes.

### Implementation trap, inherited from BUG-3236

**Do not compare `sqlite_master.sql` text.** SQLite stores the *original* `CREATE`
statement verbatim and never rewrites it, so a comment added to a `CREATE TABLE` body after
the table was created reads as drift forever. A naive text diff of this checkout's database
against a fresh one flags `raw_events` as drifted; the only difference is a block comment
added long after the table existed, and the structure is identical. Any structural check
must compare **PRAGMA-derived column sets and index names**, never SQL strings.

## Impact

- **Priority**: P2 — no user-visible defect today once BUG-3236 and BUG-3241 land; this
  prevents the class. Piece 1 is small and high-leverage; pieces 2 and 3 are larger.
- **Effort**: Piece 1 small, piece 2 medium (needs a startup-cost measurement), piece 3
  medium-large (touches 60+ call sites, mechanically).
- **Sequencing**: after BUG-3236, so the manifest snapshot is taken against a correct v42
  schema rather than baking in the drift. Independent of BUG-3241.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] A test asserts the full PRAGMA-derived structure (table and view column sets, index
      names) of a fresh database at the current `SCHEMA_VERSION` against a checked-in
      manifest, and fails when a migration changes structure without updating it.
- [ ] The test compares PRAGMA output, never `sqlite_master.sql` text; a comment-only edit
      to a `CREATE TABLE` body does not fail it.
- [ ] A decision is recorded — with a startup-cost measurement, not an estimate — on
      whether the `ensure_db()` fast-path check ships or is replaced by an explicit
      `ll-history doctor` command.
- [ ] Whichever ships detects a database stamped current but structurally drifted, on both
      known shapes: a missing view column (BUG-3236) and a missing index (BUG-3241).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of BUG-3236 during its pre-implementation review, where items 3 and 4 of the Fix
section were correctly scoped out of the point fix but had no issue to land in.

## Status

- [ ] open
