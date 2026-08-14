---
id: ENH-3165
type: ENH
title: Qwen subagent transcripts never backfill into subagent_runs (inverted nesting,
  unread .meta.json sidecars)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-13'
captured_at: '2026-08-13T23:28:23Z'
testable: true
depends_on: []
relates_to:
- ENH-3166
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3165: Qwen subagent transcripts never backfill into subagent_runs (inverted nesting, unread .meta.json sidecars)

## Summary

Qwen subagent spawns never reach `.ll/history.db`: on 2026-08-13 `subagent_runs`
held no rows for recent qwen sessions (e.g. `cd4599f4` with 8 subagent
transcripts on disk) even though the transcripts exist under
`~/.qwen/projects/<encoded>/subagents/<session-id>/`. The live capture tier is
landed (FEAT-3158 hook adapter, active once `ll-init --hosts qwen` has run per
project), but the **backfill/repair tier** cannot see qwen at all.

Two concrete defects:

1. **`_backfill_subagent_runs` assumes Claude's transcript nesting.**
   `scripts/little_loops/session_store/writers.py:1897` globs
   `sessions_root.glob("*/subagents")` — the Claude shape
   `<session-dir>/subagents/agent-*.jsonl`. Qwen **inverts** the nesting:
   `~/.qwen/projects/<encoded>/subagents/<session-id>/agent-*.jsonl`, one level
   shallower with the session id as the *child* directory. Compounding this,
   `get_project_folder(host="qwen")` (`user_messages.py:476`,
   `_get_qwen_project_folder`) returns the sibling `chats/` folder, so
   `ll-session backfill --host qwen` passes a root where the glob can never
   match.

2. **The `.meta.json` sidecars are ignored, and they are strictly better than
   the mtime heuristic.** Every qwen subagent transcript has a sibling
   `<name>.meta.json`:

   ```json
   {"agentId":"codebase-locator-call_47db5168b354492ca94be889",
    "agentType":"codebase-locator","parentSessionId":"cd4599f4-…",
    "parentAgentId":null,"toolUseId":"call_47db5168b354492ca94be889",
    "createdAt":"2026-08-13T23:01:41.299Z","lastUpdatedAt":"2026-08-13T23:01:41.527Z",
    "status":"failed","depth":0}
   ```

   The Claude backfill path infers `started_at`/`ended_at` from file mtime and
   hardcodes `status = "completed"`, on the reasoning that a persisted
   transcript implies the spawn ran to completion. **That reasoning does not
   hold for qwen** — the sidecar above records `status: "failed"` for a
   transcript that exists on disk. Reusing the Claude heuristic would write
   provably wrong status and timestamps.

### Idempotency trap: `agent_id` must come from the sidecar

`subagent_runs` is `UNIQUE(parent_session_id, agent_id)`. The Claude backfill
uses the transcript file **stem** as `agent_id`. For qwen the stem is
`agent-codebase-locator-call_47db…` while the sidecar (and the FEAT-3158 live
hook payload) reports `agentId` as `codebase-locator-call_47db…`. Deriving
`agent_id` from the filename would therefore insert a **second row per spawn**
on top of any live-captured row instead of no-op'ing through
`INSERT OR IGNORE`. Backfill must use the sidecar's `agentId` verbatim.

Test blindness accompanies the code gap: `test_enh_2505_subagent_runs.py` covers
the spawn-tree lifecycle and backfill only against the Claude-shaped layout.

## Motivation

Live hooks capture spawns only from the moment of `ll-init --hosts qwen`
onward; every earlier qwen run is recoverable only through backfill. Until
then, `subagent_tree()` / `subagent_retries()` / `subagent_budget()` and any
sprint/loop analytics built on them are permanently incomplete for qwen.

Reading the sidecars also makes qwen backfill **richer than Claude's**: real
`status` (including `failed`), real `createdAt`/`lastUpdatedAt` timestamps,
`agentType`, and `parentAgentId` for nested spawn trees — none of which the
Claude mtime path can reconstruct.

## Current Behavior

