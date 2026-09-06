---
id: ENH-3394
type: ENH
title: history.db backfill has no host coverage for omp (oh-my-pi)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-06'
captured_at: '2026-09-06T03:39:22Z'
labels:
- backfill
- session-store
- omp
depends_on:
- ENH-3393
---

# ENH-3394: history.db backfill has no host coverage for omp (oh-my-pi)

## Summary

`ll-session backfill --host omp` has no code path, mirroring the gap ENH-3393
fixed for `gemini`. omp (oh-my-pi) is a fully wired, production orchestration
host (`OmpRunner` in `host_runner.py`'s `_HOST_RUNNER_REGISTRY`) with a real
hook adapter (`hooks/adapters/omp/`, FEAT-2261 — `session_start` +
`post_tool_use` only), but its transcript-backfill tier has no host support:
`ll-session backfill --host` doesn't accept `"omp"`, `get_project_folder()`
has no omp branch, and `host_layout_for()` has no omp entry.

This issue depends on ENH-3393, which added the `HostLayout.normalize_file`
contract (a file-level normalizer hook, needed because — like gemini — omp's
session id lives only in a file header, not on each record) and split omp
out as "Recommended split" in that issue's Impact section, since qwen alone
took two issues (ENH-3165 + ENH-3166) for a friendlier record format, and omp
needs an additional decision gemini didn't (child-session `subagent_runs`
mapping).

## Current Behavior

- `scripts/little_loops/cli/session.py` — `ll-session backfill --host`
  choices do not include `"omp"`.
- `scripts/little_loops/user_messages.py` — `get_project_folder()`'s
  `if`/`elif` host chain has no `omp` branch; falls through to `None`.
- `scripts/little_loops/session_store/writers.py` — `host_layout_for()` has
  no `omp` branch; an `omp` host string degrades to the generic
  Claude-shaped default (`projects_root=None`, no normalizer).
- No `session_store/omp.py` normalizer module exists.

Net effect: `omp` sessions can never be recovered via `ll-session backfill
--host omp`. Their only path into `.ll/history.db` is the partial live-hook
tier (`session_start`/`post_tool_use` only, FEAT-2261) — a dropped/interrupted
live session, or any event type FEAT-2261 didn't wire, has no repair path.

## Expected Behavior

`ll-session backfill --host omp` walks omp's on-disk session-transcript
layout and populates `sessions`/`tool_events`/`raw_events` (and
`subagent_runs`, pending the child-session decision below), matching the
pattern ENH-3393 established for gemini and reusing its `HostLayout.
normalize_file` contract.

## Motivation

`omp` is a production orchestration host today (loops, sprints, and
subagents can run under it via `host_runner.py`, and it has a real hook
adapter per FEAT-2261), but its history is permanently unrecoverable once
the live-hook tier's `session_start`/`post_tool_use`-only coverage misses an
event, or a session predates `ll-init`. Every other wired host got a
dedicated backfill fix when this gap was found (ENH-1945 for codex/pi,
ENH-3165/3166 for qwen, ENH-3393 for gemini); omp was the deliberate
carve-out from ENH-3393 rather than an oversight, but it still needs its own
issue so the coverage matrix doesn't silently drift further from the
orchestration layer's actual host list.

## Proposed Solution

Follow ENH-3393's gemini implementation as the structural template — one
`host_layout_for()` branch, a `session_store/omp.py` file-level normalizer
(`normalize_omp_session(path: Path) -> Iterator[dict]`), a
`_get_omp_project_folder(cwd)` helper plus `get_project_folder()` branch, and
the `--host omp` CLI wire-in — but omp's on-disk shape differs from gemini's
in ways ENH-3393's "Verified Host Layouts" section already documented from
the vendored omp 18.0.11 source
(`scripts/little_loops/hooks/adapters/omp/node_modules/@oh-my-pi/pi-coding-agent/src/session/`);
re-verify against whatever omp version is vendored when this issue is
implemented.

**omp** (`~/.omp/`):
- Sessions root: `~/.omp/agent/sessions/` (`pi-utils/src/dirs.ts:872`,
  `getSessionsDir`); `PI_CONFIG_DIR` overrides `.omp`; `XDG_DATA_HOME`
  flattens to `$XDG_DATA_HOME/omp/sessions`.
- Project folder encoding (`pi-coding-agent/src/session/session-paths.ts:40-90`):
  cwd under `$HOME` → `-<home-relative with /\: → ->` (dots preserved); cwd
  under `os.tmpdir()` → `-tmp-<rel>`; other absolute → legacy `--<abs sans
  leading />--`. A transitional `<scope>-<basename>-<sha256hex>` form from omp
  17.2.5–17.2.8 may also exist; omp migrates old `--<home>-…--` dirs to the
  new form on first access (`migrateHomeSessionDirs`).
