---
id: ENH-2739
title: harness_events schema, kind registration, and record_harness_event() recorder
type: ENH
priority: P3
status: done
discovered_date: 2026-07-22
completed_at: '2026-07-22T20:35:17Z'
discovered_by: issue-size-review
parent: EPIC-2457
labels:
- enhancement
- history-db
- eval
relates_to:
- ENH-2493
confidence_score: 96
outcome_confidence: 90
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2739: harness_events schema, kind registration, and record_harness_event() recorder

## Summary

Child 1 of 3 decomposed from ENH-2493 ("Persist ll-harness / eval outcomes into
history.db"). This child lands the foundational, independently-shippable
layer: the `harness_events` table migration, kind/table registrations, and
the `record_harness_event()` write function in `session_store.py`. It ships a
table and a recorder that nothing calls yet (ENH-2740 wires the producer) —
that's fine, it's testable and mergeable on its own via direct round-trip
tests.

## Parent Issue

Decomposed from ENH-2493: Persist ll-harness / eval outcomes into history.db.
See ENH-2493 for full motivation, current-behavior analysis, and the complete
codebase research trail (anchors drift fast in this file — re-verify every
line number against live `main` before implementing, per ENH-2493's own
repeated "Anchor Refresh" notes).

## Scope

- **Schema migration**: append a `harness_events` table + indexes to
  `_MIGRATIONS` in `session_store.py`, at whatever `SCHEMA_VERSION` is open at
  implementation time (read the live constant — do not trust any version
  number cited in ENH-2493's history, which has drifted from 18→19→20→21→30
  across successive refine passes). Columns per ENH-2493's Proposed Solution
  + the "Anchor Refresh (2026-07-16)" schema extensions: `runner`, `target`,
  `exit_code`, `semantic_verdict`, `semantic_passed`, `timed_out`,
  `duration_ms`, `head_sha`, `branch`, plus the nullable `parent_id INTEGER`
  (for DSL per-task linkage — see ENH-2740) and the semantic-detail columns
  (`semantic_prompt`, `semantic_confidence`, `semantic_reason`,
  `semantic_evidence`, `semantic_model`).
- **Kind registration**: add `"harness"` to `VALID_KINDS` and
  `"harness": "harness_events"` to `_KIND_TABLE`.
- **`record_harness_event(...)`**: kwargs-only function mirroring
  `record_test_run_event()`'s shape (`connect()` → `INSERT` → `_index(...,
  kind="harness", ...)` → `commit()` in `try/finally`). The function itself
  raises on failure — callers (ENH-2740) are responsible for
  `contextlib.suppress(Exception)`. Export in `__all__`.
- **Export/rebuild wiring**: append `"harness_event": ("harness_events",
  "ts")` to `_EXPORT_TABLE_MAP` + `_EXPORT_DEFAULT_TABLES`; extend the
  `_REBUILD_TABLES` exclusion comment to note `harness_events` is
  direct-write-only (no code change, comment only); append `, harness_event`
  to the `export --tables` help text in `cli/session.py`.
- **DES audit registration**: add `HarnessEventVariant` (`Literal
  ["harness_event"]`) to `observability/schema.py`, register it in
  `DES_VARIANTS`, and add the counterpart assertion in
  `scripts/tests/test_des_schema.py`. **Mandatory** — `record_harness_event`
  is a direct DB insert, not an `event_bus.emit()` call, so
  `ll-verify-des-audit`'s regex-based scan will NOT catch an unregistered
  producer on its own; the explicit variant registration is what makes the
  gate meaningful here.
- **Docs**: `docs/ARCHITECTURE.md` schema-versions table row + mermaid
  `v1–vN` range bump; `docs/reference/API.md` `record_harness_event`
  reference block.

## Acceptance Criteria

- `harness_events` table exists after `ensure_db()`; `SCHEMA_VERSION` bumped
  to the next open slot (read live, don't hardcode from ENH-2493).
- `"harness" in VALID_KINDS` and `_KIND_TABLE["harness"] == "harness_events"`.
- `record_harness_event(...)` round-trips all columns including
  `parent_id` and the semantic-detail columns; FTS-indexes `target` under
  `kind="harness"`.
- `ll-session export --tables harness_event` does not fail (table registered
  in `_EXPORT_TABLE_MAP`).
- `ll-verify-des-audit` passes with `HarnessEventVariant` registered.
- `test_verify_kinds.py::test_clean_state_returns_zero` passes (kind/table
  registration satisfies the data-driven invariant).
- Docs updated: schema-versions table + mermaid range in
  `docs/ARCHITECTURE.md`, `record_harness_event` block in
  `docs/reference/API.md`.
- Full test suite (`python -m pytest scripts/tests/`) passes, including the 14
  literal `assert SCHEMA_VERSION == 30` sites in `test_session_store.py`
  updated to `31` (see Tests subsection below — added by `/ll:wire-issue`).

## Explicitly Out of Scope

- Wiring `main_harness()` / `cmd_*` to actually call `record_harness_event()`
  — that's ENH-2740.
- `history_reader` read API, `ll-session recent/search --kind harness`
  end-to-end behavior with real data, and CLI/reader docs — that's ENH-2741.
- `config-schema.json` `analytics.capture` toggle for harness events — ENH-2493
  itself marks this as not strictly required to ship (parity with ENH-2459,
  which doesn't gate `test_run_events` either). Deferred indefinitely unless a
  future issue asks for it explicitly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (live-verified against
`main`, 2026-07-22):_

- **`SCHEMA_VERSION`**: currently `30` (`scripts/little_loops/session_store.py:222`,
  verified live). The next open slot is `31`. `_MIGRATIONS` is a flat
  `list[str]` starting at `session_store.py:360`; the newest entry is the
  `v30 (ENH-2506)` `hook_events` migration at lines 921-944. Append the new
  `harness_events` DDL string directly after it, preceded by a
  `# v31 (ENH-2739): ...` comment following the same convention (short
  rationale + any `_REBUILD_TABLES`/backfill caveat).
