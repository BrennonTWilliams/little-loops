---
id: ENH-1013
type: ENH
priority: P2
status: active
title: "Document `agent:` and `tools:` in FSM loop narrative guides"
discovered_date: 2026-04-09
discovered_by: issue-size-review
confidence_score: 70
outcome_confidence: 100
testable: false
---

# ENH-1013: Document `agent:` and `tools:` in FSM loop narrative guides

## Summary

Add `agent:` and `tools:` state-level field documentation to the FSM loop narrative guides: `LOOPS_GUIDE.md`, `generalized-fsm-loop.md`, and a cross-reference note in `CLI.md`. Decomposed from ENH-1012.

## Parent Issue

Decomposed from ENH-1012: "Document `agent:` and `tools:` state fields in FSM loop guides"

## Background

FEAT-1011 adds `agent:` and `tools:` as optional fields to `StateConfig` in the ll-loop FSM. Users reading the narrative loop guides cannot currently discover these fields.

## Current Behavior

`docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, and `docs/reference/CLI.md` do not document the `agent:` and `tools:` state-level fields. Users reading the narrative guides cannot discover these fields without inspecting source code or the Python API reference.

## Expected Behavior

- `docs/guides/LOOPS_GUIDE.md` has a new `### Subprocess Agent and Tool Scoping` section after "Retry and Timing Fields" with a field table and YAML example
- `docs/generalized-fsm-loop.md` "Other State Properties" schema block includes `agent: string` and `tools: list` entries
- `docs/reference/CLI.md` has a cross-reference note pointing to the new `LOOPS_GUIDE.md` section

## Motivation

This enhancement would:
- Close a discoverability gap: `agent:` and `tools:` fields exist in `StateConfig` (FEAT-1011) but are invisible to users reading narrative guides
- Enable users to configure subprocess agent scoping and tool restrictions without inspecting source code
- Additive-only doc change with no risk to existing loop configurations

## Implementation Steps

### 1. `docs/guides/LOOPS_GUIDE.md` — New section after "Retry and Timing Fields"

After line 701 (end of `### Retry and Timing Fields`): add a new sibling section `### Subprocess Agent and Tool Scoping` with a two-row table and YAML example.

Format (consistent with `### Retry and Timing Fields` at line 682):

```markdown
### Subprocess Agent and Tool Scoping

These optional fields apply to `action_type: prompt` states only. They are ignored for `action_type: shell` states.

| Field | Type | Description |
|-------|------|-------------|
| `agent:` | string | Passes `--agent <name>` to the Claude subprocess. Loads `.claude/agents/<name>.md`, picking up its system prompt and tool set. |
| `tools:` | list of strings | Passes `--tools <csv>` to the Claude subprocess. Explicitly scopes available tools without needing a full agent file (e.g. `["Read", "Bash"]`). |

Example — run a state under a specialized agent, and another with restricted tools:

```yaml
explore:
  action: |
    Run the exploratory eval as defined in the agent file.
  action_type: prompt
  agent: exploratory-user-eval    # loads --agent flag → picks up Playwright tools
  next: validate

validate:
  action: |
    Check the output file for correctness.
  action_type: prompt
  tools: ["Read", "Bash"]          # scopes to Read + Bash only
  on_yes: done
  on_no: fix
```
```

### 2. `docs/generalized-fsm-loop.md` — Schema block update

Lines 263–269: Under `# --- Other State Properties ---`, add `agent: string` and `tools: list` entries following the format of the existing `next`, `terminal`, `capture`, `timeout`, `fragment` entries.

### 3. `docs/reference/CLI.md` — Cross-reference note

Lines 236–260: `ll-loop run` flag table does not describe state-level YAML fields `agent:`/`tools:`. Add a note or cross-reference pointing to the new `### Subprocess Agent and Tool Scoping` section in LOOPS_GUIDE.md.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be considered in the implementation:_

