---
id: ENH-1012
type: ENH
priority: P2
status: active
title: "Document `agent:` and `tools:` state fields in FSM loop guides"
discovered_date: 2026-04-09
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 86
testable: false
---

# ENH-1012: Document `agent:` and `tools:` state fields in FSM loop guides

## Summary

Add `agent:` and `tools:` state-level field documentation to the FSM loop reference guides and API docs. Decomposed from FEAT-1010; can be implemented independently from (or alongside) FEAT-1011.

Decomposed from FEAT-1010: "Add `agent:` and `tools:` state-level fields to ll-loop FSM"

## Background

FEAT-1011 adds `agent:` and `tools:` as optional fields to `StateConfig` in the ll-loop FSM. Once implemented, these fields need to be discoverable by users reading the guides and API reference.

## Current Behavior

The `agent:` and `tools:` state-level fields added by FEAT-1011 are not documented in any of the FSM loop reference guides. Users reading `LOOPS_GUIDE.md`, `API.md`, or `CLI.md` cannot discover these fields exist or how to use them.

## Expected Behavior

After this enhancement, the `agent:` and `tools:` state-level fields are documented in all relevant FSM loop guides:
- `docs/guides/LOOPS_GUIDE.md` includes field descriptions with usage notes
- `docs/reference/API.md` `StateConfig` block lists the new fields
- `docs/reference/CLI.md` references or cross-links to the state config documentation

## Motivation

This enhancement would:
- Enable users to discover and use the `agent:` and `tools:` state fields added in FEAT-1011
- Close the documentation gap between implementation (FEAT-1011) and user-facing guides
- Ensure all FSM loop documentation is consistent across `LOOPS_GUIDE.md`, `API.md`, and `CLI.md`

## Implementation Steps

### 1. `docs/guides/LOOPS_GUIDE.md` — New section after "Retry and Timing Fields"

- After line 701 (end of `### Retry and Timing Fields`): Add a new sibling section `### Subprocess Agent and Tool Scoping` with a two-row table for `agent:` and `tools:`, followed by a YAML example

> **Correction from original issue:** Lines 1556–1681 are the `## Reusable State Fragments` section — not a "state config reference." There is no extended state config reference at those lines. The second doc location described in the original text does not exist; only the post-"Retry and Timing Fields" insertion point applies in LOOPS_GUIDE.md.

New section format (consistent with `### Retry and Timing Fields` at line 682):

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

### 2. `docs/reference/API.md` — Three blocks to update

- Lines 3766–3786: `StateConfig` dataclass reference block — add `agent: str | None` and `tools: list[str] | None` field entries as inline `# comment` entries following the existing field format (e.g., after `context_passthrough`)
- Lines 4044–4057: `ActionRunner` Protocol signature documentation block — update the `run()` method signature to add `agent: str | None = None` and `tools: list[str] | None = None` parameters
- Lines 1923–1942: `run_claude_command` function signature documentation — add `agent`/`tools` params

> **Pre-existing divergence note:** The current API.md `run_claude_command` block (lines 1923–1932) documents a signature with `logger: Logger` and `stream_output: bool` that does NOT match the actual implementation at `scripts/little_loops/subprocess_utils.py:62–71` (which uses `timeout`, `working_dir`, `stream_callback`, `on_process_start`, `on_process_end`, `idle_timeout`, `on_model_detected`). ENH-1012 should add `agent` and `tools` to the doc signature in FEAT-1011's spirit, but be aware this block is already stale. Reconciling the full signature divergence is out of scope for this issue.

### 3. `docs/reference/CLI.md` — ll-loop run flag table

- Lines 236–260: Does not currently describe state-level YAML fields `agent:`/`tools:`. Add a note or cross-reference pointing to the new `### Subprocess Agent and Tool Scoping` section in LOOPS_GUIDE.md.

### 4. `docs/generalized-fsm-loop.md` — Schema block update (correction from original)

> **Correction from original issue:** The file DOES contain a canonical "Other State Properties" YAML schema block at lines 263–269 that enumerates per-state fields. `agent:` and `tools:` must be added here.

- Lines 263–269: Under `# --- Other State Properties ---`, add `agent: string` and `tools: list` entries following the format of the existing `next`, `terminal`, `capture`, `timeout`, `fragment` entries.

### 5. `skills/create-loop/reference.md` — Advanced State Configuration update

- Lines 393–992: "Advanced State Configuration" section — add `#### agent: (Optional)` and `#### tools: (Optional)` subsections following the format of the existing 10 documented fields. Each subsection should include type, when-to-use note ("`action_type: prompt` states only"), and a YAML example.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/generalized-fsm-loop.md:263–269` — add `agent: string` and `tools: list` to the "Other State Properties" YAML schema block (the canonical machine-readable FSM field inventory)
6. Update `skills/create-loop/reference.md` — add `#### agent: (Optional)` and `#### tools: (Optional)` subsections to the "Advanced State Configuration" section so the create-loop wizard can surface these fields during loop generation

## Scope Boundaries

