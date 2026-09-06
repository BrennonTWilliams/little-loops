---
id: ENH-3393
type: ENH
title: history.db backfill has no host coverage for gemini and omp (oh-my-pi)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-06'
captured_at: '2026-09-06T01:54:32Z'
confidence_score: 98
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 23
score_ambiguity: 17
score_change_surface: 17
---

# ENH-3393: history.db backfill has no host coverage for gemini and omp (oh-my-pi)

## Summary

`ll-session backfill` — the transcript-ingestion tier of `.ll/history.db` — has no
code path for the `gemini` and `omp` (oh-my-pi) hosts, even though `host_runner.py`
treats both as fully wired, production orchestration hosts (`GeminiRunner`,
`OmpRunner` in `_HOST_RUNNER_REGISTRY`, not stubs like `opencode`/`pi`). Live-hook
capture and transcript backfill are separate tiers with separate host coverage;
this issue is about the backfill tier only.

## Current Behavior

- `scripts/little_loops/cli/session.py:213` — `ll-session backfill --host` choices
  are hardcoded to `["claude-code", "codex", "opencode", "pi", "kimi-code", "qwen"]`.
  `gemini` and `omp` are not accepted values.
- `scripts/little_loops/user_messages.py` (`get_project_folder()`, ~399-411)
  branches per host for those same six hosts and falls through to `return None`
  for any other host string, so there is no project-folder discovery for
  `gemini`/`omp`.
- `scripts/little_loops/session_store/writers.py` (`host_layout_for()`,
  ~2206-2250) special-cases `qwen` and otherwise looks up `projects_root` from a
  dict covering `claude-code`/`codex`/`opencode`/`pi` (kimi-code is
  index-resolved and intentionally absent); `gemini`/`omp` fall into the generic
  Claude-shaped default with `projects_root=None` and no normalizer.
- `docs/reference/HOST_COMPATIBILITY.md`'s session-store / history.db support
  table (~line 513, 520) lists columns for Claude Code, OpenCode, Codex CLI, Kimi
  Code, and Qwen Code only — `gemini` and `omp` aren't represented as columns, so
  the gap is currently undocumented rather than merely unimplemented.

Net effect: `gemini` and `omp` sessions can never be recovered via
`ll-session backfill --host gemini|omp`. Their only path into `.ll/history.db` is
live hooks, which are themselves partial for `omp` (only `session_start` +
`post_tool_use` wired per FEAT-2261; everything else deferred) and, for `gemini`,
full but backfill-only-recoverable-never (a dropped/interrupted live session has
no repair path).

## Expected Behavior

`ll-session backfill --host gemini` and `--host omp` walk each host's actual
on-disk session-transcript layout and populate `sessions`/`tool_events`/
`raw_events` (and `subagent_runs` where transcripts expose subagent spawns),
matching the pattern established for `codex`/`pi` (ENH-1945) and `qwen`
(ENH-3165/ENH-3166). `docs/reference/HOST_COMPATIBILITY.md`'s session-store table
gains `gemini`/`omp` columns reflecting the new support.

## Motivation

`gemini` and `omp` are production orchestration hosts today (loops, sprints, and
subagents can run under them via `host_runner.py`), but their history is
permanently unrecoverable once a live-hook gap or a pre-`ll-init` session occurs.
Every other wired host got a dedicated backfill ticket when this gap was found
(ENH-1945 for codex/pi, ENH-3165/3166 for qwen); nothing tracks it for gemini/omp,
so the coverage matrix silently drifts further from the orchestration layer's
actual host list as `omp`/`gemini` usage grows.

## Proposed Solution

Follow the ENH-3165/ENH-3166 precedent (one `HostLayout` entry in
`host_layout_for()` plus a per-host normalizer module under
`session_store/`), but note that **neither host is Claude-shaped or
qwen-shaped** — the on-disk layouts were verified on 2026-09-06 against
gemini-cli 0.46.0 (installed, real transcripts under `~/.gemini/tmp/`) and the
omp 18.0.11 source vendored at
`scripts/little_loops/hooks/adapters/omp/node_modules/@oh-my-pi/pi-coding-agent/src/session/`.
See "Verified Host Layouts" under Program Design. Three consequences drive the
design:

1. **Project-folder discovery is index/derived, not dash-encoded**, for both
   hosts — the new `get_project_folder()` helpers take `cwd: Path` (kimi-shaped),
   not `encoded_path: str`.
