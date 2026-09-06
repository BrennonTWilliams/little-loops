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

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table
- `docs/reference/API.md` — `ll-session backfill --host {…}` host list

### Configuration
- N/A

## Implementation Steps

1. Investigate the real on-disk transcript layout for `gemini` and `omp` (do not
   assume — confirm against an actual install or authoritative host docs).
2. Add host-layout entries/descriptor cases for both in `host_layout_for()` and
   `get_project_folder()`.
3. Wire `--host gemini`/`--host omp` through `ll-session backfill`.
4. Add committed fixtures and tests for both hosts, including a no-host-installed
   regression case.
5. Update `docs/reference/HOST_COMPATIBILITY.md` and `docs/reference/API.md`.

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
- `/ll:format-issue` - 2026-09-06T01:59:12 - `c0275b19-45a2-4dc2-bddf-421eab5bb2a9.jsonl`
- `/ll:capture-issue` - 2026-09-06T01:54:41 - `259dddc7-3ed5-489c-a2c5-bdbcc4004163.jsonl`
