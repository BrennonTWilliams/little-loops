---
id: ENH-3685
type: ENH
title: Serve MCP history_search and batch sft-corpus enrich from a remote history
  store
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:20:51Z'
blocked_by:
- ENH-3668
- ENH-3700
relates_to:
- EPIC-3693
- ENH-3657
- ENH-3684
- ENH-3677
- ENH-3682
deferred_by: human
deferred_date: '2026-10-02T17:58:39Z'
---

# ENH-3685: Serve MCP history_search and batch sft-corpus enrich from a remote history store

> **Deferred 2026-10-02** (Opus review of EPIC-3693's children): no known remote read demand. Remote read serving is out of scope for EPIC-3693 and was detached from it so the epic branch can close. Revive when demand exists. Until then ENH-3657 documents MCP `history_search` as "not supported with a remote backend" and ENH-3700 degrades `sft-corpus` `enrich` with an explicit note. Now `blocked_by` ENH-3700 instead of ENH-3657.

## Summary

Serve MCP `history_search` and the `sft-corpus` `enrich` state from an opt-in remote libSQL store, using the strict-read infrastructure from ENH-3668. `enrich` gets a batched `lookup_session_metadata_batch` so remote cost is O(chunks), not O(examples). Split from the original ENH-3668 (2026-09-30 Opus review).

## Current Behavior

- MCP `_tool_history_search` resolves `resolve_history_db(project_root / DEFAULT_DB_PATH, root=project_root)` and calls `history_reader.search`; under remote config ENH-3657 refuses it.
- `scripts/little_loops/loops/sft-corpus.yaml` `enrich` loops over JSONL examples calling `lookup_session_metadata(session_id)` with no `db` argument (cwd-assumed). Each call does `Path(db).exists()` (False for the default path under remote config, so it silently returns `{}`) and then about four sequential `SELECT`s on a fresh connection. Served remotely as-is this would cost N examples x 4 round trips plus connection setup.

## Expected Behavior

- MCP `history_search` enters `strict_reads()`, resolves with `resolve_history_target(None, root=project_root)`, and serves from remote under a foreign cwd; failures surface through `history_error_verdict()` as a structured MCP error. An explicit local override (`LL_HISTORY_DB`) remains local.
- Add `lookup_session_metadata_batch(session_ids, *, db=...) -> dict[str, dict]`: one connection, four grouped `IN` queries in chunks of 500 parameters, same per-session dict shape as `lookup_session_metadata`. The loop becomes two-pass (collect ids, one batch call, join). `lookup_session_metadata` stays for single lookups and is reimplemented over the batch.
- Reuse ENH-3700's failure routing: `stage` and `enrich` have `on_error: corpus_failed`, whose state is `terminal: true, failure: true`. The executor follows `next` after a non-zero shell exit when `on_error` is absent, so exit non-zero alone does not halt the pipeline. Remove the stage's `2>/dev/null || touch "$OUTPUT"` masking. On strict error emit one safe stderr line, fail the run, and never enter `filter`/`publish` or emit a success sentinel.
- Write enrichment to a unique temporary sibling; close and atomically replace `enriched.jsonl` only after the entire batch and serialization succeed. Failure cleans up the temp file and leaves no new partial final output; an existing final file is unchanged and cannot be consumed by this failed run.
- Resolve the target once against the project root supplied by the loop invocation, before reading metadata; pass it explicitly to the batch. Test with a foreign cwd. Do not derive the root from the output/run directory.

### Batch semantics and independent oracle

Deduplicate IDs for queries while preserving every input record and its order when joining results. Empty input makes zero requests. At most 500 distinct IDs per chunk; a failure in any query or later chunk fails the entire strict operation, with no partially returned batch. A successfully queried absent session receives the existing five-key zero/None dict, distinct from the legacy `{}` fallback for an unavailable local file.

Freeze expected metadata from the current single-reader SQL before replacing it: `has_corrections=count > 0`, `issue_outcome="done"` from the issue/session join with a matching completion event (latest timestamp), `tool_count`, `files_modified` for `write/create/Write`, and `loop_outcome=None`. Use fixtures containing correction and completion ties, tool/file operations, and absent sessions. Compare both single and batch APIs to these independent expected dicts; comparing single to batch after single delegates to batch is circular. Include duplicate IDs, empty input, 500/501/1001 distinct sessions, and a failure in the final chunk. Count data-query round trips separately from access verification; expect four grouped queries per non-empty chunk, with one connection.

## Motivation

MCP `history_search` and SFT enrichment are the two non-CLI consumers; the SFT loop also needs a batch API to be usable remotely.

## Proposed Solution

Enter `strict_reads()` in `_tool_history_search`; add `lookup_session_metadata_batch` and rewrite `enrich` to use it. See Expected Behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/tools.py` (`_tool_history_search`), `history_reader/search.py` (target coercion, missing-FTS catch must propagate under strict remote mode), `history_reader/sessions.py` (new batch API, re-export in `history_reader/__init__.py`), `scripts/little_loops/loops/sft-corpus.yaml` (`stage`, `enrich`, `corpus_failed`; reuse ENH-3700 wiring).

### Dependent Files (Callers/Importers)
- `cli/logs.py` (`lookup_session_metadata` at ~line 1996; may adopt the batch), `history_reader.search`.

### Similar Patterns
- ENH-3171/BUG-3181 project-root resolution in the MCP tools; FSM `$${...}` brace escaping in shell actions.

### Tests
- `test_mcp_server.py`, `test_enh_3171_mcp_project_root.py`, a batch-parity test for `history_reader/sessions.py`, `test_builtin_loops.py` (sft-corpus), remote-stub request-count test.

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CONFIGURATION.md` (reader table), `docs/reference/API.md`.

### Configuration
- No new config key.

## Program Design

### Types

- Reuses `strict_reads()` and `Verdict` from ENH-3668. Batch result type is `dict[str, dict]` keyed by session id, each value the existing `lookup_session_metadata` dict shape.

### Signatures

- `lookup_session_metadata_batch(session_ids: Sequence[str], *, db: Path | str | HistoryTarget | None = None) -> dict[str, dict]` — one connection, four grouped `IN` queries in chunks of 500 parameters; a session with no rows maps to the zero-valued dict, an unreachable store raises under `strict_reads()`.
- `lookup_session_metadata(session_id: str, *, db: Path | str | HistoryTarget | None = None) -> dict` — reimplemented over the batch; unchanged local behavior.

### Call Path

- MCP: `mcp_server.tools._tool_history_search` → `strict_reads()` → `resolve_history_target(None, root=project_root)` → `history_reader.search` → `history_error_verdict`.
- SFT: `sft-corpus.yaml` `enrich` → `lookup_session_metadata_batch` → `_connect_readonly`; a strict error exits non-zero with one stderr line.

## Implementation Steps

1. Land ENH-3668 (infra) and ENH-3657.
2. Freeze independent expected metadata fixtures from the current SQL; implement the batch and compare both APIs to that oracle, including chunk boundaries and failures.
3. Update `_tool_history_search`; add tests in `test_mcp_server.py` and `test_enh_3171_mcp_project_root.py` with config at `project_root` and a foreign cwd, plus local override.
4. Rewrite packaged `enrich` with explicit target, atomic output and existing failure routing (mind `$${...}` brace escaping); `ll-loop validate sft-corpus`; test remote request counts and execute the failure path, not just YAML structure.
5. Docs: `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/CONFIGURATION.md` reader table, `API.md`. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P4 — opt-in remote backend.
- **Effort:** Medium.
- **Risk:** Low-Medium — loop rewrite and MCP error shape.

## Scope Boundaries

- **In scope:** MCP `history_search`, `lookup_session_metadata_batch`, `sft-corpus.yaml` `enrich`.
- **Out of scope:** `ll-history` command flips (ENH-3684), infra (ENH-3668), `ll-logs eval-export` and other `lookup_session_metadata` callers unless trivially covered by the batch, prepatch reads (ENH-3682).

## Acceptance Criteria

- [ ] MCP `history_search` returns the same shape from a migrated remote stub and a local twin, resolves against `project_root` under a foreign cwd, and reports unavailable / uninitialized as structured errors.
- [ ] Single and batch results match the independent five-key metadata oracle for corrections, completions, tool events, file writes and absent sessions. Empty input sends no request; duplicate IDs preserve record order; 500/501/1001 distinct sessions require four grouped data queries per chunk plus separately accounted verification.
- [ ] Stage or enrichment failure follows `on_error` to `terminal: true, failure: true`, exits the run non-zero with one safe stderr line, and reaches no filter/publish/success sentinel. Inject a later-chunk failure: no partial final file is published, the temp file is removed and any prior final file is unchanged.
- [ ] No `.ll/history.db` is created under remote config; `python -m pytest scripts/tests/` and `ll-loop validate sft-corpus` pass.

## Related

- ENH-3668 (infra; blocked_by), ENH-3657, ENH-3677, ENH-3684 (`ll-history` command flips), ENH-3682, FEAT-3535.

## Related Key Documentation

- `docs/guides/MCP_SERVER_GUIDE.md`, `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`.

## Status

**Deferred** | Created: 2026-09-30 | Priority: P4
