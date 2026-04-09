---
id: ENH-1014
type: ENH
priority: P2
status: active
title: "Document `agent:` and `tools:` in API.md and create-loop wizard reference"
discovered_date: 2026-04-09
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 78
testable: false
---

# ENH-1014: Document `agent:` and `tools:` in API.md and create-loop wizard reference

## Summary

Add `agent:` and `tools:` state-level field documentation to `docs/reference/API.md` (3 locations) and `skills/create-loop/reference.md` (Advanced State Configuration section). Decomposed from ENH-1012.

## Current Behavior

The `agent:` and `tools:` state-level fields (added by FEAT-1011 to `StateConfig`) are not documented in `docs/reference/API.md` or `skills/create-loop/reference.md`. Users and the create-loop wizard have no reference for these fields.

## Expected Behavior

`docs/reference/API.md` documents `agent:` and `tools:` in three locations (`StateConfig` dataclass block, `ActionRunner` Protocol `run()` signature, `run_claude_command` function signature), and `skills/create-loop/reference.md` includes `#### agent: (Optional)` and `#### tools: (Optional)` subsections with type, when-to-use guidance, and YAML examples.

## Motivation

This enhancement ensures the `agent:` and `tools:` fields implemented in FEAT-1011 are discoverable by:
- Programmatic users reading the API reference
- The create-loop wizard surfacing advanced state configuration options
- Agents implementing issues that involve multi-agent or tool-restricted FSM states

Without this documentation, FEAT-1011's feature is invisible to users who rely on API.md or the create-loop wizard for field discovery.

## Parent Issue

Decomposed from ENH-1012: "Document `agent:` and `tools:` state fields in FSM loop guides"

## Background

FEAT-1011 adds `agent:` and `tools:` as optional fields to `StateConfig` in the ll-loop FSM. The API reference and create-loop wizard reference must reflect these new fields so that both programmatic users and the create-loop wizard can surface them.

> **Dependency**: As of 2026-04-09, `agent:` and `tools:` do **not** exist in the codebase (`schema.py`, `runners.py`, `subprocess_utils.py`, `fsm-loop-schema.json`). ENH-1014 should be implemented after FEAT-1011 lands, or in the same PR.

## Implementation Steps

### 1. `docs/reference/API.md` — Three blocks to update

- **Lines 3766–3786**: `StateConfig` dataclass reference block — add `agent: str | None` and `tools: list[str] | None` field entries as inline `# comment` entries following the existing field format (e.g., after `context_passthrough`)
- **Lines 4044–4057**: `ActionRunner` Protocol signature documentation block — update the `run()` method signature to add `agent: str | None = None` and `tools: list[str] | None = None` parameters
- **Lines 1923–1942**: `run_claude_command` function signature documentation — add `agent`/`tools` params

> **Pre-existing divergence note:** The current API.md `run_claude_command` block (lines 1923–1932) documents a signature that does NOT match the actual implementation at `scripts/little_loops/subprocess_utils.py:62–71`. ENH-1014 should add `agent` and `tools` to the doc signature, but reconciling the full signature divergence is out of scope.

### 2. `skills/create-loop/reference.md` — Advanced State Configuration

Lines 393–890: "Advanced State Configuration" section — add `#### agent (Optional)` and `#### tools (Optional)` subsections **immediately before the `---` separator at line 890** (before "Sub-Loop Composition"). Follow the format of the existing 10 documented optional fields. Each subsection should include:
- Type
- When-to-use note ("`action_type: prompt` states only")
- YAML example

> **Heading format**: Existing subsections use `#### field (Optional)` — no colon before `(Optional)`. Do NOT use `#### agent: (Optional)`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Location 1: `docs/reference/API.md` — StateConfig block (line 3785)

Current last field: `context_passthrough: bool = False  # Pass parent context vars to child; merge child captures back`

Insert these two lines **before the closing ` ``` ` on line 3786**:
```python
    agent: str | None = None           # Claude agent model override for this state (prompt action_type only)
    tools: list[str] | None = None     # Restrict available tools for this state (prompt action_type only)
```

#### Location 2: `docs/reference/API.md` — ActionRunner Protocol (lines 4044–4057)

Current `run()` signature ends with `on_output_line: Callable[[str], None] | None = None,`.

Insert these two lines **before `    ) -> ActionResult: ...`** (line 4054):
```python
        agent: str | None = None,
        tools: list[str] | None = None,
```

#### Location 3: `docs/reference/API.md` — `run_claude_command` (lines 1923–1942)

Current doc signature has 4 params (`command`, `logger`, `timeout`, `stream_output`) that diverge from the real 8-param implementation — do not reconcile divergence per scope note. Add `agent` and `tools` to the documented signature **before the closing `)` on line 1931**:
```python
    agent: str | None = None,
    tools: list[str] | None = None,
```

Add two bullets to the `**Parameters:**` list:
```
- `agent` - Claude agent model override; appended as `--agent <value>` to CLI invocation
- `tools` - Restrict available tools; appended as `--tools <value>` to CLI invocation
```

#### Location 4: `skills/create-loop/reference.md` (before line 890)

Insert before the `---` separator at line 890:

```markdown
#### agent (Optional)

Specifies the Claude agent model to use for this state. Only applies to `action_type: prompt` states; ignored for shell or other action types.

**Type:** `str`

**When to use:**
- **Model override per state**: Use a different model for a specific state than the loop-level default
- **Cost optimization**: Route simple classification states to a faster or cheaper model

