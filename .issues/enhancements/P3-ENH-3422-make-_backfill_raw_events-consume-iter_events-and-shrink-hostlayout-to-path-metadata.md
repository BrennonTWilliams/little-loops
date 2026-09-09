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
reconcile_attempted: true
confidence_score: 85
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
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

## Program Design

### Types

- `SessionHandle` (`session_store/sessions.py:56-73`) — `host: str`, `session_id: str`, `path: Path`, `cwd: Path`, `updated_at: float`, `is_agent: bool = False`. Unchanged by this issue; it is the type `_backfill_raw_events` starts consuming.
- `SessionEvent` (`session_store/sessions.py:76-83`) — `type: str`, `timestamp: str`, `host: str`, `payload: dict[str, Any]`. `iter_events(handle)` already yields these; `_backfill_raw_events` stores `event.payload` as-is.
- `HostLayout` (post-shrink, `session_store/writers.py:2456`) — retains only `glob`, `parent_from`, `sidecar_suffix`, `sessions_subdir`, `name`, `projects_root`, `session_glob`; drops `normalize: Callable[[dict], dict | None] | None`, `skip_at_ingest: Callable[[dict], bool] | None`, `normalize_file: Callable[[Path], Iterator[dict]] | None`. `tool_names`/`tool_arg_keys` are untouched by this issue — `_backfill_raw_events` never reads them.

### Signatures

- `_backfill_raw_events(conn: sqlite3.Connection, jsonl_files: list[Path], *, host: str | None = None) -> int` (`lifecycle.py:747`) — current.
- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle], *, host: str | None = None) -> int` — target.
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` (`session_store/sessions.py:824`) — existing, already implemented by ENH-3420; dispatches through `_PARSERS[handle.host]` (`sessions.py:812-821`) to one of `_parse_claude_shaped`, `parse_codex_rollout`, `parse_kimi_wire`, `parse_qwen_session`, `parse_gemini_session`, `parse_omp_session`.

### Call Path

`backfill_raw_events()` / `backfill()` (`lifecycle.py:859`, `lifecycle.py:1108`) -> `_backfill_raw_events(conn, handles, host=...)` -> `iter_events(handle)` (`sessions.py:824`) -> `_PARSERS[handle.host](handle.path)` -> `INSERT OR IGNORE INTO raw_events(..., raw_line, parsed_json)` with `event.payload` stored verbatim (no `layout.normalize`/`normalize_file` call in this path).

Read/replay side (`writers.py::_iter_events`, `writers.py:3250-3299`) must stop calling `layout.normalize` for qwen rows in the same change — `normalize_qwen_record` is not idempotent (a normalized record carries `message.content`, not `message.parts`; `_message_parts()` at `qwen.py:138-144` returns `None` for every branch on a re-normalized input, so re-normalizing silently drops the row).

### Decision Rules

N/A — no new decision logic. This issue changes an existing function's parameter type and an existing dataclass's field set; it introduces no new gap kind, gate, threshold, or classification rule.

## Proposed Solution

`_backfill_raw_events` (`lifecycle.py:747-831`) switches its per-host branching (`layout.normalize_file` for gemini/omp, raw-line-plus-`skip_at_ingest` for everyone else, with qwen rows landing unnormalized today) for a single loop over `iter_events(handle)` per `SessionHandle`, storing `event.payload` verbatim. The parser dispatch this reuses already exists and is already exercised end-to-end by `test_session_discovery.py` (ENH-3420) — this issue is a consumer swap at the `raw_events` write boundary, not new parsing logic. `HostLayout` sheds `normalize`/`skip_at_ingest`/`normalize_file` once its four production readers (see Integration Map) are retargeted; `tool_names`/`tool_arg_keys` are unaffected. The `writers.py::_iter_events` (private, read/replay path — distinct from the public `sessions.py::iter_events` this issue targets) landmine above must land in the same change, or a pre-normalized qwen row silently vanishes on rebuild.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events()` (lines 747-831): change signature to `handles: list[SessionHandle]`, replace the `layout.normalize_file`/`layout.normalize`/`skip_at_ingest` branching with a loop over `iter_events(handle)`.
- `scripts/little_loops/session_store/writers.py` — `HostLayout` (lines 2456-2511): drop the `normalize`, `skip_at_ingest`, `normalize_file` fields; `host_layout_for()` (lines 2527-2607): drop the corresponding kwargs from the qwen (2545), gemini (2561), omp (2582) branches; `_iter_events()` (lines 3250-3299): stop calling `layout.normalize` at line 3284 for the cursor-replay path (the qwen landmine above).
- `scripts/little_loops/cli/logs.py` — two independent `.normalize` call sites, not one: `_has_ll_activity()` (lines 97-131, call at ~122-125) **and** `_extract_ll_event_streams()` (lines 261-329, call at ~308-311). The issue's own Current Behavior section names only the first.
- `scripts/little_loops/cli/session.py` — lines 672 and 711 (`host_layout_for(_backfill_host).sessions_subdir` glob); lines 700-706 (drop the "Codex backfill via detect_sessions() is not wired up yet (ENH-3420)" notice); line 718 (the `backfill(...)` call site).
- `scripts/little_loops/cli/backfill_worker.py` — line 60 (`layout.session_glob`). **This file has no argparse** (module docstring: "no argparse by design"); `--host` is read via a hand-rolled `for i, arg in enumerate(args)` loop (lines 30-41) with no validation today. "Add `choices=` validation" (Implementation Step 4 below) cannot literally add an argparse `choices=` kwarg here — see the superseded-line note on that step.
- `scripts/little_loops/user_messages.py` — `get_sessions_folder()` (lines 422-449): `.sessions_subdir` read at line 448.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/lifecycle.py:859` — `backfill_raw_events()` calls `_backfill_raw_events(conn, filtered, host=host)`.
- `scripts/little_loops/session_store/lifecycle.py:1108` — `backfill()` calls `_backfill_raw_events(conn, jsonl_files, host=host)`.
- `scripts/little_loops/session_store/__init__.py:79` — sole importer of `lifecycle.py` (confirmed via code-graph `importers-of`); re-exports `HostLayout`, `host_layout_for`, `_backfill_subagent_runs` (import block ~147-168, `__all__` ~244-299).

