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

`SqliteBackend.connect_readonly` and `_connect_readonly_bound` in `scripts/little_loops/session_store/backend.py` interpolate paths into `file:` URIs. Five further expressions appear in the export source opener, both native session-index readers, the codegraph reader and workspace-quality ATTACH source. `PRAGMA query_only` runs after opening, so it cannot prevent opening/creating the wrong file. The writable export ATTACH also interprets a relative destination beginning with `file:` as URI syntax, selecting a different scratch file.

## Expected Behavior

Valid literal local database paths select that exact file. Internally owned SQLite URI options survive special characters in the path. Strict read-only and existing-file read-write opens never create a missing main database or a truncated/decoded alias. Reject actual embedded NULs before encoding, preserving `ValueError` rather than opening a prefix alias. The writable export scratch destination may be created at its intended literal path. Preserve each consumer's error, timeout, deadline and ATTACH behavior; SQLite-managed WAL/SHM coordination sidecars retain their existing documented exception.

## Motivation

Callers rely on these readers to inspect existing databases without creating files or selecting unrelated evidence. Special-character project/store paths violate that guarantee today. Fixing the shared construction independently protects existing consumers and lets the ll-next reader/writer consume an already proven literal-path primitive.

## Proposed Solution

Add one dependency-free helper that builds a percent-encoded absolute `file:` URI from a literal `Path` and an internally chosen mode (`ro` or `rw`). Reject actual embedded NULs and unsupported modes before returning a URI. Use `Path.absolute().as_uri()` followed by the owned mode query; do not interpret the Path as pre-escaped URI syntax or perform another project/store lookup.

Use the helper for all seven read-only URI expressions, retaining their separate connection policies. The export source opener must still permit writes to its attached scratch DB and cannot use the query-only backend connection. For that writable ATTACH destination, pass `str(Path(dest).absolute())` as an ordinary absolute filename: it cannot begin with the `file:` scheme and retains SQLite's existing create-on-attach behavior. This needs no `rwc` helper mode.

## Integration Map

### Files to Modify

| File | Required change / stable anchor |
|------|---------------------------------|
| `scripts/little_loops/sqlite_uri.py` (**new**) | Pure `sqlite_file_uri` builder; no connection or routing policy. |
| `scripts/little_loops/session_store/backend.py` | `SqliteBackend.connect_readonly` and `_connect_readonly_bound`: encode both read-only opens. |
| `scripts/little_loops/session_store/queries.py` | `_connect_readonly`: encode source; `build_snapshot_db`: make writable scratch ATTACH destination an absolute ordinary filename. |
| `scripts/little_loops/session_store/sessions.py` | `_query_threads_db` and `_list_codex_workspaces`: encode both native-index opens. |
| `scripts/little_loops/codequery/codegraph.py` | `_open_db`: encode read-only index open. |
| `scripts/little_loops/issue_history/workspace_quality.py` | `_open_union`: encode each parameter-bound read-only ATTACH source. |
| `docs/reference/API.md` | Add dotted `little_loops.sqlite_uri` Module Overview entry and note literal-path validation/encoding in backend read-only/deadline contracts. |

### Dependent Files and Similar Patterns

- `session_store/__init__.py`, `session_store/lifecycle.py`, `issue_history/evolution.py`, existing history readers and CLI consumers inherit the backend fix; no routing or re-export changes. The dashboard inherits the export fix through `build_snapshot_db`.
- FEAT-3721 reuses the corrected backend; FEAT-3711 reuses the helper with `mode="rw"` for its future existing-file writer. Neither feature's implementation belongs here.
- Keep the helper top-level, following dependency-free utility modules such as `little_loops.paths` and `little_loops.env_file`; use a flat `scripts/tests/test_sqlite_uri.py` test module with real temporary databases.
- `scripts/tests/test_history_store_chokepoint_gate.py` scans raw `sqlite3.connect` calls, not URI construction. Keep existing connections at their current sites and keep the helper connection-free; the allowlist stays unchanged. Update its export exception's explanatory wording if the source-text pin changes.
- The spike-only raw interpolation in `scripts/tests/spike/session_store_backend_dialect/dialects.py` remains out of scope.

