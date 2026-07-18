---
id: FEAT-2679
title: "F1-prereq (c) — Tool-definition JSON schema catalog for the Anthropic Messages API"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T19:30:38Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2672
- FEAT-2673
blocks:
- FEAT-2672
- FEAT-2673
spike_needed: true
learning_tests_required:
- anthropic
---

# FEAT-2679: F1-prereq (c) — Tool-definition JSON schema catalog for the Anthropic Messages API

## Summary

New code path that assembles full Anthropic Messages API tool-definition JSON
(`{"name", "description", "input_schema"}` per tool, with an optional
`cache_control` key) for little-loops' own tools. Today, no such catalog
exists anywhere in the codebase: the only "tools" surface that flows through
`fsm/runners.py` → `subprocess_utils.run_claude_command()` → `host_runner.py`
is a flat `list[str]` of tool *names* (`ActionRunner.run()`'s `tools` param),
serialized as a `--tools` CSV flag by `ClaudeCodeRunner.build_streaming()`
(`host_runner.py:263-264`). This is EPIC-2456 § F1's third cache-stability
prerequisite, alongside FEAT-2671 (content-hash fragment store) and FEAT-2672
(deferred tool loading).

## Current Behavior

- `fsm/runners.py`'s `ActionRunner.run()` Protocol accepts `tools:
  list[str] | None` — bare tool names, no schema bodies.
- `host_runner.py`'s `ClaudeCodeRunner.build_streaming()` joins that list into
  a `--tools` CSV flag passed to the `claude` CLI subprocess.
- `CodexRunner`/`GeminiRunner` silently ignore `tools` with a
  `CapabilityNotSupported` warning (`host_runner.py:501-510`, `871-878`);
  `OpenCodeRunner`/`PiRunner` raise `HostNotConfigured` unconditionally.
- `mcp_call.py` performs a JSON-RPC `tools/list`/`tools/call` handshake
  against servers in `.mcp.json` (currently empty in this repo), but it is a
  standalone one-shot CLI — it queries/invokes a single tool per process and
  never assembles a tool-schema catalog into a prompt-assembly path.
- No code anywhere serializes full tool-definition JSON into a request the
  way the Anthropic Messages API's `tools` param (or the `defer_loading`/
  `tool_reference` pattern) expects.

## Expected Behavior

A catalog-assembly function exists that, given little-loops' own tool/skill
set, produces the full Anthropic Messages API `tools` array — each entry
carrying `name`, `description`, `input_schema`, and (when applicable)
`cache_control`. This catalog is what `FEAT-2673`'s `build_anthropic_request()`
serializes into the request body, and what `FEAT-2672`'s deferred-loading
stub/resolve mechanism attaches to.

## Motivation

This is the architectural gap both FEAT-2672 and FEAT-2673 already ran into
during their own confidence checks:

- **FEAT-2672** ("deferred tool loading"): its AC "a deferred tool invoked by
  the model resolves to its full definition" has no existing data structure
  to attach to — there is no full tool definition to defer in the first
  place. Readiness dropped to 45/100 (later 62/100) specifically citing this
  gap.
- **FEAT-2673** ("cache_control: ephemeral integration"): its
  `build_anthropic_request()` is specified to mark `cache_control: ephemeral`
  on "system, tool, and stable-skill blocks" — but it assumes tool-definition
  blocks already exist to mark. They don't.

Without this catalog, neither F1 cache-stability prerequisite has anything
concrete to operate on, and F1 itself (`cache_control` on tool blocks) has no
tool blocks to mark.

## Proposed Solution

Derive the catalog from one of two existing surfaces rather than inventing a
third:

1. Claude Code's own tool/skill definitions (the source Claude Code itself
   uses to build its tool list) — would need investigation into whether
   little-loops has read access to that definition set outside the host CLI
   subprocess boundary.
2. The MCP `tools/list` surface `mcp_call.py` already exercises — extend it
   from a one-shot single-tool query into a catalog-assembly function that
   enumerates all configured MCP servers' tools into the Anthropic API shape.

Both options need a spike to determine feasibility before committing;
this issue should not proceed straight to config plumbing (the same lesson
FEAT-2672's confidence check already surfaced for a related mechanism).

## Integration Map

### Files to Modify
- TBD — depends on which source surface (Claude Code tool defs vs. MCP) the
  spike selects.
- `scripts/little_loops/mcp_call.py` — likely extension point if MCP is the
  chosen source (already performs `tools/list`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()`
  (lines ~263-264) is the current `--tools` CSV assembly site; would need to
  consume the new catalog once it exists.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
  (~282-328), the `resolve_host()` call site FEAT-2671/FEAT-2672 already
  identified as the actual integration point (not `fsm/runners.py`).

### Similar Patterns
- `scripts/little_loops/mcp_call.py` — existing JSON-RPC `tools/list`
  handshake, the closest structural precedent for enumerating tool schemas.

### Tests
- TBD — new test file once the source surface is chosen.

### Documentation
- N/A until implementation approach is decided.

### Configuration
- N/A — this issue produces a data structure, not a config surface; config
  gating belongs to FEAT-2672/FEAT-2673.

## Implementation Steps

1. Spike: determine whether Claude Code's own tool/skill definitions are
   readable from little-loops' process, or whether the MCP `tools/list`
   surface is the more viable catalog source.
2. Build the catalog-assembly function producing Anthropic Messages API
   `tools` array entries (`name`, `description`, `input_schema`,
   optional `cache_control`).
3. Add a learning-test claim proving the `anthropic` SDK's `tools=[...]`
   param accepts a `cache_control` key per-block and the API honors it
   (extends the existing `learning_tests_required: [anthropic]` proof,
   which currently only covers basic SDK-client claims).
4. Wire the catalog as the input FEAT-2673's `build_anthropic_request()` and
   FEAT-2672's deferred-loading stub/resolve mechanism both consume.

## Acceptance Criteria

- [ ] A function exists that produces a full Anthropic Messages API `tools`
      array for little-loops' own tool set (not just names).
- [ ] Each catalog entry includes `name`, `description`, and `input_schema`
      at minimum.
- [ ] Learning test proves the `anthropic` SDK/API accepts `cache_control`
      on a tool-definition block.
- [ ] FEAT-2672 and FEAT-2673 can each name this catalog as their input data
      structure without further architectural investigation.

## Status

**Open** | Created: 2026-07-18 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-07-18T19:31:27 - `34636038-c9ad-4b77-b634-680b13ded0fc.jsonl`
