---
id: FEAT-2679
title: "F1-prereq (c) \u2014 Tool-definition JSON schema catalog for the Anthropic\
  \ Messages API"
type: FEAT
priority: P2
status: done
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
decision_needed: false
learning_tests_required:
- anthropic
confidence_score: 85
outcome_confidence: 59
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 10
score_change_surface: 25
implementation_order_risk: true
size: Very Large
completed_at: '2026-07-18T19:59:24Z'
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

> ⚠ **Codebase Research Correction**: `mcp_call.py`'s `call_mcp_tool()`
> (lines 117-312) only implements `initialize` → `tools/call`
> (line 261: `"method": "tools/call"`). There is **no `tools/list` call
> anywhere in the file or the codebase** — `grep "tools/list"` matches only
> this issue's and FEAT-2672's prose, never code. The caller must already
> know the tool name (`server_name, tool_name = args.spec.split("/", 1)` in
> `main()`, line 347); nothing enumerates *all* of a server's tools. `.mcp.json`
> also currently has zero configured servers (`{"mcpServers": {}}`), so even
> a `tools/list` extension would have nothing to enumerate today. The MCP
> option (Proposed Solution #2) requires adding `tools/list` from scratch,
> not "extending" an existing enumeration call.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

A third source surface already exists and is already implemented, unlike
Options 1 and 2 above (which both require new investigation/code):

**Option A**: Claude Code's own tool/skill definitions (source Claude Code
itself uses to build its tool list) — would need investigation into whether
little-loops has read access to that definition set outside the host CLI
subprocess boundary. *(= existing Proposed Solution option 1, verbatim)*

**Option B**: The MCP `tools/list` surface — per the correction above, this
does not yet exist in `mcp_call.py` and would need to be built from
scratch, and `.mcp.json` has zero configured servers today, so there is
nothing to enumerate even once built. *(= existing Proposed Solution
option 2, corrected)*

**Option C**: little-loops' own `skills/*/SKILL.md`, `commands/*.md`, and
`agents/*.md` frontmatter — already readable today via
`scripts/little_loops/frontmatter.py:parse_skill_frontmatter()` (lines
175-217, canonical SKILL.md frontmatter reader) and already enumerated by
two existing precedents: `scripts/little_loops/cli/action.py:_load_skills()`
(lines 45-64, walks `skills/*/SKILL.md` → `{name, description, args}`,
exposed via `ll-action list`) and
`scripts/little_loops/cli/artifact.py:_load_skill_catalog()` (line 24+,
used by the policy-builder artifact to stamp a skill catalog into
generated HTML). Neither `name` nor `description` needs new plumbing;
`input_schema` would need to be derived from each skill's `args`/
`argument-hint` frontmatter field (currently a loose free-text hint string,
not structured JSON Schema) or hand-authored per tool, following the
`_str()`/`_int()`/`_schema()` typed-field-builder pattern in
`scripts/little_loops/generate_schemas.py` (lines 33-74) — the repo's only
existing JSON-Schema-authoring convention, though it targets `LLEvent`
wire-format schemas, not Anthropic `input_schema` blocks.

**Recommended**: Option C for the spike's first investigation pass — it
requires no new read-access boundary (Option A) and no new protocol
surface (Option B), reusing `parse_skill_frontmatter()` and the
`_load_skills()`/`_load_skill_catalog()` precedents directly. The open
question the spike must resolve is whether `args`/`argument-hint`
free-text is sufficient to derive a real `input_schema`, or whether schemas
need hand-authoring per tool (per the `generate_schemas.py` precedent).

> **Selected:** Option C — only option with existing reusable enumeration
> precedent and a live test pattern to extend.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-18.

**Selected**: Option C — little-loops' own `skills/*/SKILL.md`,
`commands/*.md`, and `agents/*.md` frontmatter