- **Two sibling recorder shapes exist — use `record_test_run_event`'s, not
  `record_hook_event`'s**: `record_test_run_event()`
  (`session_store.py:1727-1789`) does a plain `connect(db_path)` with no
  surrounding `try/except` around the connect call, and lets `INSERT`/commit
  errors propagate — this matches the issue's stated contract ("the function
  itself raises on failure — callers are responsible for
  `contextlib.suppress(Exception)`"). By contrast, `record_hook_event()`
  (`session_store.py:1432-1492`) wraps `connect()` and the insert in
  `try/except sqlite3.Error` and swallows failures via `logger.warning(...)`
  — do **not** copy that shape for `record_harness_event`, since it would
  contradict the "raises on failure" requirement. Both follow the same
  `connect()` → `INSERT` → `_index(conn, content=..., kind=..., ref=...,
  anchor=..., ts=ts)` → `conn.commit()` → `finally: conn.close()` skeleton;
  `_index()` itself is defined at `session_store.py:1101-1114`.
- **`VALID_KINDS`/`_KIND_TABLE`**: tuple/dict at `session_store.py:224-263`;
  `"test_run"` (line 235) and `"hook_event"` (line 242) are the existing
  entries to pattern-match. `_KINDLESS_TABLES`
  (`session_store.py:271-282`) is the exemption list for structural tables
  with no kind — `harness_events` must NOT go there, since it's a queryable
  event stream like `test_run_events`.
- **`_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES`/`_REBUILD_TABLES`**: at
  `session_store.py:4419-4434`, `4436-4449`, and `3926-3936` respectively
  (exclusion-comment block for `_REBUILD_TABLES` at lines 3919-3925 already
  names `hook_events` as a live-write-only precedent — extend it to include
  `harness_events`). Note `"test_run_event": ("test_run_events", "ts")` is
  the closest existing `_EXPORT_TABLE_MAP` entry to mirror.
