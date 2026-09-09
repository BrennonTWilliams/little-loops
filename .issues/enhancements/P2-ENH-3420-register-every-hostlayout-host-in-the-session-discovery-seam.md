---
id: ENH-3420
type: ENH
title: Register every HostLayout host in the session-discovery seam (unify, phase 1)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:27:16Z'
labels:
- multi-host
- architecture
- tech-debt
blocked_by:
- FEAT-3417
blocks:
- ENH-3419
- ENH-3422
relates_to:
- FEAT-3417
reconcile_attempted: true
---

# ENH-3420: Register every HostLayout host in the session-discovery seam (unify, phase 1)

## Summary

Follow-up filed from FEAT-3417's decision rationale. FEAT-3417 has landed (`scripts/little_loops/session_store/sessions.py`, commits df112fecc / f9768d61a), so the tree now carries two live per-host dispatch mechanisms for reading host session logs:

- `session_store/writers.py`'s `HostLayout` (`host_layout_for`, `writers.py:2527`) — `projects_root`, `sessions_subdir`, `session_glob`, and `normalize`/`normalize_file` entries for qwen/gemini/omp that translate host-native records into a shared Claude-shaped record. Consumed by `writers.py::_iter_events` (3250, cursor replay), `lifecycle.py::_backfill_raw_events` (747), `cli/session.py backfill`, `cli/backfill_worker.py`, `writers.py::_backfill_subagent_runs` (2670), and `cli/logs.py`'s `_has_ll_activity` (97) / `_extract_cwd_from_project` (134) / `_extract_ll_event_streams` (261).
- `session_store/sessions.py` — `detect_sessions`/`iter_events`/`list_workspaces` with a `_PARSERS` dict (`sessions.py:451`) and an `if host == ...` chain in `detect_sessions` (279-283), registered for `claude-code` and `codex` only (`_REGISTERED_HOSTS`, 250). `host=None` unions those two and ignores `LL_HOOK_HOST`.

**Decision (2026-09-09 review): unify, in two phases.** This issue is phase 1 — register every host that `get_project_folder` (`user_messages.py:373-419`) knows (`opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`) in `detect_sessions`/`iter_events`, so the seam is a superset of `HostLayout` for discovery and reading. Phase 2 (ENH-3422) makes `_backfill_raw_events` consume `iter_events` and shrinks `HostLayout` to path metadata. The "keep separate, documented" option was rejected because ENH-3419 cannot rewire `ll-logs`/`ll-messages`/`ll-ctx-stats` onto a seam that covers two of eight hosts without regressing the qwen/gemini/omp support those CLIs already have (ENH-3165, ENH-3166, ENH-3393) — see § Motivation. The "wait for a goal 6/7 signal" deferral is also moot: FEAT-3418 (landed) reads history.db and `ll-logs eval-export` reads raw sessions, so both consumer kinds exist.

## Current Behavior

`detect_sessions(cwd, "qwen")` (or gemini/omp/kimi-code/opencode/pi) returns `[]` (`sessions.py:283`), and `iter_events` on a handle with any such host yields nothing (`sessions.py:459-461`). Those hosts are reachable only through `get_project_folder`/`get_sessions_folder` + `HostLayout`, and only when `LL_HOOK_HOST` names them (`user_messages.py:395,442`, `cli/logs.py:190,649`). Codex is the reverse: reachable through the seam only; `host_layout_for("codex").projects_root` is `None` (`writers.py:2591-2604`) and `ll-session backfill --host codex` prints the "not wired up yet (ENH-3420)" notice (`cli/session.py:702`) — that notice is ENH-3422's to remove, not this issue's.

`HostLayout`'s normalization is a two-tier split by where the session id lives: qwen's `normalize_qwen_record(record) -> dict | None` (`qwen.py:59`) is per-record (id on every record), consumed inline in `_iter_events` and directly in `cli/logs.py`'s `_has_ll_activity`/`_extract_ll_event_streams`; gemini's `normalize_gemini_session(path) -> Iterator[dict]` (`gemini.py:40`) and omp's `normalize_omp_session(path) -> Iterator[dict]` (`omp.py:54`) are whole-file generators (id only in a header line), consumed once at `_backfill_raw_events` ingest time. Consequence: gemini/omp rows in `raw_events` are pre-normalized at rest; qwen rows are stored raw and re-normalized on every read.