### Conventions in Force
- Back-compat aliasing for a retired name in this codebase is a bare module-level rebind with a one-line comment (`OldName = NewName`) — never a wrapper function, `functools.partial`, or `DeprecationWarning` — evidence: `git_operations.py:354-355`, `config/core.py:1132-1133`, `cli/verify_triggers.py:169-170`. This shape assumes matching signatures between old and new; `normalize`/`normalize_file` (`dict -> dict | None` / `Path -> Iterator[dict]`) and their `parse_qwen_session`/`parse_gemini_session`/`parse_omp_session` replacements (`Path -> Iterator[SessionEvent]`) do not share signatures, so the bare-rebind shape does not transfer cleanly to this retirement.
- Where `--host` choices validation exists, it is a hand-typed argparse `choices=[...]` literal, not imported from a shared constant — evidence: `cli/session.py:211-216`. `_REGISTERED_HOSTS` (`sessions.py:268-277`) holds the same 8 values but neither list references the other.
- `HostLayout`-backed tests build layouts exclusively through the `host_layout_for(host)` factory and drive ingest through the public `backfill_raw_events()` entry point against fixture files — never a literal `HostLayout(...)` constructor call — evidence: `test_enh_3166_qwen_normalizer.py`, `test_enh_2505_subagent_runs.py` (`layout=host_layout_for(...)` kwarg). A repo-wide search for `HostLayout(` finds it constructed in exactly one place in source: `writers.py::host_layout_for`.
- The one existing precedent for widening a `_backfill_*` helper's input type kept both old and new branches rather than retiring the old one: `writers.py::_iter_events` accepts `list[Path] | sqlite3.Cursor` via `isinstance` branching (`writers.py:3250-3299`). No function in this codebase currently *consumes* `list[SessionHandle]` as a parameter — every existing use is a producer return type (`detect_sessions` and its private helpers, `sessions.py`) — so `_backfill_raw_events(handles: list[SessionHandle])` is a new consumption shape, not a repeat of an existing one.

### Tests
- `scripts/tests/test_session_store_schema.py::test_backfill_raw_events_ingests_one_row_per_line` (line 916).
- `scripts/tests/test_ll_session.py`, `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py` — named in Expected Behavior as passing unmodified except for retired-field `HostLayout(...)` constructor calls; per Conventions in Force above, none of these files actually construct `HostLayout` literally today, so this constraint is not expected to bite.
- `scripts/tests/test_hook_session_start.py:277` — asserts `"backfill_worker" in " ".join(calls[0])`; unaffected by the signature change but exercises the `--host` argv path into `backfill_worker.py`.
- `scripts/tests/test_session_discovery.py` — already covers `detect_sessions`/`iter_events`/`SessionHandle` end-to-end (72 occurrences); the parser dispatch this issue reuses is already under test here.

### Documentation
- `docs/reference/API.md` — session discovery section (lines 9497-9524) already documents `detect_sessions`/`iter_events`/`SessionHandle`/`SessionEvent`; needs the `_backfill_raw_events` signature change reflected.
- `docs/reference/CLI.md` — `backfill` `--host` flag row (line 3939, inside the flags table lines 3928-3943).
- `docs/ARCHITECTURE.md` — HostLayout/iter_events/backfill_worker narrative (seam note per Scope Boundaries).