- **`cli/session.py`**: the `--tables` help text for `export` is a
  hand-maintained comma-separated string at lines 239-254 (not derived
  programmatically from `_EXPORT_TABLE_MAP.keys()`) — append `harness_event`
  there. Additionally (not currently listed in this issue's Docs/Scope
  section), the module docstring at `cli/session.py:1-24` also enumerates
  supported kinds and should get `harness` added for consistency, and
  `docs/reference/CLI.md`'s `--kind` choice documentation should list
  `harness` alongside `test_run`/`hook_event`.
- **DES variant registration**: `DESVariant` base class at
  `observability/schema.py:20-30`; the Channel-A ("direct writers to
  .ll/history.db") section starts around line 446. `TestRunEventVariant`
  (lines 501-505) is the minimal pattern to copy — a frozen dataclass with
  just a docstring and `type: Literal["harness_event"] = "harness_event"`,
  registered in the `DES_VARIANTS` tuple (~lines 571-644). **Caveat**:
  `hook_events` (the most recently added sibling table, v30) has **no**
  corresponding `HookEventVariant` registered at all (confirmed via live
  grep — zero matches) — DES registration is not automatically kept in
  lockstep with `_KIND_TABLE` additions elsewhere in the codebase. This
  issue's explicit "Mandatory" call-out for `HarnessEventVariant` is
  correctly stricter than that lapsed precedent, not redundant with it.
- **`test_des_schema.py` "counterpart assertion"**: the existing
  `TestSchemaDefinitions` class (lines 27-66) verifies `DES_VARIANTS`
  completeness generically via set-difference against `SCHEMA_DEFINITIONS`/
  `_LOOP_EVENT_TYPES` (Channel B/EventBus-emitted types only) — there is no
  per-table named assertion like `test_test_run_event_variant_registered`
  for any existing Channel-A direct-writer variant. Adding
  `HarnessEventVariant` to `DES_VARIANTS` is likely sufficient on its own;
  if a literal "counterpart assertion" is wanted, it would be a new,
  precedent-setting test (no existing Channel-A variant has one to copy).
- **Schema-upgrade test pattern**: `_bootstrap_schema_at(db, version)` helper
  is at `scripts/tests/test_session_store.py:4095-4115`.
  `TestSchemaV30HookEvents` (lines 5376-5434) is the freshest full template
  to copy for a `TestSchemaV31HarnessEvents` class — covers columns
  (`PRAGMA table_info`), indexes (`sqlite_master` query), the
  `_bootstrap_schema_at(db, 30)` + `ensure_db()` upgrade path, the
  `"harness" in VALID_KINDS` / `_KIND_TABLE` kind check, and a
  `test_harness_events_excluded_from_rebuild_tables` assertion.
- **Docs**: `docs/ARCHITECTURE.md`'s schema-versions table has one row per
  version (e.g. the `v30` / `hook_events` row around line 688) — prose
  covers the column tuple, live-write-only status, gating config key, and
  reader/CLI surface it enables, closing with the `(ENH-NNNN)` tag.
  `docs/reference/API.md` lists new writer functions both in an import-list
  comment (pattern: `record_hook_event,     # write a hook_events row
  (ENH-2506)` around API.md:7808-7809) and as a full `###`-level entry with
  signature + prose (around API.md:7868-7903 for the `hook_event` example).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py` — the `SCHEMA_VERSION` bump from 30→31
  breaks 14 existing **literal** `assert SCHEMA_VERSION == 30` sites that must
  be bumped to `31` as part of this change (distinct from, and in addition to,
  the already-scoped "add `TestSchemaV31HarnessEvents`" work): lines 1382,
  1827, 1997, 2049, 2145, 3862, 3903, 4651, 4797, 5018, 5123, 5163, 5207, 5414
  (the last of these is inside `TestSchemaV30HookEvents.test_v29_db_upgrades_gains_hook_events`,
  the class this issue's new test class is modeled on). Other `SCHEMA_VERSION`
  references in the same file (lines 80, 346, 699, 1096, 1162, 1339, 2034,
  2202, 3100, 4156) compare against the *live* imported constant rather than a
  hardcoded literal and need no edit. [wiring pass finding]
- `scripts/tests/test_verify_kinds.py::TestRun::test_clean_state_returns_zero`
  — confirmed fully data-driven against the live `_MIGRATIONS`/`_KIND_TABLE`/
  `_KINDLESS_TABLES`; requires no test-code change, only the `session_store.py`
  registration already in scope. [wiring pass finding, confirms existing AC]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2560` — the `export --tables` choices row hardcodes
  table-kind names (`test_run_event`, `hook_event`, etc.) separately from the
  `--kind` choices row at line 2485 (already noted in this issue's Codebase
  Research Findings). Needs `harness_event` appended alongside the `--kind`
  row's `harness` addition. [wiring pass finding]

## Notes carried from ENH-2493

- Naming: prefer `record_harness_event` (matches sibling
  `record_test_run_event`); no naming-collision risk on this symbol.
- `_bootstrap_schema_at(db, version)` test helper in
  `test_session_store.py` is the existing pattern for the schema-upgrade test
  (`_bootstrap_schema_at(db, <version-1>)` then assert `harness_events` in
  `sqlite_master` after `ensure_db()`).

## Resolution

Implemented as scoped, verified live against `main`:

- `session_store.py`: bumped `SCHEMA_VERSION` 30→31; appended the `v31`
  `harness_events` migration (16 columns incl. `parent_id` + 5 `semantic_*`
  detail columns, 4 indexes); registered `"harness"` in `VALID_KINDS`/
  `_KIND_TABLE`; added `record_harness_event()` (kwargs-only, raises on
  failure, mirrors `record_test_run_event`'s shape) and exported it in
  `__all__`; extended `_REBUILD_TABLES`'s exclusion comment; added
  `"harness_event": ("harness_events", "ts")` to `_EXPORT_TABLE_MAP` +
  `_EXPORT_DEFAULT_TABLES`.
- `cli/session.py`: added `harness_event`/`harness` to the `export --tables`
  help text and module docstring.
- `observability/schema.py`: added `HarnessEventVariant` and registered it in
  `DES_VARIANTS`.
- Docs: `docs/ARCHITECTURE.md` v31 schema-versions row + `v1–v31` mermaid/table
  range bump; `docs/reference/API.md` `record_harness_event` import-list line
  + full `###` reference block; `docs/reference/CLI.md` `--kind`/`--tables`
  choice lists + example line.
- Tests: new `TestSchemaV31HarnessEvents` + `TestRecordHarnessEvent` classes in
  `test_session_store.py` (columns, indexes, upgrade path, kind registration,
  rebuild exclusion, round-trip incl. `parent_id` linkage, kwargs-only
  signature, raises-on-failure contract, FTS indexing). Bumped all literal
  `SCHEMA_VERSION`/schema-version-value `== 30` assertions to `31` across
  `test_session_store.py` (22 sites — the 14 the wiring pass listed plus 8
  more `int(row[0])`/`int(version[0]) == 30` sites the wiring pass's grep
  pattern missed) and `test_assistant_messages.py` (1 site).
- Full suite (`python -m pytest scripts/tests/`): 15851 passed, 38 skipped.
  `ruff check scripts/` and `python -m mypy scripts/little_loops/` clean.
  `ll-verify-des-audit` passes. Manually verified `ll-session export --tables
  harness_event` does not fail.

## Session Log
- `/ll:manage-issue` - 2026-07-22T20:34:27Z - `d595f465-9725-4c4c-a7d5-1eec5ab2a827.jsonl`
- `/ll:wire-issue` - 2026-07-22T20:12:18 - `bcf7e327-9406-4f93-8939-ba2998c7c2b7.jsonl`
- `/ll:refine-issue` - 2026-07-22T20:04:53 - `dc740421-9224-4b93-ac72-bcc97f62f681.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `5a7a2fd0-cba1-488a-89c7-36283dba4691.jsonl`
