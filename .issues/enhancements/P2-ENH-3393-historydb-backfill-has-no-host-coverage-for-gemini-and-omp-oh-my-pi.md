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
- `/ll:capture-issue` - 2026-09-06T01:54:41 - `259dddc7-3ed5-489c-a2c5-bdbcc4004163.jsonl`