### Tests

| Test file | Coverage / existing anchors |
|-----------|-----------------------------|
| `scripts/tests/test_sqlite_uri.py` (**new**) | Broad literal-path matrix, `ro`/`rw` behavior, missing intended file with/without populated aliases, NUL and invalid-mode rejection, relative/absolute and symlink/`..` behavior. |
| `scripts/tests/test_session_store_backend.py` | Extend `TestConnectReadonlyStrict`; reuse `_mark` sentinels and existing byte-identity/missing-store checks. |
| `scripts/tests/test_enh3720_session_store_deadline.py` | Extend `TestLocalBinding` with deadline-bound identity/no-creation cases; keep expired-before-open, lock-wait and cancellation tests. New identity fixtures are not timing-sensitive and need no `no_parallel` marker. |
| `scripts/tests/test_session_discovery.py` | Extend `TestDetectSessionsCodexSqlitePath` and `TestListWorkspaces`; place `state_N.sqlite` under a special-character home using `_make_state_db`. Keep missing/unusable-index fallback tests. |
| `scripts/tests/test_codequery_codegraph.py` | Extend `TestQueries` with a special-character index path; preserve `TestStatusMissingIndex` and the existing existence guard. |
| `scripts/tests/test_feat3304_artifact_dashboard.py` | Extend `TestBuildSnapshotDb` / `TestSnapshotRoundTrip` and `TestSourceDbUntouched`; pin source read-only, writable scratch, exact literal destination (including relative `file:` prefix), and source byte identity. |
| `scripts/tests/test_feat3323_sse_bridge.py` | Keep `TestHistoryRoute` write-rejection and missing-source/no-migration contracts green. |
| `scripts/tests/test_feat3418_workspace_quality.py` | Extend `TestUnionViewCoverage` with a special-character member path; preserve discriminator behavior and `TestSourceUntouchedDuringTotals`. |
| `scripts/tests/test_feat3410_workspace_quality.py` | Update `TestSourceDbUntouched.test_never_uses_migrating_opener`; preserve no-migration / no-`immutable` checks. Member fixtures keep non-default `<name>-history.db` names so the autouse history override does not collapse them. |

The workspace source-text pin loses its `mode=ro` match when ATTACH uses the helper; the export pin can falsely pass by matching a docstring. Re-express both against executable code (AST or a narrowly selected call), backed by behavioral write/no-creation tests. Retain the no-migration checks; do not preserve a passing substring assertion through comments/docstrings.

### Documentation and Configuration

- No config, manifest, CLI, schema, migration, remote-backend or package-data change: the new module ships automatically under `little_loops/**`.
- Architecture/contributor module trees are optional; preserve architecture references enforced by `scripts/tests/test_wiring_guides_and_meta.py`. New API overview entries use dotted names per the docs-audience gate.
- Existing `.ll/learning-tests/sqlite3.md` ATTACH evidence supports the mechanism; behavioral tests here prove the encoded source URI and writable destination. No additional learning-test provisioning gate is required.

## Implementation Steps

1. Add failing real-file regressions for both backend branches and the helper contract, including populated aliases, missing intended paths, actual NUL versus literal `%00`, and a relative `file:` export destination.
2. Implement the URI builder with explicit mode/NUL validation; adapt all seven read-only URI expressions and the writable destination spelling without changing connection policies.
3. Add focused integration fixtures for both native-index paths, codegraph, export and workspace ATTACH; re-express the two source-text pins against code and update the API contract.
4. Run the focused files above, the chokepoint gate, and the authoritative `python -m pytest scripts/tests/` gate. Run lint/type checks appropriate to the new module and imports.

## Program Design

### Signatures

- `sqlite_file_uri(path: Path, *, mode: Literal["ro", "rw"] = "ro") -> str` — new helper in `little_loops.sqlite_uri`.