**Example - Use a faster model for a classification state:**
```yaml
classify_input:
  action: "Classify whether this text is relevant..."
  action_type: prompt
  agent: claude-haiku-4-5-20251001
  on_yes: process
  on_no: skip
```

**Most users can omit this field** — the loop-level default agent applies when not set.

#### tools (Optional)

Restricts the set of tools available to Claude for this state. Only applies to `action_type: prompt` states.

**Type:** `list[str]`

**When to use:**
- **Read-only states**: Prevent write tools in analysis or classification states
- **Tool allowlist**: Restrict a state to only the tools it needs for predictability

**Example - Restrict tools for a read-only analysis state:**
```yaml
analyze_code:
  action: "Analyze this code for issues..."
  action_type: prompt
  tools:
    - Read
    - Grep
  next: report
```

**Most users can omit this field** — Claude has its full tool set when `tools:` is not specified.
```

## Scope Boundaries

- **In scope**: API.md (3 locations) and skills/create-loop/reference.md only
- **Out of scope**: LOOPS_GUIDE.md, generalized-fsm-loop.md, CLI.md (covered by ENH-1013)

## Integration Map

### Files to Modify
- `docs/reference/API.md`:
  - Lines 3766–3786: `StateConfig` dataclass block (add two field lines)
  - Lines 4044–4057: `ActionRunner` Protocol `run()` signature (add two parameters)
  - Lines 1923–1942: `run_claude_command` signature block (add `agent`/`tools` params)
- `skills/create-loop/reference.md:393+` — "Advanced State Configuration" section: add two subsections

### Similar Patterns
- `docs/reference/API.md:3766–3786` — `StateConfig` field format: `field: type | None = None  # brief inline comment`
- `docs/reference/API.md:4044–4057` — `ActionRunner` Protocol format: Python Protocol class with inline parameter annotations
- `docs/reference/API.md:1923–1942` — `run_claude_command` format: `**Parameters:**` bulleted list `` `name` - description ``
- Other `#### FieldName: (Optional)` subsections in `skills/create-loop/reference.md` for format reference

### Dependent Files (Callers/Importers)
- N/A — documentation files only; no callers/importers

### Tests
- N/A — no automated tests for doc content; validate with `ll-verify-docs` and `ll-check-links`

### Documentation
- `docs/reference/API.md` — primary file being updated
- `skills/create-loop/reference.md` — primary file being updated

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:538` — documents `MockActionRunner.run()` with only 3 parameters (`action`, `timeout`, `is_slash_command`); already missing `on_output_line` before FEAT-1011 lands; after FEAT-1011+ENH-1014 the documented example mock will diverge further from the actual Protocol signature (which will gain `agent` and `tools`). Neither FEAT-1011 nor ENH-1014 currently lists this file. If the implementation PR covers both issues, updating the mock signature example in TESTING.md should be included. [Agent 2 finding]

### Configuration
- N/A

## Acceptance Criteria

- [ ] `docs/reference/API.md` `StateConfig` block includes `agent: str | None` and `tools: list[str] | None` fields
- [ ] `docs/reference/API.md` `ActionRunner` Protocol `run()` signature includes `agent` and `tools` parameters
- [ ] `docs/reference/API.md` `run_claude_command` block includes `agent`/`tools` params
- [ ] `skills/create-loop/reference.md` "Advanced State Configuration" has `#### agent: (Optional)` and `#### tools: (Optional)` subsections with type, when-to-use, and YAML examples

## Impact

- **Priority**: P2 — FEAT-1011 is implemented; documentation is needed to make the fields discoverable; not urgent but blocks informed usage
- **Effort**: Small — 4 file locations, all purely additive text with no code changes
- **Risk**: None — documentation-only; no runtime behavior affected
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `fsm`, `ll-loop`, `api`

## Related

- Parent: ENH-1012 (decomposed)
- Sibling: ENH-1013 (narrative guides)
- Implementation: FEAT-1011

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-09
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1015: Document `agent:` and `tools:` fields in docs/reference/API.md
- ENH-1016: Document `agent:` and `tools:` fields in skills/create-loop/reference.md

---

## Status

Decomposed

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-09_

**Readiness Score**: 90/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **FEAT-1011 not completed**: `agent` and `tools` fields do not exist in `scripts/little_loops/fsm/schema.py` yet. Merging ENH-1014 before FEAT-1011 would document non-existent fields. Enforce "same PR or after FEAT-1011 lands" sequencing.
- **Heading format inconsistency**: Acceptance criteria item 4 says `#### agent: (Optional)` (with colon) but Implementation Steps explicitly say to use `#### agent (Optional)` (no colon). Follow the Implementation Steps format.

## Session Log
- `/ll:confidence-check` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb52f860-f8b3-47fd-89ce-763a41dbdc5a.jsonl`
- `/ll:wire-issue` - 2026-04-09T15:46:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb52f860-f8b3-47fd-89ce-763a41dbdc5a.jsonl`
- `/ll:refine-issue` - 2026-04-09T15:41:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2408bcd-760c-4589-a5bb-13fd356691b2.jsonl`
- `/ll:format-issue` - 2026-04-09T15:37:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5318c406-f32e-436b-b6df-7b27eeeb7634.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40c29be0-4e98-4828-a76b-5f21269ed7a5.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a3e695e-d9fa-4fce-939c-e7bfcc83f05b.jsonl`