**Reasoning**: Option C is the only source surface with existing, tested
enumeration code to build on — `parse_skill_frontmatter()`
(`frontmatter.py:175-217`) plus two live catalog-builder precedents
(`_load_skills()` in `cli/action.py:45-64`, `_load_skill_catalog()` in
`cli/artifact.py:24+`) already produce `{name, description}` for every
skill/command with zero new plumbing. Option A has no codebase precedent at
all — `host_runner.py` treats every host CLI as an opaque `subprocess.Popen`
boundary with no channel to read a host's internal tool definitions back
out, so it would require inventing a new access mechanism from scratch with
unproven feasibility. Option B requires building `tools/list` in
`mcp_call.py` from scratch (confirmed absent everywhere in the codebase)
against a `.mcp.json` with zero configured servers, so even a working
implementation would enumerate nothing in this repo today. Option C's own
open gap — deriving `input_schema` from the free-text `args`/
`argument-hint` field, and enumerating `agents/*.md` (which no existing
function walks) — is real but narrower than either alternative's blocking
gap, and is the spike's first investigation target per the existing
"Recommended" note above.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A — Claude Code internal tool/skill defs | 0/3 | 0/3 | 0/3 | 0/3 | 0/12 |
| B — MCP `tools/list` surface | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| C — little-loops skill/command/agent frontmatter | 2/3 | 2/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Option A: zero call sites, zero utilities, zero test patterns for reading
  Claude Code's internal tool-definition set; `host_runner.py`'s
  `HostInvocation`/`HostRunner` Protocol never exposes a read channel back
  from the host CLI subprocess.
- Option B: `_send_jsonrpc()` (`mcp_call.py:67-114`) is method-agnostic and
  reusable, but `tools/list` is confirmed absent everywhere in
  `scripts/little_loops/` (only appears in issue-file prose), and
  `.mcp.json` currently has `{"mcpServers": {}}` — nothing to enumerate.
- Option C: `_load_skills()` (`cli/action.py:45-64`, 1 prod call site, 6
  tests) and `_load_skill_catalog()` (`cli/artifact.py:24-56`, 1 prod call
  site) already enumerate `skills/*/SKILL.md` (and `commands/*.md`) into
  catalog dicts; `TestLoadSkills` (`test_action.py:124-195`) gives the spike
  a live test pattern to extend directly.

## Integration Map

### Files to Modify
- TBD — depends on which source surface (Claude Code tool defs vs. MCP vs.
  skill/command frontmatter) the spike selects.
- `scripts/little_loops/mcp_call.py` — extension point if MCP is the
  chosen source; note `tools/list` does not exist yet in this file (see
  Codebase Research Correction above) and would need to be added, not
  extended.
- `scripts/little_loops/cli/action.py` (`_load_skills()`, lines 45-64) and/or
  `scripts/little_loops/cli/artifact.py` (`_load_skill_catalog()`, line 24+)
  — likely extension points if the skill/command frontmatter source (Option
  C) is chosen; both already enumerate `skills/*/SKILL.md` into
  `{name, description}` shape.