### Configuration
- N/A

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/little_loops/session_store/lifecycle.py::_backfill_raw_events` | Takes `jsonl_files: list[Path]`; branches per host on `layout.normalize_file` (gemini/omp, whole-file) vs. a raw line read plus `skip_at_ingest` (qwen and everyone else) | CHANGED | Replaced by a single loop over `iter_events(handle)` per `handles: list[SessionHandle]`; qwen rows go from raw-stored to pre-normalized (`parse_qwen_session` already applies `normalize_qwen_record`) |
| `scripts/little_loops/session_store/lifecycle.py::_backfill_raw_events` idempotent `INSERT OR IGNORE` dedup on `(source_path, line_no)` | PRESERVED | Dedup index and idempotency semantics are unchanged by the consumer swap |
| `scripts/little_loops/cli/backfill_worker.py` `--host` argument handling | Hand-rolled `for i, arg in enumerate(args)` loop (lines 30-41); no validation against a fixed host list today | CHANGED | AC requires rejecting an unknown `--host` with `SystemExit`; cannot literally "add `choices=`" since this file has no argparse — equivalent validation must be hand-rolled to match `cli/session.py`'s behavior |
| `scripts/little_loops/cli/backfill_worker.py` `layout.session_glob` glob (line 60) | PRESERVED | `session_glob` is a path-metadata `HostLayout` field, retained post-shrink |

## Implementation Steps

1. Confirm ENH-3420 phase 1 landed: `detect_sessions(cwd, h)` returns handles for every `h` in `get_project_folder`'s vocabulary.
2. Add a direct unit test for `cli/logs.py::_extract_ll_event_streams` with a non-default `HostLayout` (no such test exists at any layout today) before touching `HostLayout`.
3. Rewrite `_backfill_raw_events` to take handles; keep a `jsonl_files` compatibility path only if a test patches it directly.
4. Retarget `_has_ll_activity` and `_extract_ll_event_streams` (`cli/logs.py` — two independent `.normalize` call sites, ~122-125 and ~308-311), `_backfill_subagent_runs`, `_iter_events`, `cli/session.py`, `user_messages.py:446-448`, and `cli/backfill_worker.py`: this file has no argparse (hand-rolled `for i, arg in enumerate(args)` loop, lines 30-41), so add equivalent hand-rolled `--host` validation there instead of a `choices=` kwarg, matching `cli/session.py`'s `backfill_parser` `SystemExit` behavior.
5. Delete `normalize`/`normalize_file` from `HostLayout`; keep `normalize_qwen_record`/`normalize_gemini_session`/`normalize_omp_session` exported from `session_store/__init__.py` as thin compatibility wrappers over the ENH-3420 `parse_*` functions for one release — the codebase's bare-rebind alias pattern (`git_operations.py:354-355`, `config/core.py:1132-1133`, `cli/verify_triggers.py:169-170`) doesn't transfer here since `normalize`/`normalize_file` (`dict -> dict | None` / `Path -> Iterator[dict]`) and their `parse_*` replacements (`Path -> Iterator[SessionEvent]`) don't share a signature.
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-09_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 60/100 → MODERATE

### Concerns
- Motivation section is still the unfilled template placeholder (`[Why this issue matters - business value, user impact, technical debt cost]`), capping Criterion 4 at 10/20 per the Structure Cap rule.
- The bare-rebind back-compat alias convention this codebase otherwise uses doesn't transfer to retiring `HostLayout.normalize`/`normalize_file` (signature mismatch vs. the `parse_*` replacements); Step 5's thin-wrapper approach is a justified but non-standard deviation worth double-checking during implementation.

### Outcome Risk Factors
- Broad dependent surface: 4 production readers of `HostLayout.normalize`/`normalize_file` (`writers.py` ×2 sites, `cli/logs.py` ×2 sites) plus `cli/session.py`, `cli/backfill_worker.py`, and `user_messages.py` all need correct retargeting in one change — 6-10 dependents, each with different behavior (not a uniform mechanical substitution).
- qwen idempotency landmine: `writers.py::_iter_events` must stop re-normalizing pre-normalized qwen rows in the same change as the write-path swap, or rows silently vanish on cursor replay — easy to miss since it's a separate read-path file from `lifecycle.py`.

## Session Log
- `/ll:reconcile-issue` - 2026-09-09T20:34:13 - `2fd45f5b-ae88-495d-9824-d79e9d1a2e5f.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:26:42 - `707b6c2b-2b94-48e8-86f8-1ee81a021633.jsonl`