2. **Both record formats need a normalizer module** (`session_store/gemini.py`,
   `session_store/omp.py`) — the qwen normalizer is not reusable even though
   qwen forked gemini-cli; qwen moved to Claude-like records, gemini did not.
3. **The session id lives only in the file header (or filename), not on each
   record**, so the existing stateless per-record `HostLayout.normalize`
   contract cannot stamp `raw_events.session_id`. `HostLayout` must grow a
   file-level hook (e.g. `normalize_file: Callable[[Path], Iterator[dict]]` that
   carries header state) or a `session_id_from: "record" | "header" | "filename"`
   discriminator — decide this first; two more `elif` branches will not work.

Wire the new host names into `ll-session backfill --host` choices and
`get_project_folder()`'s host branch. Use the real gemini captures at
`~/.gemini/tmp/srs-ai-automation/chats/` (sanitized) as fixtures; omp has no
sessions on disk on the dev machine (binary not on PATH, `~/.omp/agent/sessions`
absent), so build omp fixtures from the vendored `session-entries.ts` types.

## Program Design

### Signatures

- `_get_gemini_project_folder(cwd: Path) -> Path | None` — new branch in `get_project_folder()`, mirrors `_get_kimi_project_folder` (index-resolved, **not** `_get_codex_project_folder`); reads `~/.gemini/projects.json` (`{"projects": {"<abs cwd>": "<slug>"}}`) and returns `~/.gemini/tmp/<slug>` when it exists, falling back to `~/.gemini/tmp/<sha256(cwd)>` for sessions written before the slug registry.
- `_get_omp_project_folder(cwd: Path) -> Path | None` — new branch in `get_project_folder()`; returns `<sessions_root>/<omp-encoded cwd>` where `sessions_root` is `$XDG_DATA_HOME/omp/sessions` if set else `~/<PI_CONFIG_DIR or .omp>/agent/sessions`, probing the current encoding first and then the two legacy encodings (see Verified Host Layouts).
- `encode_omp_session_dir(cwd: Path) -> str` — omp's cwd encoding (home-relative `-<rel>`, tmp-relative `-tmp-<rel>`, else `--<abs>--`, with `/\:` → `-` and dots preserved). Separate from `encode_project_path`, which is Claude's every-non-alnum scheme and would mangle `.worktrees`. Written so a future pi fix can reuse it.
- `normalize_gemini_session(path: Path) -> Iterator[dict]` (`session_store/gemini.py`) — file-level normalizer: reads the header line for `sessionId`, applies `$set`/`$rewindTo` records, unpacks the initial `$set.messages` array, and yields Claude-shaped `user`/`assistant` records with `sessionId`/`timestamp` stamped and inline `toolCalls[]` split into `tool_use`/`tool_result` content blocks.
- `normalize_omp_session(path: Path) -> Iterator[dict]` (`session_store/omp.py`) — file-level normalizer: reads the `{type:"session", id, cwd, parentSession?}` header, yields Claude-shaped records from `{type:"message", message:{role, content}}` entries, drops `model_change`/`thinking_level_change`/`compaction` entries (or routes them to `skip_at_ingest`).
- `HostLayout` — new field(s) to carry the above: `normalize_file: Callable[[Path], Iterator[dict]] | None = None` (preferred) or `session_id_from: str = "record"`. The exact shape is the first decision of the implementation; `_backfill_raw_events` (`lifecycle.py:747`) and `_backfill_sessions` (`lifecycle.py:707-732`, reads `record.get("sessionId")`) must both consult it.

### Call Path

`ll-session backfill --host gemini|omp` -> `get_project_folder` -> `_get_gemini_project_folder`/`_get_omp_project_folder` (new, `cwd`-based) -> `host_layout_for` -> `HostLayout` (with file-level normalizer) -> `backfill` -> `_backfill_raw_events` (uses `normalize_file` to stamp `session_id`) -> `rebuild` extractors -> `_backfill_subagent_runs` (omp only, if child-session dirs are mapped)

### Verified Host Layouts

_Verified 2026-09-06 against gemini-cli 0.46.0 (installed) and omp 18.0.11 (vendored source). Supersedes the "unconfirmed" language elsewhere in this issue._

