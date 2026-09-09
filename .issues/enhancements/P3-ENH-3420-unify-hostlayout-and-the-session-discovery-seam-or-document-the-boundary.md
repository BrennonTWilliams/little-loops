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

- `session_store/writers.py`'s `HostLayout` (`host_layout_for`, lines ~2527-2604) — `projects_root`, `sessions_subdir`, `session_glob`, and `normalize`/`normalize_file` entries for qwen/gemini/omp that translate host-native records into a shared Claude-shaped record. Consumed by `_iter_events`'s cursor-replay path, `session_store/lifecycle.py`'s `_backfill_raw_events`, `cli/session.py backfill`, `cli/backfill_worker.py`, and `cli/logs.py`'s `_has_ll_activity`/`_extract_cwd_from_project`/`_extract_ll_event_streams`.
- `session_store/sessions.py` (FEAT-3417) — `detect_sessions`/`iter_events`/`list_workspaces` yielding `SessionEvent`s with host-native `payload`, deliberately refusing content normalization. Consumed by `ll-logs`/`ll-messages`/`ll-ctx-stats` once the rewire ENH lands.

Decide whether and how to unify them, or record why they stay separate.

## Current Behavior

Two registries answer "how do I find and read sessions for host X" with different contracts: `HostLayout` returns a folder + a normalizer to Claude shape (batch backfill into history.db); `detect_sessions` returns per-session handles + host-native events (activity reporting). Codex has an entry in the second only (`HostLayout.projects_root` is `None` for Codex after FEAT-3417 step 3), so `ll-session backfill --host codex` prints a "use detect_sessions-backed backfill (follow-up)" notice instead of ingesting. qwen/gemini/omp have entries in the first only, so `ll-logs`/`ll-messages` will not enumerate their sessions through the seam until someone adds them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed by direct read: `session_store/sessions.py` (the FEAT-3417 seam) does not exist in production. It exists only as a spike at `scripts/tests/spike/session_discovery_lifecycle/lifecycle.py`, guarded by `TestIsolationGuard.test_lifecycle_module_has_no_production_imports` (`test_lifecycle.py:224-239`) which AST-asserts the spike imports zero `little_loops` names. FEAT-3417 itself carries `status: open`. So today there is no live "two parallel seams" collision — only `HostLayout` (`session_store/writers.py`) is wired into production; this issue's unify-vs-document decision is about a seam that has not landed yet, not two coexisting live mechanisms.
- `HostLayout`'s normalization is a **two-tier split by where the session id lives**, not one uniform strategy: qwen's `normalize_qwen_record(record: dict) -> dict | None` (`qwen.py:59`) is per-record — no `yield` — because the id is present on every record, consumed inline at read time (`writers.py:_iter_events` cursor-replay path, and directly in `cli/logs.py`'s `_has_ll_activity`/`_extract_ll_event_streams`, which call `.normalize()` per line, bypassing `_iter_events`/`raw_events` entirely). gemini's `normalize_gemini_session(path: Path) -> Iterator[dict]` (`gemini.py:40`) and omp's `normalize_omp_session(path: Path) -> Iterator[dict]` (`omp.py:54`) are whole-file generators, because the id lives only in a header line — consumed once, at `_backfill_raw_events` ingest time (`lifecycle.py:747`), and the already-Claude-shaped result is what gets written to `raw_events` as both `raw_line` and `parsed_json`. Consequence: gemini/omp rows in `raw_events` are pre-normalized at rest; qwen rows are stored raw and re-normalized on every read.
- Naming collision: `writers.py:_iter_events` (line 3247, underscore-prefixed, cursor/list-of-Path replay for the `rebuild` command, unrelated signature) and the FEAT-3417 spike's `iter_events` (no underscore, `SessionHandle -> Iterator[SessionEvent]`) share a base name but are unrelated functions. A repo-wide grep for `iter_events(` surfaces both — worth flagging so implementation doesn't conflate them.
- Existing "unsupported host" edge case: `discover_all_projects()` (`cli/logs.py:166`, the `--all` enumeration) checks `layout.projects_root is None`, logs `logger.debug(...)`, and returns `[]` — silent, non-fatal. This is the precedent this issue's `detect_sessions` qwen/gemini/omp branches would need to preserve or explicitly change.
- Malformed-input handling is consistent across every normalizer/parser in this area (qwen per-record, gemini/omp per-file, and the FEAT-3417 spike's `parse_codex_rollout`/`parse_claude_transcript`): `try/except json.JSONDecodeError: continue`, never raising; file-open `OSError` triggers a bare generator `return` (gemini/omp) or a per-file `continue` in `_backfill_raw_events`'s non-`normalize_file` branch.

## Expected Behavior

One of:

- **Unify on the seam**: `HostLayout` gains a `detect`/`iter` delegation (or is reduced to `sessions_subdir`/`session_glob` metadata consumed by `detect_sessions`), the qwen/gemini/omp normalizers become per-host `parse_*` functions behind `iter_events`, and `_backfill_raw_events` ingests `SessionEvent`s (applying Claude-shape normalization only at the history.db boundary, where a shared schema is genuinely required). `ll-session backfill --host codex` then works.
- **Keep separate, documented**: record in `docs/ARCHITECTURE.md` that `HostLayout` is the *ingest-to-history.db* seam (shared schema required by the `raw_events` table) and `sessions.py` is the *activity-reporting* seam (per-host content), with a rule for which one a new host must implement first.

The choice should be informed by whether goal 6/7 consumers end up reading history.db (favours unify) or raw sessions (favours separate).

## Motivation

Every new host currently has to be wired twice (once per seam) or ends up half-supported — Codex will be readable by `ll-logs` but not backfillable into history.db; qwen/gemini/omp the reverse. That is the "silently covers one host while claiming to generalize" failure FEAT-3417 set out to fix, reproduced one layer down.

## Scope Boundaries

- **In scope**: the unify-vs-document decision itself; if unify, adding qwen/gemini/omp branches to `detect_sessions`, lifting the three normalizers to `parse_*` generators, making `_backfill_raw_events` consume `iter_events` and normalize at the write boundary, and shrinking `HostLayout`; if document, the `docs/ARCHITECTURE.md` boundary note and the "which seam does a new host implement first" rule.
- **Out of scope**: ENH-3419's CLI rewiring of `ll-logs`/`ll-messages`/`ll-ctx-stats` onto the seam — this issue is blocked by it, not a substitute for it. Adding Codex-native equivalents of the Claude-schema-coupled `cli/logs.py` content functions — out of scope in FEAT-3417 and unaffected by which seam design wins here. Any change to the `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`) — decided out of scope in FEAT-3417 and not reopened by this issue.

## Program Design

### Types

- `HostLayout` (`session_store/writers.py:2456`) — existing per-host path/normalizer metadata; shrinks to path fields only if unified
- `SessionHandle`, `SessionEvent` (`session_store/sessions.py`, FEAT-3417) — discovery-seam types this issue would extend to qwen/gemini/omp

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None) -> list[SessionHandle]` — gains qwen/gemini/omp branches alongside the existing claude-code/codex ones
- `parse_qwen_session(handle: SessionHandle) -> Iterator[SessionEvent]` / `parse_gemini_session(...)` / `parse_omp_session(...)` (new — lifted from the existing generator-shaped normalizers `qwen.py`, `gemini.py:40-52`, `omp.py:54`)
- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle], *, host: str | None = None) -> int` — replaces the current `jsonl_files: list[Path]` parameter (`session_store/lifecycle.py:747`)

### Call Path

`cli/session.py` backfill subcommand (664-718) -> `detect_sessions(cwd, host)` -> `iter_events(handle)` -> `_backfill_raw_events(conn, handles, host=host)` -> Claude-shape normalization applied at the `raw_events` write boundary

## Proposed Solution

Recommend the first option, scoped in two moves: (1) add qwen/gemini/omp `detect_sessions` branches by wrapping their existing `get_project_folder` probes plus `sessions_subdir`, and lift their normalizers to `parse_*` generators (they are already generator-shaped: `gemini.py:40-52`, `omp.py:54`); (2) make `_backfill_raw_events` consume `iter_events` and apply the Claude-shape normalization at the write boundary. `HostLayout` shrinks to path metadata. Confirm by running `ll-session backfill --host codex` against the FEAT-3417 fixtures.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Correction to this section's "already generator-shaped: `qwen.py`, `gemini.py:40-52`, `omp.py:54`" claim: this holds for gemini/omp but **not** qwen. `session_store/qwen.py:59` `normalize_qwen_record(record: dict) -> dict | None` is a per-record function with no `yield` — it would need wrapping in a per-line loop (the shape `_backfill_raw_events`'s non-`normalize_file` branch already uses) to become a `parse_qwen_session`-style whole-file generator matching gemini/omp's signature. gemini (`gemini.py:40`) and omp (`omp.py:54`) are confirmed already generator-shaped, whole-file, matching the target `parse_*(handle) -> Iterator[SessionEvent]` shape directly.
- The FEAT-3417 spike (`scripts/tests/spike/session_discovery_lifecycle/lifecycle.py:246-257`) already implements the exact dispatch convention this move (1) would extend: a `_PARSERS = {"codex": parse_codex_rollout, "claude-code": parse_claude_transcript}` dict, with `iter_events(handle)` doing `parser = _PARSERS.get(handle.host); yield from parser(handle.path)`. Its `detect_sessions` branch selection, by contrast, is a literal `if host == "codex": ... if host == "claude-code": ...` chain rather than a dict — the two dispatch idioms coexist in the same spike module, so "add qwen/gemini/omp branches" means extending both the `_PARSERS` dict and the `if`/`elif` chain, not just one.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — `HostLayout` dataclass and `host_layout_for` (~2527-2604); `_iter_events` (~3247)
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events` (747)
- `scripts/little_loops/session_store/sessions.py` (from FEAT-3417) — add qwen/gemini/omp branches to `detect_sessions`; register `parse_qwen_*`/`parse_gemini_*`/`parse_omp_*` in the parser table
- `scripts/little_loops/session_store/qwen.py`, `gemini.py`, `omp.py` — normalizers become per-host parsers (already generator-shaped)
  > ⚠ Superseded — qwen.py is per-record, not generator-shaped; see § Codebase Research Findings under Proposed Solution
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Conventions in force — dispatch on a bare host string recurs three times in this codebase, each rendered differently: `host_layout_for()` (`writers.py:2527`, `if`/`elif` chain with a shared dict-literal fallback tail for claude-code/codex/opencode/pi), `get_project_folder()` (`user_messages.py:373-419`, named private per-host functions `_get_codex_project_folder`/`_get_opencode_project_folder`/`_get_pi_project_folder`), and the FEAT-3417 spike's `_PARSERS` dict (above). None of the three is treated as canonical over the others in the existing codebase — a new host-dispatch site should pick the shape matching its nearest neighbor, not invent a fourth.
- Conventions in force — `session_store/__init__.py:67,91,100` re-exports each normalizer with an eager top-level import plus an explicit `__all__` entry (lines 221-224), not a lazy/deferred import like `host_layout_for`'s per-branch local imports. Any new `parse_*` export this issue adds should follow the eager-import + `__all__` pattern, and per this issue's own Dependent Files note, keep the old normalizer names as aliases for one release if renamed.
- Conventions in force — this codebase has a documented precedent for "keep separate, documented" (the second option this issue considers), not just "unify": `docs/ARCHITECTURE.md`'s "SDK/Batches Dispatch Path" (§ ~881-911) and "Host Adapter Capability Map" (§ ~1317-1336) both name two structurally distinct mechanisms living in the same subsystem, state explicitly that one does not implement the other's contract, name the axis they differ on, and cross-reference `docs/reference/HOST_COMPATIBILITY.md` — without proposing a merge. A repo-wide search for a prior instance of actually *unifying* two such registries (as opposed to documenting the boundary) found no precedent; both located examples chose to document.
- Conventions in force — the three per-host normalizer test files (`test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`) share a docstring-names-the-ENH + `FIXTURES = Path(__file__).parent / "fixtures" / "<host>"` + committed-JSONL-fixture pattern, but qwen's file exercises the per-record `HostLayout.normalize` branch (`host_layout_for`, `discover_all_projects`, `_has_ll_activity`, `raw_events.host` stamping) while gemini/omp's exercise the per-file `normalize_file` branch end-to-end through `_backfill_raw_events`/`rebuild()` — reflecting the same per-record-vs-per-file split noted under Current Behavior. The FEAT-3417 spike's own test file (`test_lifecycle.py`) uses a third convention (programmatic `tmp_path` fixtures via local `_make_state_db`/`_write_rollout` helpers, not committed JSONL) and adds a `TestIsolationGuard` class with no counterpart in the three normalizer test files.

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


## Session Log
- `/ll:refine-issue` - 2026-09-09T14:08:38 - `1658f0c5-d510-42b4-beb1-234626dbd6e5.jsonl`
- `/ll:format-issue` - 2026-09-09T13:22:54 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
