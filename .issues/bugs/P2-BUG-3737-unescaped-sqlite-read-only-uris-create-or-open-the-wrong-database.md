---
id: BUG-3737
type: BUG
title: Unescaped SQLite read-only URIs create or open the wrong database
priority: P2
status: open
discovered_by: ll:capture-issue
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:21:19Z'
relates_to:
- EPIC-3710
- FEAT-3721
- FEAT-3711
- ENH-3720
blocks:
- FEAT-3721
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

- New dependency-free `scripts/little_loops/sqlite_uri.py`: shared literal file-URI builder.
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

## Implementation Steps

1. Add a focused reproduction with literal filename and directory characters `#`, `?`, `%`, spaces and Unicode, plus differently populated truncated/decoded decoy DBs.
2. Implement the shared stdlib URI builder; adapt both backend read-only branches and the enumerated raw read-only/ATTACH consumers without changing their connection policies.
3. Verify existing and missing-file identity, no alias creation/mutation, relative and absolute paths, timeout/deadline/error behavior, and writable attached export scratch behavior. Run focused tests, the chokepoint gate and the local suite.

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

## Review Notes

- 2026-10-05: Found during EPIC-3710 pre-implementation review; temporary-store reproduction confirmed wrong-file creation. `/ll:advise` with Opus (confidence 0.76) corroborated the URI mechanism and recommended an independent prerequisite bug so current readers do not wait on the arena core.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Local backend strict-read-only and deadline contracts. |

## Status

**Open** | Created: 2026-10-05 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-10-05T18:34:07 - `af0cc2df-1eb5-430f-a8c4-2e0bd187887f.jsonl`
- `/ll:capture-issue` - 2026-10-05T18:26:42 - `e0d3fb45-7fc3-4e7a-a2c8-9ad8bfdb517e.jsonl`
