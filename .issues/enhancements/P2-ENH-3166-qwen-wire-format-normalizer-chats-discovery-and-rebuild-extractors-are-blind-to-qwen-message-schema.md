---
id: ENH-3166
type: ENH
title: 'Qwen wire-format normalizer: chats/ discovery and rebuild extractors are blind
  to qwen message schema'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-14'
captured_at: '2026-08-14T00:57:49Z'
testable: true
relates_to:
- ENH-3165
---

# ENH-3166: Qwen wire-format normalizer: chats/ discovery and rebuild extractors are blind to qwen message schema

## Summary

Qwen session JSONL is **Claude-shaped at the envelope level but divergent in the
message body**, and no code path knows the difference. Split out of ENH-3165,
which retains the subagent-transcript backfill; this issue covers session
discovery and the raw_events → cache-table extraction path.

A real record from `~/.qwen/projects/<encoded>/chats/<id>.jsonl` (qwen 0.21.6):

```json
{"uuid":"71805e93-…","parentUuid":null,"sessionId":"61c364ea-…",
 "timestamp":"2026-08-13T01:36:19.752Z","type":"user","provenance":"real_user",
 "cwd":"/private/tmp/ll-qwen-spike","version":"0.21.6",
 "message":{"role":"user","parts":[{"text":"Reply with exactly: BYE"}]}}
```

Consequences of the envelope match — **narrower than ENH-3165 originally
claimed**. `sessionId`, `timestamp`, `type`, and `cwd` are all present with
Claude's names, so `_backfill_raw_events` (`lifecycle.py:747`) and
`_backfill_sessions` (`lifecycle.py:708`) parse qwen files **unmodified** once
files reach them. "No sessions extracted" is not the failure mode.

What actually diverges, and where it bites:

1. **`ll-logs` project discovery has no qwen branch, and the fix is not a
   one-line `elif`.** `cli/logs.py:164–172` maps host → projects root for
   `claude-code`/`codex`/`opencode`/`pi` only; qwen and kimi-code fall through
   to `return []`. But the two helpers the loop calls —
   `_has_ll_activity` (`logs.py:88`) and `_extract_cwd_from_project`
   (`logs.py:111`) — both glob `project_dir/*.jsonl`, while qwen's sessions live
   one level deeper under `chats/`. Worse, `_is_ll_relevant`/`_cmd_matches`
   (`logs.py:203`) inspect `message.content[]` `tool_use` blocks, so even with
   the path corrected `_has_ll_activity` returns `False` for every qwen project
   until the body normalizer below exists. Discovery **depends on** the
   normalizer; they cannot be sequenced independently.

2. **Message body shape.** Qwen uses `message.parts[]` where Claude uses
   `message.content[]`:

   | Concern | Claude Code | Qwen 0.21.6 |
   |---------|-------------|-------------|
   | Body key | `message.content[]` | `message.parts[]` |
   | Text block | `{"type":"text","text":…}` | `{"text": …}` |
   | Tool call | `{"type":"tool_use","name":…,"input":…}` | `{"functionCall":{"name":…,"args":…}}` |
   | Tool result | `{"type":"tool_result",…}` inside a `user` record | top-level `type:"tool_result"`, `{"functionResponse":{"id":…,"name":…,"response":…}}` |
   | Assistant role | `"assistant"` | `"model"` |

   So `rebuild()`'s derived extractors (`_backfill_tool_events`,
   message/assistant/skill events — `lifecycle.py:957–…`) yield zero rows for
   qwen even when `raw_events` and `sessions` are correctly populated.

3. **`host` column is stamped from the ambient host, not the ingested files.**
   `_backfill_raw_events` sets `host = resolve_host().name`. Running
   `ll-session backfill --host qwen` under the default config (`orchestration.host_cli`
   = `claude-code`) writes qwen rows tagged `host="claude-code"`. Today's db has
   911,646 `raw_events` rows, all `claude-code` — any per-host query silently
   folds qwen into Claude. `--host` must plumb through to the column.

Qwen also carries signal Claude's extractors have no analogue for and that a
normalizer should not discard: `type:"system"` records with
`subtype:"slash_command"` (`systemPayload.rawCommand`, e.g. `/ll:commit`) map
cleanly onto `skill_events`, and `subtype:"ui_telemetry"` carries
`qwen-code.api_response` token usage for `usage_events`.

## Motivation

Without this, `ll-logs`, `ll-messages`, and every `rebuild()`-derived table are
blind to qwen work — no tool events, no message events, no slash-command
history — and the `host` mislabeling actively corrupts per-host analytics
rather than merely omitting data. ENH-3165's subagent backfill lands
`subagent_runs` rows whose `parent_session_id` points at sessions that only
exist as raw JSON until this issue closes the loop.