4. **Prerequisite: FEAT-1011 must ship first or concurrently** — `scripts/little_loops/fsm/fsm-loop-schema.json` enforces `"additionalProperties": false` on `stateConfig` (line 266); any loop YAML using `agent:` or `tools:` will fail `ll-loop validate` until FEAT-1011 updates this schema file. The YAML examples in the new LOOPS_GUIDE.md section will not be functional until FEAT-1011 lands.

## Scope Boundaries

- **In scope**: LOOPS_GUIDE.md, generalized-fsm-loop.md, CLI.md updates only
- **Out of scope**: API.md and skills/create-loop/reference.md (covered by ENH-1014)

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — insert new `### Subprocess Agent and Tool Scoping` section after line 701
- `docs/generalized-fsm-loop.md:263–269` — add `agent: string` and `tools: list` entries to "Other State Properties" YAML schema block
- `docs/reference/CLI.md:236–260` — add cross-reference note to new LOOPS_GUIDE.md section

### Similar Patterns
- `docs/guides/LOOPS_GUIDE.md:682–701` — `### Retry and Timing Fields`: exact format to follow (header, table, YAML example)
- `docs/claude-code/cli-reference.md:37,81` — upstream `--agent` and `--tools` Claude CLI flag definitions for cross-referencing

### Tests
- N/A — no automated tests for doc content; validate with `ll-verify-docs` and `ll-check-links`

_Wiring pass clarification: `ll-verify-docs` scope is limited to `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` — it will **not** run against the three target files. Use `ll-check-links` run against the project root to validate any new links added. [Agent 3 finding]_

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — cross-references `LOOPS_GUIDE.md` as "Full FSM loops reference: evaluators, state fields, CLI commands"; the new section will be automatically visible to its readers; no direct edit needed [Agent 1 finding]
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — cross-references `generalized-fsm-loop.md` for "sub-loop chaining, state field reference"; the schema block update (step 2) will be visible to its readers; no direct edit needed [Agent 1 finding]

## Acceptance Criteria

- [ ] `docs/guides/LOOPS_GUIDE.md` has new `### Subprocess Agent and Tool Scoping` section after "Retry and Timing Fields" with table and YAML example
- [ ] `docs/generalized-fsm-loop.md` "Other State Properties" schema block includes `agent: string` and `tools: list`
- [ ] `docs/reference/CLI.md` has a cross-reference note pointing to the new LOOPS_GUIDE.md section

## Impact

- **Priority**: P2
- **Effort**: Small — 3 file edits, all additive
- **Risk**: None
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `fsm`, `ll-loop`

## Related

- Parent: ENH-1012 (decomposed)
- Sibling: ENH-1014 (reference/wizard docs)
- Implementation: FEAT-1011

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-09_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- All three acceptance criteria are already satisfied in the working tree (`M` status on all target files). `### Subprocess Agent and Tool Scoping` exists in LOOPS_GUIDE.md:703, `agent:` / `tools:` are in generalized-fsm-loop.md:270–271, and CLI.md:261 has the cross-reference. **This issue is essentially complete — consider closing it rather than implementing it.**
- FEAT-1011 is still active. The `stateConfig` JSON schema (`additionalProperties: false`) does not yet include `agent:` or `tools:`, so loop YAML using these fields will fail `ll-loop validate` until FEAT-1011 lands.

## Status

Active

## Session Log
- `/ll:confidence-check` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29a41c7a-497d-4808-82ba-0064f72a4ceb.jsonl`
- `/ll:wire-issue` - 2026-04-09T15:32:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05c0c04b-cec7-471b-8bc5-c491127e61eb.jsonl`
- `/ll:refine-issue` - 2026-04-09T15:26:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49a28fdb-35d3-477d-a5fb-07b0663c322c.jsonl`
- `/ll:refine-issue` - 2026-04-09T15:26:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49a28fdb-35d3-477d-a5fb-07b0663c322c.jsonl`
- `/ll:format-issue` - 2026-04-09T15:22:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/735b8049-6dff-4f23-9f21-d98285afcdb6.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40c29be0-4e98-4828-a76b-5f21269ed7a5.jsonl`
