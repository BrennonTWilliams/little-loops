---
id: ENH-3420
type: ENH
title: Register every HostLayout host in the session-discovery seam (unify, phase
  1)
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:27:16Z'
completed_at: '2026-09-09T20:04:11Z'
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
confidence_score: 100
outcome_confidence: 85
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-3420: Register every HostLayout host in the session-discovery seam (unify, phase 1)

## Summary

Follow-up filed from FEAT-3417's decision rationale. FEAT-3417 has landed (`scripts/little_loops/session_store/sessions.py`, commits df112fecc / f9768d61a), so the tree now carries two live per-host dispatch mechanisms for reading host session logs:

- `session_store/writers.py`'s `HostLayout` (`host_layout_for`, `writers.py:2527`) — `projects_root`, `sessions_subdir`, `session_glob`, and `normalize`/`normalize_file` entries for qwen/gemini/omp that translate host-native records into a shared Claude-shaped record. Consumed by `writers.py::_iter_events` (3250, cursor replay), `lifecycle.py::_backfill_raw_events` (747), `cli/session.py backfill`, `cli/backfill_worker.py`, `writers.py::_backfill_subagent_runs` (2670), and `cli/logs.py`'s `_has_ll_activity` (97) / `_extract_cwd_from_project` (134) / `_extract_ll_event_streams` (261).
- `session_store/sessions.py` — `detect_sessions`/`iter_events`/`list_workspaces` with a `_PARSERS` dict (`sessions.py:466`) and an `if host == ...` chain in `detect_sessions` (281-285), registered for `claude-code` and `codex` only (`_REGISTERED_HOSTS`, 252). `host=None` unions those two and ignores `LL_HOOK_HOST`.

**Decision (2026-09-09 review): unify, in two phases.** This issue is phase 1 — register every host that `get_project_folder` (`user_messages.py:373-419`) knows (`opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`) in `detect_sessions`/`iter_events`, so the seam is a superset of `HostLayout` for discovery and reading. Phase 2 (ENH-3422) makes `_backfill_raw_events` consume `iter_events` and shrinks `HostLayout` to path metadata. The "keep separate, documented" option was rejected because ENH-3419 cannot rewire `ll-logs`/`ll-messages`/`ll-ctx-stats` onto a seam that covers two of eight hosts without regressing the qwen/gemini/omp support those CLIs already have (ENH-3165, ENH-3166, ENH-3393) — see § Motivation. The "wait for a goal 6/7 signal" deferral is also moot: FEAT-3418 (landed) reads history.db and `ll-logs eval-export` reads raw sessions, so both consumer kinds exist.

**Second review (2026-09-09, pre-implementation) corrected three premises** that are now folded into the sections below: (a) kimi-code is *not* Claude-shaped and has no normalizer, so it is registered as a host-native passthrough like codex, not aliased to `parse_claude_transcript`; (b) the gemini/omp/kimi project-folder probes read `Path.home()` and env vars internally, so the `home` override is threaded *into* the existing private probes rather than reimplemented in `sessions.py`; (c) `SessionHandle.session_id` for gemini/omp comes from the file header, not the filename stem, so handles join to `raw_events.session_id`.