Malformed-input handling is consistent across every normalizer and both seam parsers: `try/except json.JSONDecodeError: continue`, never raising; file-open `OSError` yields a bare generator `return`. FEAT-3417's close-out added a second rule to `sessions.py`: a line that is valid JSON but not an object is skipped, not raised on. New `parse_*` functions follow both.

Naming collision to keep straight: `writers.py::_iter_events` (3250, underscore, cursor/list-of-Path replay for `rebuild`) and `sessions.py::iter_events` (no underscore, `SessionHandle -> Iterator[SessionEvent]`) are unrelated.

## Expected Behavior

`detect_sessions(cwd, host)` returns handles for every host in `get_project_folder`'s vocabulary, and `detect_sessions(cwd)` (host `None`) unions all of them, newest first. `iter_events(handle)` yields `SessionEvent`s for each. The payload contract per host is:

- `claude-code`, `codex`: host-native record, unchanged (FEAT-3417's "refused on content" rule).
- `opencode`, `pi`: Claude-shaped on disk already (`host_layout_for` treats them with the generic Claude tail); parsed with `parse_claude_transcript` and stamped with their own `host`.
- `qwen`, `gemini`, `omp`, `kimi-code`: the record the host's existing normalizer produces — i.e. Claude-shaped. This is not a new cross-host abstraction: it is each host's *existing* contract (ENH-3166/ENH-3393/omp), lifted behind the seam so that ENH-3419's Claude-schema content functions in `cli/logs.py` keep recognizing qwen/gemini/omp activity exactly as they do today via `HostLayout.normalize`. The `sessions.py` module docstring's "refused on content" paragraph is amended to state this rule: *payload is host-native where no normalizer exists (claude-code, codex); where a host already ships a normalizer to Claude shape, payload is that normalizer's output.*

`HostLayout` is untouched in this phase except that its normalizers are re-exported as the new `parse_*` functions' implementation, so both seams read the same code.

## Motivation

ENH-3419's acceptance criterion is that `ll-logs`, `ll-messages`, and `ll-ctx-stats` obtain sessions only via `detect_sessions`/`iter_events`. Today that would silently drop qwen/gemini/omp: `test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl::test_resolves_qwen_chats_transcript` (909) and `test_resolves_gemini_chats_transcript` (941) set `LL_HOOK_HOST` and expect the per-host `sessions_subdir` to be honoured; `test_enh_3166_qwen_normalizer.py` (277-296) expects `discover_all_projects(host="qwen")` and `_has_ll_activity` to find qwen projects. Every new host otherwise has to be wired twice (once per seam) or ends up half-supported — the "silently covers one host while claiming to generalize" failure FEAT-3417 set out to fix, reproduced one layer down.

## Scope Boundaries

- **In scope**: adding `opencode`/`pi`/`kimi-code`/`qwen`/`gemini`/`omp` branches to `detect_sessions` (wrapping the existing `_get_<host>_project_folder` probes + `HostLayout.sessions_subdir`/`session_glob`, with the `home` override honoured), `list_workspaces` branches for hosts with a `projects_root` (`opencode`, `pi`; `kimi-code` via `session_index.jsonl` if cheap, else documented `[]`), `parse_qwen_session`/`parse_gemini_session`/`parse_omp_session`/`parse_kimi_session` registered in `_PARSERS`, the `sessions.py` docstring amendment, `LL_HOOK_HOST` awareness (below), `docs/reference/HOST_COMPATIBILITY.md:522`'s "readable via `detect_sessions()`" row flipped to ✓ for each added host, `docs/ARCHITECTURE.md` seam note.
- **`LL_HOOK_HOST`**: `detect_sessions(host=None)` stays a pure union (FEAT-3417 decided). The env-var fallback belongs in the CLIs' host resolution (`args.host or os.environ.get("LL_HOOK_HOST")`, union only when neither is set) — that lives in ENH-3419, not here.
- **Out of scope**: ENH-3422 (backfill consuming `iter_events`, `HostLayout` shrink, the `backfill --host codex` notice); ENH-3419's CLI rewiring; Codex-native equivalents of the Claude-schema content functions in `cli/logs.py`; the `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`).

## Program Design

### Types

- `SessionHandle`, `SessionEvent` (`session_store/sessions.py:41-67`) — unchanged.
- `HostLayout` (`session_store/writers.py:2456`) — unchanged this phase.

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — existing; `_REGISTERED_HOSTS` (`sessions.py:250`) grows to the full `get_project_folder` vocabulary and the `if host ==` chain (279-283) gains one `_detect_<host>_sessions` branch per host.
- `_detect_layout_sessions(host: str, cwd: Path, home: Path, limit: int | None, include_agents: bool) -> list[SessionHandle]` (new) — shared implementation for every non-codex host: resolve the project folder (reimplementing the `_get_<host>_project_folder` probe under `home`, as `_detect_claude_sessions` does at `sessions.py:218-247`), join `host_layout_for(host).sessions_subdir`, glob `session_glob`, `is_agent = name.startswith("agent-")`.
- `parse_qwen_session(path: Path) -> Iterator[SessionEvent]` (new) — per-line loop over `normalize_qwen_record` (the shape `_backfill_raw_events`'s non-`normalize_file` branch already uses at `lifecycle.py:747+`); qwen is per-record, **not** already generator-shaped.
- `parse_gemini_session(path) -> Iterator[SessionEvent]` / `parse_omp_session(path) -> Iterator[SessionEvent]` (new) — wrap the already-generator-shaped `normalize_gemini_session` (`gemini.py:40`) / `normalize_omp_session` (`omp.py:54`), stamping `host`.
- `parse_kimi_session(path) -> Iterator[SessionEvent]` (new) — per `_get_kimi_project_folder`'s layout (`user_messages.py:412`); if kimi records are Claude-shaped, alias `parse_claude_transcript` with a host stamp.

### Call Path

`detect_sessions(cwd, "qwen", home=...)` -> `_detect_layout_sessions("qwen", ...)` -> `SessionHandle(host="qwen", ...)` -> `iter_events(handle)` -> `_PARSERS["qwen"]` = `parse_qwen_session(handle.path)` -> `normalize_qwen_record(record)` per line -> `SessionEvent(host="qwen", payload=<Claude-shaped>)`

## Proposed Solution

1. Extend `_REGISTERED_HOSTS` and the `detect_sessions` chain with one branch per host, all delegating to `_detect_layout_sessions`. Dispatch on a bare host string already appears three ways in this codebase (`host_layout_for`'s `if`/`elif` chain, `get_project_folder`'s named `_get_<host>_project_folder` functions, `sessions.py`'s `_PARSERS` dict); extend the two idioms `sessions.py` already uses rather than introducing a fourth.
2. Add the four `parse_*` generators next to `parse_codex_rollout`/`parse_claude_transcript`; register them in `_PARSERS`; export them from `session_store/__init__.py` with the eager-import + `__all__` pattern the existing normalizers use (`__init__.py:67,91,100`, `__all__` 221-224). Do not rename the `normalize_*` functions in this phase; the `parse_*` functions call them.
3. Amend the `sessions.py` module docstring per § Expected Behavior.
4. Add `list_workspaces` branches for `opencode`/`pi` (walk `projects_root`, reuse `_first_record_cwd`); `kimi-code`/`qwen`/`gemini`/`omp` return `[]` unless the probe is trivial, matching `discover_all_projects`'s existing silent-`[]` precedent for a `None` `projects_root` (`cli/logs.py:196-198`).
5. Docs.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/sessions.py` — `_REGISTERED_HOSTS` (250), `detect_sessions` chain (279-283), `_PARSERS` (451), `list_workspaces` (286-307), module docstring (10-18); new `_detect_layout_sessions` + four `parse_*`
- `scripts/little_loops/session_store/__init__.py` — export the new `parse_*` names (eager import + `__all__`)
- `docs/reference/HOST_COMPATIBILITY.md:522` (detect_sessions row), `docs/ARCHITECTURE.md` (seam note: one seam, discovery half here, ingest half ENH-3422), `docs/reference/API.md` (session-discovery entry added by f9768d61a)

### Dependent Files (must not change)
- `session_store/writers.py` `HostLayout`/`host_layout_for` (2456-2604), `_iter_events` (3250), `_backfill_subagent_runs` (2670) — read-only this phase; ENH-3422 retargets them.
- `session_store/lifecycle.py::_backfill_raw_events` (747) — ENH-3422.
- `cli/logs.py` `_has_ll_activity` (97), `_extract_cwd_from_project` (134), `_extract_ll_event_streams` (261) — ENH-3419 rewires the call sites; the `HostLayout` parameter goes in ENH-3422.
- `user_messages.py:373-419` `get_project_folder` and `:422-450` `get_sessions_folder` — contract locked by `session_log.py:159-212`, `fsm/continuity.py:43`, `cli/session.py:664,702,718` and their tests; `_detect_layout_sessions` reimplements the probes under `home` rather than calling them (same reason `_detect_claude_sessions` does — they read `Path.home()` directly).
- `session_store/qwen.py`, `gemini.py`, `omp.py` — normalizer bodies unchanged; only wrapped.

### Tests
- `scripts/tests/test_session_discovery.py` — add a per-host class mirroring `TestDetectSessionsCodexSqlitePath`/`TestIterEventsDispatch` for each new host, using `home=tmp_path` (never the real home) and the committed fixtures under `scripts/tests/fixtures/{qwen,gemini,omp}/` that the three normalizer test files already use (`FIXTURES = Path(__file__).parent / "fixtures" / "<host>"`). Assert `iter_events` on a qwen handle yields the same records `normalize_qwen_record` yields per line, and on a gemini/omp handle the same records `normalize_*_session` yields.
- `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py`, `test_ll_session.py` — must pass unmodified.
- Add a union test: a `tmp_path` home with one claude-code, one codex, and one qwen session for the same cwd → `detect_sessions(cwd, home=tmp_path)` returns three handles newest-first with distinct `host` values.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:522` — flip the "readable via `detect_sessions()`" cells; `:582,599,616` already discuss `HostLayout.normalize_file` — extend, do not duplicate.
- `docs/ARCHITECTURE.md` — precedent for documenting two mechanisms in one subsystem exists ("SDK/Batches Dispatch Path" ~881-911, "Host Adapter Capability Map" ~1317-1336); write the note in that style, stating discovery/reading = `sessions.py`, ingest-to-history.db = `HostLayout` until ENH-3422.

## Implementation Steps

1. Confirm FEAT-3417 is `done` (it is; frontmatter flipped in the 2026-09-09 close-out) and `python -m pytest scripts/tests/test_session_discovery.py` is green.
2. `_detect_layout_sessions` + six `detect_sessions` branches + `_REGISTERED_HOSTS`; per-host discovery tests.
3. `parse_qwen_session` (per-line loop), `parse_gemini_session`/`parse_omp_session` (wrap), `parse_kimi_session`; register in `_PARSERS`; export; per-host `iter_events` tests.
4. `list_workspaces` branches for `opencode`/`pi`.
5. Docstring amendment; docs; run the four normalizer/backfill test files unmodified.

## Impact

- **Priority**: P2 — raised from P3 on 2026-09-09 because ENH-3419 (P2, user-visible) is blocked on it.
- **Effort**: Medium-Low — additive; no signature changes to existing production functions.
- **Risk**: Low — nothing in production consumes the new branches until ENH-3419; the normalizers are wrapped, not modified.
- **Breaking Change**: No.

## Acceptance Criteria

- `detect_sessions(cwd, h, home=tmp_path)` returns handles for every `h` in `get_project_folder`'s vocabulary (`claude-code`, `codex`, `opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`) given a matching fixture tree under `tmp_path`; `detect_sessions(cwd, home=tmp_path)` unions them newest-first.
- `iter_events` on a qwen/gemini/omp handle yields `SessionEvent`s whose `payload` equals the host's existing normalizer output for the same file, with `host` stamped; on opencode/pi it yields the raw Claude-shaped record.
- `sessions.py`'s docstring states the per-host payload rule (host-native vs. existing-normalizer output).
- `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py`, `test_ll_session.py` pass unmodified.
- `docs/reference/HOST_COMPATIBILITY.md:522` row and a `docs/ARCHITECTURE.md` seam note are updated.

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — per-host session-log table (row 522)
- `docs/reference/API.md` — `little_loops.session_store.sessions` entry

## Status

**Open** | Created: 2026-09-09 | Priority: P2

## Session Log
- `review (manual: FEAT-3417 landed — dropped stale "spike only" findings; decided unify; split ingest half to ENH-3422; flipped dependency so this blocks ENH-3419; P3→P2; per-host payload rule)` - 2026-09-09T19:10:00
- `/ll:confidence-check` - 2026-09-09T15:01:22 - `a4ac4148-e562-4d02-a9a9-889fd2f8dc3f.jsonl`
- `/ll:wire-issue` - 2026-09-09T14:51:25 - `8e56ec89-cd99-46e0-b932-f07e5ea9315c.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T14:15:24 - `aea90797-734c-47d9-89ed-e343ebbf4673.jsonl`
- `/ll:refine-issue` - 2026-09-09T14:08:38 - `1658f0c5-d510-42b4-beb1-234626dbd6e5.jsonl`
- `/ll:format-issue` - 2026-09-09T13:22:54 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