## Current Behavior

`discover_all_projects(host="qwen")` returns `[]` — qwen falls through the
host→root chain to the default `return []`. `ll-session backfill --host qwen`
is not an accepted host value, and even if the files were handed to
`_backfill_raw_events` directly, the resulting rows would be tagged
`host="claude-code"` and would derive zero `tool_events`/`message_events` rows
on `rebuild()`, because every extractor reads `message.content[]`.

## Expected Behavior

`discover_all_projects(host="qwen")` returns qwen project paths by globbing
`chats/*.jsonl` and recognizing qwen-shaped ll activity.
`ll-session backfill --host qwen --also-rebuild` writes `raw_events` rows tagged
`host="qwen"` and materializes `sessions`, `tool_events`, `message_events`, and
`assistant_messages` from them, with `parts[]` normalized to `content[]` at the
raw_events→rebuild boundary. Claude-host output is byte-identical to today's.

## Scope Boundaries

**In scope**: the host layout descriptor, qwen record normalization for the four
observed record types (`user`, `assistant`, `tool_result`, `system`), `ll-logs`
discovery helpers, and the `raw_events.host` plumbing.

**Out of scope**: qwen subagent transcripts and `subagent_runs` (ENH-3165);
kimi-code record extraction (ENH-2918); backfilling the 911,646 existing
`claude-code` rows (they are correctly labeled); `skill_events`/`usage_events`
derivation from qwen `system` records — listed under Stretch and droppable.

## Program Design

### Types

```python
@dataclass(frozen=True)
class HostLayout:
    """Per-host description of where session logs live and how to read them."""
    name: str                       # "claude-code" | "qwen" | ...
    projects_root: Path             # ~/.qwen/projects
    session_glob: str               # "chats/*.jsonl" (qwen) | "*.jsonl" (claude)
    normalize: Callable[[dict], dict | None]
```

### Signatures

- `host_layout_for(host: str) -> HostLayout` — single source of truth for per-host session-log layout; raises `KeyError` for unknown hosts so callers fail loudly instead of silently returning `[]`.
- `normalize_qwen_record(record: dict) -> dict | None` — maps `message.parts[]` to `message.content[]`, `functionCall`/`functionResponse` to `tool_use`/`tool_result`, role `model` to `assistant`; returns `None` for records with no Claude-shaped equivalent.
- `_normalize_parts(parts: list[dict]) -> list[dict]` — block-level translation shared by the `assistant` and `tool_result` record paths.
- `discover_all_projects(logger: Logger, *, host: str | None = None, existing_only: bool = False) -> list[Path]` — existing signature, reimplemented over `HostLayout` instead of the inline `if host ==` chain.
- `_backfill_raw_events(conn: sqlite3.Connection, jsonl_files: list[Path], *, host: str | None = None) -> int` — `host` overrides the ambient `resolve_host().name` for the `raw_events.host` column.

### Call Path

1. `ll-logs` / `ll-messages` — call `discover_all_projects()`
2. `discover_all_projects()` → `host_layout_for()` → `_has_ll_activity()` / `_extract_cwd_from_project()`, both globbing `layout.session_glob`
3. `ll-session backfill --host qwen` → `backfill()` → `_backfill_raw_events(host="qwen")`
4. `rebuild()` → `_backfill_sessions()` / `_backfill_tool_events()` — fed normalized records via `layout.normalize`
5. `resolve_host()` — remains the orchestration-CLI selector; it is *not* the source of the ingested-file host

## Implementation Steps

1. Introduce `HostLayout` + `host_layout_for()` with entries for the four
   currently-supported hosts, and reimplement `discover_all_projects` over it
   with no behavior change for Claude.
2. Add the qwen entry (`chats/*.jsonl`) and teach `_has_ll_activity` /
   `_is_ll_relevant` to recognize `functionCall` and `slash_command` records.
3. Write `normalize_qwen_record` against fixtures captured from real qwen
   0.21.6 output; wire it in at the raw_events→rebuild boundary.
4. Thread `--host` into `_backfill_raw_events`'s `host` column.
5. Regression-test the Claude fixture path, add qwen fixtures, and update
   `docs/reference/API.md` + `docs/reference/HOST_COMPATIBILITY.md`.

## Proposed Solution

Introduce an explicit **host layout descriptor** rather than scattered
`if host == "qwen"` branches — one record per host holding:

- `projects_root` (`~/.qwen/projects`)
- `session_glob` (`chats/*.jsonl` for qwen, `*.jsonl` for Claude)
- `subagent_layout` (consumed by ENH-3165)
- `normalize(record) -> dict | None` — maps a host record into the
  Claude-shaped internal form the existing `_backfill_*` extractors already
  consume

