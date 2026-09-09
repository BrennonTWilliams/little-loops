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

`_backfill_raw_events` and the read-path `_iter_events` each carry their own per-host normalization branching today, duplicating the host-dispatch logic that ENH-3420 already centralized in `iter_events`/`_PARSERS`. That duplication is the direct cause of the qwen landmine this issue has to close (`normalize_qwen_record` applied twice silently drops rows) and is why Codex sessions currently can't be ingested at all — `cli/session.py:702` prints a standing "not wired up yet" notice and a Codex backfill ingests 0 sessions, even though `iter_events` has supported Codex since ENH-3420 landed. Leaving the two paths unmerged means every future host addition (kimi-code today, whatever comes next) has to be wired into ingestion *and* normalization *and* the four other `HostLayout.normalize`/`normalize_file` readers separately, instead of once through `iter_events`. Completing this consumer swap is what lets `raw_events` — and everything downstream that aggregates over it (`ll-ctx-stats`, `ll-history`, FEAT-3418's workspace totals) — treat all 8 registered hosts uniformly, and it closes out the seam-unification work ENH-3420 started rather than leaving it half-migrated.

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
- `scripts/little_loops/session_store/lifecycle.py:1129` — `backfill_incremental()`, a thin wrapper over `backfill_raw_events()` (per its own docstring) used by the `SessionStart` hook worker; not previously listed among this issue's dependents.
- `scripts/little_loops/session_store/lifecycle.py:959-1023` (`rebuild()`) via `_raw_events_cursor()` at line 998 — the concrete call path that feeds stored `raw_events` rows into `writers.py::_iter_events`'s cursor-replay branch (lines 3268-3289), where the qwen non-idempotency landmine (line 3284) actually fires.
- `scripts/little_loops/session_store/__init__.py:79` — sole importer of `lifecycle.py` (confirmed via code-graph `importers-of`); re-exports `HostLayout`, `host_layout_for`, `_backfill_subagent_runs` (import block ~147-168, `__all__` ~244-299).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py:145-199` — a **second, distinct** re-export block (not the lifecycle.py block at line 79 already listed) importing `HostLayout` (147), `host_layout_for` (168), `_backfill_subagent_runs` (154), `_backfill_assistant_messages`/`_backfill_messages` (151-152) directly from `writers.py`. No functional change needed here (the dataclass name and factory function are untouched, only their field set shrinks), but confirm no `__all__` entry names a field being retired.
- `scripts/little_loops/session_store/sessions.py:425` — `_detect_layout_sessions()` does a local deferred `from little_loops.session_store.writers import host_layout_for` and reads `host_layout_for(host).session_glob` — a direct `host_layout_for` dependency outside the four files already named. `session_glob` is a retained path-metadata field, so no change is required, but this caller was missing from the map.
- `scripts/little_loops/session_store/writers.py` — six `_backfill_*` functions all consume `_iter_events()`'s cursor-replay output and therefore all benefit from (and must be verified against) the qwen-normalize-removal fix at line 3284, not just the single call site the map names: `_backfill_tool_events` (3302, call at 3309), `_backfill_usage_events` (3391, call at 3415), `_backfill_messages` (3477, call at 3487), `_backfill_assistant_messages` (3529, call at 3546), `_backfill_prompt_opt` (3596, call at 3623), `_backfill_skill_events` (3669, call at 3680). Each does `json.loads(line)` and branches on `record.get("type")`, so each is a live consumer of whatever `_iter_events` yields for a qwen row today and post-fix.
- `scripts/little_loops/session_store/lifecycle.py:834-868` (`backfill_raw_events()`), `:1050-1126` (`backfill()`), `:1129-1180` (`backfill_incremental()`) — all three PUBLIC wrappers still declare `jsonl_files: list[Path]` and pass it straight through to `_backfill_raw_events`. The issue's signature change targets only the private `_backfill_raw_events`; nothing in the Integration Map says whether these three public wrappers also gain a `handles` parameter or instead internally convert `list[Path]` → `list[SessionHandle]` before calling it — and **no code in the tree today performs a bare-`Path`-to-`SessionHandle` conversion** (`detect_sessions()` is the only producer, via DB query or directory scan, not via glob-then-wrap). This is a real open design gap, not a mechanical rename — see the new Wiring Phase step below.
- Production callers that build `list[Path]` via glob and feed it into the three public wrappers above (all cross the same unresolved Path→Handle boundary): `scripts/little_loops/cli/session.py:671-684,709-727`; `scripts/little_loops/cli/backfill_worker.py:52-67`; `scripts/little_loops/hooks/session_start.py:159-179` (crosses a `subprocess.Popen` argv boundary into `backfill_worker.py`, not just a function call).
- ~30 test call sites invoke `backfill_raw_events(db, jsonl_files=[...], ...)` directly against `list[Path]` and will need updating (or the public wrapper needs to keep accepting `list[Path]` for back-compat): `test_ll_session.py:1450`, `test_session_store_schema.py:931,961,962,972`, `test_session_store_lifecycle.py:1375,1390,1439,1461,1481,1559,1954`, `test_enh_3166_qwen_normalizer.py:315,333,367,384,509`, `test_enh_3393_gemini_normalizer.py:149,176,177,191,227,246`, `test_enh_omp_normalizer.py:160,186,187,198,220`.
- `scripts/little_loops/session_store/writers.py::host_layout_for` (2538-2600) and `scripts/little_loops/session_store/sessions.py` (`parse_qwen_session`/`parse_gemini_session`/`parse_omp_session`, lines 751-809) both import `normalize_qwen_record`/`normalize_gemini_session`/`normalize_omp_session` directly from their submodules (`qwen.py`, `gemini.py`, `omp.py`), never via the `session_store/__init__.py` package-root re-export. Confirmed by repo-wide search: **zero production dependents** of the package-root re-export exist — only the three named normalizer test files (`test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`) import from the package root. This narrows what Implementation Step 5's "thin compatibility wrapper for one release" actually needs to serve — production code needs no shim at all.

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

_Wiring pass added by `/ll:wire-issue`:_
- **Breaking, not in the issue's known-tests list**: `scripts/tests/test_ll_session.py::TestBackfill::test_backfill_host_codex_prints_enh_3420_notice` (~lines 741-759) asserts `"ENH-3420" in capsys.readouterr().err` — a direct executable assertion on the exact notice string `cli/session.py:702` drops per this issue's own Proposed Solution. This test must be deleted or rewritten in the same change, or it fails immediately after the notice is removed.
- **Coverage gap, priority**: no existing test constructs a `raw_events` row for `host="qwen"` whose `raw_line` is *already* Claude-shaped (the ingest shape ENH-3422 produces) and then verifies `writers.py::_iter_events`'s cursor-replay branch does NOT re-run `normalize_qwen_record` on it. `TestRebuildQwenRecords` (`test_enh_3166_qwen_normalizer.py:377-464`) only exercises today's raw-wire-format → single-normalization-at-rebuild flow. New test needed: insert a pre-normalized qwen `raw_events` row directly (model row construction on `test_session_store_lifecycle.py:1392-1400`), run `rebuild()`, and assert all six downstream tables populate correctly — `tool_events`, `usage_events`, `message_events`, `assistant_messages`, `prompt_opt_events`, `skill_events` (writers.py:3309,3415,3487,3546,3623,3680) — not just `raw_events` row count as the issue's Expected Behavior section currently specifies.
- Of those six tables, existing qwen-rebuild coverage today is uneven: `tool_events`/`message_events`/`assistant_messages` have positive content-level assertions; `usage_events`/`skill_events` are only ever asserted as zero-count for qwen (no positive-path proof); `prompt_opt_events` (`_backfill_prompt_opt`) has no qwen assertion at all. Add positive-path coverage for the latter three alongside the double-normalization regression test above.
- New test needed for `_backfill_raw_events(handles: list[SessionHandle], ...)` itself — no fixture builder in the codebase constructs a `list[SessionHandle]` and passes it as a function argument today (only single-`SessionHandle` args in `test_session_discovery.py::TestIterEventsDispatch:424-449`, and `detect_sessions()`'s own return values are asserted on, never re-fed as input elsewhere). Model the handle literals on `test_session_discovery.py:424-433`'s field pattern (`host`, `session_id`, `path`, `cwd`, `updated_at`, `is_agent`).
- New test needed for `cli/backfill_worker.py`'s planned `--host` validation (Acceptance Criterion 4): confirmed via both name-based and behavior-based search that **no test anywhere exercises this file's hand-rolled argv parser with an invalid value** — not even its pre-existing "missing positional args" or "path not found" error branches have coverage today. `TestBackfillWorkerHost` (`test_enh_3166_qwen_normalizer.py:532-578`) only calls `worker_main([...])` with a *valid* `--host qwen`. The nearest same-intent (not same-mechanism) analog is `test_ll_session.py::test_backfill_host_choices_list` (41-61), which relies on argparse's own `choices=` `SystemExit` — `backfill_worker.py` has no argparse, so the new test must call `worker_main([...])` directly and assert on the hand-rolled validation's `SystemExit`/return code once Implementation Step 4 adds it.

### Documentation
- `docs/reference/API.md` — session discovery section (lines 9497-9524) already documents `detect_sessions`/`iter_events`/`SessionHandle`/`SessionEvent`; needs the `_backfill_raw_events` signature change reflected.
- `docs/reference/CLI.md` — `backfill` `--host` flag row (line 3939, inside the flags table lines 3928-3943).
- `docs/ARCHITECTURE.md` — HostLayout/iter_events/backfill_worker narrative (seam note per Scope Boundaries).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` lines 9533, 9539, 9541 — additional lines in the *same* session-discovery narrative block, outside the cited 9497-9524/9502-9505 ranges: line 9533 notes qwen "already ships a normalizer for the `HostLayout`/`writers.py` seam"; lines 9539/9541 explicitly promise "a kimi `HostLayout` entry is deferred to ENH-3422" — this issue is what's supposed to deliver that, so these lines need updating alongside the already-cited range, not separately forgotten.
- `docs/reference/HOST_COMPATIBILITY.md` — four footnotes not in the issue's docs list, each narrating the exact mechanism being retired/relocated: `[^kimiwire]` (~555-556, already anticipates this issue by number); `[^qwenwire]` (~564-568, documents qwen normalizing "at rebuild time inside `_iter_events`" — the call site being changed); `[^geminiwire]` (~598-601, names `HostLayout.normalize_file` as gemini's contract); `[^ompwire]` (~616-617, documents omp reusing gemini's `normalize_file` contract). All four need updating once `normalize`/`normalize_file`/`skip_at_ingest` are removed from `HostLayout`.

### Configuration
- N/A

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/little_loops/session_store/lifecycle.py::_backfill_raw_events` | Takes `jsonl_files: list[Path]`; branches per host on `layout.normalize_file` (gemini/omp, whole-file) vs. a raw line read plus `skip_at_ingest` (qwen and everyone else) | CHANGED | Replaced by a single loop over `iter_events(handle)` per `handles: list[SessionHandle]`; qwen rows go from raw-stored to pre-normalized (`parse_qwen_session` already applies `normalize_qwen_record`) |
| `scripts/little_loops/session_store/lifecycle.py::_backfill_raw_events` idempotent `INSERT OR IGNORE` dedup on `(source_path, line_no)` | PRESERVED | Dedup index and idempotency semantics are unchanged by the consumer swap |
| `scripts/little_loops/cli/backfill_worker.py` `--host` argument handling | Hand-rolled `for i, arg in enumerate(args)` loop (lines 30-41); no validation against a fixed host list today | CHANGED | AC requires rejecting an unknown `--host` with `SystemExit`; cannot literally "add `choices=`" since this file has no argparse — equivalent validation must be hand-rolled to match `cli/session.py`'s behavior |
| `scripts/little_loops/cli/backfill_worker.py` `layout.session_glob` glob (line 60) | PRESERVED | `session_glob` is a path-metadata `HostLayout` field, retained post-shrink |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- **Dataclass field retirement has no delete-with-zero-readers precedent in this codebase**: the closest analog (`IssuesConfig.completed_dir`/`.deferred_dir`, `config/features.py:234-235`) is annotated `# DEPRECATED: use X instead` on the field declaration but keeps live readers (`config/core.py:571-572`, `cli/migrate.py:122-146`) — it documents "deprecate in place while still read," not "delete once the last reader is gone." A repo-wide search for field-retirement language (`field retired`, `no longer read`, `removed field`, `deprecated field`, `kept for backward`) found no precedent for outright deletion. Step 5's plan to delete `normalize`/`normalize_file` outright (rather than deprecate-in-place) has no existing convention either confirming or refuting it — it is uncharted, not just "non-standard."
- **`--host` is validated four different, non-interoperating ways today**, not just the two already named above (`cli/session.py`'s `choices=` vs. `session_store/sessions.py::_REGISTERED_HOSTS`): `init/cli.py:33-34,184-185` keeps its own `_KNOWN_HOSTS` frozenset and **logs-and-continues** (`error(...); continue`) rather than exiting on an unknown host; `adapters/core.py:53-78`'s `_EMITTER_MAP` is a *6-host* subset (missing `opencode`/`pi`) that raises a custom `AdapterError`, caught by its caller (`cli/adapt.py:86-90`) and converted to `print(...); return 1` — not `SystemExit` at all. No shared `validate_host` helper exists anywhere in the codebase (searched repo-wide). AC 4's `SystemExit`-on-unknown-host requirement for `backfill_worker.py` matches only `cli/session.py`'s convention, not the other two.
- `scripts/tests/test_session_discovery.py::test_kimi_host_layout_unchanged_and_backfill_glob_ingests_zero` (line 711) — an existing test explicitly citing ENH-3422 by number as a regression guard: asserts `host_layout_for("kimi-code")` stays the generic default and `backfill_worker.py`'s `path_arg.glob(layout.session_glob)` still matches zero files.
- `scripts/tests/test_ll_session.py::TestArgumentParsing::test_backfill_host_choices_list` (lines 41-61) — existing coverage for `cli/session.py`'s `--host` `choices=` list, asserting `pytest.raises(SystemExit)` for `"not-a-real-host"`. No equivalent test exists for `cli/backfill_worker.py` today (confirmed: no `test_backfill_worker*.py` file exists) — AC 4's new `backfill_worker.py` validation has no existing test to extend, only this one to pattern-match.

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
- `/ll:refine-issue` - 2026-09-09T20:49:55 - `7f9ebdc1-1c66-49aa-88bc-4fc32b3d04be.jsonl`
- `/ll:confidence-check` - 2026-09-09T20:36:46 - `33e77cdf-52d2-4350-bc12-c11c654aafbd.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T20:34:13 - `2fd45f5b-ae88-495d-9824-d79e9d1a2e5f.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:26:42 - `707b6c2b-2b94-48e8-86f8-1ee81a021633.jsonl`
