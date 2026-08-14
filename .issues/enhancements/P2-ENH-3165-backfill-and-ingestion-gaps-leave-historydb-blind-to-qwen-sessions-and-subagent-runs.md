---
id: ENH-3165
type: ENH
title: Backfill and ingestion gaps leave history.db blind to qwen sessions and subagent
  runs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-13'
captured_at: '2026-08-13T23:28:23Z'
---

# ENH-3165: Backfill and ingestion gaps leave history.db blind to qwen sessions and subagent runs

## Summary

Qwen sessions and their subagent spawns never reach `.ll/history.db`: on
2026-08-13 the `sessions` table held 12,277 claude rows and **zero** qwen
rows, and `subagent_runs` had no rows for recent qwen sessions (e.g.
`cd4599f4` with 8 subagent transcripts on disk) even though transcripts
exist under `~/.qwen/projects/<encoded>/subagents/<session-id>/`. The live
capture tier is already landed (FEAT-3158 hook adapter; fires once
`ll-init --hosts qwen` has run per project), but the **backfill/repair
tier** has three gaps that make qwen history unrecoverable:

1. **`ll-logs` project discovery has no qwen branch.**
   `scripts/little_loops/cli/logs.py` (~lines 164–172) maps host →
   projects root for `claude-code`/`codex`/`opencode`/`pi` only; qwen
   (and kimi-code) fall through to `return []`, so ll-* discovery over
   session logs is blind to qwen projects.

2. **`_backfill_subagent_runs` assumes Claude's transcript layout.**
   `scripts/little_loops/session_store/writers.py:1897` globs
   `sessions_root.glob("*/subagents")` — the Claude shape
   `<session-dir>/subagents/agent-*.jsonl`. Qwen inverts the nesting:
   `~/.qwen/projects/<encoded>/subagents/<session-id>/agent-*.jsonl`,
   one level shallower with the session id as the child directory.
   Worse, `get_project_folder(host="qwen")` (`user_messages.py`,
   `_get_qwen_project_folder`) returns the sibling `chats/` folder, so
   `ll-session backfill --host qwen` passes a root where the glob can
   never match.

3. **Qwen chat JSONL schema parsing is unimplemented.**
   `_get_qwen_project_folder`'s docstring defers wire-format parsing as
   a follow-up (same posture as kimi's ENH-2918), so even with
   discovery fixed, `ll-session backfill --host qwen` extracts no
   sessions/messages/tool rows from `chats/*.jsonl`.

Test blindness accompanies the code gap: `test_enh_2505_subagent_runs.py`
covers the spawn-tree lifecycle and backfill only against the
Claude-shaped layout.

## Motivation

Every qwen session silently drops its session/subagent observability.
Live hooks (post `ll-init --hosts qwen`) only capture spawns from the
moment of installation onward, and only `running`/`completed` states for
new sessions — past runs, and any `failed`/`timeout` states that need
transcript evidence, are recoverable only through backfill. With all
three tiers broken, `subagent_tree()`/`subagent_retries()`/`subagent_budget()`
queries and any sprint/loop analytics built on them are permanently
incomplete for qwen.

## Scope Notes

- kimi-code shares gap shapes 1 and 3 (ENH-2918 posture); keep the fix
  host-parameterized, but kimi extraction is out of scope here.
- QwenRunner's missing `--agent` CLI flag is a documented upstream
  limitation, not part of this issue.

## Acceptance Criteria

- [ ] `ll-logs` project discovery returns qwen project paths when
      `host="qwen"` (via `LL_HOOK_HOST` or explicit flag).
- [ ] `ll-session backfill --host qwen` ingests qwen sessions from
      `~/.qwen/projects/<encoded>/chats/` into the `sessions` table.
- [ ] Subagent transcripts under `~/.qwen/projects/<encoded>/subagents/<session-id>/`
      backfill into `subagent_runs` with `parent_session_id` set to the
      qwen session id (idempotent, same `INSERT OR IGNORE` posture).
- [ ] Unit tests cover the qwen transcript layout (backfill glob shape)
      alongside the existing Claude-layout coverage.
- [ ] Verified against real data: sessions `cd4599f4` and `4b8198c0`
      (2026-08-13) yield `subagent_runs` rows after backfill.

## Related

- ENH-2918 — kimi wire-format parsing (same deferred posture for qwen schema)
- FEAT-3158 — qwen hook adapter + ll-init wiring (the live capture tier)
- ENH-2505 — subagent_runs spawn-tree infrastructure
- Commit `48cff0aa` — link subagent spawn tree into history.db via SubagentStart/Stop hooks


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | history.db schema version history — `subagent_runs` (ENH-2505), `raw_events`/backfill pipeline (ENH-2581), `tool_events.agent_type` (ENH-2497) |
| architecture | docs/reference/API.md | `SubagentRun`/`subagent_tree()` API; documents `ll-session backfill --host {claude-code,codex,opencode,pi}` — the host list this issue extends with qwen |

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-13T23:28:34 - `11cec642-cd22-402c-9028-1a36bba4a9e1.jsonl`
