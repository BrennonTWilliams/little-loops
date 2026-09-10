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
- ENH-3430
relates_to:
- ENH-3420
- FEAT-3417
reconcile_attempted: true
decision_needed: false
confidence_score: 80
outcome_confidence: 37
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 0
---

# ENH-3422: Make _backfill_raw_events consume iter_events and shrink HostLayout to path metadata

> **Rewritten 2026-09-10** to consolidate eight refine/wire passes and fold in the
> pre-implementation review. Line numbers were verified on 2026-09-10 against
> `main` at `415d6b1cb`; re-derive by grep at implementation time rather than
> trusting them. The Session Log at the bottom is preserved verbatim.

## Summary

Phase 2 of the `HostLayout` / session-discovery-seam unification (ENH-3420 was
phase 1, ENH-3430 rewired `ll-logs`). This issue is the **ingest half**:
`session_store/lifecycle.py::_backfill_raw_events` stops taking bare paths and
consumes `iter_events(handle)` for each `SessionHandle`, so every one of the 8
registered hosts is ingested through the one parser dispatch that already exists
(`sessions.py::_PARSERS`) instead of through a second, duplicated per-host branch
at the write boundary. `HostLayout` shrinks to path metadata (its
`normalize`/`skip_at_ingest`/`normalize_file` callables are deleted), kimi-code
gets the `HostLayout` entry that three code comments and the docs defer to this
issue by number, and `ll-session backfill --host codex` ingests real Codex
rollouts instead of printing the standing "not wired up yet (ENH-3420)" notice.

Eight design decisions folded in from the 2026-09-10 review are recorded under
`## Proposed Solution → ### Design decisions (D1–D8)`. Each has a matching
Acceptance Criterion. **D1 (line-number provenance) and D2 (legacy qwen rows) are
data-integrity fixes for existing `history.db` files, not cleanups — do not drop
them to shrink scope.**

## Current Behavior

- `_backfill_raw_events(conn, jsonl_files: list[Path], *, host)` (`lifecycle.py:747-831`)
  resolves one `HostLayout` per call and branches:
  - **Branch A** (`HostLayout.normalize_file`, gemini/omp, lines 778-798): enumerates
    the file-level normalizer's yielded Claude-shaped dicts; `line_no` is the
    enumeration index; `raw_line` and `parsed_json` both store the re-serialized dict.
  - **Branch B** (everything else, lines 799-830): reads the file line by line;
    `line_no` is the **real file line number** (blank/malformed lines consume a
    number and are skipped); `raw_line` is the verbatim stripped line; qwen rows
    are stored **raw** (wire format), filtered only by `skip_at_ingest`.
- `raw_events` dedup is the unique index on `(source_path, line_no)`
  (`schema.py:488-489`). `backfill_raw_events()` re-ingests every file whose mtime
  is past the watermark and relies on that index to make re-ingest a no-op.
- `writers.py::_iter_events` (3271-3320) is the **only** place qwen rows are
  normalized today: on cursor replay it calls `HostLayout.normalize` for any host whose
  layout carries one (3300-3308). `rebuild()` (`lifecycle.py:959`) replays every
  `raw_events` row through it into seven consumers: `_backfill_sessions`
  (`lifecycle.py:708`) plus `_backfill_tool_events`, `_backfill_usage_events`,
  `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_prompt_opt`,
  `_backfill_skill_events` in `writers.py`.
- `sessions.py::iter_events` (856) dispatches via `_PARSERS` (844-853) to
  `parse_codex_rollout`, `_parse_claude_shaped` (claude-code/opencode/pi),
  `parse_kimi_wire`, `parse_qwen_session`, `parse_gemini_session`,
  `parse_omp_session` (663-841). `parse_qwen_session` already applies
  `normalize_qwen_record`, so its events are pre-normalized. `SessionEvent`
  (`sessions.py:78`) carries `type`, `timestamp`, `host`, `payload` — **no line
  number and no verbatim line**. For codex, `payload` is the *inner* payload; the
  envelope `type`/`timestamp` live only on the event.
- `iter_events` has **zero callers** in the ingest/backfill/rebuild path today.
- `cli/session.py:699-704` prints the ENH-3420 notice for `--host codex`;
  `get_project_folder(host="codex")` returns `None` by design (`user_messages.py:507`,
  Codex never writes `~/.codex/projects/`), so the codex full backfill globs nothing.
  Both `cli/session.py` glob sites (671-673, 710-712) hardcode a flat `"*.jsonl"`
  pattern under the layout's sessions subdirectory, whereas
  `cli/backfill_worker.py:59-60` uses the layout's full `HostLayout.session_glob`
  — the two disagree for any host with a nested glob.