- **In scope**: Documentation updates to `LOOPS_GUIDE.md`, `API.md`, `CLI.md`, and `generalized-fsm-loop.md` for `agent:` and `tools:` state-level fields only
- **Out of scope**: Implementation of `agent:` and `tools:` fields in code (that is FEAT-1011); any other FSM documentation changes not directly related to these two fields

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — insert new `### Subprocess Agent and Tool Scoping` section after line 701 (end of `### Retry and Timing Fields`)
- `docs/reference/API.md` — three locations:
  - Lines 3766–3786: `StateConfig` dataclass block (add two field lines)
  - Lines 4044–4057: `ActionRunner` Protocol `run()` signature (add two parameters)
  - Lines 1923–1942: `run_claude_command` signature block (add `agent`/`tools` params; note pre-existing divergence in this block)
- `docs/reference/CLI.md` — lines 236–260: `ll-loop run` flag table; add cross-reference note pointing to new LOOPS_GUIDE.md section
- `docs/generalized-fsm-loop.md:263–269` — "Other State Properties" YAML schema block: add `agent: string` and `tools: list` entries alongside the existing per-state field inventory (`next`, `terminal`, `capture`, `timeout`, `fragment`)
- `skills/create-loop/reference.md:393+` — "Advanced State Configuration" section: add `#### agent: (Optional)` and `#### tools: (Optional)` subsections following the same format as the existing 10 documented optional fields (type, when-to-use, YAML example)

### Dependent Files (Callers/Importers)
- N/A — documentation only, no code callers or importers

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:263–269` — canonical machine-readable FSM schema block; `agent:` and `tools:` absent from the "Other State Properties" inventory [Agent 2 finding]
- `skills/create-loop/reference.md:393–992` — "Advanced State Configuration" section actively consulted by the create-loop wizard; no `agent:` or `tools:` sub-heading alongside the 10 other documented optional fields [Agent 2 finding]

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `docs/guides/LOOPS_GUIDE.md:682–701` — `### Retry and Timing Fields` section: the exact format to follow (section header, "These optional fields can be added to any state:", three-column table, YAML example block)
- `docs/reference/API.md:3766–3786` — `StateConfig` dataclass block: field format is `field: type | None = None  # brief inline comment`
- `docs/reference/API.md:4044–4057` — `ActionRunner` Protocol block: Python Protocol class format with inline parameter annotations
- `docs/reference/API.md:1923–1942` — `run_claude_command` block: `**Parameters:**` bulleted list format `` `name` - description ``
- `docs/claude-code/cli-reference.md:37,81` — upstream `--agent` and `--tools` Claude CLI flag definitions that the YAML fields map to; can be cross-referenced

### Tests
- N/A — no automated tests for doc content; validate with `ll-verify-docs` and `ll-check-links`

### Documentation
- All files above are the documentation being updated

### Configuration
- N/A

## Acceptance Criteria

- [ ] `docs/guides/LOOPS_GUIDE.md` state field sections include `agent:` and `tools:` with descriptions and usage notes
- [ ] `docs/reference/API.md` `StateConfig` block reflects new fields
- [ ] `docs/reference/API.md` `ActionRunner` Protocol block reflects updated signature
- [ ] `docs/reference/API.md` `run_claude_command` block reflects new params
- [ ] `docs/reference/CLI.md` references or explains state-level `agent:`/`tools:` fields
- [ ] All doc cross-references are consistent (field described the same way in all locations)

## Example Documentation to Write

```yaml
# Example: state using agent field
execute:
  action: |
    Run the exploratory eval as defined in the agent file.
  action_type: prompt
  agent: exploratory-user-eval    # loads --agent flag → picks up Playwright tools

# Example: state using tools field
validate:
  action: |
    Check the output file for correctness.
  action_type: prompt
  tools: ["Read", "Bash"]          # explicitly scopes to Read + Bash only
```

## Impact

- **Priority**: P2 - Documentation gap for FEAT-1011 capability
- **Effort**: Small - Additive doc updates; no code changes
- **Risk**: None
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `fsm`, `ll-loop`

## Related

- Parent: FEAT-1010 (decomposed)
- Sibling: FEAT-1011 (implementation)

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-09
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1013: Document `agent:` and `tools:` in FSM loop narrative guides (LOOPS_GUIDE.md, generalized-fsm-loop.md, CLI.md)
- ENH-1014: Document `agent:` and `tools:` in API.md and create-loop wizard reference

---

## Status

Active

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-09T15:20:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40c29be0-4e98-4828-a76b-5f21269ed7a5.jsonl`
- `/ll:confidence-check` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a11aabf-f903-47e7-b3ea-a42ab7ba537a.jsonl`
- `/ll:wire-issue` - 2026-04-09T15:15:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52dab5ee-45a0-4c56-8819-98801126cfc8.jsonl`
- `/ll:refine-issue` - 2026-04-09T15:10:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/885bf5e8-0537-43ff-8bd8-ea01f8521c19.jsonl`
- `/ll:format-issue` - 2026-04-09T15:05:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/016808f5-a357-4d5a-bfbd-271f3cf90ec1.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b4a844-219d-40e6-8201-677dabfe574c.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40c29be0-4e98-4828-a76b-5f21269ed7a5.jsonl`
