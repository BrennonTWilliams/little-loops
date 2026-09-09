---
id: ENH-3422
type: ENH
title: Make _backfill_raw_events consume iter_events and shrink HostLayout to path
  metadata
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:03:19Z'
labels:
- multi-host
- architecture
- tech-debt
blocked_by:
- ENH-3420
relates_to:
- ENH-3419
- FEAT-3417
---

# ENH-3422: Make _backfill_raw_events consume iter_events and shrink HostLayout to path metadata

## Summary

Phase 2 of the `HostLayout` / session-discovery-seam unification, split out of ENH-3420 on 2026-09-09 so that ENH-3419 is gated only on the discovery half (ENH-3420 phase 1: every `HostLayout` host registered in `detect_sessions`/`iter_events`). This issue is the ingest half: `session_store/lifecycle.py`'s `_backfill_raw_events` stops taking `jsonl_files: list[Path]` and instead consumes `iter_events(handle)` for each `SessionHandle` — which already yields Claude-shaped records for qwen/gemini/omp under ENH-3420's payload rule, so no normalization happens at the write boundary; the writer stores `event.payload` as-is; `HostLayout` shrinks to path metadata (`sessions_subdir`, `session_glob`, `projects_root`, subagent fields) with its `normalize`/`normalize_file` members retired; `ll-session backfill --host codex` ingests the FEAT-3417 fixtures instead of printing the ENH-3420 notice.

## Current Behavior

After ENH-3420 phase 1, `detect_sessions` covers every host but `_backfill_raw_events` (`lifecycle.py:747`) still globs `jsonl_files` from `get_project_folder()` + `HostLayout.session_glob`, normalizing through `HostLayout.normalize` (qwen, per record) / `HostLayout.normalize_file` (gemini/omp, per file). `cli/session.py:702` prints "Codex backfill via detect_sessions() is not wired up yet (ENH-3420)" and a Codex full backfill ingests 0 sessions. `HostLayout` is read directly by `writers.py::_iter_events` (~3250), `writers.py::_backfill_subagent_runs` (~2670, `.glob`/`.parent_from`/`.sidecar_suffix`), `cli/logs.py::_has_ll_activity` (97, `.normalize`), `cli/session.py:672,705` (`.sessions_subdir`), `cli/backfill_worker.py:60` (`.session_glob`), `user_messages.py:446-448` (`.sessions_subdir`).

## Expected Behavior

`_backfill_raw_events(conn, handles: list[SessionHandle], *, host: str | None = None) -> int` iterates `iter_events(handle)`; the `raw_events` row's `raw_line`/`parsed_json` are Claude-shaped for every normalizer host (gemini/omp rows are already pre-normalized at rest; **qwen rows change** from raw-plus-`skip_at_ingest` to pre-normalized, since `parse_qwen_session` already applies `normalize_qwen_record`). **Landmine (ENH-3420 hand-off):** `normalize_qwen_record` is not idempotent — a normalized record carries `message.content`, not `message.parts`, so re-normalizing it returns `None`. `writers.py::_iter_events` (~3250) must stop re-normalizing qwen rows in the same change, or every pre-normalized qwen row silently vanishes on cursor replay; add a regression test that rebuilds from pre-normalized qwen `raw_events` and asserts the row count. kimi-code rows are host-native `wire.jsonl` events (no normalizer), like codex. `ll-session backfill --host codex` writes Codex rollouts into `raw_events` with `host = "codex"`. `HostLayout.normalize`/`normalize_file` are removed once no production reader remains; the four direct readers above are retargeted. Existing backfill tests (`test_ll_session.py`, `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py`) pass unmodified except where they construct a `HostLayout` with the retired fields.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. Confirm ENH-3420 phase 1 landed: `detect_sessions(cwd, h)` returns handles for every `h` in `get_project_folder`'s vocabulary.
2. Add a direct unit test for `cli/logs.py::_extract_ll_event_streams` with a non-default `HostLayout` (no such test exists at any layout today) before touching `HostLayout`.
3. Rewrite `_backfill_raw_events` to take handles; keep a `jsonl_files` compatibility path only if a test patches it directly.
4. Retarget `_has_ll_activity`, `_backfill_subagent_runs`, `_iter_events`, `cli/session.py`, `cli/backfill_worker.py` (add `choices=` validation to the worker's free-form `--host`), `user_messages.py:446-448`.
5. Delete `normalize`/`normalize_file` from `HostLayout`; keep `normalize_qwen_record`/`normalize_gemini_session`/`normalize_omp_session` exported from `session_store/__init__.py` as aliases of the ENH-3420 `parse_*` functions for one release (alias pattern: `git_operations.py:354-355`).
6. Drop the `cli/session.py:702` notice; verify `ll-session backfill --host codex` against `scripts/tests/fixtures/codex/` with `home=tmp_path`.
7. Docs: `docs/ARCHITECTURE.md` seam note (one seam, two halves), `docs/reference/API.md`, `docs/reference/CLI.md` backfill flags table.

## Impact

- **Priority**: P3 — debt; Codex data in history.db is not yet required by a goal 6/7 consumer (FEAT-3418's workspace totals read history.db but only for hosts already ingested).
- **Effort**: Medium.
- **Risk**: Medium — `_backfill_raw_events` feeds history.db, which `ll-ctx-stats` and `ll-history` aggregate over.
- **Breaking Change**: No (aliases kept one release).

## Scope Boundaries

- **In scope**: the `_backfill_raw_events` signature change and its callers (`cli/session.py` backfill subcommand 664-718, `cli/backfill_worker.py:57-60`, `hooks/session_start.py:162-178` argv); dropping the `backfill --host codex` notice; retargeting `_has_ll_activity`, `_backfill_subagent_runs`, `_iter_events`; deleting `HostLayout.normalize`/`normalize_file`; the `docs/reference/CLI.md` `backfill` `--host` choices enumeration; `docs/reference/API.md:3573,9502-9505`.
- **Out of scope**: registering hosts in `detect_sessions` (ENH-3420 phase 1); ENH-3419's CLI rewiring; the `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`).

## Acceptance Criteria

- `ll-session backfill --host codex` ingests both FEAT-3417 Codex fixtures into `raw_events` with `host = "codex"`; the ENH-3420 notice is gone.
- `_backfill_raw_events` takes `list[SessionHandle]` and calls `iter_events`; no production code reads `HostLayout.normalize`/`normalize_file`.
- `test_ll_session.py`, the three per-host normalizer tests, and `test_enh_2505_subagent_runs.py` pass unmodified except for `HostLayout(...)` constructor calls that named the retired fields.
- `cli/backfill_worker.py` rejects an unknown `--host` with `SystemExit` like `cli/session.py`'s `backfill_parser`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3
