---
id: ENH-1661
type: ENH
priority: P4
status: open
discovered_date: 2026-05-23
discovered_by: conversation
confidence_score: 60
outcome_confidence: 55
---

# ENH-1661: Make ll-action self-advertising so non-Claude-Code agents find it

## Summary

`ll-action` is the right surface for coding agents in *any* host (Codex, Cursor, aider, gptme, plain scripts) to invoke ll skills programmatically — but those agents have no reason to know it exists. They will either reinvent the workflow (spawn `claude -p` themselves, write ad-hoc Python) or skip ll skills entirely. A small amount of self-advertisement closes this gap without building anything network-protocol-shaped (MCP, HTTP, etc.).

## Problem

Today's discovery paths:

- **Claude Code session**: user types `/ll:help`, sees skills, invokes via the Skill tool. Doesn't need `ll-action`.
- **Codex / Cursor / other host with shell**: user has to *tell* the agent that `ll-action` exists, or the agent has to stumble onto it via `which ll-action`. Most agents won't.
- **CI / scripts**: someone wrote the script, so they already know.

The gap is the middle row. The HarnessAPI paper (docs/research/HarnessAPI-A-Skill-First-Framework.md) reaches for MCP to solve this, but for our shape — local CLI, agent already has Bash — a discoverability nudge is enough.

## Proposal

Three small additions, any subset:

1. **`ll-doctor` mentions `ll-action`** in its output when a host other than `claude` is detected, pointing the user at `ll-action list` as the agent-callable entry point.
2. **Top of `ll-action --help`** includes a one-paragraph "For agents:" blurb: "If you are an LLM coding agent, run `ll-action list --json` to discover skills, then `ll-action invoke <skill> --args ...` to call one." This text gets surfaced any time an agent runs `--help`.
3. **A `docs/AGENT_USAGE.md`** (or section in existing docs) that documents the agent-facing CLI contract: `list`, `invoke`, `--output stream-json` event shape, exit codes. Linked from `ll-adapt-skills-for-codex` output so Codex projects bootstrap with the pointer.

Recommend starting with #2 — single-file change, zero new surface area, immediately useful next time anyone uses ll in a non-Claude-Code host.

## Acceptance Criteria

- [ ] `ll-action --help` includes a clearly-labeled "For LLM agents" paragraph at the top of the epilog
- [ ] The blurb explicitly names `list --json` and `invoke` as the discovery+invocation pair
- [ ] (Optional) `ll-doctor` mentions `ll-action` when host != `claude`
- [ ] (Optional) `docs/AGENT_USAGE.md` written and linked from README + `ll-adapt-*` command output

## Out of Scope

- An MCP server wrapping ll-action (separately considered and rejected in conversation as solving a problem we don't have — agents in scope already have shell access)
- Long-running daemon mode for `ll-action` (would solve Python startup cost, but no evidence that cost is actually painful yet)

## Related

- [[ENH-1660]] — companion issue, adds the per-skill `args` hint that the discovered agent then needs
- docs/research/HarnessAPI-A-Skill-First-Framework.md — source of the framing