Validate `mode` at runtime (`Literal` is not runtime enforcement): anything except `ro`/`rw`, including `rwc`, `memory` and `ro&immutable=1`, raises `ValueError`. Reject an actual `\x00` in the filesystem spelling before encoding. A literal `%00` filename is valid and becomes `%2500`; it must not be rejected or decoded first.

Convert the Path with `.absolute()` and `.as_uri()`, then append exactly the owned mode query. Keep symlink and `..` spelling: no `.resolve()`, `os.path.abspath()`, `expanduser()`, `unquote()` or fresh ownership/config lookup. The helper does not stat/open/create the DB, configure connections, or resolve remote targets. Invalid-input `ValueError` passes through existing callers; do not broaden SQLite catches or translate it into `HistoryUnavailable`/fail-soft fallback. Preserve each caller's existing pre-open guards and deadline ordering.

### Call Path

`SqliteBackend.connect_readonly` / `_connect_readonly_bound` → new `sqlite_file_uri` → existing `sqlite3.connect`. Direct readers and `workspace_quality._open_union` use the same builder without moving their connection sites.

Resolved local Path → `sqlite_file_uri(..., mode="ro")` → existing `sqlite3.connect(..., uri=True)` or parameter-bound ATTACH. FEAT-3711 later supplies `mode="rw"` for its separate writer.

| Consumer | Policy to preserve |
|----------|--------------------|
| Backend ordinary / deadline | Row factory, query-only, timeout, deadline-bound factory/budget and `sqlite3.Error` → `HistoryUnavailable` with cause retained. |
| Export source | Read-only main; writable scratch ATTACH; raw SQLite errors propagate. No connection-wide query-only. |
| Native session index | Existing SQLite-error fallback to another index / rollout scan. |
| Codegraph | Existing existence guard, row factory, query-only and SQLite-error `None` result. |
| Workspace union | `uri=True` in-memory host, ATTACH capability gate, bound source parameters, TEMP views before query-only. |

Export destination → `str(Path(dest).absolute())` → existing bound writable ATTACH. Pass an ordinary filename here, not a URI or `mode="rw"` (which would refuse creation of the scratch file). No new mode or generalized connection abstraction is needed.

### Validation

- Use distinct sentinel rows for intended and truncated/decoded aliases. For encoding cases, test aliases absent and populated; also test a missing intended path with a populated alias, which must fail rather than read/write that alias. Check alias main-file hashes/content and the complete fixture-root file set.
- Put all intended parents below a plain fixture-owned container under `tmp_path`; delimiters in a directory can create sibling aliases outside that directory. Snapshot the whole container, and keep every possible alias inside it. Close fixture connections; use fully checkpointed/rollback-journal fixtures for byte-identity assertions so WAL coordination is not mistaken for main-DB mutation.
- Helper tests own the broad matrix: filename/directory, relative/absolute, `#`, `?`, `%23`, `%3F`, `%00`, spaces, Unicode and option-like content such as `?mode=rw&...`. `ro` rejects writes; `rw` permits committed writes only to the intended existing file; both reject missing files without creation. Actual NUL and unsupported modes raise `ValueError` before any alias can be opened. A symlink/`..` fixture pins the absolute-spelling policy.
- Avoid a full matrix at every consumer: cover every identified site with a focused special-character behavioral case; explicitly cover both backend branches and both native-index entry paths. Existing timeout/deadline/error/fallback tests remain the policy regressions.
- Export tests cover a special-character source and writable scratch plus a relative destination such as `Path("file:dest#name.db")` from a temporary cwd: only that exact literal destination may be created. Verify ATTACH/TEMP-view behavior and source immutability.

## Impact

- **Priority:** P2 — a documented read-only primitive can create an unintended file and read the wrong source.
- **Effort:** Small — shared URI builder, narrow call-site adaptations and focused fixtures.
- **Risk:** Low–Medium — preserve intentional direct-export ATTACH semantics and existing fail-soft readers.
- **Breaking Change:** No; restores literal filesystem path and no-creation contracts.