**Gemini** (`~/.gemini/`):
- Project folder: `~/.gemini/tmp/<project-id>/`. `<project-id>` is a human slug registered in `~/.gemini/projects.json` (bundle `Storage.initialize` → `ProjectRegistry.getShortId`); dirs created before the registry are keyed by `sha256(abs cwd)` hex (the same value stored as `projectHash` in every session header). `~/.gemini/tmp/` also contains `bin/` — `discover_all_projects` must filter to dirs that contain `chats/`.
- Sessions: `chats/session-<YYYY-MM-DDTHH-MM>-<8-char id>.jsonl` (bundle `listProjectChatFiles`). Pre-Oct-2025 sessions are single-document `chats/session-*.json` (whole `messages[]` array) — **decide in/out of scope explicitly**; the JSONL reader must at minimum skip them without error.
- Record format (JSONL): line 1 header `{sessionId, projectHash, startTime, lastUpdated, kind: "main"}`; then message records `{id, timestamp, type: "user" | "gemini", content: [{text}], thoughts?, tokens?, model?, toolCalls?: [{id, name, args, result, resultDisplay, status, timestamp, ...}]}`; `{"$set": {...}}` metadata patches (the **first** `$set` carries the initial `messages[]` including the session-context user turn); `{"$rewindTo": "<message id>"}` rewind markers. Reader helpers in the bundle: `isPartialMetadataRecord` / `isMessageRecord` / `isMetadataUpdateRecord` / `isRewindRecord`. Messages carry **no `sessionId`** and tool calls + results are inline on the `gemini` message, not separate records.
- Other files: `logs.json` (flat user-prompt log per project, has `sessionId`+`message`), `<session-id>/plans/`, `checkpoints/`. No subagent transcript directory observed; `kind` values other than `"main"` are unverified.
- Live-hook tier: gemini hook payloads carry `transcript_path` (hooks/adapters/gemini/README.md:37), so `backfill_worker.py` gets a real path today — only the reader is missing.

**omp** (`~/.omp/`):
- Sessions root: `~/.omp/agent/sessions/` (`pi-utils/src/dirs.ts:872`, `getSessionsDir`); `PI_CONFIG_DIR` overrides `.omp`; `XDG_DATA_HOME` flattens to `$XDG_DATA_HOME/omp/sessions`. `~/.omp/agent/agent.db` (SQLite) holds auth/usage/settings only — **no session data**.
- Project folder encoding (`pi-coding-agent/src/session/session-paths.ts:40-90`): cwd under `$HOME` → `-<home-relative with /\: → ->` (e.g. `-AIProjects-brenentech-little-loops`; dots preserved); cwd under `os.tmpdir()` → `-tmp-<rel>`; other absolute → legacy `--<abs sans leading />--`. A transitional `<scope>-<basename>-<sha256hex>` form from omp 17.2.5–17.2.8 may also exist; omp migrates old `--<home>-…--` dirs to the new form on first access (`migrateHomeSessionDirs`).
- Session files: `<ts with :. → ->_<sessionId>.jsonl` (`session-manager.ts:1142`). Child/subagent sessions: `<parent stem>/<agentId>.jsonl` — a sibling dir named after the parent file minus `.jsonl` (`session-manager.ts:139-151`; also the artifacts dir). This matches neither `parent_from="parent_dir"` nor `"child_dir"`; a third mode (`"stem_dir"`) or a per-host callable is needed if `subagent_runs` is populated for omp.
- Record format (`session-entries.ts:28-80`): header `{type: "session", version?, id, title?, timestamp, cwd, additionalDirectories?, parentSession?}`; then `{type: "message", id, parentId, timestamp, message: {role, content}}` plus `thinking_level_change`, `model_change`, `compaction`, `custom` entries. Header key is `id` (not `sessionId`) and message entries carry no session id.
- omp itself ships readers for Claude and Codex session stores (`claude-session-store.ts`, `codex-session-store.ts`) — useful as a reference for the reverse mapping, not something to depend on.