`ll-session backfill --host qwen` inserts zero `subagent_runs` rows. The glob in
`_backfill_subagent_runs` looks for `<session-dir>/subagents`, which never
matches qwen's `subagents/<session-id>/` inversion, and the `sessions_root` it
receives points at qwen's `chats/` folder — a directory that contains no
subagent transcripts at all. The `.meta.json` sidecars sitting beside every
qwen transcript are never opened.

## Expected Behavior

`ll-session backfill --host qwen` walks `<projects_root>/<encoded>/subagents/*/`,
writes one `subagent_runs` row per transcript, and sources
`agent_id`/`agent_type`/`started_at`/`ended_at`/`status` from the transcript's
`.meta.json` sidecar. Rows already written by the FEAT-3158 live hooks are
matched and left untouched by `INSERT OR IGNORE`, because backfill derives the
same `agent_id` the hooks record. Claude-host backfill behavior is unchanged.

## Scope Boundaries

**In scope**: `_backfill_subagent_runs` layout branching, the qwen sidecar
reader, `_get_qwen_project_folder` root resolution, `--host qwen` acceptance in
`ll-session backfill`, and qwen-layout test fixtures.

**Out of scope**: qwen chat-message extraction into `sessions`/`tool_events`/
`message_events` (ENH-3166); kimi-code subagent layout (ENH-2918); the
`raw_events.host` mislabeling (ENH-3166); QwenRunner's missing `--agent` CLI
flag (documented upstream limitation); any schema change to `subagent_runs`
beyond what `parentAgentId` may require.

## Program Design

### Types

```python
@dataclass(frozen=True)
class SubagentLayout:
    """Per-host description of how subagent transcripts nest on disk."""
    glob: str                  # "*/subagents" (claude) | "subagents/*" (qwen)
    parent_from: str           # "parent_dir" | "child_dir"
    sidecar_suffix: str | None # ".meta.json" for qwen, None for claude

@dataclass(frozen=True)
class SubagentMeta:
    """Normalized sidecar contents; all fields optional so callers can degrade."""
    agent_id: str
    agent_type: str | None
    parent_session_id: str | None
    parent_agent_id: str | None
    started_at: str | None
    ended_at: str | None
    status: str
```

### Signatures

- `_backfill_subagent_runs(conn: sqlite3.Connection, sessions_root: Path, *, layout: SubagentLayout | None = None) -> int` — existing signature plus an optional layout; `None` preserves today's Claude behavior verbatim.
- `_read_subagent_meta(transcript: Path, suffix: str) -> SubagentMeta | None` — parses the sidecar beside a transcript, returning `None` on missing file, `OSError`, or `json.JSONDecodeError` so the caller falls back to the mtime heuristic.
- `_subagent_meta_from_mtime(transcript: Path, parent_session_id: str) -> SubagentMeta | None` — today's inline mtime/`"completed"` heuristic, extracted so both paths produce the same record type.
- `subagent_layout_for(host: str) -> SubagentLayout` — descriptor lookup; becomes a field on ENH-3166's `HostLayout` if that lands first, but stands alone otherwise.

### Call Path

1. `ll-session backfill --host qwen` — CLI entry in `scripts/little_loops/cli/session.py`
2. `backfill()` — resolves `sessions_root` and `layout` for the host
3. `_backfill_subagent_runs()` — globs per `layout.glob`, derives `parent_session_id` per `layout.parent_from`
4. `_read_subagent_meta()` → falls back to `_subagent_meta_from_mtime()` when the sidecar is absent
5. `INSERT OR IGNORE INTO subagent_runs` — dedups against rows written by `record_subagent_run_stop`

## Implementation Steps

1. Extract the current mtime heuristic into `_subagent_meta_from_mtime` and
   introduce `SubagentMeta`/`SubagentLayout`, keeping Claude output identical.
2. Add the qwen layout entry and sidecar reader; branch the glob and the
   parent-session derivation on the layout.
3. Fix `_get_qwen_project_folder` to expose a root reaching both `chats/` and
   `subagents/`, and plumb `--host qwen` through `ll-session backfill`.
