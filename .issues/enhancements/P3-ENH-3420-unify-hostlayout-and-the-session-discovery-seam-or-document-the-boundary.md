---
id: ENH-3420
type: ENH
title: Unify HostLayout and the session-discovery seam (or document the boundary)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:27:16Z'
labels:
- multi-host
- architecture
- tech-debt
blocked_by:
- ENH-3419
relates_to:
- FEAT-3417
---

# ENH-3420: Unify HostLayout and the session-discovery seam (or document the boundary)

## Summary

Follow-up filed from FEAT-3417's decision rationale ("worth a follow-up issue, not a blocker"), which three consecutive `/ll:confidence-check` passes flagged as unfiled. After FEAT-3417 lands, the tree carries two parallel per-host dispatch mechanisms for reading host session logs:

- `session_store/writers.py`'s `HostLayout` (`host_layout_for`, lines ~2527-2604) — `projects_root`, `sessions_subdir`, `session_glob`, and `normalize`/`normalize_file` entries for qwen/gemini/omp that translate host-native records into a shared Claude-shaped record. Consumed by `_iter_events`'s cursor-replay path, `_backfill_raw_events`, `cli/session.py backfill`, `cli/backfill_worker.py`, and `cli/logs.py`'s `_has_ll_activity`/`_extract_cwd_from_project`/`_extract_ll_event_streams`.
- `session_store/sessions.py` (FEAT-3417) — `detect_sessions`/`iter_events`/`list_workspaces` yielding `SessionEvent`s with host-native `payload`, deliberately refusing content normalization. Consumed by `ll-logs`/`ll-messages`/`ll-ctx-stats` once the rewire ENH lands.

Decide whether and how to unify them, or record why they stay separate.

## Current Behavior

Two registries answer "how do I find and read sessions for host X" with different contracts: `HostLayout` returns a folder + a normalizer to Claude shape (batch backfill into history.db); `detect_sessions` returns per-session handles + host-native events (activity reporting). Codex has an entry in the second only (`HostLayout.projects_root` is `None` for Codex after FEAT-3417 step 3), so `ll-session backfill --host codex` prints a "use detect_sessions-backed backfill (follow-up)" notice instead of ingesting. qwen/gemini/omp have entries in the first only, so `ll-logs`/`ll-messages` will not enumerate their sessions through the seam until someone adds them.

## Expected Behavior

One of:

- **Unify on the seam**: `HostLayout` gains a `detect`/`iter` delegation (or is reduced to `sessions_subdir`/`session_glob` metadata consumed by `detect_sessions`), the qwen/gemini/omp normalizers become per-host `parse_*` functions behind `iter_events`, and `_backfill_raw_events` ingests `SessionEvent`s (applying Claude-shape normalization only at the history.db boundary, where a shared schema is genuinely required). `ll-session backfill --host codex` then works.
- **Keep separate, documented**: record in `docs/ARCHITECTURE.md` that `HostLayout` is the *ingest-to-history.db* seam (shared schema required by the `raw_events` table) and `sessions.py` is the *activity-reporting* seam (per-host content), with a rule for which one a new host must implement first.

The choice should be informed by whether goal 6/7 consumers end up reading history.db (favours unify) or raw sessions (favours separate).

## Motivation

Every new host currently has to be wired twice (once per seam) or ends up half-supported — Codex will be readable by `ll-logs` but not backfillable into history.db; qwen/gemini/omp the reverse. That is the "silently covers one host while claiming to generalize" failure FEAT-3417 set out to fix, reproduced one layer down.

## Proposed Solution

Recommend the first option, scoped in two moves: (1) add qwen/gemini/omp `detect_sessions` branches by wrapping their existing `get_project_folder` probes plus `sessions_subdir`, and lift their normalizers to `parse_*` generators (they are already generator-shaped: `gemini.py:40-52`, `omp.py:54`); (2) make `_backfill_raw_events` consume `iter_events` and apply the Claude-shape normalization at the write boundary. `HostLayout` shrinks to path metadata. Confirm by running `ll-session backfill --host codex` against the FEAT-3417 fixtures.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — `HostLayout` dataclass and `host_layout_for` (~2527-2604); `_iter_events` (~3247); `_backfill_raw_events`
- `scripts/little_loops/session_store/sessions.py` (from FEAT-3417) — add qwen/gemini/omp branches to `detect_sessions`; register `parse_qwen_*`/`parse_gemini_*`/`parse_omp_*` in the parser table
- `scripts/little_loops/session_store/qwen.py`, `gemini.py`, `omp.py` — normalizers become per-host parsers (already generator-shaped)
- `scripts/little_loops/cli/session.py` (`backfill` subcommand, 664-718) and `scripts/little_loops/cli/backfill_worker.py:57-59` — consume the seam
- `scripts/little_loops/cli/logs.py` — `_has_ll_activity` (97), `_extract_cwd_from_project` (134), `_extract_ll_event_streams` (261) take `layout: HostLayout | None`; retarget once `HostLayout` shrinks
- `docs/ARCHITECTURE.md`, `docs/reference/API.md` (`session_store` entry) — either way, document the boundary

### Dependent Files (Callers/Importers)
- `session_store/__init__.py` re-exports the normalizers by name (lines ~67/91/100, `__all__` 176-283); keep the names as aliases for one release if they are renamed
- `hooks/session_start.py:162-178` spawns the backfill worker with `--host`

### Tests
- `scripts/tests/test_ll_session.py` (patches `get_project_folder` at 704), `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py` — must pass unmodified
- FEAT-3417's `test_session_discovery.py` — add qwen/gemini/omp branch tests mirroring the codex ones

### Documentation
- `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md` (add a "session log readable by" column if unified)

## Implementation Steps

1. Decide unify-vs-document after ENH-3419 lands, based on whether goal 6/7 consumers read history.db or raw sessions.
2. If unify: add qwen/gemini/omp `detect_sessions` branches (wrap existing folder probes + `sessions_subdir`); lift normalizers to `parse_*` generators; make `_backfill_raw_events` consume `iter_events` and normalize at the write boundary; shrink `HostLayout` to path metadata; drop the `backfill --host codex` notice.
3. If document: write the two-seam boundary into `docs/ARCHITECTURE.md` with the "new host implements X first" rule.
4. Verify: existing backfill/normalizer tests unmodified; `ll-session backfill --host codex` against FEAT-3417 fixtures (unify path only).

## Impact

- **Priority**: P3 — debt, not a user-visible gap; becomes P2 if a goal 6/7 consumer needs Codex data in history.db.
- **Effort**: Medium.
- **Risk**: Medium — `_backfill_raw_events` feeds history.db, which `ll-ctx-stats` and `ll-history` aggregate over.
- **Breaking Change**: No.

## Acceptance Criteria

- A single documented answer to "which seam does a new host implement", either by unification or by an architecture note naming both seams and their boundary.
- If unified: `ll-session backfill --host codex` ingests the FEAT-3417 Codex fixtures into `raw_events`, and `detect_sessions(cwd, "qwen"|"gemini"|"omp")` returns handles.
- Existing backfill tests (`test_ll_session.py`, per-host normalizer tests `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`) pass unmodified.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3
