---
id: ENH-3393
type: ENH
title: history.db backfill has no host coverage for gemini and omp (oh-my-pi)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-06'
captured_at: '2026-09-06T01:54:32Z'
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
  dict populated with the same six hosts; `gemini`/`omp` fall into the generic
  default with `projects_root=None`.
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

Follow the ENH-3165 precedent: add a host-layout descriptor entry (or extend
whatever descriptor type that issue lands, since it explicitly designed
`SubagentLayout`/`host_layout_for` to be host-parameterized) for `gemini` and
`omp`, each describing its transcript root, chats/subagents glob shape, and
whether a sidecar-metadata file exists (as qwen's `.meta.json` does). Wire the new
host names into `ll-session backfill --host` choices and `get_project_folder()`'s
host branch. Verify against a real `gemini`/`omp` install before writing fixtures
— do not assume the layout mirrors `~/.qwen` or `~/.codex` without checking.

## Program Design

### Signatures

- `_get_gemini_project_folder(encoded_path: str) -> Path | None` — new branch in `get_project_folder()`, mirrors `_get_codex_project_folder`/`_get_qwen_project_folder`; resolves the encoded cwd against gemini's on-disk project-session root (root path unconfirmed — see Implementation Steps step 1).
- `_get_omp_project_folder(encoded_path: str) -> Path | None` — new branch in `get_project_folder()`, same shape as above; resolves against omp's project-session root (also unconfirmed).

### Call Path

`ll-session backfill --host gemini|omp` -> `get_project_folder` -> `_get_gemini_project_folder`/`_get_omp_project_folder` (new) -> `host_layout_for` -> `HostLayout` -> `backfill` -> `_backfill_subagent_runs`

### Codebase Research Findings

- `get_project_folder()` (`user_messages.py:370`) dispatches on a flat `if`/`elif host == ...` chain (`:399-410`) that returns `None` for any unmatched host; `gemini`/`omp` each need one new `elif` branch calling a new per-host helper, following the existing `_get_codex_project_folder`/`_get_qwen_project_folder` pattern rather than inlining logic into `get_project_folder` itself.
- `host_layout_for()` (`session_store/writers.py:2206`) special-cases `qwen` (nested `subagents/<session-id>/` with a `.meta.json` sidecar) before falling into a generic `projects_root` dict covering `claude-code`/`codex`/`opencode`/`pi` (`:2237-2242`) that returns a `HostLayout` with `glob="*/subagents"`, `parent_from="parent_dir"`, `sidecar_suffix=None`. Whether `gemini`/`omp` need a third special case (qwen-shaped) or just two more dict entries (Claude-shaped) is unresolved until step 1's on-disk layout investigation — do not assume the flat-dict shape without checking.
- `backfill()` (`session_store/lifecycle.py:1022`) only calls `host_layout_for(host)` and walks `sessions_root` when both are non-`None`/a real directory (`:1080-1082`), so a `gemini`/`omp` host string with no matching `host_layout_for` branch degrades silently to the Claude-shaped default rather than erroring — the CLI-level `--host` choices gate (`cli/session.py:213`) is what actually prevents that today, not `backfill()` itself.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/session.py:213` — `backfill --host` choices
- `scripts/little_loops/user_messages.py` — `get_project_folder()` (~399-411),
  new host branches for `gemini`/`omp`
- `scripts/little_loops/session_store/writers.py` — `host_layout_for()`
  (~2206-2250), new dict entries or descriptor cases
- `scripts/little_loops/session_store/lifecycle.py` — `backfill()` `sessions_root`
  resolution per host
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table, add `gemini`/`omp`
  columns

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
  `gemini`/`omp`
- Backfill test module (wherever ENH-3165's qwen fixtures landed) — add
  `gemini`/`omp` fixtures, both with and without the host CLI installed on the
  test machine

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed: the qwen backfill/normalizer test module is
  `scripts/tests/test_enh_3166_qwen_normalizer.py`, fixtures at
  `scripts/tests/fixtures/qwen/{session,noise}.jsonl` — this is the file/dir to
  mirror, not a differently-named module [Agent 3 finding]
- `scripts/tests/test_enh_3166_qwen_normalizer.py` `TestHostLayoutRegistry`
  (196-247), specifically `test_registered_claude_shaped_hosts_get_projects_roots`
  (231-234) — add `gemini`/`omp` assertions here if Claude-shaped, or add new
  dedicated tests mirroring `test_qwen_layout_widens_without_losing_enh_3165_fields`
  (197-219) if sidecar-shaped [Agent 3 finding]
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
  `host_layout_for("qwen")` calls feeding `_backfill_subagent_runs` — add
  `gemini`/`omp` analogues if subagent-run backfill applies to those hosts
  [Agent 1 finding]
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- **Host dispatch is one `elif` branch + one private helper per host** — `get_project_folder()` (`scripts/little_loops/user_messages.py:399-411`) is a flat `if`/`elif` chain; the docstring (`:385-386`) states this explicitly: "Future hosts... add a new branch here rather than a new code path elsewhere." Every Claude-shaped helper (`_get_codex_project_folder`, `_get_opencode_project_folder`, `_get_pi_project_folder`, lines 450-465) is a one-liner building `Path.home() / "<host-dir>" / "projects" / encoded_path`.
- **Contested convention — two host shapes exist, and this issue's own Proposed Solution assumes a decision hasn't been made yet**: (a) flat-dict, no-normalizer hosts (claude-code/codex/opencode/pi) get one `projects_root` dict entry in `host_layout_for()` (`session_store/writers.py:2237-2242`) with no `sidecar_suffix`/`normalize`; (b) qwen instead gets a dedicated `if host == "qwen"` special case (`writers.py:2206-2236`) plus a whole normalizer module (`session_store/qwen.py`) and committed real-capture fixtures, because its project root holds both `chats/` and `subagents/` and needs a `.meta.json` sidecar. Which shape gemini/omp need is unresolved until the on-disk layout investigation (Implementation Steps step 1) — do not assume the flat-dict shape without checking.
- **The descriptor type this issue's Proposed Solution names does not exist**: Proposed Solution says to extend "whatever descriptor type ENH-3165 lands, since it explicitly designed `SubagentLayout`/`host_layout_for`..." — there is no `SubagentLayout` type in `scripts/little_loops/session_store/`. The actual (single, already host-parameterized) type is `HostLayout` (`writers.py:2145-2190`), whose docstring (`:2150-2156`) confirms it was "widened from ENH-3165's subagent-only descriptor by ENH-3166... One record per host — a second host table would drift from the first." New hosts plug into this existing type; no new type is needed.
- **`get_project_folder` coverage and `host_layout_for` `projects_root` coverage are tracked independently**: `kimi-code` has a `get_project_folder` branch (index-file-resolved, not path-dash-encoding) but no `projects_root` entry in `host_layout_for()` — it falls through to the generic default, confirmed by `test_kimi_code_has_no_static_projects_root` (`scripts/tests/test_enh_3166_qwen_normalizer.py:246-247`). A host can have one without the other; gemini/omp will need both explicitly checked, not assumed to travel together.
- **Test convention for a new Claude-shaped host**: a three-line positive-resolve test per host (`scripts/tests/test_user_messages.py:146-159` for codex, `:161-174` opencode, `:176-189` pi) — build `fake_home / ".<host>" / "projects" / <encoded>`, monkeypatch `Path.home`, assert `get_project_folder(host=...)` resolves it. A companion "returns None when no project dir exists" test exists only for qwen (`:293-303`) and kimi-code (`:241-252`) — codex/opencode/pi have no such regression test today. ENH-3393's own Implementation Steps step 4 asks for "a no-host-installed regression case" for gemini/omp, which would make them the first flat-dict-shaped hosts to have one.
- **Fixture convention diverges by host shape**: qwen is the only backfill host with committed real-capture fixtures (`scripts/tests/fixtures/qwen/session.jsonl`, `noise.jsonl`, consumed by `test_enh_3166_qwen_normalizer.py:48-56`; module docstring: "sanitized captures from real qwen 0.21.6 output"). codex/opencode/pi (ENH-1945-era) tests instead build directories/files synthetically inline via `tmp_path`/`monkeypatch`, with no committed fixture files. Which convention gemini/omp should follow depends on which host shape (flat-dict vs sidecar-having) their real layout turns out to need.

## Implementation Steps

1. Investigate the real on-disk transcript layout for `gemini` and `omp` (do not
   assume — confirm against an actual install or authoritative host docs).
2. Add host-layout entries/descriptor cases for both in `host_layout_for()` and
   `get_project_folder()`.
3. Wire `--host gemini`/`--host omp` through `ll-session backfill`.
4. Add committed fixtures and tests for both hosts, including a no-host-installed
   regression case.
5. Update `docs/reference/HOST_COMPATIBILITY.md` and `docs/reference/API.md`.

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
- Conditional: if step 1's on-disk investigation finds `gemini`/`omp` need a
  qwen-shaped sidecar normalizer (not the flat-dict shape), add corresponding
  exports to `scripts/little_loops/session_store/__init__.py` mirroring
  `normalize_qwen_record`/`qwen_skip_at_ingest`

## Impact

- **Priority**: P2 — observability gap, not data loss; source transcripts persist
  on disk (when they exist) so recovery remains possible once implemented.
- **Effort**: Medium — layout for two new hosts is unconfirmed, so investigation
  precedes implementation; the wiring itself follows an established pattern
  (ENH-1945, ENH-3165/3166).
- **Risk**: Low — additive host branches; no change to existing host behavior.
- **Breaking Change**: No.

## Scope Boundaries

**In scope**: extending `get_project_folder()`, `host_layout_for()`, and the
`ll-session backfill --host` choices to accept `gemini` and `omp`; determining
each host's real on-disk transcript layout (unconfirmed — needs direct
investigation against an installed `gemini`/`omp` CLI or its docs, not assumed by
analogy to `~/.qwen`/`~/.codex`); committed fixtures for each; updating
`docs/reference/HOST_COMPATIBILITY.md`'s session-store table.

**Out of scope**: improving `omp`'s live-hook coverage beyond `session_start`/
`post_tool_use` (separate issue against FEAT-2261's follow-up); any change to
`gemini`/`omp` orchestration in `host_runner.py` itself; `kimi-code` (already has
backfill support); `opencode`/`pi` (already have `get_project_folder`/
`host_layout_for` entries despite being orchestration stubs — no change needed).

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

## Status

**Open** | Created: 2026-09-06 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-06T02:17:09 - `f6ee5fef-8198-4d16-b8a2-3bbb8e726d3e.jsonl`
- `/ll:refine-issue` - 2026-09-06T02:05:42 - `8aa8caa8-0bcc-4ea2-ac50-00eea4c9d01b.jsonl`
- `/ll:format-issue` - 2026-09-06T01:59:12 - `c0275b19-45a2-4dc2-bddf-421eab5bb2a9.jsonl`
- `/ll:capture-issue` - 2026-09-06T01:54:41 - `259dddc7-3ed5-489c-a2c5-bdbcc4004163.jsonl`