Normalize once at the raw_events → rebuild boundary. Do **not** branch inside
each `_backfill_*` extractor; there are six of them and the branch count
multiplies per host. `raw_events` keeps the verbatim source line (its stated
contract), so normalization is a read-time transform and re-running `rebuild()`
after a normalizer fix requires no re-ingest.

kimi-code shares gap shapes 1 and 2 (ENH-2918); its extraction stays out of
scope here, but the descriptor must make kimi a table entry rather than a
refactor.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — host → projects root map (164–172),
  `_has_ll_activity` (88), `_extract_cwd_from_project` (111), `_is_ll_relevant`/
  `_cmd_matches` (203)
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events`
  (747, host column), `rebuild()` extractor chain (913–…)
- `scripts/little_loops/user_messages.py` — `_get_qwen_project_folder`
  (476–490); drop the "wire-format parsing is a follow-up" deferral note
- New: host layout descriptor module (or extend `host_runner.py` if the
  descriptor belongs alongside `resolve_host()`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session backfill --host` plumbing
- Any `ll-logs`/`ll-messages` consumer relying on `discover_all_projects`

### Similar Patterns
- `_get_kimi_project_folder` (`user_messages.py:437`) — non-Claude layout
  resolution already special-cased
- `hooks/adapters/<host>/` — existing per-host directory convention

### Tests
- `scripts/tests/` — new qwen-fixture coverage for discovery + normalizer;
  fixtures modeled on the real records quoted above

### Documentation
- `docs/reference/API.md` — `ll-session backfill --host {…}` host list
- `docs/reference/HOST_COMPATIBILITY.md` — qwen session-log support row

### Configuration
- N/A

## Acceptance Criteria

- [ ] `discover_all_projects(host="qwen")` returns qwen project paths, with
      `_has_ll_activity`/`_extract_cwd_from_project` honoring the `chats/`
      subdirectory rather than `project_dir/*.jsonl`.
- [ ] `_has_ll_activity` recognizes ll activity in qwen records
      (`functionCall`-shaped tool calls, `slash_command` system records) — not
      just Claude `tool_use` blocks.
- [ ] A host layout descriptor supplies projects root, session glob, and record
      normalizer; no new `if host == "qwen"` branches inside individual
      `_backfill_*` extractors.
- [ ] `rebuild()` derives `tool_events`, `message_events`, and
      `assistant_messages` rows from qwen `raw_events` (`parts[]` →
      `content[]`, `functionCall`/`functionResponse` → `tool_use`/`tool_result`,
      role `model` → `assistant`).
- [ ] `ll-session backfill --host qwen` writes `raw_events.host = "qwen"`
      regardless of the ambient `orchestration.host_cli` / `LL_HOST_CLI` value.
- [ ] Existing Claude-host discovery, ingestion, and rebuild behavior is
      byte-identical (regression coverage on the Claude fixture path).
- [ ] Unit tests use committed qwen fixtures (not `~/.qwen`), so the suite
      passes on a machine with no qwen install.
- [ ] Manual check on real data: a qwen session under
      `~/.qwen/projects/-Users-…-little-loops/chats/` yields `sessions`,
      `tool_events`, and `message_events` rows after
      `ll-session backfill --host qwen --also-rebuild`.

## Stretch (defer if it grows the change)

- [ ] `subtype:"slash_command"` system records → `skill_events`
- [ ] `subtype:"ui_telemetry"` `api_response` records → `usage_events`

## Impact

- **Priority**: P2 — observability gap, not a functional break; no data loss
  (source JSONL persists on disk and can be re-ingested at any time).
- **Effort**: Medium — descriptor plumbing plus a normalizer covering four
  record types, with the Claude path held byte-identical.
- **Risk**: Medium — touches the shared `rebuild()` extractor chain that all
  hosts depend on; mitigated by keeping normalization at the boundary and
  regression-testing the Claude fixtures.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-14 | Priority: P2

## Related

- ENH-3165 — qwen subagent-transcript backfill (split from this issue; lands
  `subagent_runs` rows whose parent sessions this issue materializes)
- ENH-2918 — kimi wire-format parsing (same deferred posture, same descriptor)
- FEAT-3158 — qwen hook adapter + `ll-init` wiring (live capture tier)
- FEAT-3155 — qwen path-encoding spike (established `chats/` layout)
- ENH-2581 — `raw_events` + `rebuild()` split this issue extends

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | history.db schema — `raw_events`/rebuild pipeline (ENH-2581) |
| architecture | docs/reference/API.md | `ll-session backfill --host {claude-code,codex,opencode,pi}` — the host list this issue extends |
| reference | docs/reference/HOST_COMPATIBILITY.md | per-host support matrix |
