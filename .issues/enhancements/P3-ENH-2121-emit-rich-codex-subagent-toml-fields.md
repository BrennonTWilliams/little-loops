---
id: ENH-2121
title: Emit rich Codex subagent TOML fields in ll-adapt-agents-for-codex
type: ENH
priority: P3
status: cancelled
captured_at: "2026-06-13T00:00:00Z"
discovered_date: 2026-06-13
discovered_by: capture-issue
parent: EPIC-1463
relates_to: [FEAT-1527, ENH-1533, ENH-1529]
labels: [codex, host-runner, agents, host-compat]
---

# ENH-2121: Emit rich Codex subagent TOML fields in ll-adapt-agents-for-codex

> **CANCELLED 2026-06-25 — absorbed into FEAT-2260.** `ll-adapt-agents-for-codex`
> is being generalized into the host-parameterized adapter (FEAT-2260,
> ARCHITECTURE-049). Implementing the rich-field emission as a standalone Codex
> patch first, then re-touching the same emitter during the `--host` refactor,
> is a double-touch. This scope now lives as FEAT-2260's "Codex-host emitter
> parity" acceptance criterion, so the richer fields land once, inside the
> generic adapter. The source-mapping detail, scope boundaries, and Codex schema
> link below remain the authoritative spec for that criterion. See the
> Phase-1 sequencing in the EPIC-1463/2178/2257/2258 plan.

## Summary

`ll-adapt-agents-for-codex` generates `.codex/agents/*.toml` subagent
definitions from ll's `agents/*.md` files, but emits only four fields:
`name`, `description`, `model`, and `developer_instructions`. The Codex
subagent schema (<https://developers.openai.com/codex/subagents>) supports
several additional optional fields that ll currently drops, producing
subagent definitions that are strictly weaker than what Codex supports.

## Motivation

The dropped fields map directly onto ll concepts and feature work already in
flight:

- `model_reasoning_effort` — effort tuning per agent (ll has effort concepts
  in loops and harness runs).
- `sandbox_mode` — per-agent execution constraint; the exact axis ENH-1529
  exposed on `CodexRunner` build methods (`off` / `read-only` /
  `write-to-cwd` / `network`). An agent's TOML could declare its own sandbox
  rather than inheriting the runner default.
- `mcp_servers` — scope which MCP servers an agent may reach; ll has MCP
  integration but no per-agent scoping in the Codex bridge.
- `skills.config` — scope which skills an agent may invoke.
- `nickname_candidates` — ergonomic aliases for `/agent` thread switching.

Without these, a Codex user invoking an ll-generated subagent gets a lossy
persona: correct instructions and model, but none of the execution/tool
scoping the source agent intends.

## Current Behavior

`scripts/little_loops/cli/adapt_agents_for_codex.py` writes a TOML containing
only `name`, `description`, `model`, `developer_instructions`. Confirmed: none
of `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, `skills.config`,
`nickname_candidates` are referenced anywhere in the adapter.

## Expected Behavior

The adapter maps available source-agent metadata onto the richer Codex schema
when present, and omits fields with no source mapping (Codex inherits from the
parent session for omitted optional fields, so omission stays safe).

## Acceptance Criteria

- `adapt_agents_for_codex.py` emits `sandbox_mode` when the source agent
  declares an execution constraint (align values with ENH-1529's
  `off`/`read-only`/`write-to-cwd`/`network`).
- `model_reasoning_effort` emitted when a source agent specifies a reasoning
  effort.
- `mcp_servers` and `skills.config` emitted when the source agent's tool/MCP
  access can be derived from its `tools:` frontmatter.
- Fields with no source mapping are omitted (not emitted empty), preserving
  Codex's parent-inheritance semantics.
- `scripts/tests/test_adapt_agents_for_codex.py` asserts each new field is
  emitted for a fixture agent that declares it and omitted otherwise.
- Regenerated `.codex/agents/*.toml` validated against the documented schema.

## Scope Boundaries

- Emitting `nickname_candidates` is **out of scope** — no clean source mapping
  exists in ll agent frontmatter; defer to a follow-on once a canonical alias
  system is established.
- Inventing new `agents/*.md` frontmatter fields (e.g., `sandbox_mode:`,
  `reasoning_effort:`) to drive TOML output is **out of scope**; derive from
  existing `tools:` frontmatter and model identifiers only.
- Full Codex Skills API scoping beyond what is derivable from `tools:` is
  **out of scope** for this issue.
- Runtime invocation changes (how ll agents are executed) are **out of scope**;
  this is a TOML generation/adaptation concern only.

## Implementation Steps

1. Audit `adapt_agents_for_codex.py` and `agents/*.md` frontmatter to document
   available source fields for each target TOML key.
2. Implement `sandbox_mode` mapping: derive from agent `tools:` or execution
   constraint hints; align value vocabulary with ENH-1529
   (`off` / `read-only` / `write-to-cwd` / `network`).
3. Implement `model_reasoning_effort` mapping: derive from model identifier or
   explicit effort hint in agent frontmatter.
4. Implement `mcp_servers` and `skills.config` derivation from `tools:`
   frontmatter; emit as TOML arrays, omit when no mapping exists.
5. Extend `scripts/tests/test_adapt_agents_for_codex.py` with fixture agents
   that declare each new field and assert both emit (field present) and omit
   (field absent) behavior.
6. Regenerate `.codex/agents/*.toml` and validate against the documented Codex
   subagent schema.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — TOML emitter logic

### Dependent Files (Callers/Importers)
- N/A — `ll-adapt-agents-for-codex` is a standalone generator with no Python callers

### Similar Patterns
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — sibling adapter for
  skills; may share field-derivation utility helpers

### Tests
- `scripts/tests/test_adapt_agents_for_codex.py` — extend with per-field
  fixture agents

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — `[^agent]` footnote references this
  gap; update once fixed

### Configuration
- N/A

## Impact

- **Priority**: P3 — Additive quality improvement; Codex users get a lossy
  subagent persona without these fields, but minimal interop still works.
- **Effort**: Small — Adapter script extension plus test fixtures; no new
  infrastructure or frontmatter schema changes required.
- **Risk**: Low — All new fields are optional in the Codex schema; Codex
  inherits from the parent session for omitted fields. The change is purely
  additive.
- **Breaking Change**: No

## Notes

- Source mapping is the hard part: ll `agents/*.md` frontmatter does not have
  1:1 fields for all of these. Where there is no clean mapping (e.g.
  `mcp_servers`), prefer deriving from `tools:` rather than inventing new
  frontmatter; document the mapping in the adapter docstring.
- Coordinate value vocabulary with ENH-1529 so `sandbox_mode` means the same
  thing at the runner and the TOML layers.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/cli/adapt_agents_for_codex.py` | File to modify |
| `scripts/tests/test_adapt_agents_for_codex.py` | Test coverage to extend |
| `docs/reference/HOST_COMPATIBILITY.md` | `[^agent]` footnote references this gap |
| <https://developers.openai.com/codex/subagents> | Authoritative Codex subagent schema |

## Verification Notes

2026-06-18 (ACCURATE): `adapt_agents_for_codex.py` confirmed to emit only `name`, `description`, `model`, `developer_instructions` — none of `sandbox_mode`, `model_reasoning_effort`, `mcp_servers`, `skills.config`, or `nickname_candidates` are referenced. Current behavior claim is accurate.

## Status

**Cancelled** | Created: 2026-06-13 | Cancelled: 2026-06-25 (absorbed into FEAT-2260) | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-13T23:48:27 - `b252dabd-1baf-4665-95fb-2099fac23f7c.jsonl`