**Existing code facts (unchanged from the original research):**
- `get_project_folder()` (`user_messages.py:370`) dispatches on a flat `if`/`elif host == ...` chain (`:399-410`) that returns `None` for any unmatched host; `gemini`/`omp` each need one new `elif` branch calling a new per-host helper rather than inlining logic into `get_project_folder` itself.
- `host_layout_for()` (`session_store/writers.py:2206`) special-cases `qwen` (nested `subagents/<session-id>/` with a `.meta.json` sidecar) before falling into a generic `projects_root` dict covering `claude-code`/`codex`/`opencode`/`pi` (`:2237-2242`). `gemini`/`omp` are a **third shape** (index/derived project dir + non-Claude records + header-only session id) and each need a dedicated branch; `projects_root` stays `None` for both (like kimi) unless `discover_all_projects` is taught to walk `~/.gemini/tmp` / `~/.omp/agent/sessions` with a filter.
- `backfill()` (`session_store/lifecycle.py:1022`) only calls `host_layout_for(host)` and walks `sessions_root` when both are non-`None`/a real directory (`:1080-1082`), so a `gemini`/`omp` host string with no matching `host_layout_for` branch degrades silently to the Claude-shaped default rather than erroring — the CLI-level `--host` choices gate (`cli/session.py:213`) is what actually prevents that today, not `backfill()` itself.
- The existing `pi` entries (`~/.pi/projects` in both `_get_pi_project_folder` and `host_layout_for`) are also wrong: real pi writes `~/.pi/agent/sessions/--<abs>--/` (observed on the dev machine, and omp's legacy encoding is pi's current one). Out of scope here, but `encode_omp_session_dir` and `_get_omp_project_folder` should be shaped so a follow-up pi fix is a one-line reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/session.py:213` — `backfill --host` choices
- `scripts/little_loops/user_messages.py` — `get_project_folder()` (~399-411),
  new host branches for `gemini`/`omp`
- `scripts/little_loops/session_store/writers.py` — `HostLayout` (~2145-2190):
  add the file-level normalizer / session-id-source field; `host_layout_for()`
  (~2206-2250): two new dedicated branches (not dict entries)
- `scripts/little_loops/session_store/gemini.py` (new) — gemini file-level
  normalizer (`$set`/`$rewindTo` handling, inline `toolCalls` split)
- `scripts/little_loops/session_store/omp.py` (new) — omp/pi-format file-level
  normalizer
- `scripts/little_loops/session_store/__init__.py` — export the new normalizers
  mirroring `normalize_qwen_record`/`qwen_skip_at_ingest`
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events()`
  (~747-800) must use the layout's file-level normalizer to stamp `session_id`;
  `_backfill_sessions()` (~707-732) must handle header-only ids (`id` for omp,
  `sessionId` on line 1 only for gemini); `backfill()` `sessions_root`
  resolution per host
- `scripts/little_loops/user_messages.py` — `discover_all_projects` (if it walks
  `projects_root`): gemini's `~/.gemini/tmp` must be filtered to dirs containing
  `chats/`
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table, add `gemini`/`omp`
  columns; also line 31 still says omp "Recognized, adapter pending" although
  EPIC-2258 is done — fix while there

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/queries.py` — consumers of the newly
  populated rows (session/tool-event queries, analytics)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/backfill_worker.py` — a **separate** ingestion path
  (invoked as a detached subprocess by `hooks/session_start.py`) that calls
  `host_layout_for()` and `backfill_incremental()`. It has no argparse
  `choices=` gate, so it is already host-agnostic — the live-hook auto-backfill
  tier is unblocked for `gemini`/`omp` mechanically today; only
  `get_project_folder`/`host_layout_for` returning `None`/generic-default
  blocks it functionally, matching the issue's stated "net effect" [Agent 1
  finding]
- `scripts/little_loops/session_store/lifecycle.py:1098` `backfill_incremental()`
  — distinct from `backfill()` (already in Files to Modify); threads `host`
  straight into `backfill_raw_events(..., host=host)` with no validation of its
  own — benefits automatically once `host_layout_for` is extended, no code
  change needed here but it must stay covered by tests [Agent 1 finding]
- `scripts/little_loops/session_log.py:15,174` — `get_sessions_folder(cwd)`
  caller, host resolved via `LL_HOOK_HOST` env default — host-agnostic [Agent 1
  finding]
- `scripts/little_loops/fsm/continuity.py:22,43` — same `get_sessions_folder`
  pattern [Agent 1 finding]