- `scripts/little_loops/generate_schemas.py` — potential home for a shared
  typed-field JSON-Schema-builder pattern (`_str()`/`_int()`/`_schema()`,
  lines 33-74) if `input_schema` bodies are hand-authored rather than
  derived from frontmatter.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()`
  (lines ~263-264) is the current `--tools` CSV assembly site; would need to
  consume the new catalog once it exists.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
  (~282-328), the `resolve_host()` call site FEAT-2671/FEAT-2672 already
  identified as the actual integration point (not `fsm/runners.py`).

### Similar Patterns
- `scripts/little_loops/mcp_call.py` — existing JSON-RPC transport
  (`_send_jsonrpc()`, lines 67-114; `initialize` handshake, lines 211-226),
  the closest structural precedent for a future `tools/list` call, though
  `tools/list` itself does not exist yet (see correction above).
- `scripts/little_loops/cli/action.py:_load_skills()` (lines 45-64) and
  `scripts/little_loops/cli/artifact.py:_load_skill_catalog()` (line 24+)
  — existing catalog-builder precedents that already enumerate
  `skills/*/SKILL.md` via `frontmatter.py:parse_skill_frontmatter()`
  (lines 175-217).
- `scripts/little_loops/generate_schemas.py` — `_schema()` (lines 57-74)
  and typed-field helpers (`_str()`, `_int()`, etc.) show the repo's
  convention for hand-authored JSON-Schema property dicts; also see
  `BLIND_COMPARATOR_SCHEMA` in `scripts/little_loops/fsm/evaluators.py`
  (lines 176-201) for an `input_schema`-shaped module-level dict constant.
- `scripts/little_loops/host_runner.py` — `CapabilityEntry`/`HookEntry`/
  `CapabilityReport` frozen-dataclass trio (lines 118-156) is the repo's
  established "list of small frozen dataclass entries wrapped in a report"
  shape, a structural precedent a `ToolDefinition` dataclass could mirror.
- `scripts/little_loops/adapters/codex.py:_format_agent_toml()` (lines
  207-247) and `CodexEmitter.emit_skill()`/`emit_command()` (lines 255-340+)
  — parallel "read SKILL.md frontmatter → derive rich fields → emit a
  different host's definition format" conversion, structurally analogous
  to converting little-loops skills into Anthropic `tools` entries.

### Tests
- `scripts/tests/test_mcp_call.py` — existing test pattern to model after:
  one `Test<Behavior>` class per unit of behavior, mocking `subprocess.Popen`
  via `_make_proc_mock()` (helper) and `patch("little_loops.mcp_call.subprocess.Popen", ...)`.
  A new catalog-assembly test file would likely follow this same
  class-per-behavior structure.
- `scripts/tests/test_generate_schemas.py` — precedent for testing
  schema-dict output shape if the catalog reuses `generate_schemas.py`'s
  builder pattern.
- `scripts/tests/test_host_runner.py`, `test_subprocess_utils.py`,
  `test_fsm_runners.py` — existing coverage of the `tools: list[str] | None`
  pass-through chain; would need new assertions once that chain carries
  full tool-definition objects instead of bare names.
- No dedicated test exists yet for `cli/action.py:_load_skills()` or
  `cli/artifact.py:_load_skill_catalog()` — a gap if Option C is chosen.

### Documentation
- N/A until implementation approach is decided.

### Configuration
- N/A — this issue produces a data structure, not a config surface; config
  gating belongs to FEAT-2672/FEAT-2673.

## Implementation Steps

1. Spike: determine whether Claude Code's own tool/skill definitions are
   readable from little-loops' process, whether the MCP `tools/list`
   surface (which must be built from scratch — see correction above) is
   the more viable catalog source, or whether little-loops' own
   `skills/*/SKILL.md`/`commands/*.md` frontmatter (Option C — already
   readable via existing `_load_skills()`/`_load_skill_catalog()`
   precedents) is sufficient.
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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 59/100 → LOW

### Concerns
- The Integration Map's "Files to Modify" subsection still reads "TBD —
  depends on which source surface... the spike selects," even though the
  Decision Rationale section already selected Option C. The Integration Map
  wasn't updated post-decision, which could mislead an implementer who skims
  only that section.

### Outcome Risk Factors
- Ambiguity: whether the existing `args`/`argument-hint` free text is
  sufficient to derive `input_schema`, or whether schemas need hand-authoring
  per tool, remains an unresolved design detail the spike must still resolve
  — moderate risk of iteration once implementation starts.
- Test coverage: no dedicated test exists yet for `_load_skill_catalog()`,
  and the new catalog-assembly function has no existing test to extend —
  write tests first (test-first, per this repo's tdd_mode) alongside the new
  code rather than after.
- Complexity: reusing the `_load_skills()`/`_load_skill_catalog()`
  precedents is straightforward, but assembling a new catalog with
  `input_schema` plus a learning-test claim for `cache_control` spans
  multiple modules (`frontmatter.py`, `action.py`/`artifact.py`,
  `generate_schemas.py`) — moderate cross-module depth, not a single-file
  change.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-18
- **Reason**: Issue too large for single session (score: 11/11, Very Large)

### Decomposed Into
- FEAT-2680: F1-prereq (c.1) — Catalog-assembly function deriving Anthropic
  tool definitions from skill/command/agent frontmatter
- FEAT-2681: F1-prereq (c.2) — Learning test: anthropic SDK/API accepts
  cache_control on a tool-definition block

## Status

**Done** | Created: 2026-07-18 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `478e94ef-30f6-4532-a6ed-1ba334c74117.jsonl`
- `/ll:confidence-check` - 2026-07-18T20:10:00 - `e4b449a3-a299-4075-8e2a-90bf611c1051.jsonl`
- `/ll:decide-issue` - 2026-07-18T19:53:34 - `4b5cc7c6-c85e-4bff-bee5-cf538f82df77.jsonl`
- `/ll:refine-issue` - 2026-07-18T19:49:28 - `ade649ff-5c28-4208-9a7c-ec33b90c8f71.jsonl`
- `/ll:capture-issue` - 2026-07-18T19:31:27 - `34636038-c9ad-4b77-b634-680b13ded0fc.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-18
- **Decomposed into**: FEAT-2680, FEAT-2681

Work for FEAT-2679 is now carried by its child issues; this parent was closed by rn-decompose.
