---
id: ENH-1016
type: ENH
priority: P2
status: closed
title: "Document `agent:` and `tools:` fields in skills/create-loop/reference.md"
discovered_date: 2026-04-09
discovered_by: issue-size-review
parent_issue: ENH-1014
confidence_score: 95
outcome_confidence: 93
testable: false
---

# ENH-1016: Document `agent:` and `tools:` fields in skills/create-loop/reference.md

## Summary

Add `#### agent (Optional)` and `#### tools (Optional)` subsections to the "Advanced State Configuration" section of `skills/create-loop/reference.md`. Decomposed from ENH-1014.

## Parent Issue

Decomposed from ENH-1014: "Document `agent:` and `tools:` in API.md and create-loop wizard reference"

## Current Behavior

The `agent:` and `tools:` state-level fields (added by FEAT-1011 to `StateConfig`) are not documented in `skills/create-loop/reference.md`. The create-loop wizard has no reference for these fields, making them undiscoverable to users building FSM loops.

## Expected Behavior

`skills/create-loop/reference.md` "Advanced State Configuration" section includes `#### agent (Optional)` and `#### tools (Optional)` subsections, each with type, when-to-use guidance, and a YAML example.

## Motivation

FEAT-1011 added `agent:` and `tools:` state-level fields to the FSM loop system, but these fields are not documented in the create-loop wizard reference. Users building loops via the wizard cannot discover these fields, so cost-optimization (routing cheap states to faster models) and tool-isolation (restricting write tools in read-only states) capabilities go unused. The value delivered by FEAT-1011 is partially unrealized until this documentation gap is closed.

## Implementation Steps

In `skills/create-loop/reference.md`, insert the following content **immediately before the `---` separator at line 890** (before `### Sub-Loop Composition` at line 892), after line 888 (end of `max_retries`/`on_retry_exhausted` subsection):

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

> **Heading format**: Use `#### agent (Optional)` — no colon before `(Optional)`. Do NOT use `#### agent: (Optional)`.

## Format Reference

Other optional field subsections in the same file follow this pattern:
- `#### FieldName (Optional)` heading
- Description paragraph
- `**Type:**` line
- `**When to use:**` bulleted list
- `**Example - [description]:**` YAML block
- `**Most users can omit this field**` closing note

## Scope Boundaries

- **In scope**: `skills/create-loop/reference.md` only (1 location, 2 subsections)
- **Out of scope**: `docs/reference/API.md` (covered by ENH-1015), LOOPS_GUIDE.md, generalized-fsm-loop.md, CLI.md (covered by ENH-1013)

## Integration Map

### Files to Modify
- `skills/create-loop/reference.md:888` — "Advanced State Configuration" section: insert two subsections after line 888 (end of `max_retries`/`on_retry_exhausted`), before the `---` separator at line 890 that precedes `### Sub-Loop Composition` (line 892)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/SKILL.md:87` — links to `reference.md` in Sub-loop composition note; wizard reads reference.md as live context during generation sessions [Agent 1 finding]
- `skills/create-loop/SKILL.md:299` — "Additional Resources" section links to `reference.md`; new subsections become active wizard knowledge [Agent 1 finding]
- `skills/create-loop/loop-types.md:849` — links to `reference.md` as companion reference for field details [Agent 1 finding]
- `skills/create-loop/loop-types.md:1014` — links to `reference.md` for full loop: field specification [Agent 1 finding]

These are awareness items only — none require changes; the additive insertion does not break any existing anchors or headings in consumers.

### Similar Patterns
- `skills/create-loop/reference.md` — existing `#### FieldName (Optional)` subsections in the same "Advanced State Configuration" section serve as the pattern to follow

### Documentation
- `docs/reference/API.md` — covered by sibling ENH-1015 (separate scope)
- `docs/guides/LOOPS_GUIDE.md` — covered by ENH-1013 (separate scope)

### Tests
- N/A — no automated tests for doc content; validate with `ll-verify-docs` and `ll-check-links`

### Configuration
- N/A

### Dependency
- Should be implemented after FEAT-1011 lands, or in the same PR

## Acceptance Criteria

- [ ] `skills/create-loop/reference.md` "Advanced State Configuration" has `#### agent (Optional)` subsection with type, when-to-use, and YAML example
- [ ] `skills/create-loop/reference.md` "Advanced State Configuration" has `#### tools (Optional)` subsection with type, when-to-use, and YAML example
- [ ] Both subsections appear before the `---` separator that precedes "Sub-Loop Composition"
- [ ] Heading format uses no colon: `#### agent (Optional)` not `#### agent: (Optional)`

## Impact

- **Priority**: P2 — documentation needed to make FEAT-1011 fields discoverable via create-loop wizard
- **Effort**: Small — single insertion point, two subsections, purely additive
- **Risk**: None — documentation-only; no runtime behavior affected
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `fsm`, `ll-loop`, `create-loop`

## Related

- Sibling: ENH-1015 (API.md)
- Parent: ENH-1014 (decomposed)
- Grandparent: ENH-1012
- Implementation: FEAT-1011

---

## Status

Closed - Already Fixed

## Session Log
- `/ll:ready-issue` - 2026-04-11T00:55:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a0ad83d-ee85-4fbb-aaef-cdb01ebc3d20.jsonl`
- `/ll:confidence-check` - 2026-04-09T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82f6692f-8a42-4bea-9dea-30f1102357d9.jsonl`
- `/ll:refine-issue` - 2026-04-09T16:05:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7afb930-71b8-4aa8-a6de-d80bf985f5f6.jsonl`
- `/ll:format-issue` - 2026-04-09T16:02:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ece9b7b8-3ce6-4b94-8a9a-6e84b44149d3.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a3e695e-d9fa-4fce-939c-e7bfcc83f05b.jsonl`
