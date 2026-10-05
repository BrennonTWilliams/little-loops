---
id: BUG-3737
type: BUG
title: Unescaped SQLite read-only URIs create or open the wrong database
priority: P2
status: open
discovered_by: ll:capture-issue
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:21:19Z'
verify_verdict: VALID
relates_to:
- EPIC-3710
- FEAT-3721
- FEAT-3711
- ENH-3720
blocks:
- FEAT-3721
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3737: Unescaped SQLite read-only URIs create or open the wrong database

## Summary

Read-only SQLite opens interpolate literal filesystem paths into a URI without percent encoding. A path containing `#` or `?` can be truncated before the internally supplied `mode=ro` option, causing SQLite's default read-write-create open to create a different database. Literal `%XX` sequences can select a decoded alias. Repair literal file-URI construction independently of the ll-next implementation; FEAT-3721 depends on this existing primitive's no-creation guarantee.

## Current Behavior

`SqliteBackend.connect_readonly` and `_connect_readonly_bound` use raw path interpolation in `scripts/little_loops/session_store/backend.py` at lines 442 and 458. The same construction appears in the artifact export's raw opener, native session-index readers, codegraph reader and workspace-quality ATTACH source URI. `PRAGMA query_only` is applied after the connection opens, so it cannot prevent opening/creating the wrong file.

## Expected Behavior

All literal local database paths select that exact file. Internally owned SQLite URI options survive special characters in the path. Strict read-only and existing-file read-write opens never create a missing main database or a truncated/decoded alias. Preserve each consumer's error, timeout, deadline and ATTACH behavior; SQLite-managed WAL/SHM coordination sidecars retain their existing documented exception.

## Motivation

Callers rely on these readers to inspect existing databases without creating files or selecting unrelated evidence. Special-character project/store paths violate that guarantee today. Fixing the shared construction independently protects existing consumers and lets the ll-next reader/writer consume an already proven literal-path primitive.

## Proposed Solution

Add one dependency-light helper that builds a percent-encoded absolute `file:` URI from a literal Path and an internally chosen mode (`ro` or `rw`). `Path.absolute().as_uri()` with the internally owned mode query is a proven stdlib option. Do not reinterpret a Path as caller-supplied URI syntax, re-resolve project/store ownership, or introduce migrations. Use the helper for the identified raw opens and ATTACH source URI; retain their separate connection policies. In particular, the export opener must still permit writes to its attached scratch DB and cannot be replaced with the query-only backend connection.

## Integration Map

### Files to Modify

- `scripts/little_loops/sqlite_uri.py` — **new**: dependency-free shared literal file-URI builder.
- `scripts/little_loops/session_store/backend.py`: both ordinary and deadline-bound read-only opens.
- `scripts/little_loops/session_store/queries.py`: `_connect_readonly`, preserving read-only main / writable attached scratch export semantics.
- `scripts/little_loops/session_store/sessions.py`: both native SQLite session-index opens, preserving fail-soft fallback.
- `scripts/little_loops/codequery/codegraph.py`: raw read-only codegraph opener.
- `scripts/little_loops/issue_history/workspace_quality.py`: parameter-bound read-only ATTACH URI.
- `scripts/tests/test_session_store_backend.py`, `scripts/tests/test_enh3720_session_store_deadline.py` and focused existing consumer/export tests: literal identity/no-creation fixtures and unchanged connection policies.

### Dependent Files

