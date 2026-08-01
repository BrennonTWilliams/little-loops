---
id: FEAT-2911
title: "Research spike: kimi-cli binary surface, hook events, plugin discovery"
type: FEAT
status: done
priority: P2
parent: EPIC-2910
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
---

# FEAT-2911: Research spike: kimi-cli binary surface, hook events, plugin discovery

## Summary

Research spike auditing the `kimi` binary surface, lifecycle hook model, and
plugin/skill discovery — the three questions that blocked all downstream
EPIC-2910 children. **Done**: artifact
`thoughts/research/kimi-cli-surface.md` written 2026-07-29 against kimi
0.30.0.

Findings digest:

- **Binary surface**: `kimi -p --output-format stream-json` — OpenAI-style
  assistant/tool_calls/tool events plus a terminal meta
  `session.resume_hint`; no result event, no token-usage events. No
  single-blob JSON mode — blocking = consume the final assistant event
  (Codex pattern). `-p` implies auto permissions and rejects
  `--yolo`/`--auto`/`--plan`. Native `--agent` (conflicts with `--continue`).
- **Hooks**: via `[[hooks]]` in `config.toml` or the plugin manifest; stdin
  JSON is claude-shaped with drift rows — UserPromptSubmit `prompt` is a
  block array; PostToolUse `tool_output` not `tool_response`;
  SubagentStart/Stop use `agent_name` + inline `response`, no
  `transcript_path`; SessionEnd native.
- **Session logs**: mapped by `~/.kimi-code/session_index.jsonl`
  (workDir → sessionDir) and `workspaces.json`.
- **Skills/agents/commands**: SKILL.md / agents / commands near-1:1
  compatible (extra frontmatter keys tolerated); `kimi.plugin.json` with id
  `ll` preserves the `/ll:` namespace.

## Motivation

Before any kimi-code adapter code lands, we need to know what the `kimi`
binary actually supports — what flags to call, what hook events fire, and
what the plugin surface looks like. Analogous to FEAT-2179 (Gemini spike)
and FEAT-1483 (Codex spike). The artifact answers all three questions with
evidence from the actual binary, so the runner/adapter children are
mechanical translations rather than guesswork.

## Implementation Steps

1. ✅ Install kimi-code locally; capture `kimi --help` (kimi 0.30.0).
2. ✅ Audit headless/streaming flags and JSON output modes.
3. ✅ Audit lifecycle hook events, registration surface, and payload shapes
   (incl. the claude-shaped drift rows).
4. ✅ Audit plugin/skill/command discovery (`kimi.plugin.json`, `.kimi-code/`).
5. ✅ Map session-log discovery (`session_index.jsonl`, `workspaces.json`).
6. ✅ Write findings to `thoughts/research/kimi-cli-surface.md` (2026-07-29).

## Integration Map

### Files to Modify

- None — research artifact only.

### New Files

- `thoughts/research/kimi-cli-surface.md` — findings artifact (written 2026-07-29)

### Dependent Files

- `scripts/little_loops/host_runner.py` — `KimiRunner` flag translation source (FEAT-2914)
- `scripts/little_loops/hooks/adapters/kimi/` — payload drift rows (FEAT-2974)
- `docs/reference/HOST_COMPATIBILITY.md` — footnote target for the kimi-code column (ENH-2919)

## Impact

- **Priority**: P2 — blocks every downstream EPIC-2910 child.
- **Effort**: S — read-only research, single artifact.
- **Risk**: Low — no code changes.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Done** | Created: 2026-07-29 | Completed: 2026-07-29 | Priority: P2