- Session files: `<ts with :. → ->_<sessionId>.jsonl`
  (`session-manager.ts:1142`). Child/subagent sessions:
  `<parent stem>/<agentId>.jsonl` — a sibling dir named after the parent file
  minus `.jsonl` (`session-manager.ts:139-151`; also the artifacts dir). This
  matches neither `parent_from="parent_dir"` nor `"child_dir"`; a third mode
  (`"stem_dir"`) or a per-host callable is needed if `subagent_runs` is
  populated for omp.
- Record format (`session-entries.ts:28-80`): header `{type: "session",
  version?, id, title?, timestamp, cwd, additionalDirectories?,
  parentSession?}`; then `{type: "message", id, parentId, timestamp, message:
  {role, content}}` plus `thinking_level_change`, `model_change`,
  `compaction`, `custom` entries. Header key is `id` (not `sessionId`) and
  message entries carry no session id.
- omp has no sessions on disk on the ENH-3393 dev machine (binary not on
  PATH, `~/.omp/agent/sessions` absent) — build fixtures from the vendored
  `session-entries.ts` types, labeled as synthesized (not sanitized real
  captures, unlike gemini's).

Note: the existing `pi` entries (`~/.pi/projects` in both
`_get_pi_project_folder` and `host_layout_for`) are also wrong — real pi
writes `~/.pi/agent/sessions/--<abs>--/` (omp's legacy encoding is pi's
current one). Out of scope here too, but shape `encode_omp_session_dir`/
`_get_omp_project_folder` so a follow-up pi fix is a one-line reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/session.py` — `backfill --host` choices: add
  `"omp"`
- `scripts/little_loops/user_messages.py` — `get_project_folder()`: new
  `elif host == "omp"` branch calling `_get_omp_project_folder(cwd)`
- `scripts/little_loops/session_store/writers.py` — `host_layout_for()`: new
  dedicated `omp` branch
- `scripts/little_loops/session_store/omp.py` (new) — omp file-level
  normalizer
- `scripts/little_loops/session_store/__init__.py` — export
  `normalize_omp_session` mirroring `normalize_gemini_session`
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table, add the
  `omp` column (gemini's column landed in ENH-3393)

### Similar Patterns
- ENH-3393 — gemini backfill + the `HostLayout.normalize_file` contract this
  issue reuses directly
- ENH-3165 / ENH-3166 — qwen backfill + wire-format normalizer

### Tests
- `scripts/tests/test_user_messages.py` — `get_project_folder` cases for
  `omp` (home-relative, tmp-relative, legacy `--abs--`, and
  `PI_CONFIG_DIR`/`XDG_DATA_HOME` overrides), plus `encode_omp_session_dir`
  unit cases including a `.worktrees` path (dot must survive)
- `scripts/tests/test_enh_omp_normalizer.py` (new), mirroring
  `scripts/tests/test_enh_3393_gemini_normalizer.py`, with synthesized
  fixtures at `scripts/tests/fixtures/omp/` built from the vendored
  `session-entries.ts` types (labeled as synthesized, not real captures)
- `scripts/tests/test_enh_3166_qwen_normalizer.py`'s
  `test_gemini_and_omp_have_no_static_projects_root` — flip the `omp` half
  of this assertion once `host_layout_for("omp")` is registered (currently
  passes because omp falls through to the unregistered-host default)
- `scripts/tests/test_ll_session.py::test_backfill_host_choices_list` — add
  `"omp"` to the accepted-choices list and drop the `SystemExit` case for it
- `scripts/tests/test_enh_2505_subagent_runs.py` — add an `omp`
  `host_layout_for` case if the `<parent stem>/<agentId>.jsonl` child-session
  layout is mapped into `subagent_runs`

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table (add `omp`
  column, mirroring the `[^geminiwire]` footnote pattern)
- `docs/reference/API.md` — `get_project_folder`/`get_sessions_folder`
  docstrings: add `"omp"` to the host vocabulary list
- `docs/reference/CLI.md` — `backfill --host` flags table: add `omp`
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "Incremental backfill" example
  commands: add an `omp` example

## Program Design

### Signatures

- `_get_omp_project_folder(cwd: Path) -> Path | None` — new branch in
  `get_project_folder()`; returns `<sessions_root>/<omp-encoded cwd>` where
  `sessions_root` is `$XDG_DATA_HOME/omp/sessions` if set else
  `~/<PI_CONFIG_DIR or .omp>/agent/sessions`, probing the current encoding
  first and then the legacy encoding.
- `encode_omp_session_dir(cwd: Path) -> str` — omp's cwd encoding
  (home-relative `-<rel>`, tmp-relative `-tmp-<rel>`, else `--<abs>--`, with
  `/\:` → `-` and dots preserved). Separate from `encode_project_path`
  (Claude's every-non-alnum scheme, which would mangle `.worktrees`).
- `normalize_omp_session(path: Path) -> Iterator[dict]`
  (`session_store/omp.py`) — file-level normalizer (same
  `HostLayout.normalize_file` contract ENH-3393 added): reads the
  `{type:"session", id, cwd, parentSession?}` header, yields Claude-shaped
  records from `{type:"message", message:{role, content}}` entries, drops
  `model_change`/`thinking_level_change`/`compaction` entries (or routes them
  to `skip_at_ingest`).
- `host_layout_for("omp")` — new branch using `normalize_file=
  normalize_omp_session`; decide the `parent_from` mode (new `"stem_dir"` or
  a per-host callable) if child-session `subagent_runs` mapping is in scope.

### Call Path

`ll-session backfill --host omp` -> `get_project_folder` ->
`_get_omp_project_folder` (new, `cwd`-based) -> `host_layout_for` ->
`HostLayout` (with `normalize_file=normalize_omp_session`) -> `backfill` ->
`_backfill_raw_events` (uses `normalize_file` to stamp `session_id`, per the
ENH-3393 contract) -> `rebuild` extractors -> `_backfill_subagent_runs` (if
child-session dirs are mapped)

## Implementation Steps

1. Decide the `subagent_runs` child-session question (a new `parent_from:
   "stem_dir"` mode vs. a per-host callable) before writing the normalizer,
   since it shapes whether `session_store/omp.py` needs to expose a
   directory-walk helper alongside `normalize_omp_session`.
2. Add `session_store/omp.py` (file-level normalizer reusing the
   `HostLayout.normalize_file` contract from ENH-3393), `_get_omp_project_folder`
   + `encode_omp_session_dir` in `user_messages.py`, and the `omp`
   `host_layout_for()` branch.
3. Wire `--host omp` through `ll-session backfill` (`cli/session.py` choices)
   and update `test_backfill_host_choices_list`'s expectations.
4. Add synthesized fixtures (from the vendored `session-entries.ts` types,
   labeled as synthesized — omp has no real captures on the ENH-3393 dev
   machine) and tests mirroring `test_enh_3393_gemini_normalizer.py`.
5. Update `docs/reference/HOST_COMPATIBILITY.md` (add the `omp` column),
   `docs/reference/API.md`, `docs/reference/CLI.md`, and
   `docs/guides/HISTORY_SESSION_GUIDE.md`.
6. Run `python -m pytest scripts/tests/` to confirm the Claude/qwen/gemini
   fixtures are unaffected (the `HostLayout.normalize_file` contract is
   additive; this issue must not touch its ENH-3393 regression tests).

## Impact

- **Priority**: P2 — observability gap, not data loss; source transcripts
  persist on disk (when they exist) so recovery remains possible once
  implemented.
- **Effort**: Medium — the `HostLayout.normalize_file` contract already
  exists (ENH-3393); this issue is "one more host" plus the child-session
  `subagent_runs` decision gemini didn't need.
- **Risk**: Low — additive host branch; the contract this issue depends on
  is already regression-locked against Claude/qwen fixtures by ENH-3393.
- **Breaking Change**: No.

## Scope Boundaries

**In scope**: `_get_omp_project_folder`/`encode_omp_session_dir` in
`user_messages.py`; the `omp` `host_layout_for()` branch and
`session_store/omp.py` normalizer; wiring `--host omp` into `ll-session
backfill`; fixtures (synthesized from `session-entries.ts`); the
`HOST_COMPATIBILITY.md` session-store table's `omp` column.

**Explicit decision the implementer must record**: whether omp child sessions
(`<parent stem>/<agentId>.jsonl`) map into `subagent_runs` in this issue or a
further follow-up — the `parent_from` mode doesn't exist yet (`"stem_dir"` or
a per-host callable).

**Out of scope**: improving omp's live-hook coverage beyond
`session_start`/`post_tool_use` (separate issue against FEAT-2261's
follow-up); any change to `omp` orchestration in `host_runner.py`; fixing
`pi`'s existing `~/.pi/projects` entries (capture as a follow-up, but shape
this issue's helpers so that fix is a reuse).

## Related

- ENH-3393 — HostLayout.normalize_file contract + gemini backfill (this
  issue depends on it)
- ENH-1945 — host-aware session-log discovery (codex, pi)
- ENH-3165 / ENH-3166 — qwen subagent transcript backfill + normalizer
- FEAT-2261 — omp session_start/post_tool_use hook wiring (live-hook tier;
  this issue does not extend that work)
- P4-EPIC-2258 — oh-my-pi (omp) host adapter tracking (done)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-06 | Priority: P2