- kimi-code has no `HostLayout` entry: `host_layout_for("kimi-code")` is the generic
  default and `sessions.py::_detect_layout_sessions` special-cases it with the
  module-level `_KIMI_WIRE_GLOB` (301, 444-445). `sessions.py:20,300,436` and
  `docs/reference/API.md:9539,9541` say the entry is "deferred to ENH-3422";
  `test_session_discovery.py:731` guards the deferral by this issue's number.
- `cli/backfill_worker.py` has no argparse (by design) and no `--host` validation;
  its existing error branches `print(..., file=sys.stderr); return 1` (42-47, 61-63).
- The `ll-logs` CLI module no longer references the layout dataclass (ENH-3430,
  verified 2026-09-10 by grepping `scripts/little_loops/cli/logs.py` for the
  dataclass name, its factory, and the project-folder helper: no hits). The remaining `.normalize`/`.normalize_file`/`.skip_at_ingest`
  readers are `lifecycle.py::_backfill_raw_events` and `writers.py::_iter_events` only.

## Expected Behavior

- `_backfill_raw_events(conn, handles: list[SessionHandle], *, host=None) -> int`
  loops `iter_events(handle)` and stores `event.payload` as the row for every host.
  Column sources: `ts` ← `event.timestamp`; `event_type` ← `event.type`;
  `session_id` ← `event.payload.get("sessionId") or handle.session_id`;
  `line_no` ← `event.line_no` (new field, D1); `raw_line`/`parsed_json` ←
  `json.dumps(event.payload)` (D6).
- The three public wrappers keep `jsonl_files: list[Path]` **and** gain an
  optional `handles: list[SessionHandle] | None = None` (D4). Paths are widened to
  handles via a new `sessions.py::handles_from_paths(paths, host)` that reuses the
  per-host `session_id` derivation discovery already uses (D3).
- `raw_events.line_no` for per-line hosts is still the real file line number, so
  an existing DB re-ingested after upgrade produces no duplicates (D1).
- qwen rows ingested after this change are pre-normalized; qwen rows ingested
  before it (raw wire format) still rebuild correctly (D2). Rebuild is idempotent
  over a DB containing both kinds.
- `HostLayout` retains `glob`, `parent_from`, `sidecar_suffix`, `sessions_subdir`,
  `name`, `projects_root`, `session_glob`, `tool_names`, `tool_arg_keys`; the
  `normalize`, `skip_at_ingest`, `normalize_file` fields are deleted, and
  `qwen_skip_at_ingest` is deleted with them (D7). The `normalize_*` functions are
  untouched — they are the parsers' implementation, not aliases.
- `host_layout_for("kimi-code")` returns a real entry with
  `session_glob = "session_*/agents/main/wire.jsonl"`; `_KIMI_WIRE_GLOB` and the
  kimi special case in `_detect_layout_sessions` are removed (D5).
- `ll-session backfill --host codex` (full and `--since`) discovers rollouts via
  `detect_sessions(Path.cwd(), "codex")` and ingests them with `host = "codex"`,
  `session_id` from the `session_meta` header, `event_type` = envelope type; the
  ENH-3420 notice is gone (D4). Codex is ingest-only for now — no derived-table
  rows, stated in docs.
- `cli/backfill_worker.py` rejects an unknown `--host` with a stderr message and
  `return 1` (D8).
- Both `cli/session.py` glob sites use `host_layout_for(h).session_glob` relative
  to the project folder, matching `backfill_worker.py`.

## Motivation

`_backfill_raw_events` and `writers.py::_iter_events` each carry their own per-host
normalization branching, duplicating the dispatch ENH-3420 centralized in
`iter_events`/`_PARSERS`. That duplication is the direct cause of the qwen
double-normalization landmine (D2) and of Codex being un-ingestible even though
`iter_events` has parsed Codex since ENH-3420. Every new host (kimi today) has to
be wired into ingestion *and* replay normalization *and* the `HostLayout` readers
separately. Finishing the consumer swap lets `raw_events` — and everything that
aggregates over it (`ll-ctx-stats`, `ll-history`, FEAT-3418 workspace totals) —
treat all 8 hosts uniformly and closes the seam ENH-3420 opened.

## Program Design

### Types

- `SessionHandle` (`sessions.py:58`) — `host`, `session_id`, `path`, `cwd`,
  `updated_at`, `is_agent`. Unchanged.
- `SessionEvent` (`sessions.py:78`) — gains `line_no: int | None = None` (D1).
  Per-line parsers (`parse_codex_rollout`, `_parse_claude_shaped`,
  `parse_kimi_wire`, `parse_qwen_session`) set it from their
  `enumerate(handle, start=1)`; `parse_gemini_session`/`parse_omp_session` set it
  from `enumerate(..., start=1)` over the normalizer's yield (same value Branch A
  stores today).
- `HostLayout` (`writers.py:2477`) — post-shrink field set listed under Expected
  Behavior; plus a new kimi-code entry in `host_layout_for` (D5).

### Signatures

- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle], *, host: str | None = None) -> int` — target (`lifecycle.py:747`).
- `backfill_raw_events(db, *, jsonl_files: list[Path] | None = None, handles: list[SessionHandle] | None = None, since_ts=None, host=None) -> int` — `jsonl_files` widened via `handles_from_paths`; `since_ts` filters on `handle.updated_at`; exactly one of the two may be given (D4). Same shape added to `backfill()` and `backfill_incremental()`.
- `handles_from_paths(paths: list[Path], host: str, *, cwd: Path | None = None) -> list[SessionHandle]` — new, `sessions.py`; `session_id` via `session_id_for` (D3), `updated_at` from mtime (skip on `OSError`, BUG-2489 pattern), `is_agent = name.startswith("agent-")`, `cwd` defaults to `Path.cwd()`.
- `session_id_for(host: str, path: Path) -> str` — new, `sessions.py`; extracted from the inline rule at `_detect_layout_sessions:457-462` plus the codex header read (`_detect_codex_sessions`' `payload.get("id", rollout.stem)`); `_detect_layout_sessions` calls it too so discovery and synthesis cannot drift (D3).
- `is_raw_qwen_record(record: dict) -> bool` — new, `qwen.py`; true when `_message_parts(record)` is not `None` (D2).
- `iter_events(handle) -> Iterator[SessionEvent]` (`sessions.py:856`) — unchanged.

### Call Path

`backfill_raw_events()` / `backfill()` / `backfill_incremental()` → (`jsonl_files` given) `handles_from_paths(paths, host)` → `_backfill_raw_events(conn, handles, host=...)` → `iter_events(handle)` → `_PARSERS[handle.host](handle.path)` → `INSERT OR IGNORE INTO raw_events(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)`.

Replay: `rebuild()` → `_raw_events_cursor()` → `writers.py::_iter_events` → for `host == "qwen"` rows only, `if is_raw_qwen_record(record): normalize_qwen_record(record)` (legacy-row shim, D2) → the seven `_backfill_*` consumers.

Codex CLI: `cli/session.py` → `detect_sessions(Path.cwd(), "codex")` → `backfill(..., handles=...)` / `backfill_incremental(..., handles=...)`.

### Decision Rules

- `_backfill_raw_events`: no per-host branching. `session_id` fallback order is payload `sessionId`, then `handle.session_id`.
- `writers.py::_iter_events`: the qwen shim is the only host-specific branch and is keyed on record *shape*, not on `HostLayout`; it is marked removable once no pre-ENH-3422 qwen rows exist.
- Public wrappers: `jsonl_files` and `handles` both given → `ValueError`; neither → no ingest (existing `if jsonl_files:` behaviour in `backfill()` preserved).

## Proposed Solution

### Option A — public wrappers retyped to handles only

The three public wrappers replace their path-typed parameter with a handles-typed
one and ripple that change into every caller (the session CLI, the backfill
worker, the session-start hook's argv boundary) and ~30 test call sites.

- **Pro**: one type through the whole chain.
- **Con**: widest blast radius; discovery-based callers would silently drop
  agent transcripts (discovery defaults to excluding them); the worker receives no
  working-directory argument today; no precedent for a structured object crossing
  the hook-to-worker subprocess boundary.

### Option B — wrappers keep paths, widen internally *(selected, amended)*

> **Selected:** Option B, amended by D4 — the wrappers keep `jsonl_files` and
> **also** accept `handles=`, because the codex CLI path cannot produce paths at all
> (no project folder exists to glob). Widening is via `handles_from_paths`, which
> reuses discovery's own `session_id` rule (D3) rather than "trivially synthesizing"
> — the original rationale's claim that only `handle.host`/`handle.path` are read
> downstream was wrong once `raw_events.session_id` falls back to
> `handle.session_id` for codex/kimi.

- **Pro**: no caller or test signature changes for the path case; the worker/hook
  boundary is untouched; matches the `list[Path] | sqlite3.Cursor` widening
  precedent in `writers.py::_iter_events`.
- **Con**: a new path→handle synthesis helper; mitigated by sharing
  `session_id_for` with discovery.

### Decision Rationale

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — wrappers retyped to handles only | 1 | 0 | 1 | 0 | 2/12 |
| B (amended) — keep paths, add `handles=`, widen internally | 3 | 2 | 3 | 3 | 11/12 |

Decided 2026-09-09 via `/ll:decide-issue`; amended 2026-09-10 (D3/D4) after review
found the codex CLI path and the `session_id` column both need handles.

### Design decisions (D1–D8, folded in 2026-09-10)

- **D1 — `line_no` provenance.** Add `line_no: int | None` to `SessionEvent`,
  populated by every parser. Without it the writer would have to enumerate yielded
  events, which shifts numbering whenever a line is skipped (always, for qwen, since
  `normalize_qwen_record` drops `system` rows). Because the dedup index is
  `(source_path, line_no)` and incremental backfill re-ingests whole files past the
  watermark, a shifted numbering duplicates every previously ingested row in an
  existing DB. This is the one place the issue *does* touch `sessions.py` parsers.
  gemini/omp keep their enumeration-index semantics (identical to today).
- **D2 — legacy raw qwen rows.** The forward landmine (pre-normalized rows
  re-normalized → `normalize_qwen_record` returns `None` → row silently dropped) is
  known. The reverse is not: any DB that already holds qwen rows stores raw wire
  format, and once replay stops normalizing, the extractors see `message.parts`
  records and silently yield nothing — qwen history vanishes from every derived
  table. Fix: replace the `HostLayout.normalize` branch in `writers.py::_iter_events`
  with a shape-keyed shim — `host == "qwen" and is_raw_qwen_record(record)` →
  normalize, else pass through. Idempotent over mixed DBs; closes both landmines.
- **D3 — `session_id` for codex/kimi.** The writer's `record.get("sessionId")`
  is `None` for every codex and kimi payload (codex's id lives in line 1's
  `session_meta.payload.id`/`session_id`; kimi's is the `session_*` directory name),
  and `_backfill_sessions` keys on the same field, so those sessions would never be
  seeded. Fall back to `handle.session_id`, and make `handles_from_paths` derive it
  with the same `session_id_for` rule discovery uses (header for gemini/omp/codex,
  `parents[2]` for kimi, stem otherwise).
- **D4 — codex CLI discovery.** `get_project_folder(host="codex")` is `None` by
  design, so `cli/session.py` must use `detect_sessions(Path.cwd(), "codex")` and
  pass `handles=` to the wrappers. Consequence: codex backfill is cwd-scoped (so is
  the Claude project-folder glob, via `encode_project_path`). Store `event.payload`
  as-is for codex; the envelope `type` (`session_meta`/`response_item`/`event_msg`)
  is preserved in the `event_type` column and the envelope `timestamp` in `ts`, so a
  future codex normalizer loses nothing. Codex is ingest-only until such a
  normalizer exists — `rebuild()` derives no rows from codex payloads.
- **D5 — kimi-code `HostLayout` entry.** Add it here (three comments, two API.md
  lines, and one test defer it to this issue by number). `sessions_subdir = ""`,
  `session_glob = "session_*/agents/main/wire.jsonl"`, subagent fields left at
  their defaults. Delete `_KIMI_WIRE_GLOB` and the kimi special case in
  `_detect_layout_sessions`. Invert `test_kimi_host_layout_unchanged_and_backfill_glob_ingests_zero`.
- **D6 — `raw_line` is no longer verbatim.** Post-swap `raw_line` is
  `json.dumps(event.payload)` for every host (gemini/omp already are). No production
  reader needs byte equality (all `json.loads` it; `recompress_raw_events` only
  repacks). Update the schema comment (`schema.py:463`, "verbatim JSONL line"), the
  `_backfill_raw_events` docstring, and `test_claude_host_still_uses_per_line_path`.
- **D7 — no compatibility wrappers.** The earlier plan to keep
  `normalize_qwen_record`/`normalize_gemini_session`/`normalize_omp_session` "as
  thin wrappers over the `parse_*` functions" was backwards — the parsers call the
  normalizers. Delete the three dataclass fields; leave the normalizer functions
  and their package-root re-exports untouched. `qwen_skip_at_ingest` becomes dead
  once `skip_at_ingest` goes: delete it, its `__init__.py` import/`__all__` entry
  (`__init__.py:111,252`), and its three assertions
  (`test_enh_3166_qwen_normalizer.py:184-190`). Its volume guard is subsumed by
  `normalize_qwen_record` dropping `type: "system"` (which `ui_telemetry` is).
- **D8 — worker `--host` validation mechanism.** `cli/backfill_worker.py` has no
  argparse; follow its own convention: unknown host → stderr message naming
  `REGISTERED_HOSTS` → `return 1` (not `raise SystemExit`). Validate against
  `from little_loops.session_store import REGISTERED_HOSTS` (public since ENH-3427,
  `__init__.py:130`). Test asserts on the return value of `main([...])`.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/sessions.py` — `SessionEvent` gains `line_no` (D1); six parsers populate it; new `session_id_for`, `handles_from_paths` (D3); `_detect_layout_sessions` uses `session_id_for` and drops the kimi special case; delete `_KIMI_WIRE_GLOB` (D5); update the three "deferred to ENH-3422" comments (20, 300, 436).
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events` (747-831) rewritten onto handles; `backfill_raw_events` (834), `backfill` (1053, call at 1108), `backfill_incremental` (1129, call at 1176) gain `handles=` and widen `jsonl_files` via `handles_from_paths` (D4); `since_ts` filter moves onto `handle.updated_at`; docstrings updated (D6).
- `scripts/little_loops/session_store/writers.py` — `HostLayout` (2477-2532): delete `normalize`/`skip_at_ingest`/`normalize_file` and their docstring paragraphs (2484-2517); `host_layout_for` (2548-2628): drop the kwargs at 2563/2577 (qwen), 2590 (gemini), 2610 (omp), add the kimi-code entry (D5); `_iter_events` (3271-3320): replace the `HostLayout.normalize` block (3300-3308) with the D2 shim; docstring updated.
- `scripts/little_loops/session_store/qwen.py` — add `is_raw_qwen_record` (D2); delete `qwen_skip_at_ingest` (D7).
- `scripts/little_loops/session_store/__init__.py` — drop the `qwen_skip_at_ingest` import (111) and `__all__` entry (252); export `handles_from_paths`/`session_id_for` if the CLI imports them from the package root (D7/D3).
- `scripts/little_loops/session_store/schema.py` — `raw_events` comment block (463-487) no longer says "verbatim" (D6). No schema version bump: columns are unchanged.
- `scripts/little_loops/cli/session.py` — codex branch uses `detect_sessions` + `handles=` for both full (707-726) and `--since` (663-683) paths; delete the notice (699-704); both glob sites switch from `sessions_subdir + "*.jsonl"` to `session_glob` (D4/D5).
- `scripts/little_loops/cli/backfill_worker.py` — hand-rolled `--host` validation after the argv loop (30-41) using `REGISTERED_HOSTS`, `return 1` on failure (D8); docstring mentions it.
- `scripts/little_loops/user_messages.py` — `get_sessions_folder` (471-498) reads `.sessions_subdir` at 497; retained field, no change needed. Verify only.
- `scripts/little_loops/hooks/session_start.py` — **unchanged** (argv boundary carries `--host` and a path; Option B keeps that).

### Dependent Files (Callers/Importers)

- `lifecycle.py::rebuild` (959-1023) → `_raw_events_cursor` (998) → `writers.py::_iter_events` cursor branch; seven consumers: `_backfill_sessions` (`lifecycle.py:708`), `_backfill_tool_events`, `_backfill_usage_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_prompt_opt`, `_backfill_skill_events` (`writers.py`, each `json.loads(line)` then branches on `type`). All seven must be exercised against a mixed qwen DB (D2).
- `sessions.py::_detect_layout_sessions` (425) reads `host_layout_for(host).session_glob` (447-449); after D5 it does so for kimi too.
- `writers.py::_backfill_subagent_runs` reads `.glob`/`.parent_from`/`.sidecar_suffix` — retained, unaffected.
- `cli/backfill_worker.py:57-60` reads `HostLayout.session_glob` — retained; after D5 it finds kimi wires in directory mode.
- Test callers of the wrappers with `jsonl_files=` (unchanged by Option B): `test_ll_session.py:1450`; `test_session_store_schema.py:931,961,962,972`; `test_session_store_lifecycle.py:1375,1390,1439,1461,1481,1559,1954`; `test_enh_3166_qwen_normalizer.py:315,333,367,384,509`; `test_enh_3393_gemini_normalizer.py:149,176,177,191,227,246`; `test_enh_omp_normalizer.py:160,186,187,198,220`; `test_assistant_messages.py` (nine `backfill` calls + one `backfill_incremental` at 317); `test_enh_2497_agent_type.py:237`; `test_enh_2511_mcp_telemetry.py:256`; `test_workflow_sequence_analyzer.py:499`.
- Package-root re-exports of `normalize_*` are consumed only by the three normalizer test files; no production code imports them from the root (they import from the submodules). No shim needed (D7).

### Conventions in Force

- Widening an input type internally rather than rippling a public signature: `writers.py::_iter_events`'s `list[Path] | sqlite3.Cursor` union; `rebuild()`. This issue follows it (Option B).
- `SessionHandle` is produced only by discovery today; `handles_from_paths` is the first synthesizer, which is why D3 forces it to share `session_id_for` with discovery.
- `HostLayout` is constructed in exactly one place (`writers.py::host_layout_for`); tests never call the constructor, they call the factory and then assert attributes — so retiring fields breaks attribute assertions, not constructors (see Tests).
- Non-argparse CLI validation in this codebase disagrees on mechanism (`backfill_worker.py` returns 1; `fsm/context_seed.py::apply_context_overrides` raises `SystemExit`). D8 picks the file's own convention.
- Back-compat for a retired name is a bare rebind (`OldName = NewName`), never a wrapper — inapplicable here because nothing is renamed; fields are deleted (D7).
- `REGISTERED_HOSTS` (ENH-3427) is the canonical host list; `add_host_arg` (`cli_args.py:334-361`) wraps it for argparse consumers. `backfill_worker.py` would be its first non-argparse consumer.

### Tests

Existing tests that **must change**:

- `scripts/tests/test_ll_session.py::TestBackfill::test_backfill_host_codex_prints_enh_3420_notice` (~741-759) — asserts the string being deleted. Rewrite as: `--host codex` calls `detect_sessions` and passes `handles=` to `backfill` (patch both).
- `scripts/tests/test_session_discovery.py:731 test_kimi_host_layout_unchanged_and_backfill_glob_ingests_zero` — invert per D5: kimi layout has the wire glob and the worker's directory mode ingests the fixture wire file.
- `scripts/tests/test_enh_3166_qwen_normalizer.py:184-190` (`qwen_skip_at_ingest` assertions) — delete (D7); `218-219,227-228` (`TestHostLayoutRegistry` attribute assertions on `.normalize`/`.skip_at_ingest`) — delete or invert to `not hasattr`.
- `scripts/tests/test_enh_3393_gemini_normalizer.py:128-129,132,136` and `scripts/tests/test_enh_omp_normalizer.py:138-139,142,148-149` — same attribute-assertion fix for `.normalize_file`.
- `scripts/tests/test_enh_3393_gemini_normalizer.py:206-236 test_claude_host_still_uses_per_line_path` — pins verbatim `raw_line`; relax to JSON equality (D6). `182-203` and the omp analog (`test_enh_omp_normalizer.py:192-210`) already assert re-serialized form and should pass unchanged.
- `scripts/tests/test_session_store_schema.py:916 test_backfill_raw_events_ingests_one_row_per_line` — asserts `line_no == 1`; passes under D1, and is the model for the new blank-line test.

New tests (one per decision):

- **D1** — file with a blank line and a malformed line before the third record: assert the third row's `line_no == 3`; re-ingest the same file and assert `COUNT(*)` unchanged (dedup still collides). Cover claude-code and qwen.
- **D2** — insert one raw wire-format qwen row and one pre-normalized qwen row directly (model on `test_session_store_lifecycle.py:1392-1400`), run `rebuild()` twice, assert both rows produce derived rows and counts are identical across the two runs. Add positive-path qwen assertions for `usage_events`, `skill_events`, `prompt_opt_events` (today only zero-count or absent).
- **D3** — `handles_from_paths` for gemini/omp/codex/kimi fixtures yields the same `session_id` as `detect_sessions` for the same file; `_backfill_raw_events` on a codex handle stores that id in `raw_events.session_id` and `_backfill_sessions` seeds it.
- **D4** — place both `scripts/tests/fixtures/codex/` rollouts under `tmp_home/.codex/sessions/2026/09/08/` (the pattern at `test_session_discovery.py:171`), call `backfill(db, handles=detect_sessions(Path("/workspace/project"), "codex", home=tmp_home), host="codex")`, assert two sessions' rows with `host = "codex"`, `event_type` in the envelope vocabulary, `ts` non-empty. CLI-level: patch `detect_sessions` in `cli/session.py`'s namespace and assert `backfill` receives `handles=`.
- **D5** — `host_layout_for("kimi-code").session_glob == "session_*/agents/main/wire.jsonl"`; `_detect_layout_sessions` finds the kimi fixture without `_KIMI_WIRE_GLOB`.
- **D8** — `worker_main([db, path, "--host", "not-a-host"])` returns 1 and writes to stderr; valid host still returns 0 (extend `TestBackfillWorkerHost`, `test_enh_3166_qwen_normalizer.py:532-578`).
- Direct `_backfill_raw_events(conn, [SessionHandle(...), ...])` unit test with literal handles (pattern: `test_session_discovery.py:424-433`).
- Wrapper contract: `jsonl_files` and `handles` both given → `ValueError`.

Existing coverage to re-run, no change expected: `test_session_discovery.py` (parser dispatch), `test_enh_2505_subagent_runs.py`, `test_hook_session_start.py:277`, `test_assistant_messages.py`, the four other wrapper callers listed above.

### Documentation

- `docs/reference/API.md` — session-discovery block (~9497-9541): `SessionEvent.line_no`, `handles_from_paths`/`session_id_for`, `_backfill_raw_events` signature; lines ~9533/9539/9541 stop saying kimi is deferred; ~9566/9581/9584 (`projects_root`, `_iter_events` signature/consumers) updated for the D2 shim.
- `docs/reference/CLI.md` — `ll-session backfill` flags table (~3928-3943): `--host codex` now discovers via `detect_sessions` and is cwd-scoped; ingest-only note.
- `docs/reference/HOST_COMPATIBILITY.md` — footnotes `[^kimiwire]` (~555), `[^qwenwire]` (~564-568), `[^geminiwire]` (~598-601), `[^ompwire]` (~616-617), plus lines ~568 and ~633: normalization now happens in the `sessions.py` parsers at ingest; the replay shim exists only for pre-ENH-3422 qwen rows.
- `docs/ARCHITECTURE.md` — one seam, two halves: discovery (`detect_sessions`) and ingest (`iter_events` → `raw_events`).
- `scripts/tests/fixtures/codex/README.md` — note the fixtures are now also the backfill AC fixtures.

### Configuration

- N/A.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `lifecycle.py::_backfill_raw_events` | per-host branching on `HostLayout` callables | CHANGED | single `iter_events` loop; qwen rows now pre-normalized at rest |
| `raw_events` dedup on `(source_path, line_no)` | real file line numbers for per-line hosts | PRESERVED | via `SessionEvent.line_no` (D1) |
| `raw_events.raw_line` | verbatim source line for per-line hosts | CHANGED | re-serialized payload for all hosts (D6); JSON-equal |
| `raw_events.session_id` | payload `sessionId` only | CHANGED | falls back to `handle.session_id` (D3) |
| `writers.py::_iter_events` qwen replay normalization | unconditional via `HostLayout.normalize` | CHANGED | shape-keyed shim, idempotent (D2) |
| gemini/omp ingest | file-level normalizer, enumeration `line_no`, re-serialized `raw_line` | PRESERVED | same normalizers behind `parse_gemini_session`/`parse_omp_session` |
| `ll-session backfill --host codex` | notice + 0 sessions | CHANGED | discovery via `detect_sessions`, cwd-scoped (D4) |
| `host_layout_for("kimi-code")` | generic default | CHANGED | real entry (D5) |
| `cli/backfill_worker.py --host` | unvalidated | CHANGED | `return 1` on unknown host (D8) |
| Public wrapper `jsonl_files=` callers | `list[Path]` | PRESERVED | widened internally (Option B) |
| `hooks/session_start.py` worker argv | `<db> <path> [--rebuild] [--host H]` | PRESERVED | untouched |

## Implementation Steps

1. `sessions.py`: add `SessionEvent.line_no`; populate in all six parsers; add `session_id_for` and `handles_from_paths`; route `_detect_layout_sessions` through `session_id_for`. Tests D1, D3.
2. `qwen.py`: add `is_raw_qwen_record`. `writers.py::_iter_events`: replace the `HostLayout.normalize` block with the shape-keyed qwen shim. Test D2 (mixed-DB rebuild, run twice).
3. `lifecycle.py`: rewrite `_backfill_raw_events` onto handles; add `handles=` to the three wrappers with `handles_from_paths` widening and the both-given `ValueError`; move the `since_ts` filter onto `handle.updated_at`. Direct-handle unit test; wrapper contract test; run the full existing wrapper-caller test list.
4. `writers.py`: delete the three `HostLayout` fields and their `host_layout_for` kwargs; add the kimi-code entry; delete `_KIMI_WIRE_GLOB` and the kimi special case in `sessions.py`. `qwen.py`: delete `qwen_skip_at_ingest`; fix `__init__.py` and the nine attribute assertions. Invert the kimi test. Test D5.
5. `cli/session.py`: codex branch via `detect_sessions` + `handles=` for both paths; delete the notice; both glob sites → `session_glob`. Rewrite the notice test; add the D4 fixture test.
6. `cli/backfill_worker.py`: `--host` validation against `REGISTERED_HOSTS`, `return 1`. Test D8.
7. Docs per `### Documentation`; update the three `sessions.py` ENH-3422 comments and the `schema.py` comment (D6).
8. Gate: `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`; `grep -rn "normalize_file\|skip_at_ingest\|layout\.normalize\|_KIMI_WIRE_GLOB" scripts/little_loops` returns nothing.