4. Add qwen fixtures to `test_enh_2505_subagent_runs.py`, including the
   live-write-then-backfill dedup assertion and a `status: "failed"` sidecar.
5. Verify against real data (`cd4599f4`, `4b8198c0`) and update
   `docs/reference/API.md` + `docs/reference/HOST_COMPATIBILITY.md`.

## Proposed Solution

Introduce a `SubagentLayout` descriptor describing (a) the glob shape and
(b) whether sidecar metadata is available, then branch
`_backfill_subagent_runs` on it rather than hardcoding a second glob. This
issue owns the descriptor and can land in either order relative to ENH-3166,
which folds it into the broader `HostLayout` table when that lands; neither
issue blocks the other.

- Claude: `sessions_root.glob("*/subagents")`, parent = `dir.parent.name`,
  metadata = mtime heuristic
- Qwen: `<projects_root>/<encoded>/subagents/*/`, parent = the child dir name
  (cross-checked against the sidecar's `parentSessionId`), metadata = sidecar

Also fix `_get_qwen_project_folder` so the subagent path resolves. It currently
returns `chats/` because backfill consumers glob sessions there; rather than
overloading one return value for two consumers, resolve the project root and
let the descriptor name the `chats/` and `subagents/` subdirectories.

Populate from the sidecar: `agent_id` ← `agentId`, `agent_type` ← `agentType`,
`parent_session_id` ← `parentSessionId`, `started_at` ← `createdAt`,
`ended_at` ← `lastUpdatedAt`, `status` ← `status`. Fall back to the Claude
mtime heuristic only when a sidecar is missing or unparseable.

kimi-code shares gap shape 1 (ENH-2918 posture); keep the descriptor
host-parameterized, but kimi extraction is out of scope here. QwenRunner's
missing `--agent` CLI flag is a documented upstream limitation, not part of
this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — `_backfill_subagent_runs`
  (1897): descriptor-driven glob, sidecar reader, mtime fallback
- `scripts/little_loops/user_messages.py` — `_get_qwen_project_folder`
  (476–490): resolve project root, not just `chats/`
- `scripts/little_loops/session_store/lifecycle.py` — `backfill()` (1007)
  `sessions_root` resolution per host
- `scripts/little_loops/cli/session.py` — `ll-session backfill --host` accepts
  and plumbs `qwen`
- `scripts/little_loops/user_messages.py` — new `get_sessions_folder()` helper:
  `get_project_folder()` joined with `subagent_layout_for(host).sessions_subdir`
  (consumer follow-up: the root-return change above silently broke every
  `get_project_folder` consumer that globs `*.jsonl` non-recursively under
  `LL_HOOK_HOST=qwen`)
- `scripts/little_loops/session_log.py` — `get_current_session_jsonl()`
  resolves through `get_sessions_folder()` (feeds `get_current_session_id`
  session stamping in issue lifecycle, FSM executor, parallel orchestrator)
- `scripts/little_loops/fsm/continuity.py` — `summarize_completed_state()`
  transcript lookup resolves through `get_sessions_folder()`
- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_jsonl()`
  resolves through `get_sessions_folder()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/queries.py` — `subagent_tree()`,
  `subagent_retries()`, `subagent_budget()` consumers of the new rows
- `scripts/little_loops/hooks/subagent_start.py` / `subagent_stop.py` — the
  live writers whose `agent_id` convention backfill must match

### Similar Patterns
- `record_subagent_run_stop` (`writers.py:~1860`) — the live `INSERT OR IGNORE`
  / `UPDATE` posture backfill must stay compatible with
- `_backfill_learning_test_events` (`writers.py:1632`) — sidecar-JSON-driven
  backfill precedent

### Tests
- `scripts/tests/test_enh_2505_subagent_runs.py` — add qwen-layout fixtures
  alongside the existing Claude-layout coverage; cover the live-then-backfill
  dedup case explicitly
- `scripts/tests/test_user_messages.py` — `TestGetSessionsFolder`: qwen
  `chats/` join (with and without the dir on disk), Claude no-op equality,
  `LL_HOOK_HOST` auto-detect, explicit-host precedence
- `scripts/tests/test_session_log.py` / `test_fsm_continuity.py` /
  `test_cli_ctx_stats.py` — real-resolution-chain qwen tests (transcript found
  under `chats/`, root-level decoy ignored) plus patch-target migration to
  `get_sessions_folder`

### Documentation
- `docs/reference/API.md` — `SubagentRun` / `ll-session backfill --host {…}`
  host list
- `docs/reference/HOST_COMPATIBILITY.md` — qwen subagent support row

### Configuration
- N/A

## Acceptance Criteria

- [ ] Subagent transcripts under
      `~/.qwen/projects/<encoded>/subagents/<session-id>/` backfill into
      `subagent_runs` with `parent_session_id` set to the qwen session id.
- [ ] `agent_id` is read from the sidecar's `agentId` (not the filename stem),
      so a backfill run after live capture inserts **zero** duplicate rows —
      asserted by a test that runs the live writer, then backfill, then counts.
- [ ] `agent_type`, `started_at`, `ended_at`, and `status` are populated from
      the sidecar; a transcript whose sidecar says `status: "failed"` lands as
      `failed`, not `completed`.
- [ ] Missing or unparseable sidecar degrades to the existing mtime heuristic
      rather than skipping the transcript.
- [ ] `parentAgentId` is recorded where present, so nested qwen spawn trees
      reconstruct (or: explicitly deferred with a note, if `subagent_runs` has
      no column for it).
- [ ] `get_project_folder(host="qwen")` (or its replacement) resolves a root
      from which **both** `chats/` and `subagents/` are reachable.
- [ ] Existing Claude-layout backfill behavior is unchanged (regression test).
- [ ] Unit tests use committed qwen fixtures, not `~/.qwen`, so the suite passes
      on a machine with no qwen install.
- [ ] Manual check on real data: sessions `cd4599f4` and `4b8198c0`
      (2026-08-13) yield `subagent_runs` rows after backfill, with at least one
      row carrying `status = "failed"` sourced from its sidecar.

## Impact

- **Priority**: P2 — observability gap; source transcripts persist on disk, so
  nothing is lost permanently and backfill remains possible later.
- **Effort**: Small — one glob shape plus a sidecar reader, behind the ENH-3166
  descriptor.
- **Risk**: Low — additive to a single backfill function; the Claude path is
  held unchanged and `INSERT OR IGNORE` bounds the blast radius.
- **Breaking Change**: No.

## Related

- ENH-3166 — qwen wire-format normalizer and `chats/` discovery (split from
  this issue; supplies the host layout descriptor and materializes the parent
  sessions these rows point at)
- ENH-2918 — kimi wire-format parsing (same deferred posture)
- FEAT-3158 — qwen hook adapter + `ll-init` wiring (the live capture tier whose
  `agent_id` convention backfill must match)
- ENH-2505 — `subagent_runs` spawn-tree infrastructure
- Commit `48cff0aa` — link subagent spawn tree into history.db via
  SubagentStart/Stop hooks

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | history.db schema version history — `subagent_runs` (ENH-2505), `raw_events`/backfill pipeline (ENH-2581), `tool_events.agent_type` (ENH-2497) |
| architecture | docs/reference/API.md | `SubagentRun`/`subagent_tree()` API; documents `ll-session backfill --host {claude-code,codex,opencode,pi}` — the host list this issue extends with qwen |
| reference | docs/reference/HOST_COMPATIBILITY.md | per-host support matrix |

## Status

**Open** | Created: 2026-08-13 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-08-13T23:28:34 - `11cec642-cd22-402c-9028-1a36bba4a9e1.jsonl`
- Consumer follow-up: `get_sessions_folder()` helper + migration of
  `session_log.get_current_session_jsonl`, `fsm/continuity.summarize_completed_state`,
  `cli/ctx_stats._compute_cache_rate_from_jsonl` (qwen `chats/` join regression
  from the root-return change) - 2026-08-14