## Steps to Reproduce

1. Under a plain temporary container, create `hash#name.db`, `query?name.db`, `percent%23name.db` and `percent%00name.db`, each with `evidence(label)` containing `literal`.
2. Create their aliases (`hash`, `query`, `percent#name.db`, `percent`) with the same table containing `decoy`. Run `SqliteBackend().connect_readonly(path)` both ordinarily and with `deadline=Deadline.after(10)`, then read the label.
3. Both branches return `decoy`; encoded `path.absolute().as_uri() + "?mode=ro"` controls return `literal`. Repeat with no aliases: hash/query paths can create truncated files before query-only, and percent paths can fail instead of selecting the intended DB.
4. For the helper-regression case, create `nul` with a sentinel, then construct `Path(str(nul_path) + "\x00tail.db")`. The proposed unguarded `.as_uri()` control opens `nul` via `%00`; `mode=rw` can update that alias. The current raw URI containing an actual NUL raises `ValueError`. Add rejection before encoding, while preserving literal `%00` support.
5. On an export-source connection opened with `uri=True`, ATTACH a relative `Path("file:dest#name.db")` from a temporary cwd. SQLite creates `dest`, not the requested filename. Passing its absolute ordinary spelling creates the correct writable scratch file.

All cases were reproduced on 2026-10-05 on inspected branch `main`; review fixtures were confined to automatically removed temporary directories. Encoded `ro`/`rw` controls rejected missing files, retained symlink/`..` identity, and allowed writable export scratch ATTACH. The earlier discovery reproduction also observed `OperationalError: no such table: evidence` for new hash/query aliases and `HistoryUnavailable: ... unable to open database file` for a missing decoded-percent alias.

## Root Cause

- **File / functions:** `scripts/little_loops/session_store/backend.py`, `SqliteBackend.connect_readonly` and `_connect_readonly_bound`.
- **Explanation:** Filesystem characters are parsed as URI fragment/query delimiters or escapes. The read-only query can disappear entirely, and query-only protection happens too late. A literal filesystem path is not a pre-escaped SQLite URI. Encoding an actual NUL would introduce a decoded-prefix alias; relative writable ATTACH paths beginning with `file:` already trigger URI parsing.

## Scope Boundaries

Fix literal local path handling at the existing read-only URI and export ATTACH sites only. No backend-routing redesign, new history schema, remote support, WAL suppression, global query-only policy, Windows/UNC support expansion, arbitrary URI options or ll-next command implementation. The helper accepts only `ro`/`rw`; the export destination keeps ordinary writable filename/create semantics. FEAT-3711's future writer consumes the helper rather than duplicating URI interpolation.

## Acceptance Criteria

- [ ] All seven read-only URI expressions use the shared builder. Ordinary/deadline backend reads and each direct/ATTACH consumer open the intended existing DB with special characters in a directory or filename; populated aliases are never read or mutated.
- [ ] Both `ro`/`rw` fail on a missing intended path with aliases absent or populated; no requested main DB, alias or parent directory is created. Filesystem snapshots contain all possible directory/filename aliases inside the fixture root.
- [ ] Relative/absolute paths, literal `%23`/`%3F`/`%00`, spaces, Unicode, option-like path content and symlink/`..` behavior are covered. `ro` rejects writes; `rw` commits only to the intended existing file.
- [ ] Actual embedded NUL and unsupported modes raise `ValueError` before encoding/opening; literal `%00` remains a valid filename. Existing SQLite error translation/fallback catches and deadline ordering are unchanged.
- [ ] Export retains a read-only main DB and writable scratch ATTACH. Special-character source and scratch paths, including a relative `file:` destination, select the intended files; source/decoy main files remain unchanged.
- [ ] Backend timeout/deadline/row-factory/query-only, native-index/codegraph fallback, workspace TEMP-view ordering, remote refusal and existing WAL/SHM exceptions are preserved. Source-text pins assert executable code; chokepoint allowlist stays unchanged.
- [ ] API documentation is updated; focused regressions, chokepoint gate and `python -m pytest scripts/tests/` pass. No schema/setup/migration changes or new dependencies.