## Impact

- **Priority**: P3 — debt, but D1/D2 protect existing `history.db` contents.
- **Effort**: Medium.
- **Risk**: Medium — `raw_events` feeds `ll-ctx-stats`, `ll-history`, FEAT-3418. D1 and D2 are the mitigations; do not ship without them.
- **Breaking Change**: No public API removed; `HostLayout` loses three fields and `qwen_skip_at_ingest` is deleted (no production importers).

## Scope Boundaries

- **In scope**: everything under `### Files to Modify`; D1–D8; kimi-code `HostLayout` entry; the codex CLI discovery path; docs listed.
- **Out of scope**: a codex or kimi normalizer to Claude shape (codex/kimi stay ingest-only); `cli/logs.py` (ENH-3430, done); `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`); any `raw_events` schema change or version bump; a one-shot migration of legacy qwen rows (D2's shim makes it unnecessary).

## Acceptance Criteria

- `_backfill_raw_events` takes handles and calls `iter_events`; no production code reads `HostLayout.normalize`/`normalize_file`/`skip_at_ingest`; `qwen_skip_at_ingest` and `_KIMI_WIRE_GLOB` are gone.
- **D1**: a file containing a blank line and a malformed line ingests with real file line numbers; re-ingesting it inserts zero new rows (claude-code and qwen).
- **D2**: a DB holding one raw and one pre-normalized qwen row rebuilds both into the derived tables, and a second `rebuild()` yields identical counts.
- **D3**: codex and kimi rows carry a non-null `session_id` matching what `detect_sessions` reports for the same file; `_backfill_sessions` seeds them.
- **D4**: `ll-session backfill --host codex` ingests both `scripts/tests/fixtures/codex/` rollouts (placed under a `tmp_path` codex home) with `host = "codex"` and envelope `event_type`; the ENH-3420 notice and its test are gone.
- **D5**: `host_layout_for("kimi-code").session_glob` is the wire glob; the kimi discovery test passes without the module-level special case.
- **D6**: `raw_line` equals `parsed_json` (JSON-equal to the parser payload) for every host; schema comment and docstrings no longer say "verbatim".
- **D8**: `backfill_worker.main([... , "--host", "bogus"])` returns 1 with a stderr message; the hook's argv shape is unchanged.
- Existing wrapper callers with `jsonl_files=` pass unmodified; the three per-host normalizer test files and `test_enh_2505_subagent_runs.py` pass with only the attribute-assertion and `skip_at_ingest` deletions listed under `### Tests`.
- Full local gate (`python -m pytest scripts/tests/`, ruff, mypy) is green.

## Related Key Documentation

- `docs/reference/API.md` — session discovery / `raw_events` rebuild narrative
- `docs/reference/HOST_COMPATIBILITY.md` — per-host wire-format footnotes
- `docs/ARCHITECTURE.md` — session-store seam

## Status

**Open** | Created: 2026-09-09 | Priority: P3 | Rewritten: 2026-09-10

## Confidence Check Notes

_The 2026-09-09 `/ll:confidence-check` (readiness 80, outcome 37) predates the
2026-09-10 rewrite; its blocking gap (ENH-3419 open) is resolved (ENH-3430 is
done) and its "unapplied decision" and "qwen landmine" risk factors are addressed
by the amended Option B and D2. Re-run `/ll:confidence-check` before implementing._

## Session Log
- `review (manual: consolidated rewrite; folded in D1–D8 — SessionEvent.line_no, legacy-qwen replay shim, session_id fallback + handles_from_paths/session_id_for, handles= on wrappers + detect_sessions for codex, kimi HostLayout entry, raw_line non-verbatim, no compat wrappers + delete qwen_skip_at_ingest, worker return-1 validation)` - 2026-09-10T15:30:00
- `/ll:reconcile-issue` - 2026-09-10T14:36:37 - `aa91b0ac-cc46-43a1-808f-2a072895521c.jsonl`
- `/ll:refine-issue` - 2026-09-10T06:29:07 - `3676ef66-ff64-449a-a773-2f0386e3eedc.jsonl`
- `/ll:refine-issue` - 2026-09-10T04:51:50 - `706ab49f-e7ae-457a-9ac3-1d50e1081cd8.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:58:19 - `a29c3127-073c-4881-95b4-061e8465cc19.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:58:00 - `2d12b93a-9de4-4b3d-ab65-1243b5697ecb.jsonl`
- `/ll:refine-issue` - 2026-09-09T22:48:09 - `ab41948f-86de-4b0f-a6d4-63b2ea97f9ce.jsonl`
- `/ll:confidence-check` - 2026-09-09T21:56:36 - `3ffb97df-a1e4-4572-9fad-20e96964df3d.jsonl`
- `/ll:wire-issue` - 2026-09-09T21:51:53 - `3ffb97df-a1e4-4572-9fad-20e96964df3d.jsonl`
- `/ll:decide-issue` - 2026-09-09T21:34:52 - `cfff13dd-6712-456b-b300-725cb5386db2.jsonl`
- `/ll:refine-issue` - 2026-09-09T21:28:52 - `f04bbf31-b730-4f98-8c45-638cd1161297.jsonl`
- `/ll:confidence-check (manual decision reformat)` - 2026-09-09T21:21:52 - `378ef5f9-2efe-4141-9b76-45d94b59278c.jsonl`
- `review (manual: blocked_by ENH-3420→ENH-3419 (3420 done; 3419 lands first and owns cli/logs.py); _has_ll_activity/_extract_cwd_from_project deletion and _extract_ll_event_streams handles signature moved to ENH-3419; step 2 and the coordination note superseded; cli/logs.py removed from Files to Modify and In-scope)` - 2026-09-09T23:40:00
- `/ll:confidence-check` - 2026-09-09T21:15:25 - `15a3a72b-d6e3-4759-990e-0642b22d6179.jsonl`
- `/ll:wire-issue` - 2026-09-09T21:04:07 - `f3e8c388-f237-4461-9091-b0b23efd2cd3.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:49:55 - `7f9ebdc1-1c66-49aa-88bc-4fc32b3d04be.jsonl`
- `/ll:confidence-check` - 2026-09-09T20:36:46 - `33e77cdf-52d2-4350-bc12-c11c654aafbd.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T20:34:13 - `2fd45f5b-ae88-495d-9824-d79e9d1a2e5f.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:26:42 - `707b6c2b-2b94-48e8-86f8-1ee81a021633.jsonl`