- `scripts/little_loops/cli/ctx_stats.py:34,355` — same `get_sessions_folder`
  pattern [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py:162,178-179` — builds `--host`
  argv for `backfill_worker.py` from `event.host or LL_HOOK_HOST`; confirmed
  this does **not** route through `cli/session.py`'s restrictive `--host`
  choices gate (`backfill_worker.py` has no argparse choices) [Agent 1
  finding]

### Similar Patterns
- ENH-1945 (`get_project_folder` host-aware discovery for codex/pi)
- ENH-3165 / ENH-3166 (qwen backfill + wire-format normalizer — the descriptor
  approach this issue should reuse rather than re-inventing)

### Tests
- `scripts/tests/test_user_messages.py` — `get_project_folder` cases for
  `gemini` (slug-registry hit, sha256 fallback, missing `projects.json` →
  `None`) and `omp` (home-relative, tmp-relative, legacy `--abs--`, and
  `PI_CONFIG_DIR`/`XDG_DATA_HOME` overrides); plus `encode_omp_session_dir`
  unit cases including a `.worktrees` path (dot must survive)
- `scripts/tests/test_enh_3393_gemini_normalizer.py` (new) and
  `scripts/tests/test_enh_3393_omp_normalizer.py` (new), mirroring
  `test_enh_3166_qwen_normalizer.py`,
  with committed fixtures at `scripts/tests/fixtures/gemini/` (sanitized from
  the real 0.46.0 captures; include a `$rewindTo` case and a legacy `.json`
  file that must be skipped) and `scripts/tests/fixtures/omp/` (synthesized
  from `session-entries.ts` types; include a child-session sibling dir)
- Both with and without the host CLI installed on the test machine
  (no-host-installed → `get_project_folder` returns `None`, backfill is a
  no-op, not an error)

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed: the qwen backfill/normalizer test module is
  `scripts/tests/test_enh_3166_qwen_normalizer.py`, fixtures at
  `scripts/tests/fixtures/qwen/{session,noise}.jsonl` — this is the file/dir to
  mirror, not a differently-named module [Agent 3 finding]
- `scripts/tests/test_enh_3166_qwen_normalizer.py` `TestHostLayoutRegistry`
  (196-247), specifically `test_registered_claude_shaped_hosts_get_projects_roots`
  (231-234) — `gemini`/`omp` are **not** Claude-shaped, so do not add them
  there; add dedicated tests mirroring
  `test_qwen_layout_widens_without_losing_enh_3165_fields` (197-219) and a
  `test_gemini_and_omp_have_no_static_projects_root` alongside the kimi one
  (246-247) [Agent 3 finding, corrected 2026-09-06]
- `scripts/tests/test_enh_3166_qwen_normalizer.py:539,557,603-604` —
  `worker_main([..., "--host", "qwen"])` and
  `TestSessionStartHookPassesHost::test_worker_argv_carries_host_and_project_root`
  — add `gemini`/`omp` cases [Agent 1 + 3 findings]
- `scripts/tests/test_session_log.py:385-450` — per-host cluster
  (`test_get_current_session_jsonl_auto_detects_codex`/`_qwen_chats`, etc.)
  exercising `session_log.py`'s `get_sessions_folder` — add `gemini`/`omp`
  analogues [Agent 1 finding]
- `scripts/tests/test_fsm_continuity.py:106`
  (`test_resolves_qwen_chats_transcript`) — add `gemini`/`omp` analogues for
  `fsm/continuity.py`'s `get_sessions_folder` call [Agent 1 finding]
- `scripts/tests/test_cli_ctx_stats.py:909`
  (`test_resolves_qwen_chats_transcript`) — add `gemini`/`omp` analogues for
  `cli/ctx_stats.py` [Agent 1 finding]
- `scripts/tests/test_enh_2505_subagent_runs.py:568-703` — repeated
  `host_layout_for("qwen")` calls feeding `_backfill_subagent_runs` — add an
  `omp` analogue if the `<parent stem>/<agentId>.jsonl` child-session layout
  is mapped into `subagent_runs`; gemini has no observed subagent transcript
  dir, so assert it yields zero rows rather than erroring [Agent 1 finding,
  corrected 2026-09-06]
- No test currently locks in the `ll-session backfill --host` choices list
  itself (confirmed: no argparse/`--help`-snapshot test exists) — write one so
  future host additions can't silently drift from docs [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table
- `docs/reference/API.md` — `ll-session backfill --host {…}` host list

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:3803-3818`, specifically line 3814 — `backfill` flags
  table's `--host HOST` row is already stale (lists only 4 of the current 6
  hosts, missing `kimi-code`/`qwen`); needs a full refresh to all 8 hosts, not
  just an append [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md:224-230` — "Incremental backfill"
  example commands show only `claude-code`/`codex`/`opencode`; add
  `kimi-code`/`qwen`/`gemini`/`omp` examples [Agent 2 finding]
- `docs/reference/API.md` — `get_project_folder` (~3426-3468),
  `get_sessions_folder`, `discover_all_projects` (~3548) sections describe host
  dispatch as "four-way" / list only 4 helpers — already stale for
  `kimi-code`/`qwen`; needs a full refresh including `gemini`/`omp`, not just
  two new bullets [Agent 2 finding]

### Configuration
- N/A

### Codebase Conventions

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis; the "which shape?" questions it raised are now answered in "Verified Host Layouts" above (both hosts are a third, non-Claude, non-qwen shape)._

- **Host dispatch is one `elif` branch + one private helper per host** — `get_project_folder()` (`scripts/little_loops/user_messages.py:399-411`) is a flat `if`/`elif` chain; the docstring (`:385-386`) states this explicitly: "Future hosts... add a new branch here rather than a new code path elsewhere." Claude-shaped helpers (`_get_codex_project_folder`, `_get_opencode_project_folder`, `_get_pi_project_folder`, lines 450-465) are one-liners building `Path.home() / "<host-dir>" / "projects" / encoded_path`; the model for gemini/omp is instead `_get_kimi_project_folder(cwd)` (`:470-520`, index-resolved, honors a `KIMI_CODE_HOME` override).
- **Two host shapes existed before this issue**: (a) flat-dict, no-normalizer hosts (claude-code/codex/opencode/pi) get one `projects_root` dict entry in `host_layout_for()` (`session_store/writers.py:2237-2242`) with no `sidecar_suffix`/`normalize`; (b) qwen gets a dedicated `if host == "qwen"` special case (`writers.py:2206-2236`) plus a normalizer module (`session_store/qwen.py`) and committed real-capture fixtures. gemini/omp follow (b) structurally but need the `HostLayout` contract extended (file-level normalizer / session-id source) because their session id is header-only.
- **`HostLayout` is the single descriptor type** (`writers.py:2145-2190`); its docstring (`:2150-2156`) says "One record per host — a second host table would drift from the first." New hosts plug into this type; extend it, don't add a sibling.
- **`get_project_folder` coverage and `host_layout_for` `projects_root` coverage are tracked independently**: `kimi-code` has a `get_project_folder` branch but no `projects_root` entry — confirmed by `test_kimi_code_has_no_static_projects_root` (`scripts/tests/test_enh_3166_qwen_normalizer.py:246-247`). gemini/omp will match kimi here (`projects_root=None`).
- **Test convention**: a positive-resolve test per host (`scripts/tests/test_user_messages.py:146-189` for codex/opencode/pi); a "returns None when no project dir exists" test exists for qwen (`:293-303`) and kimi-code (`:241-252`) — gemini/omp need both.
- **Fixture convention**: qwen is the only backfill host with committed real-capture fixtures (`scripts/tests/fixtures/qwen/session.jsonl`, `noise.jsonl`; module docstring: "sanitized captures from real qwen 0.21.6 output"). gemini follows this (real 0.46.0 captures exist on the dev machine); omp fixtures must be synthesized from the vendored `session-entries.ts` types and labeled as such.

## Implementation Steps

1. Decide the `HostLayout` contract extension (file-level `normalize_file` vs
   `session_id_from` discriminator) and thread it through `_backfill_raw_events`
   and `_backfill_sessions`. Existing hosts (`normalize_file=None`) must be
   byte-for-byte unaffected — lock with a regression test on the qwen fixtures.
2. Add `_get_gemini_project_folder(cwd)` (slug registry + sha256 fallback) and
   `_get_omp_project_folder(cwd)` + `encode_omp_session_dir` to
   `user_messages.py`; add both `elif` branches to `get_project_folder()`.
3. Add `session_store/gemini.py` and `session_store/omp.py` normalizers and the
   two dedicated `host_layout_for()` branches (`sessions_subdir="chats"`,
   `session_glob="chats/session-*.jsonl"` for gemini; `sessions_subdir=""`,
   `session_glob="*.jsonl"` for omp). Decide whether omp child sessions map
   into `subagent_runs` (needs a third `parent_from` mode).
4. Wire `--host gemini`/`--host omp` through `ll-session backfill` and add the
   choices-list regression test.
5. Add committed fixtures and tests for both hosts, including the
   no-host-installed regression case and the legacy gemini `.json` skip case.
6. Update `docs/reference/HOST_COMPATIBILITY.md` (session-store table + the
   stale line 31 omp status), `docs/reference/API.md`, `docs/reference/CLI.md`,
   and `docs/guides/HISTORY_SESSION_GUIDE.md`.

_Step 1 of the original plan ("investigate the real on-disk layout") was
completed on 2026-09-06 — see Verified Host Layouts. Re-verify only if the
installed gemini-cli or the vendored omp source has moved to a new version._

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_session_log.py`, `test_fsm_continuity.py`,
  `test_cli_ctx_stats.py` — add `gemini`/`omp` per-host cases mirroring their
  existing qwen/codex cases
- Update `scripts/tests/test_enh_3166_qwen_normalizer.py`'s
  `TestHostLayoutRegistry` and `TestSessionStartHookPassesHost` — add
  `gemini`/`omp` coverage
- Update `scripts/tests/test_enh_2505_subagent_runs.py` — add `gemini`/`omp`
  `host_layout_for` cases if subagent-run backfill applies to those hosts
- Write a new regression test asserting the full `ll-session backfill --host`
  choices list — none exists today, so a future host addition could silently
  drift from docs again
- Update `docs/reference/CLI.md`'s `backfill` `--host` flag row — full refresh
  (it's already missing `kimi-code`/`qwen`, not just `gemini`/`omp`)
- Update `docs/guides/HISTORY_SESSION_GUIDE.md`'s "Incremental backfill"
  example commands — full refresh
- Update `docs/reference/API.md`'s `get_project_folder`/`get_sessions_folder`/
  `discover_all_projects` host-dispatch prose — full refresh (already stale at
  "four-way", don't just append a seventh/eighth)
- Add exports for the new gemini/omp normalizers to
  `scripts/little_loops/session_store/__init__.py` mirroring
  `normalize_qwen_record`/`qwen_skip_at_ingest` (no longer conditional — both
  hosts need a normalizer, confirmed 2026-09-06)

## Impact

- **Priority**: P2 — observability gap, not data loss; source transcripts persist
  on disk (when they exist) so recovery remains possible once implemented.
- **Effort**: High — two normalizer modules for two unrelated non-Claude record
  formats, two non-dash-encoded discovery schemes, fixtures for both, plus a
  `HostLayout` contract extension. Qwen took two issues (ENH-3165 + ENH-3166)
  for one host with a friendlier format. **Recommended split**: keep ENH-3393
  as "HostLayout file-level normalizer contract + gemini backfill" and open a
  sibling ENH for omp backfill that depends on it (omp also needs the
  `subagent_runs` `parent_from` decision, which gemini does not). Decide at
  `/ll:ready-issue` time.
- **Risk**: Low-Medium — additive host branches, but the `HostLayout` contract
  change touches `_backfill_raw_events`, which every host's ingest goes
  through; the qwen/claude fixtures must be regression-locked before the
  change lands.
- **Breaking Change**: No.

## Scope Boundaries

**In scope**: extending `HostLayout` with a file-level normalizer / session-id
source; extending `get_project_folder()`, `host_layout_for()`, and the
`ll-session backfill --host` choices to accept `gemini` and `omp`; the two
normalizer modules; committed fixtures for each; updating
`docs/reference/HOST_COMPATIBILITY.md`'s session-store table. The on-disk
layouts are verified (see Program Design → Verified Host Layouts).

**Explicit decisions the implementer must record**: (1) legacy single-document
gemini `chats/session-*.json` files — recommended out of scope, reader skips
them silently; (2) gemini sha256-keyed project dirs from before the slug
registry — recommended in scope as a fallback probe (cheap, one extra
`exists()`); (3) omp child sessions (`<parent stem>/<agentId>.jsonl`) into
`subagent_runs` — recommended deferred to the omp sibling issue if the split
is taken.

**Out of scope**: improving `omp`'s live-hook coverage beyond `session_start`/
`post_tool_use` (separate issue against FEAT-2261's follow-up); any change to
`gemini`/`omp` orchestration in `host_runner.py` itself; `kimi-code` (already has
backfill support); `opencode` (has entries, orchestration stub); fixing `pi`'s
existing `~/.pi/projects` entries, which are wrong (real pi uses
`~/.pi/agent/sessions/--<abs>--/`) — capture as a follow-up, but shape
`encode_omp_session_dir`/`_get_omp_project_folder` so that fix is a reuse.

## Related

- ENH-1945 — host-aware session-log discovery (codex, pi)
- ENH-3165 — qwen subagent transcript backfill
- ENH-3166 — qwen wire-format normalizer and chats discovery
- FEAT-2261 — omp session_start/post_tool_use hook wiring (live-hook tier; this
  issue does not extend that work)
- P4-EPIC-2258 — oh-my-pi (omp) host adapter tracking
- P4-EPIC-2178 — Gemini CLI host adapter tracking

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-05._

- **`_first_session_id()` does not exist** — cited in Program Design
  (Signatures, Call Path), Integration Map (Files to Modify), and
  Implementation Steps as a function at `lifecycle.py:711-728` reading
  `record["sessionId"]` that must be threaded through the `HostLayout`
  contract change. `git log --all -S "_first_session_id"` on
  `session_store/lifecycle.py` returns no hits — this function never existed
  in this file. The function that actually performs this role is
  **`_backfill_sessions()`** at `lifecycle.py:707-732` (not 711-728), which
  reads `record.get("sessionId")` per JSONL line to seed the `sessions`
  table — the same behavior described, just a different name/location.
  Replace every `_first_session_id` reference with `_backfill_sessions`
  before implementation.
- All other file/line citations checked (verified accurate):
  `cli/session.py:213`, `user_messages.py:370-411` (`get_project_folder`
  dispatch chain), `session_store/writers.py` `HostLayout` (~2147-2189) and
  `host_layout_for()` (~2206-2250), `lifecycle.py:747` (`_backfill_raw_events`),
  `lifecycle.py:1022`/`1098` (`backfill`/`backfill_incremental`),
  `docs/reference/HOST_COMPATIBILITY.md` lines 30-31 (omp "Recognized,
  adapter pending") and 511-521 (State directory table host columns),
  `docs/reference/CLI.md:3814` (`--host HOST` row stale host list),
  `cli/backfill_worker.py` (no argparse `choices=`, calls `host_layout_for`/
  `backfill_incremental`), `hooks/session_start.py` (`--host` argv
  construction from `event.host`/`LL_HOOK_HOST`).
- Causal/version claims independently confirmed: gemini-cli 0.46.0 is
  installed on this machine (`gemini --version`) and `~/.gemini/tmp/`
  contains sha256-named project dirs as described; the vendored omp
  18.0.11 source (`package.json` version field) and its
  `session-entries.ts`/`session-manager.ts`/`session-paths.ts` files exist
  at the cited paths, and the `SessionHeader`/`SessionMessageEntry`/
  `ThinkingLevelChangeEntry` shapes in `session-entries.ts:28-80` match the
  issue's Verified Host Layouts description.
- `ll-verify-evidence --json`: clean (`"ok": true`, 0 findings).
- No active required decision rules to check against (`ll-issues decisions
  list --type rule --enforcement required --active-only` returned empty).
- No Acceptance Criteria gap: the `ENH` issue template has no required
  "Acceptance Criteria" section, so check B6's AC-coverage sub-check does
  not apply here.
- Graph: provider=`codegraph` freshness=`stale` — not used to originate any
  verdict; the `_first_session_id` finding was confirmed by direct `grep`/
  `git log`, not graph lookup.

## Status

**Open** | Created: 2026-09-06 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-06T02:36:24 - `7e5d98c9-0b60-4e39-b968-a0a7542f0e0d.jsonl`
- `/ll:verify-issues` - 2026-09-06T02:33:50 - `f342e966-b034-4a2f-8b9f-49272cbb2a3c.jsonl`
- manual review - 2026-09-06 - verified gemini 0.46.0 / omp 18.0.11 on-disk layouts; corrected Program Design (cwd-based helpers, file-level normalizers, HostLayout contract gap), effort → High, split recommendation, pi entries flagged
- `/ll:wire-issue` - 2026-09-06T02:17:09 - `f6ee5fef-8198-4d16-b8a2-3bbb8e726d3e.jsonl`
- `/ll:refine-issue` - 2026-09-06T02:05:42 - `8aa8caa8-0bcc-4ea2-ac50-00eea4c9d01b.jsonl`
- `/ll:format-issue` - 2026-09-06T01:59:12 - `c0275b19-45a2-4dc2-bddf-421eab5bb2a9.jsonl`
- `/ll:capture-issue` - 2026-09-06T01:54:41 - `259dddc7-3ed5-489c-a2c5-bdbcc4004163.jsonl`