## Verification Notes

- Earlier `/ll:verify-issues` corrected the new helper's missing-file citation with the `**new**` marker. No outstanding claim drift remained after that correction.
- Additional review inspected `main` at <project-root>, verified the seven production URI sites and writable export ATTACH, and reproduced wrong-store reads and the NUL/destination edge cases with real temporary DBs.
- Prior `/ll:refine-issue` and `/ll:wire-issue` findings are consolidated into the Integration Map and Program Design above; duplicated narratives and ambiguous bare filename/line citations were removed. Original session provenance is retained.
- Review baseline: the nine existing test files in the focused plan (backend, deadline, chokepoint, SSE/export, both workspace suites, session discovery, codegraph and dashboard) passed: **342 passed, 19 skipped in 31.90s**. This is the pre-fix baseline; new regressions and the full-suite implementation gate remain outstanding.
- Updated `ll-issues format-check BUG-3737 --format json` has no findings, `ll-issues check-design BUG-3737` exits 0, and `git diff --check` passes. Readiness verdict: **CORRECTED**; ready for implementation with the contracts above.

## Review Notes

- 2026-10-05: Found during EPIC-3710 pre-implementation review; temporary-store reproduction confirmed wrong-file creation. `/ll:advise` with Opus (confidence 0.76) corroborated the URI mechanism and recommended an independent prerequisite bug so current readers do not wait on the arena core.
- 2026-10-05 (additional review): `/ll:advise --signal user_requested --host claude-code --model opus` recommended readiness after NUL/runtime-mode guards and stronger absent/populated-alias fixtures (confidence 0.86). Risks: docstring-based source pins, aliases escaping fixture snapshots, accidental exception-policy changes and untested future `rw` behavior. Dissent: `rw` is mild scope expansion but justified by the planned consumer; actual-NUL rejection is necessary because encoding introduces the regression. The advisor preferred excluding writable scratch destination handling; this review includes the one-line absolute ordinary-filename fix because the public export function's relative `file:` misrouting was reproduced, with no new helper mode or connection policy. Proceed after these issue edits; implementation remains outstanding.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Local backend strict-read-only and deadline contracts. |
| external API | [SQLite URI filenames](https://www.sqlite.org/uri.html) | URI parsing, ATTACH inheritance and `ro`/`rw` modes. |
| stdlib | [Path.absolute](https://docs.python.org/3.11/library/pathlib.html#pathlib.Path.absolute) | Absolute spelling preserves symlinks and does not normalize the path. |

## Status

**Open** | Created: 2026-10-05 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-05T19:03:21 - `13393850-24a8-4cfe-a557-77414f835c41.jsonl`
- `/ll:ready-issue` - 2026-10-05T18:55:50 - `da289930-1341-4bbf-a78c-edaba31967bf.jsonl`
- `/ll:confidence-check` - 2026-10-05T18:46:02 - `31d58183-8758-4d4f-ad48-2c2f7478dd36.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:44:52 - `ba9691d0-f847-4e4f-9425-b042e4d6175b.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:43:39 - `b9eeeb68-d3f1-47df-931c-17a810117e8f.jsonl`
- `/ll:verify-issues` - 2026-10-05T18:42:30 - `9c8983c4-64a7-4209-9036-53d8d388216c.jsonl`
- `/ll:wire-issue` - 2026-10-05T18:40:42 - `011d2688-48f6-4303-aaa6-bc531df0e6b7.jsonl`
- `/ll:refine-issue` - 2026-10-05T18:34:07 - `af0cc2df-1eb5-430f-a8c4-2e0bd187887f.jsonl`
- `/ll:capture-issue` - 2026-10-05T18:26:42 - `e0d3fb45-7fc3-4e7a-a2c8-9ad8bfdb517e.jsonl`