**Third review (2026-09-09, pre-implementation) corrected two more and tightened five specs**, all folded in below: (d) a kimi `HostLayout` entry is *not* side-effect free — `cli/backfill_worker.py:60` and `cli/logs.py:108,145,289` glob `layout.session_glob` against the kimi workspace folder, so the glob would push `wire.jsonl` through the Claude line loop into `raw_events` today; the kimi glob therefore stays a constant in `sessions.py` and the `HostLayout` branch moves to ENH-3422; (e) `host_layout_for` builds `projects_root` from `Path.home()` (`writers.py:2537`), so `list_workspaces` for opencode/pi must derive the root from `home`, never from the layout; plus explicit specs for the kimi session id (`path.parents[2].name`, confirmed equal to `session_index.jsonl`'s `sessionId` in `test_user_messages.py:203`), `include_agents` being a no-op on the non-Claude hosts, a bounded omp header scan, gemini `list_workspaces` via `projects.json`, and the full set of stale docstrings.

## Current Behavior

`detect_sessions(cwd, "qwen")` (or gemini/omp/kimi-code/opencode/pi) returns `[]` (`sessions.py:285`), and `iter_events` on a handle with any such host yields nothing (`sessions.py:472-477`). Those hosts are reachable only through `get_project_folder`/`get_sessions_folder` + `HostLayout`, and only when `LL_HOOK_HOST` names them (`user_messages.py:395,442`, `cli/logs.py:190,649`). Codex is the reverse: reachable through the seam only; `host_layout_for("codex").projects_root` is `None` (`writers.py:2591-2607`) and `ll-session backfill --host codex` prints the "not wired up yet (ENH-3420)" notice (`cli/session.py:702`) — that notice is ENH-3422's to remove, not this issue's.

`HostLayout`'s normalization is a two-tier split by where the session id lives: qwen's `normalize_qwen_record(record) -> dict | None` (`qwen.py:59`) is per-record (id on every record), consumed inline in `_iter_events` and directly in `cli/logs.py`'s `_has_ll_activity`/`_extract_ll_event_streams`; gemini's `normalize_gemini_session(path) -> Iterator[dict]` (`gemini.py:40`) and omp's `normalize_omp_session(path) -> Iterator[dict]` (`omp.py:54`) are whole-file generators (id only in a header line), consumed once at `_backfill_raw_events` ingest time. Consequence: gemini/omp rows in `raw_events` are pre-normalized at rest; qwen rows are stored raw (minus `qwen_skip_at_ingest` drops) and re-normalized on every read.

**kimi-code has no normalizer and no `HostLayout` entry.** `_get_kimi_project_folder` (`user_messages.py:476-511`) resolves the workspace folder through `$KIMI_CODE_HOME/session_index.jsonl` (`workDir` → `sessionDir`, default home `~/.kimi-code`); the session logs are `session_*/agents/main/wire.jsonl` in kimi's typed-event schema (`docs/reference/HOST_COMPATIBILITY.md` `[^kimiwire]`; ENH-2918 shipped host-list plumbing only, not extraction). `host_layout_for("kimi-code")` falls through to the generic default (`session_glob="*.jsonl"`, `projects_root=None`), which never reaches `wire.jsonl`. That miss is currently load-bearing: `cli/backfill_worker.py:60` (directory arg → `path_arg.glob(layout.session_glob)`) and `cli/logs.py`'s `_has_ll_activity` (108) / `_extract_cwd_from_project` (145) / `_extract_ll_event_streams` (289) all glob `session_glob` against the folder `get_project_folder(host="kimi-code")` returns, and a kimi workspace folder holds only `session_*/` dirs, so `*.jsonl` matches nothing and no kimi bytes reach the Claude line loop. A `HostLayout` entry with `session_glob="session_*/agents/main/wire.jsonl"` would change that: the worker would ingest typed wire events into `raw_events` with `session_id` NULL (kimi records carry no `sessionId`; `lifecycle.py` line-path stamps `record.get("sessionId")`). `cli/session.py:672,711` are unaffected — they glob the literal `"*.jsonl"`.

**`host_layout_for` is not `home`-pure either.** It reads `Path.home()` once per call (`writers.py:2537`) to build `projects_root` for claude-code/opencode/pi/qwen. Any discovery or `list_workspaces` code that takes `layout.projects_root` therefore walks the *real* home regardless of a `home=tmp_path` override — a test-only leak that CI would not catch unless the runner's home has sessions. Only `sessions_subdir`/`session_glob` are safe to read off a layout under a `home` override.

**Per-host probes are not `home`-pure.** `_detect_claude_sessions` (`sessions.py:220-249`) reimplements a one-line path join to honour `home=`. The other probes cannot be reimplemented that cheaply: `_get_gemini_project_folder` (`user_messages.py:534-561`) reads `~/.gemini/projects.json` then falls back to `~/.gemini/tmp/<sha256(cwd)>`; `_get_omp_project_folder` (622-636) goes through `_omp_sessions_root()` (608-619, honours `XDG_DATA_HOME`/`PI_CONFIG_DIR`) **and** `encode_omp_session_dir` (564-606), which reads `Path.home()` internally to produce the home-relative encoding — so a `home=tmp_path` override that does not reach the encoder yields the wrong directory name; `_get_kimi_project_folder` reads `$KIMI_CODE_HOME`.

**Session-id location differs per host.** claude-code/opencode/pi/qwen: filename stem is the session id. gemini: files are `chats/session-*.jsonl`, id only in the line-1 header (`sessionId`). omp: files are `<ts>_<sessionId>.jsonl`, id only in the `type: "session"` record (which may follow a title-slot line; `normalize_omp_session` (`omp.py:54-86`) scans *every* line for the first `type: "session"` and never stops early). kimi: the file is always named `wire.jsonl`, so the stem is useless; the id is the `session_*` directory two levels up (`path.parents[2].name`), which is also what `session_index.jsonl` records as `sessionId` (`test_user_messages.py:203-206`: `"sessionId": "session_1"`, `"sessionDir": ".../session_1"`). `_backfill_raw_events` stamps `raw_events.session_id` from the header id for gemini/omp (`lifecycle.py:783`), so a stem-derived handle id would never join to history.db.

**`include_agents` has no reach on the non-Claude hosts.** Only claude-code's `session_glob` (`*.jsonl`) sees agent transcripts (`agent-*.jsonl` in the same dir). qwen's live under `subagents/<session-id>/` (not `chats/`), omp's under `<parent-stem>/<agentId>.jsonl` (`writers.py` omp branch comment), kimi's under `agents/<other>/` (the glob pins `agents/main/`), and gemini/opencode/pi have no known agent layout — so `include_agents=True` on those hosts returns exactly what `False` does.

**Malformed-input handling is *not* uniform.** `parse_codex_rollout`/`parse_claude_transcript`, `normalize_qwen_record`'s caller, and `normalize_omp_session` all skip a non-object JSON line (`isinstance(record, dict)` guard) and never raise; `normalize_gemini_session` (`gemini.py:60-76`) has no such guard — a JSON-array line 1 raises `AttributeError` on `.get("sessionId")`, and a non-dict `$set` raises on `.get("messages")`. `TestNonObjectJsonLines` (`test_session_discovery.py:511`) locks the seam rule.

Naming collision to keep straight: `writers.py::_iter_events` (3250, underscore, cursor/list-of-Path replay for `rebuild`) and `sessions.py::iter_events` (no underscore, `SessionHandle -> Iterator[SessionEvent]`) are unrelated.

## Expected Behavior

`detect_sessions(cwd, host)` returns handles for every host in `get_project_folder`'s vocabulary, and `detect_sessions(cwd)` (host `None`) unions all of them, newest first. `iter_events(handle)` yields `SessionEvent`s for each. The payload contract per host is:

- `claude-code`, `codex`, **`kimi-code`**: host-native record, unchanged (FEAT-3417's "refused on content" rule). kimi yields one `SessionEvent` per `wire.jsonl` line with `payload` = the raw typed event, `type` = its `type` field, `timestamp` = its timestamp field (whichever name kimi uses — confirm against a capture; `""` when absent). The Claude-schema content functions in `cli/logs.py`/`user_messages.py` will not match kimi events, exactly as they do not match codex events; a kimi content mapping is a follow-up, not this issue.
- `opencode`, `pi`: Claude-shaped on disk already (`host_layout_for` treats them with the generic Claude tail); parsed with the same per-line loop as `parse_claude_transcript` and stamped with their own `host`.
- `qwen`, `gemini`, `omp`: the record the host's existing normalizer produces — i.e. Claude-shaped. This is not a new cross-host abstraction: it is each host's *existing* contract (ENH-3166/ENH-3393/omp), lifted behind the seam so that ENH-3419's Claude-schema content functions in `cli/logs.py` keep recognizing qwen/gemini/omp activity exactly as they do today via `HostLayout.normalize`. `parse_qwen_session` does **not** apply `qwen_skip_at_ingest`: it is an ingest volume guard, and redundant on the read path anyway (`ui_telemetry` records are `type: "system"`, which `normalize_qwen_record` already drops).

The `sessions.py` module docstring's "refused on content" paragraph is amended to state this rule: *payload is host-native where no normalizer exists (claude-code, codex, kimi-code); where a host already ships a normalizer to Claude shape (qwen, gemini, omp), payload is that normalizer's output; opencode/pi are Claude-shaped on disk.*

`SessionHandle.session_id` is the host's real session id: filename stem for claude-code/opencode/pi/qwen (and codex via the DB / line-1 `payload.id`, unchanged); the header `sessionId` for gemini and the `type: "session"` record's `id` for omp (read at discovery time, as `_scan_rollout_tree` reads line 1 for codex; filename stem as fallback when the header is missing/malformed); for kimi, `path.parents[2].name` — the `session_*` directory, which is the `sessionId` `session_index.jsonl` records (confirmed, not a stem fallback). `updated_at` is `st_mtime` of the session file for every filesystem host.

`include_agents` is honoured wherever the host's session glob reaches agent transcripts — today only claude-code (`agent-*.jsonl`). On every other host it is a documented no-op (see § Current Behavior); the docstring says so, and ENH-3419 must not assume claude-code parity when it wires `--include-agents`-style behaviour.

`HostLayout` is **entirely untouched** in this phase — no kimi branch (it would go live in `backfill_worker`/`cli/logs.py` immediately, see § Current Behavior). Its normalizers are re-exported as the new `parse_*` functions' implementation, so both seams read the same code. The kimi wire glob lives in `sessions.py` as a module constant until ENH-3422 moves backfill onto `iter_events`, at which point a `HostLayout` kimi entry is safe because the worker no longer line-loops what the glob returns.

## Motivation

ENH-3419's acceptance criterion is that `ll-logs`, `ll-messages`, and `ll-ctx-stats` obtain sessions only via `detect_sessions`/`iter_events`. Today that would silently drop qwen/gemini/omp: `test_cli_ctx_stats.py::TestComputeCacheRateFromJsonl::test_resolves_qwen_chats_transcript` (909) and `test_resolves_gemini_chats_transcript` (941) set `LL_HOOK_HOST` and expect the per-host `sessions_subdir` to be honoured; `test_enh_3166_qwen_normalizer.py` (277-296) expects `discover_all_projects(host="qwen")` and `_has_ll_activity` to find qwen projects. Every new host otherwise has to be wired twice (once per seam) or ends up half-supported — the "silently covers one host while claiming to generalize" failure FEAT-3417 set out to fix, reproduced one layer down.

## Scope Boundaries

- **In scope**: adding `opencode`/`pi`/`kimi-code`/`qwen`/`gemini`/`omp` branches to `detect_sessions` (delegating to the existing `_get_<host>_project_folder` probes with a new `home` kwarg + `HostLayout.sessions_subdir`/`session_glob`, with the kimi glob supplied by a `sessions.py` constant — **no** `HostLayout` kimi entry, see § Current Behavior), `list_workspaces` branches for `opencode`/`pi` (walk `home / ".<cli>" / "projects"` — computed from `home`, never `host_layout_for(...).projects_root`), `gemini` (the `projects` keys of `home / ".gemini" / "projects.json"` are absolute cwds — trivial, do it), and `kimi-code` (distinct `workDir` from `session_index.jsonl` — cheap, do it), `parse_qwen_session`/`parse_gemini_session`/`parse_omp_session`/`parse_kimi_wire` registered in `_PARSERS`, the `isinstance(record, dict)` guard in `normalize_gemini_session`, the `sessions.py` docstring amendments (module + `SessionHandle` + `detect_sessions` + `_detect_claude_sessions`), `docs/reference/HOST_COMPATIBILITY.md:523`'s "readable via `detect_sessions()`" row flipped to ✓ for each added host, `docs/ARCHITECTURE.md` seam note.
- **`list_workspaces` for `qwen`/`omp`**: qwen shares the Claude walk if it is glob-parameterized (`projects_root=home/".qwen"/"projects"`, `session_glob="chats/*.jsonl"`); omp returns `[]` — its dir encoding (`encode_omp_session_dir`) is lossy (`/`, `\`, `:` all → `-`), and the `type: "session"` record's `cwd` would have to be read from every file to invert it. Matches `discover_all_projects`'s existing silent-`[]` precedent (`cli/logs.py:196-198`).
- **`home` threading into `user_messages.py`**: add a kw-only `home: Path | None = None` (default `Path.home()`) to `_get_claude_project_folder`, `_get_opencode_project_folder`, `_get_pi_project_folder`, `_get_qwen_project_folder`, `_get_gemini_project_folder`, `_get_omp_project_folder`, `_get_kimi_project_folder`, `_omp_sessions_root`, and `encode_omp_session_dir`. This is backward-compatible: the public `get_project_folder`/`get_sessions_folder` signatures and `Path | None` contract are unchanged. **Env precedence**: `home=` replaces `Path.home()` only; `XDG_DATA_HOME`, `PI_CONFIG_DIR`, and `KIMI_CODE_HOME` still win when set, matching production — tests `monkeypatch.delenv` them. `_detect_claude_sessions` may then drop its local reimplementation and call the probe too.
- **`LL_HOOK_HOST`**: `detect_sessions(host=None)` stays a pure union (FEAT-3417 decided). The env-var fallback belongs in the CLIs' host resolution (`args.host or os.environ.get("LL_HOOK_HOST")`, union only when neither is set) — that lives in ENH-3419, not here.
- **Out of scope**: ENH-3422 (backfill consuming `iter_events`, `HostLayout` shrink, the `backfill --host codex` notice, **and the `HostLayout` kimi entry** — safe only once the worker stops line-looping `session_glob` results); ENH-3419's CLI rewiring; Codex- or kimi-native equivalents of the Claude-schema content functions in `cli/logs.py`; a kimi normalizer to Claude shape; the `transcript_path`-driven raw readers (`hooks/session_start.py:150-161`, `cli/backfill_worker.py:52-53`, `hooks/pre_compact.py:108-120`, `hooks/scripts/context-monitor.sh`).

## Program Design

### Deviations

- **2026-09-09 (implementation)**: `_detect_layout_sessions` does not inline
  the per-host probe dispatch as the § Call Path sketch shows
  (`_detect_layout_sessions("qwen", ...) -> _get_qwen_project_folder(encoded,
  home=home) -> ...`). It instead delegates to a small new helper,
  `_project_folder_for_layout_host(host, cwd, home) -> Path | None`, which
  holds the `if host in (...)` dispatch to the seven per-host probes
  (`_get_opencode_project_folder`/`_get_pi_project_folder`/
  `_get_qwen_project_folder`/`_get_kimi_project_folder`/
  `_get_gemini_project_folder`/`_get_omp_project_folder`). Net call path is
  unchanged (`detect_sessions -> _detect_layout_sessions ->
  _project_folder_for_layout_host -> _get_<host>_project_folder(...,
  home=home)`); this only isolates the dispatch table so
  `_detect_layout_sessions` itself stays readable. `_list_claude_workspaces`
  matches the designed signature (`home, *, projects_root, session_glob`)
  with optional-with-defaults rather than required kwargs, which is
  behaviorally identical for every call site added here.

### Types

- `SessionHandle`, `SessionEvent` (`session_store/sessions.py:41-67`) — unchanged.
- `HostLayout` (`session_store/writers.py:2456`) — unchanged shape **and** unchanged `host_layout_for`; the kimi branch is ENH-3422's.
- `_KIMI_WIRE_GLOB = "session_*/agents/main/wire.jsonl"` (new module constant in `sessions.py`) — the only per-host path metadata the seam owns instead of reading off `HostLayout`.

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — existing; `_REGISTERED_HOSTS` (`sessions.py:252`) grows to the full `get_project_folder` vocabulary and the `if host ==` chain (281-285) gains one branch per host.
- `_detect_layout_sessions(host: str, cwd: Path, home: Path, limit: int | None, include_agents: bool) -> list[SessionHandle]` (new) — shared implementation for every non-codex host: `project = <probe>(…, home=home)` (the existing private `_get_<host>_project_folder`, now `home`-aware), join `host_layout_for(host).sessions_subdir`, glob `session_glob` (`_KIMI_WIRE_GLOB` for kimi), `is_agent = name.startswith("agent-")`, `session_id` per the § Expected Behavior rule — stem for claude-code/opencode/pi/qwen; `_header_session_id(host, path)` for gemini/omp with stem fallback; `path.parents[2].name` for kimi (no stem fallback: the stem is always `wire`); `updated_at = st_mtime`. Reads **only** `sessions_subdir`/`session_glob` off the layout — never `projects_root`, which is built from the real `Path.home()`.
- `_header_session_id(host: str, path: Path) -> str | None` (new) — gemini: line 1's `sessionId`. omp: scan lines until the first `type: "session"` record, **stopping at the first `type: "message"`** (bounded — the header, when present, precedes every message; `normalize_omp_session` scans to EOF because it is already reading the whole file, but discovery over N sessions must not). Both apply the `isinstance(record, dict)` guard and return `None` on OSError/JSONDecodeError/missing key.
- `_get_<host>_project_folder(…, *, home: Path | None = None)`, `_omp_sessions_root(*, home: Path | None = None)`, `encode_omp_session_dir(cwd: Path, *, home: Path | None = None)` (`user_messages.py`) — existing, gain the defaulted kwarg; behaviour with `home=None` byte-identical.
- `parse_qwen_session(path: Path) -> Iterator[SessionEvent]` (new) — per-line loop (`isinstance(record, dict)` guard) over `normalize_qwen_record`, dropping `None`; the shape `writers._iter_events` already uses. No `skip_at_ingest`.
- `parse_gemini_session(path) -> Iterator[SessionEvent]` / `parse_omp_session(path) -> Iterator[SessionEvent]` (new) — wrap the already-generator-shaped `normalize_gemini_session` (`gemini.py:40`) / `normalize_omp_session` (`omp.py:54`), stamping `host`; `type`/`timestamp` from the normalized record's own `type`/`timestamp` keys (the same keys `_backfill_raw_events` reads at `lifecycle.py:781,786`).
- `parse_kimi_wire(path) -> Iterator[SessionEvent]` (new) — per-line raw passthrough of `wire.jsonl` with the same guards as `parse_codex_rollout`; `payload` = whole record.
- `parse_claude_transcript` — gains an internal `host: str = "claude-code"` parameter (or a `_parse_claude_shaped(path, host)` helper) so opencode/pi handles are stamped with their own host; the public one-arg call is unchanged.

### Call Path

`detect_sessions(cwd, "qwen", home=...)` -> `_detect_layout_sessions("qwen", ...)` -> `_get_qwen_project_folder(encoded, home=home)` -> `SessionHandle(host="qwen", ...)` -> `iter_events(handle)` -> `_PARSERS["qwen"]` = `parse_qwen_session(handle.path)` -> `normalize_qwen_record(record)` per line -> `SessionEvent(host="qwen", payload=<Claude-shaped>)`

`detect_sessions(cwd, "omp", home=...)` -> `_get_omp_project_folder(cwd, home=home)` -> `_omp_sessions_root(home=home) / encode_omp_session_dir(cwd, home=home)` -> handles with `session_id` from the `type: "session"` record -> `parse_omp_session` -> `normalize_omp_session`.

## Proposed Solution

1. Thread `home` into the `user_messages.py` private probes (§ Scope Boundaries). Existing tests that patch `pathlib.Path.home` keep passing because the default still resolves to `Path.home()` at call time.
2. Add `_KIMI_WIRE_GLOB` to `sessions.py`. Do **not** add a `kimi-code` branch to `host_layout_for`: `backfill_worker.py:60` and `cli/logs.py:108,145,289` would start line-looping `wire.jsonl` the moment the glob is registered there (§ Current Behavior). ENH-3422 adds the entry once backfill reads through `iter_events`.
3. Extend `_REGISTERED_HOSTS` and the `detect_sessions` chain with one branch per host, all delegating to `_detect_layout_sessions`. Dispatch on a bare host string already appears three ways in this codebase (`host_layout_for`'s `if`/`elif` chain, `get_project_folder`'s named `_get_<host>_project_folder` functions, `sessions.py`'s `_PARSERS` dict); extend the two idioms `sessions.py` already uses rather than introducing a fourth.
4. Add the four `parse_*` generators next to `parse_codex_rollout`/`parse_claude_transcript`; register them plus opencode/pi in `_PARSERS`; export them from `session_store/__init__.py` with the eager-import + `__all__` pattern the existing normalizers use (`__init__.py:78,102,111`, `__all__` 241-243, 269-272). Do not rename the `normalize_*` functions in this phase; the `parse_*` functions call them.
5. Add the `isinstance(record, dict)` guard to `normalize_gemini_session` (line 1 and the `$set` branch) so the wrapped parser honours the seam's never-raise rule.
6. Amend the `sessions.py` docstrings. Four go stale, not one: the module docstring's "refused on content" paragraph (10-18, per § Expected Behavior) **and** its "distinct from `get_project_folder`… cannot be reused here without dropping the override" paragraph (20-25 — false once `home` is threaded; replace with "the private probes accept `home=`"); `SessionHandle`'s "a Codex rollout, or a Claude Code `<uuid>.jsonl`" (43); `_detect_claude_sessions`'s "computed locally rather than via `get_project_folder`" rationale (223-228, delete if it now delegates to the probe); and `detect_sessions`'s docstring gains the `include_agents` no-op rule.
7. `list_workspaces`: parameterize `_list_claude_workspaces(home, *, projects_root: Path, session_glob: str)` — the root is `home / ".<cli>" / "projects"` computed **from `home`**, never `host_layout_for(...).projects_root` (real-home leak, § Current Behavior) — to serve `opencode`/`pi` and `qwen` (`chats/*.jsonl`); add `_list_gemini_workspaces` (`json.loads(home/".gemini"/"projects.json")["projects"].keys()`, tolerant of a missing/malformed file → `[]`); add `_list_kimi_workspaces` (distinct `workDir` from `$KIMI_CODE_HOME`-or-`home/".kimi-code"` `session_index.jsonl`); `omp` returns `[]` (lossy encoding), matching `discover_all_projects`'s silent-`[]` precedent (`cli/logs.py:196-198`).
8. Docs.

**Hand-off note for ENH-3422**: once `_backfill_raw_events` consumes `iter_events`, qwen rows arrive already normalized (this issue's payload rule), so ENH-3422's "normalize at the write boundary" is already satisfied by the parser. Two consequences ENH-3422 must handle: (a) qwen rows at rest change from raw to pre-normalized, and (b) `normalize_qwen_record` is **not idempotent** — a normalized record has `message.content`, not `message.parts`, so re-normalizing it returns `None` and `writers._iter_events` (3250) would silently drop every qwen row on cursor replay. `_iter_events` must stop re-normalizing in the same change.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/sessions.py` — `_REGISTERED_HOSTS` (252), `detect_sessions` chain (281-285), `_PARSERS` (466), `list_workspaces` (288-309), `_list_claude_workspaces` (312), docstrings (module 10-25, `SessionHandle` 43, `_detect_claude_sessions` 223-228, `detect_sessions` 263-271); new `_KIMI_WIRE_GLOB`, `_detect_layout_sessions`, `_header_session_id`, `_list_gemini_workspaces`, `_list_kimi_workspaces`, four `parse_*`
- `scripts/little_loops/user_messages.py` — `home` kwarg on the seven `_get_<host>_project_folder` probes, `_omp_sessions_root` (608), `encode_omp_session_dir` (564); public `get_project_folder`/`get_sessions_folder` unchanged
- `scripts/little_loops/session_store/gemini.py` — `isinstance` guard in `normalize_gemini_session` (60-76)
- `scripts/little_loops/session_store/__init__.py` — export the new `parse_*` names (eager import + `__all__`)
- `docs/reference/HOST_COMPATIBILITY.md:523` (detect_sessions row; `[^kimiwire]` gains "discoverable via `detect_sessions`, host-native events"), `docs/ARCHITECTURE.md` (seam note: one seam, discovery half here, ingest half ENH-3422), `docs/reference/API.md:9497` (session-discovery entry added by f9768d61a — payload rule, per-host `session_id` rule, `home` kwarg on the probes)

### Dependent Files (must not change)
- `session_store/writers.py` `HostLayout` dataclass (2456-2511), **`host_layout_for` (2527 — no kimi branch this phase)**, `_iter_events` (3250), `_backfill_subagent_runs` (2670) — read-only this phase; ENH-3422 retargets them.
- `cli/backfill_worker.py:60`, `cli/logs.py:108,145,289` — the `session_glob` consumers whose behaviour a kimi `HostLayout` entry would change; untouched and unchanged in behaviour.
- `session_store/lifecycle.py::_backfill_raw_events` (747) — ENH-3422.
- `cli/logs.py` `_has_ll_activity` (97), `_extract_cwd_from_project` (134), `_extract_ll_event_streams` (261) — ENH-3419 rewires the call sites; the `HostLayout` parameter goes in ENH-3422.
- `user_messages.py` `get_project_folder` (373) and `get_sessions_folder` (422) — public contract locked by `session_log.py:159-212`, `fsm/continuity.py:43`, `cli/session.py:664,702,718` and their tests. Only the private probes gain a defaulted kwarg.
- `session_store/qwen.py`, `omp.py` — normalizer bodies unchanged; only wrapped.

### Tests
- `scripts/tests/test_session_discovery.py` — add a per-host class mirroring `TestDetectSessionsCodexSqlitePath`/`TestIterEventsDispatch` for each new host, using `home=tmp_path` (never the real home) plus `monkeypatch.delenv` for `XDG_DATA_HOME`/`PI_CONFIG_DIR`/`KIMI_CODE_HOME`, and the committed fixtures under `scripts/tests/fixtures/{qwen,gemini,omp}/` that the three normalizer test files already use (`FIXTURES = Path(__file__).parent / "fixtures" / "<host>"`). Assert `iter_events` on a qwen handle yields the same records `normalize_qwen_record` yields per line, and on a gemini/omp handle the same records `normalize_*_session` yields. Assert gemini/omp `session_id` equals the fixture header id (`11111111-2222-3333-4444-555555555555` in both), not the stem. Extend `TestNonObjectJsonLines` to gemini (array line 1, non-dict `$set`) and kimi. kimi: a hand-built `session_index.jsonl` + `sessions/wd_x/session_1/agents/main/wire.jsonl` with two typed events under `tmp_path`.
- omp `home` test: a cwd **under** `tmp_path` must resolve to the home-relative `-<rel>` encoding computed against `tmp_path`, proving `encode_omp_session_dir(home=...)` is honoured (this is the case a naive reimplementation gets wrong).
- `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py`, `test_ll_session.py`, `test_user_messages.py`, `test_session_log.py`, `test_fsm_continuity.py` — must pass unmodified (the probes' default path is byte-identical).
- Add a union test: a `tmp_path` home with one claude-code, one codex, one qwen, and one omp session for the same cwd → `detect_sessions(cwd, home=tmp_path)` returns four handles newest-first with distinct `host` values.
- kimi id test: the handle's `session_id` equals the `session_*` dir name (and the fixture's `session_index.jsonl` `sessionId`), not `"wire"`.
- `include_agents` no-op test: on a qwen tree with `chats/<id>.jsonl` **and** `subagents/<id>/agent.jsonl`, `detect_sessions(cwd, "qwen", include_agents=True, home=tmp_path)` equals the `False` result.
- omp bounded-scan test: a file with `type: "message"` lines and **no** `type: "session"` record yields a stem-fallback id, and `_header_session_id` returns after the first message line (assert via a line-counting wrapper or a file whose later lines are non-JSON garbage that would raise nothing but must not be read — simplest: patch `Path.open` to a counting reader).
- `home`-leak guard: `list_workspaces("opencode", home=tmp_path)` with an empty `tmp_path` returns `[]` even when `monkeypatch.setattr(Path, "home", lambda: <dir with sessions>)` — proves the walk never reads `host_layout_for(...).projects_root`.
- Regression guard for the deferred kimi `HostLayout` entry: `host_layout_for("kimi-code").session_glob == "*.jsonl"` and `backfill_worker` on a kimi workspace dir ingests 0 rows — locks the behaviour ENH-3422 will deliberately change.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:523` — flip the "readable via `detect_sessions`" cells; `:582,599,616` already discuss `HostLayout.normalize_file` — extend, do not duplicate; note the per-host payload rule (host-native for codex/kimi) beside `[^kimiwire]`.
- `docs/ARCHITECTURE.md` — precedent for documenting two mechanisms in one subsystem exists ("SDK/Batches Dispatch Path" 881, "Host Adapter Capability Map" 1317); write the note in that style, stating discovery/reading = `sessions.py`, ingest-to-history.db = `HostLayout` until ENH-3422.

## Implementation Steps

1. Confirm FEAT-3417 is `done` (it is; frontmatter flipped in the 2026-09-09 close-out) and `python -m pytest scripts/tests/test_session_discovery.py` is green.
2. `home` kwarg on the `user_messages.py` probes + `_omp_sessions_root` + `encode_omp_session_dir`; run the locked test files to prove the default path is unchanged.
3. `_KIMI_WIRE_GLOB` constant in `sessions.py` (no `host_layout_for` change) + the `host_layout_for("kimi-code")`/`backfill_worker` regression guard.
4. `_detect_layout_sessions` + `_header_session_id` (bounded omp scan) + six `detect_sessions` branches + `_REGISTERED_HOSTS`; per-host discovery tests including the omp home-relative case, the gemini/omp header-id assertions, the kimi `parents[2]` id, and the `include_agents` no-op.
5. gemini `isinstance` guard; `parse_qwen_session` (per-line loop), `parse_gemini_session`/`parse_omp_session` (wrap), `parse_kimi_wire` (raw), opencode/pi via the Claude-shaped loop with host stamp; register in `_PARSERS`; export; per-host `iter_events` tests + `TestNonObjectJsonLines` extensions.
6. `list_workspaces` branches for `opencode`/`pi`/`qwen` (glob-parameterized Claude walk rooted at `home`), `gemini` (`projects.json` keys), `kimi-code` (`session_index.jsonl` `workDir`s); `home`-leak guard test.
7. The four docstring amendments; docs; run the locked test files unmodified.

## Impact

- **Priority**: P2 — raised from P3 on 2026-09-09 because ENH-3419 (P2, user-visible) is blocked on it.
- **Effort**: Medium — additive on the seam side; the `home` threading touches nine private functions in `user_messages.py` with defaulted kwargs (no behaviour change on the default path).
- **Risk**: Low — nothing in production consumes the new `sessions.py` branches until ENH-3419; the normalizers are wrapped, not modified (one defensive guard added to gemini); probe defaults are byte-identical. This holds **only because** `host_layout_for` is untouched: a kimi `HostLayout` entry would go live in `backfill_worker`/`cli/logs.py` at once (§ Current Behavior), which is why it is deferred to ENH-3422.
- **Breaking Change**: No.

## Acceptance Criteria

- `detect_sessions(cwd, h, home=tmp_path)` returns handles for every `h` in `get_project_folder`'s vocabulary (`claude-code`, `codex`, `opencode`, `pi`, `kimi-code`, `qwen`, `gemini`, `omp`) given a matching fixture tree under `tmp_path`; `detect_sessions(cwd, home=tmp_path)` unions them newest-first.
- For a cwd under `tmp_path`, `detect_sessions(cwd, "omp", home=tmp_path)` finds the session dir named by omp's home-relative encoding computed against `tmp_path` (no `Path.home` patching).
- `SessionHandle.session_id` on a gemini/omp handle equals the header/`session`-record id, not the filename stem; on a kimi handle it equals the `session_*` directory name, never `"wire"`.
- `_header_session_id` on an omp file stops reading at the first `type: "message"` line.
- `detect_sessions(cwd, h, include_agents=True, home=tmp_path)` equals the `include_agents=False` result for every `h` other than `claude-code`, and the `detect_sessions` docstring says so.
- `host_layout_for` is byte-identical (`host_layout_for("kimi-code").session_glob == "*.jsonl"`); `backfill_worker` on a kimi workspace dir still ingests 0 rows.
- `list_workspaces(h, home=tmp_path)` for `opencode`/`pi`/`qwen`/`gemini`/`kimi-code` never reads the real home (the `home`-leak guard test passes); `gemini` returns the `projects.json` keys.
- `iter_events` on a qwen/gemini/omp handle yields `SessionEvent`s whose `payload` equals the host's existing normalizer output for the same file, with `host` stamped; on opencode/pi it yields the raw Claude-shaped record with `host` stamped; on kimi-code it yields the raw `wire.jsonl` events.
- `iter_events` never raises on a gemini/kimi file containing non-object JSON lines.
- `sessions.py`'s docstring states the per-host payload rule (host-native vs. existing-normalizer output vs. Claude-shaped-on-disk).
- `get_project_folder`/`get_sessions_folder` signatures unchanged; `test_enh_3166_qwen_normalizer.py`, `test_enh_3393_gemini_normalizer.py`, `test_enh_omp_normalizer.py`, `test_enh_2505_subagent_runs.py`, `test_ll_session.py`, `test_user_messages.py`, `test_session_log.py`, `test_fsm_continuity.py` pass unmodified.
- `docs/reference/HOST_COMPATIBILITY.md:523` row, `[^kimiwire]`, `docs/reference/API.md` session-discovery entry, and a `docs/ARCHITECTURE.md` seam note are updated.

## Related Key Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — per-host session-log table (row 523), `[^kimiwire]` (549)
- `docs/reference/API.md` — `little_loops.session_store.sessions` entry (9497)

## Resolution

Implemented per § Proposed Solution / § Program Design:

- `home: Path | None = None` threaded into the seven `user_messages.py`
  private probes (`_get_claude_project_folder`, `_get_opencode_project_folder`,
  `_get_pi_project_folder`, `_get_qwen_project_folder`,
  `_get_kimi_project_folder`, `_get_gemini_project_folder`,
  `_get_omp_project_folder`) plus `_omp_sessions_root`/`encode_omp_session_dir`,
  each defaulting to `Path.home()` at call time (byte-identical default path).
- `sessions.py`: `_REGISTERED_HOSTS` grew to all 8 hosts; `_KIMI_WIRE_GLOB`
  module constant (no `HostLayout` kimi branch — deferred to ENH-3422);
  `_detect_layout_sessions`/`_project_folder_for_layout_host`/
  `_header_session_id` added; `detect_sessions` gained the six new branches;
  `_detect_claude_sessions` now delegates to `_get_claude_project_folder`
  instead of reimplementing the join.
- Four new parsers (`parse_qwen_session`, `parse_gemini_session`,
  `parse_omp_session`, `parse_kimi_wire`) plus `parse_opencode_transcript`/
  `parse_pi_transcript` via a shared `_parse_claude_shaped` helper; all
  registered in `_PARSERS` and exported from `session_store/__init__.py`.
- `isinstance(record, dict)` guard added to `normalize_gemini_session` (line-1
  header and the `$set` value).
- `list_workspaces` gained `opencode`/`pi`/`qwen` (parameterized
  `_list_claude_workspaces`), `gemini` (`projects.json` keys), and
  `kimi-code` (`session_index.jsonl` `workDir`s) branches; `omp` stays `[]`.
  Every root is computed from `home` directly, never
  `host_layout_for(...).projects_root` (real-home leak guard).
- Docstrings amended (module, `SessionHandle`, `_detect_claude_sessions`,
  `detect_sessions`); `docs/reference/HOST_COMPATIBILITY.md`,
  `docs/ARCHITECTURE.md` (new § Session-Discovery Seam), and
  `docs/reference/API.md` updated.
- One minor deviation from the § Call Path sketch (dispatch factored into
  `_project_folder_for_layout_host`, net call path unchanged) — logged under
  § Program Design → Deviations.

**Tests**: 62 new/extended tests added to `test_session_discovery.py`
covering per-host discovery, `session_id` derivation, `include_agents`
no-op, `iter_events` payload equivalence with the existing normalizers, the
omp bounded-scan and home-relative-encoding cases, the `home`-leak guard,
the kimi `host_layout_for`/glob regression guard, and a 4-host union test.
Full suite: `python -m pytest scripts/tests/` — 23686 passed (verified
against unmodified `main` via `git stash`: the 4 pre-existing failures
(`test_host_runner`, `test_issue_parser` priority-regex allowlist ×2,
`test_verify_evidence` repo gate) and 1 flaky SSE-bridge socket-timeout test
are unrelated to this change and reproduce/pass identically without it).
`ruff check` and `python -m mypy scripts/little_loops/` both clean.

## Status

**Open** | Created: 2026-09-09 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-09-09T20:03:58 - `81a269cd-db9f-4d79-812a-51953a79e174.jsonl`
- `/ll:ready-issue` - 2026-09-09T19:41:47 - `ed3828ec-69b8-4fcb-985e-b313632d6d32.jsonl`
- `/ll:confidence-check` - 2026-09-09T19:34:17 - `a47061f4-4334-4417-ab2e-b65d6a25ae3b.jsonl`
- `review (manual, pre-implementation #3: kimi HostLayout entry deferred to ENH-3422 — backfill_worker.py:60 / cli/logs.py:108,145,289 would line-loop wire.jsonl immediately; list_workspaces roots from home not host_layout_for(...).projects_root (real-home leak); kimi session_id = path.parents[2].name (confirmed vs session_index sessionId); include_agents no-op on non-Claude hosts; bounded omp header scan; gemini list_workspaces via projects.json; four stale docstrings not one; matching tests + ACs)` - 2026-09-09T21:00:00
- `/ll:confidence-check` - 2026-09-09T19:25:52 - `97e52889-4a57-4cad-8e44-59fca7caca21.jsonl`
- `/ll:verify-issues` - 2026-09-09T19:22:12 - `ebf18a6f-ed36-4252-9599-87c271309793.jsonl`
- `review (manual, pre-implementation: kimi is host-native not Claude-shaped — passthrough parser + HostLayout glob; home threaded into user_messages probes instead of reimplemented (omp encoder reads Path.home); gemini/omp session_id from header; gemini isinstance guard; parse_qwen_session skips no skip_at_ingest; ENH-3422 non-idempotent-normalize hand-off; line anchors refreshed)` - 2026-09-09T20:30:00
- `review (manual: FEAT-3417 landed — dropped stale "spike only" findings; decided unify; split ingest half to ENH-3422; flipped dependency so this blocks ENH-3419; P3→P2; per-host payload rule)` - 2026-09-09T19:10:00
- `/ll:confidence-check` - 2026-09-09T15:01:22 - `a4ac4148-e562-4d02-a9a9-889fd2f8dc3f.jsonl`
- `/ll:wire-issue` - 2026-09-09T14:51:25 - `8e56ec89-cd99-46e0-b932-f07e5ea9315c.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T14:15:24 - `aea90797-734c-47d9-89ed-e343ebbf4673.jsonl`
- `/ll:refine-issue` - 2026-09-09T14:08:38 - `1658f0c5-d510-42b4-beb1-234626dbd6e5.jsonl`
- `/ll:format-issue` - 2026-09-09T13:22:54 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