- FEAT-3721 shared reader and FEAT-3711 existing-store writer plans; the reader must reuse the corrected primitive and the writer the encoded URI helper.
- Existing history chokepoint gate: preserve its deliberate raw-export/native-index exceptions rather than changing their routing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Raw-site inventory is one larger than the issue lists.** Every site interpolates a `Path` with no quoting and no `.absolute()`/`.as_uri()`: `backend.py:442` and `:458`, `queries.py:260` (`_connect_readonly`), `sessions.py:130` (`_query_threads_db`) **and `sessions.py:696` (`_list_codex_workspaces`)**, `codegraph.py:86` (`_open_db`, guarded by a prior `db_path.exists()`), `workspace_quality.py:223` (`_open_union` ATTACH parameter on a `:memory:` connection opened `uri=True`). The `sessions.py:696` site is the "second native session-index open"; the test-side copy at `scripts/tests/spike/session_store_backend_dialect/dialects.py:79` uses the same raw f-string but is spike code, not production.
- **Error handling differs per site and must stay per-site:** `backend.py` wraps `sqlite3.Error` into `HistoryUnavailable`; `codegraph.py` and `sessions.py` swallow and return `None`/`continue`; `queries.py` lets it propagate.
- **No existing URI helper or escaping convention.** No `as_uri(` or `urllib.parse.quote` call exists under `scripts/little_loops`; `urllib.parse` appears only for `urlsplit`/`parse_qs` parsing. This is a new primitive, not a consolidation.
- **Convention — placement:** single-purpose dependency-free helpers are flat top-level `scripts/little_loops/<name>.py` modules with a prose docstring (evidence: `paths.py`, `env_file.py`, `pii.py`, `text_utils.py`), tested by flat `scripts/tests/test_<name>.py` with `tmp_path` fixtures. Contested: SQLite-adjacent helpers have precedent both ways (`session_store/deadline.py` in the subpackage vs top-level `queue_store.py`); the issue's top-level `sqlite_uri.py` is consistent with the first rule but not with the subpackage precedent.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py` — re-exports module-level `connect_readonly`; no change (the helper lives in top-level `little_loops.sqlite_uri`, not this package) [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — calls `connect_readonly(...)` in `rebuild_needed()` and a second site near :1658; inherits corrected `backend.py` behavior, no edit [Agent 1 finding]
- `scripts/little_loops/issue_history/workspace_quality.py` — `_open_member_readonly()` already routes through `resolve_backend().connect_readonly(...)`; only `_open_union()`'s ATTACH parameter is a raw URI. The two `sqlite3.connect(":memory:", uri=True)` hosts in `_open_union()` carry no path and need no change [Agent 1 finding]
- `scripts/little_loops/issue_history/evolution.py` — `_open_db()` calls `resolve_backend().connect_readonly(...)`; inherits the fix. Not `codegraph._open_db` (same name, different function) [Agent 1 finding]
- `scripts/little_loops/cli/history.py`, `cli/session.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/doctor.py`, `cli/doctor_trim.py` — consume `connect_readonly` / `resolve_backend().connect_readonly`; inherit the fix, no edit [Agent 1 finding]
- `scripts/little_loops/cli/artifact/dashboard.py` — calls `build_snapshot_db()`, which calls `queries._connect_readonly()` at :541; inherits the fix [Agent 2 finding]
- `scripts/little_loops/session_store/sessions.py` — `_query_threads_db()` is reached only via `detect_sessions()` (:241) and `_list_codex_workspaces()` only via `list_workspaces()` (:584); neither is called directly by tests [Agent 1/3 finding]
- `scripts/little_loops/history_reader/_base.py` — `_connect_readonly()` routes through `open_history_readonly`, not a raw URI; same name as `queries._connect_readonly`, unaffected [Agent 1 finding]
- `scripts/tests/spike/session_store_backend_dialect/dialects.py:79` — spike-only raw `f"file:{self.db_path}?mode=ro"` copy; deliberately out of scope [Agent 1 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3410_workspace_quality.py` — **will break**: `test_never_uses_migrating_opener` slices `workspace_quality.py` from `def _open_member_readonly` and asserts `"mode=ro" in code`; the only `mode=ro` text in that slice is the ATTACH f-string in `_open_union()`. Replacing it with `sqlite_file_uri(path, mode="ro")` removes the substring (the module-docstring mention at :8 precedes the slice). Re-express the pin (e.g. assert `sqlite_file_uri(` and `mode="ro"`) while keeping the `ensure_db(` / `_connect_readonly(` / `immutable=1` absences [Agent 2/3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — `test_snapshot_builder_never_uses_the_migrating_open_path` survives only by accident: its slice (`def _connect_readonly` → `def export_tables_help`) includes the `_connect_readonly` docstring, which contains `mode=ro` (:252, :257). Decide deliberately whether to re-express it so the raw-open property stays asserted by code rather than docstring text [Agent 2/3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — `test_allowlist_entries_still_exist_and_still_have_raw_connects` fails if an allowlisted file (`codequery/codegraph.py`, `session_store/sessions.py`, `session_store/queries.py`, `issue_history/workspace_quality.py`) loses its last `sqlite3.connect`; keep every connect in place. The new `sqlite_uri.py` is auto-scanned by `rglob("*.py")` and must contain no `sqlite3.connect` (else it needs an allowlist entry) [Agent 2/3 finding]
- `scripts/tests/test_sqlite_uri.py` — **new**: flat helper test following `test_env_file.py` (module docstring naming `little_loops.sqlite_uri`, `from __future__ import annotations`, one class per behavior, `tmp_path: Path`, `-> None`, no mocks, no markers). Cover `ro`/`rw`, relative vs absolute, literal `%`/`#`/`?`/space/Unicode, missing file stays missing in both modes (pins the `rw` contract for FEAT-3711), and mode injection via path content [Agent 3 finding]
- `scripts/tests/test_session_store_backend.py` — extend `TestConnectReadonlyStrict` using `_mark(db_path, value)` and the decoy-file shape of `test_explicit_non_default_shaped_path_bypasses_env_override`; add special-character identity + no-creation cases there [Agent 3 finding]
- `scripts/tests/test_enh3720_session_store_deadline.py` — add deadline-bound identity/no-creation cases to `TestLocalBinding` (uses `connect_readonly(db, deadline=Deadline.after(10))`); unmarked, since not timing-sensitive (`no_parallel` is only on `TestLocalCancellationTiming` / `TestRemoteSocketEnforcement`) [Agent 3 finding]
- `scripts/tests/test_session_discovery.py` — `_query_threads_db` / `_list_codex_workspaces` have no direct tests; extend `TestDetectSessionsCodexSqlitePath` and `TestListWorkspaces::test_list_workspaces_codex_via_sqlite` (build the Codex home / `state_N.sqlite` under a `#`/`?`/`%` directory via `_make_state_db`) and keep `TestDetectSessionsCodexFallback` fail-soft cases (`..._when_db_missing`, `..._when_db_unusable_at_first_statement`) green [Agent 3 finding]
- `scripts/tests/test_codequery_codegraph.py` — `codegraph._open_db` has no direct test; extend `TestQueries` with `_build_index(db_path, ...)` at a special-character repo path, and keep `TestStatusMissingIndex::test_no_db_reports_unavailable` (the `db_path.exists()` guard) [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — extend `TestBuildSnapshotDb` / `TestSnapshotRoundTrip` (writable attached scratch DB) and `TestSourceDbUntouched::test_history_db_byte_identical_after_export` with a special-character source path; `TestMissingDatabase::test_missing_history_db_exits_1` covers missing-source [Agent 3 finding]
- `scripts/tests/test_feat3323_sse_bridge.py` — `TestHistoryRoute::test_readonly_opener_rejects_writes` and `test_never_migrates_or_creates_missing_db` call `queries._connect_readonly` directly; must stay green [Agent 2/3 finding]
- `scripts/tests/test_feat3418_workspace_quality.py` — `TestUnionViewCoverage`, `TestSupersedesScopedPerMember`, `TestFollowUpFixSurvivesDiscriminator` call `_open_union([...])`; add a special-character member path to `TestUnionViewCoverage`, and keep `TestSourceUntouchedDuringTotals::test_member_files_unchanged_after_totals_run` green [Agent 2/3 finding]
- `scripts/tests/test_feat3410_workspace_quality.py` — `_healthy_member(tmp_path, name, role)` deliberately uses non-default-shaped `<name>-history.db` names (the autouse `_isolate_history_db` fixture would otherwise collapse members); a special-character fixture must keep that property [Agent 3 finding]
- `scripts/tests/test_feat3445_workspace_activity.py` — `TestNeverUsesMigratingOpener` slices `workspace_activity.py` with no `mode=ro` assertion and does not import the helper; no change [Agent 2 finding]
- Fixture hygiene: new fixtures must use `tmp_path` (or `/nonexistent/...`), never `/home/<user>/` — the private-refs pre-commit hook rejects those [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — Module Overview table (near the `little_loops.env_file` / `little_loops.paths` / `little_loops.queue_store` rows): add a `little_loops.sqlite_uri` row (dotted name only, per the docs-audience gate) describing `sqlite_file_uri(path, *, mode)` [Agent 2 finding]
- `docs/reference/API.md` — "Backend chokepoint: little_loops.session_store.backend" section (:9988 "strict read-only open: never creates or migrates (D19)") and "Total deadline for read-only connections (ENH-3720)" (:10009-10047): note that read-only opens encode the literal path so `#`/`?`/`%` select the exact file [Agent 2 finding]
- `docs/reference/API.md:2421` — `aggregate_history_dbs` row in the `little_loops.issue_history` table says "each via its own read-only `mode=ro` connection"; wording stays true, optional [Agent 2 finding]
- `docs/ARCHITECTURE.md` — Directory Structure tree (top-level modules near `text_utils.py` / `pii.py` at :218-219; not exhaustive, so optional) and "History DB: Producer→Consumer Flow" ("never-create" / "strict read-only"). Keep the `_connect_readonly` string at :862 — `test_wiring_guides_and_meta.py` pins it (`("docs/ARCHITECTURE.md", "_connect_readonly", "ENH-1753")`) [Agent 2/3 finding]
- `CONTRIBUTING.md` — project-structure tree (:294-307) lists `text_utils.py`, `pii.py`, `queue_store.py`; optionally add `sqlite_uri.py` [Agent 2 finding]
- `docs/reference/CLI.md` — "ll-artifact dashboard" (:5586) says the snapshot uses "a raw `file:…?mode=ro` connection"; still true, no edit [Agent 2 finding]
- `.ll/learning-tests/sqlite3.md` — proven claim "ATTACH DATABASE 'file:<path>?mode=ro' … works" is for the raw form; the encoded `file:///…?mode=ro` form is the same mechanism but not separately proven. Not a gate; consider re-proving via `/ll:explore-api` [Agent 2 finding]
- No test compares the API.md Module Overview, the ARCHITECTURE.md tree or the CONTRIBUTING.md tree to the filesystem; `test_docs_audience_gate.py` applies to any new entry. Any CHANGELOG entry belongs under a concrete version section, not `[Unreleased]` [Agent 2/3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- None. `scripts/pyproject.toml` ships the new module automatically (`packages = ["little_loops"]`, wheel `include = ["little_loops/**", ...]`); no `config-schema.json` key, `history.db` schema/`SCHEMA_VERSION` change or `ll-verify-package-data` entry is needed [Agent 1/2 finding]

## Implementation Steps

1. Add a focused reproduction with literal filename and directory characters `#`, `?`, `%`, spaces and Unicode, plus differently populated truncated/decoded decoy DBs.
2. Implement the shared stdlib URI builder; adapt both backend read-only branches and the enumerated raw read-only/ATTACH consumers without changing their connection policies.
3. Verify existing and missing-file identity, no alias creation/mutation, relative and absolute paths, timeout/deadline/error behavior, and writable attached export scratch behavior. Run focused tests, the chokepoint gate and the local suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_feat3410_workspace_quality.py::test_never_uses_migrating_opener` — the `"mode=ro" in code` assertion fails once `_open_union()` calls `sqlite_file_uri(path, mode="ro")`; re-express it (e.g. `sqlite_file_uri(` + `mode="ro"`) and keep the `ensure_db(` / `_connect_readonly(` / `immutable=1` absences
- Update `scripts/tests/test_feat3304_artifact_dashboard.py::test_snapshot_builder_never_uses_the_migrating_open_path` — passes only via docstring text after the edit; re-express so the raw-open/no-migration property is asserted by code
- Keep every `sqlite3.connect` call in `codegraph.py`, `sessions.py`, `queries.py` and `workspace_quality.py` — `test_history_store_chokepoint_gate.py::test_allowlist_entries_still_exist_and_still_have_raw_connects` fails otherwise; keep `sqlite_uri.py` free of `sqlite3.connect` (else it needs an allowlist entry)
- Create `scripts/tests/test_sqlite_uri.py` following `test_env_file.py` conventions (real `tmp_path` files, no mocks, no markers)
- Extend special-character fixtures in `test_session_store_backend.py::TestConnectReadonlyStrict`, `test_enh3720_session_store_deadline.py::TestLocalBinding`, `test_session_discovery.py::TestDetectSessionsCodexSqlitePath` / `TestListWorkspaces`, `test_codequery_codegraph.py::TestQueries`, `test_feat3304_artifact_dashboard.py::TestBuildSnapshotDb` / `TestSnapshotRoundTrip`, and `test_feat3418_workspace_quality.py::TestUnionViewCoverage`
- Update `docs/reference/API.md` — add a `little_loops.sqlite_uri` Module Overview row (dotted name only) and note literal-path encoding in the "Backend chokepoint" and ENH-3720 deadline sections; optionally list `sqlite_uri.py` in `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` module trees, preserving the `_connect_readonly` string `test_wiring_guides_and_meta.py` pins

## Program Design

### Signatures

- `sqlite_file_uri(path: Path, *, mode: Literal["ro", "rw"] = "ro") -> str` — new helper in `little_loops.sqlite_uri`.

The pure stdlib helper validates the internally chosen mode, converts a relative Path to its absolute spelling without a fresh project/store lookup or symlink-ownership decision, encodes that literal path with `Path.as_uri()`, then appends the owned mode query. Literal percent sequences are encoded once; they are never interpreted as pre-existing escapes. The helper does not stat/open/create the DB, set connection pragmas, inspect config, or resolve remote targets. No new dependency, CLI or schema is needed.

### Call Path

`SqliteBackend.connect_readonly` / `_connect_readonly_bound` → new `sqlite_file_uri` → existing `sqlite3.connect`; direct readers and `workspace_quality._open_union` use the same builder for their existing connection/ATTACH operations.

Resolved local Path → `sqlite_file_uri(..., mode="ro")` → each consumer's existing `sqlite3.connect(..., uri=True)` or parameter-bound ATTACH operation. Backend ordinary/deadline branches retain row factories, query-only, timeout, deadline and error translation. Export retains a read-only main DB with a writable attached scratch DB; native-index/codegraph readers retain their current failure handling. FEAT-3711 later supplies `mode="rw"` for its separate existing-file writer. Encoding is the only policy shared by these consumers; moving them to the migrating opener or adding query-only to the export would be incorrect.

### Validation

Use temporary DBs with different identifying rows in intended and truncated/decoded decoy files. Assert identity, file sets and decoy content for both backend branches and representative direct/ATTACH consumers. A missing source must remain missing. Retain existing deadline/lock tests and the export scratch-write regression; all these checks exercise externally visible file/connection behavior rather than only comparing a generated URI string.

## Impact

- **Priority:** P2 — a documented read-only primitive can create an unintended file and read the wrong source.
- **Effort:** Small — shared URI builder, narrow call-site adaptations and focused fixtures.
- **Risk:** Low–Medium — preserve intentional direct-export ATTACH semantics and existing fail-soft readers.
- **Breaking Change:** No; restores literal filesystem path and no-creation contracts.

## Steps to Reproduce

1. In a temporary directory, create `hash#name.db`, `query?name.db` and `percent%23name.db` with a table containing their exact filename.
2. Call the current `backend.connect_readonly` with each literal Path, both with no deadline and with `Deadline.after(1.0)`; query the table and list the temporary directory afterward.
3. The deadline-bound reproduction on 2026-10-05 produced:

```text
hash#name.db: OperationalError: no such table: evidence
query?name.db: OperationalError: no such table: evidence
percent%23name.db: HistoryUnavailable: ... unable to open database file
```

The directory also contained newly created `hash` and `query` files. A second reproduction exercised both ordinary and deadline-bound branches and confirmed wrong-store reads plus those newly created aliases in each. An encoded `Path.absolute().as_uri() + '?mode=ro'` control opened the intended stores; encoded `mode=rw` rejected a missing special-character file without creation. All reproduction artifacts were confined to an automatically removed temporary directory.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Existing test conventions for the new fixtures:** real files under `tmp_path`, no `sqlite3` mocks. `test_session_store_backend.py` identifies which file a connection opened via `_mark(db_path, value)` (a `meta('which', value)` row) and already holds the strict-read-only contract in `TestConnectReadonlyStrict` (`test_missing_store_raises_history_unavailable` asserts the parent dir is not created; `test_existing_store_is_byte_identical_before_and_after` compares sha256). `test_enh3720_session_store_deadline.py` uses a `db` fixture plus `FakeClock`, with real-I/O cases marked `no_parallel`. `test_feat3410_workspace_quality.py` provides `_healthy_member` and `_sha256`. No existing test places `#`, `?`, `%` or Unicode in a SQLite path — the special-character fixtures are net-new coverage.

## Root Cause

- **File / functions:** `scripts/little_loops/session_store/backend.py`, `SqliteBackend.connect_readonly` and `_connect_readonly_bound`.
- **Explanation:** Filesystem characters are parsed as URI fragment/query delimiters or escapes. The read-only query can disappear entirely, and query-only protection happens too late. A literal filesystem path is not a pre-escaped SQLite URI.

## Scope Boundaries

Fix literal-path URI construction only. No backend-routing redesign, new history schema, remote support, WAL suppression, global query-only policy, or ll-next command implementation. The future FEAT-3711 existing-store writer consumes the helper with `mode=rw` rather than duplicating URI interpolation.

## Acceptance Criteria

- [ ] Ordinary and deadline-bound reads open the intended existing DB for special characters in either a directory or filename; populated decoy DBs are never read or mutated.
- [ ] Missing special-character paths fail without creating the requested file or a truncated/decoded alias; main-DB creation cannot occur before query-only protection.
- [ ] Identified raw consumers and ATTACH sources reuse the literal-safe URI builder; direct export/native-index connection policies remain intact, including writable attached scratch data and fail-soft fallback.
- [ ] Relative/absolute paths, literal percent sequences, spaces and Unicode are tested; the internal `ro`/`rw` modes cannot be lost or supplied by path content. The helper's `rw` missing-file case is pinned for FEAT-3711.
- [ ] Existing per-lock timeout, ENH-3720 deadline and history error translation behavior remain intact; no schema/setup/migration or remote changes. Focused regressions, chokepoint gate and `python -m pytest scripts/tests/` pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Source-text pins bind the `mode=ro` literal and will react to the edit.** `test_feat3304_artifact_dashboard.py::test_snapshot_builder_never_uses_the_migrating_open_path` slices `queries.py` from `def _connect_readonly` to `def export_tables_help` and asserts `"mode=ro" in builder` and `"_pkg.connect" not in builder`. `test_feat3410_workspace_quality.py::test_never_uses_migrating_opener` slices `workspace_quality.py` from `def _open_member_readonly` onward and asserts `"mode=ro" in code` while `ensure_db(`, `_connect_readonly(` and `immutable=1` are absent. If the `mode=ro` text moves into the helper (`mode` as a parameter, not an inline literal), both pins must still hold or be deliberately re-expressed; they exist to prove the raw-open/no-migration property and that property must stay asserted.
- **History chokepoint gate** (`test_history_store_chokepoint_gate.py`): AST-matches `sqlite3.connect` calls only (not URI strings or ATTACH) against `_ALLOWLIST`, and `test_allowlist_entries_still_exist_and_still_have_raw_connects` fails if an allowlisted file loses its last raw connect. Routing all opens through `sqlite_file_uri` leaves every `sqlite3.connect` call in place, so the allowlist should be unchanged; replacing a raw connect with a different opener would force removing that file's entry.

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Integration Map, Files to Modify: `scripts/little_loops/sqlite_uri.py` was cited as an existing path, but the file is not yet created or tracked (format-check `stale_file_ref`, blocking). Rewritten in place with the recognized `**new**` marker, matching `scripts/tests/test_sqlite_uri.py`. A follow-up `ll-issues format-check BUG-3737` reports no blocking gap keys.

## Review Notes

- 2026-10-05: Found during EPIC-3710 pre-implementation review; temporary-store reproduction confirmed wrong-file creation. `/ll:advise` with Opus (confidence 0.76) corroborated the URI mechanism and recommended an independent prerequisite bug so current readers do not wait on the arena core.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Local backend strict-read-only and deadline contracts. |

## Status

**Open** | Created: 2026-10-05 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-05T18:46:02 - `31d58183-8758-4d4f-ad48-2c2f7478dd36.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:44:52 - `ba9691d0-f847-4e4f-9425-b042e4d6175b.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:43:39 - `b9eeeb68-d3f1-47df-931c-17a810117e8f.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:42:30 - `9c8983c4-64a7-4209-9036-53d8d388216c.jsonl`
- `/ll:wire-issue` - 2026-10-05T18:40:42 - `011d2688-48f6-4303-aaa6-bc531df0e6b7.jsonl`
- `/ll:refine-issue` - 2026-10-05T18:34:07 - `af0cc2df-1eb5-430f-a8c4-2e0bd187887f.jsonl`
- `/ll:capture-issue` - 2026-10-05T18:26:42 - `e0d3fb45-7fc3-4e7a-a2c8-9ad8bfdb517e.jsonl`
