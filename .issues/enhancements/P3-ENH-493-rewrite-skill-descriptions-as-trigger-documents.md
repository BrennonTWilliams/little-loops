---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 100
outcome_confidence: 68
---

# ENH-493: Rewrite Skill Descriptions as Trigger Documents

## Summary

All 15 `SKILL.md` files use summary-style descriptions that describe what a skill does. The correct convention — confirmed by published research — is that the `description` field should be a **trigger document**: a list of exact phrases users will say to activate the skill, enabling reliable auto-activation.

## Current Behavior

Skill descriptions are written as summaries of capability. For example, `ll:product-analyzer` reads: "Analyzes codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities."

This style answers "what does this skill do?" rather than "when should this skill fire?" Claude must infer activation conditions from a description rather than matching against known trigger phrases.

## Expected Behavior

Skill descriptions contain explicit trigger phrases mirroring natural user language. For example: "When the user asks to analyze product goals, check for feature gaps, scan for goal alignment, evaluate business value, or asks 'what features are we missing' or 'are we building the right things'..."

## Motivation

The description field is used by Claude Code to decide when to auto-activate a skill. A trigger-phrase-oriented description directly reduces misses and false positives. This is low-effort, high-impact: no infrastructure changes required, just rewriting 15 description strings.

## Proposed Solution

1. Audit all 15 `SKILL.md` files in `skills/*/SKILL.md`
2. For each skill, identify the natural-language phrases a user would say to invoke it
3. Rewrite the `description` YAML field to lead with trigger phrases and include 3–6 example invocations in quotes
4. Keep the current summary content but move it to a `## Purpose` section in the skill body, not the frontmatter description

## Scope Boundaries

- **In scope**: Rewriting `description` fields in all 15 `skills/*/SKILL.md` frontmatters
- **Out of scope**: Changing skill logic, tool lists, model settings, or body content beyond moving summary text

## Implementation Steps

1. List all skills: `ls skills/*/SKILL.md`
2. For each skill, draft trigger phrases based on the skill name, purpose, and existing description
3. Update the `description` YAML field with trigger-phrase-led content
4. Optionally add `## Purpose` section in the body preserving the original summary
5. Test that Claude correctly auto-activates each skill with representative trigger phrases

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — all 15 skill files (description frontmatter field only)

### Codebase Research Findings

_Added by `/ll:refine-issue` — Skill description audit:_

**Skills already using trigger-phrase style (have inline trigger keywords):**
- `skills/analyze-history/SKILL.md` — trigger keywords present in multiline description
- `skills/capture-issue/SKILL.md` — has trigger keyword list
- `skills/confidence-check/SKILL.md` — has trigger keyword list
- `skills/issue-size-review/SKILL.md` — has trigger keyword list
- `skills/issue-workflow/SKILL.md` — has trigger keyword list
- `skills/map-dependencies/SKILL.md` — has trigger keyword list
- `skills/product-analyzer/SKILL.md` — has trigger keyword list

**Skills with summary-only descriptions (need rewriting to trigger-phrase style):**
- `skills/audit-claude-config/SKILL.md` — "Comprehensive audit of Claude Code plugin configuration with parallel sub-agents"
- `skills/audit-docs/SKILL.md` — "Audit documentation for accuracy and completeness"
- `skills/configure/SKILL.md` — "Interactively configure specific areas in ll-config.json"
- `skills/create-loop/SKILL.md` — "Create a new FSM loop configuration interactively. Guides users through paradigm selection, parameter gathering, YAML generation, and validation."
- `skills/format-issue/SKILL.md` — "Format issue files to align with template v2.0 structure through interactive Q&A or auto mode"
- `skills/init/SKILL.md` — "Initialize little-loops configuration for a project"
- `skills/manage-issue/SKILL.md` — "Autonomously manage issues - plan, implement, verify, and complete"
- `skills/workflow-automation-proposer/SKILL.md` — summary-style multiline description

**Implementation scope: 8 skills need description rewrites** (the 7 already trigger-phrase-oriented are lower priority but may still benefit from refinement)

**No `references/` subdirectories exist** — supplemental content uses flat filenames (`templates.md`, `paradigms.md`, etc.) alongside `SKILL.md`

### Similar Patterns
- `agents/*.md` — agent description fields follow a similar convention worth checking

### Tests
- Manual testing: does Claude activate the right skill when using trigger phrases?

### Documentation
- N/A — no user-facing docs change

## Impact

- **Priority**: P3 — Moderate; skill misactivation is an ongoing friction point
- **Effort**: Low — Text editing only, no code changes
- **Risk**: Low — Description changes don't affect skill logic
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `ux`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Audited all 15 SKILL.md descriptions; identified 8 needing rewrite (summary-style) and 7 already trigger-phrase-oriented

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocks

- ENH-494

- ENH-502