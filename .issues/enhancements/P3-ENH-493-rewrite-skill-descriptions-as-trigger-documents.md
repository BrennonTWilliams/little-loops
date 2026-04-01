---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 100
outcome_confidence: 71
---

# ENH-493: Rewrite Skill Descriptions as Trigger Documents

## Summary

All 16 `SKILL.md` files use summary-style descriptions that describe what a skill does. The correct convention — confirmed by published research — is that the `description` field should be a **trigger document**: a list of exact phrases users will say to activate the skill, enabling reliable auto-activation.

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
- ~~`skills/workflow-automation-proposer/SKILL.md`~~ — **Already has trigger keywords** (verified 2026-03-03): description now includes `Trigger keywords: "propose automations", "workflow proposals", "automation suggestions", "step 3 workflow analysis"`

**Implementation scope: 10 skills need description rewrites** (workflow-automation-proposer already done; the 7 already trigger-phrase-oriented are lower priority but may still benefit from refinement; 3 new skills added since last audit also need rewrites — see below)

**No `references/` subdirectories exist** — supplemental content uses flat filenames (`templates.md`, `paradigms.md`, etc.) alongside `SKILL.md`

### Proposed Trigger Phrase Drafts (7 Skills)

_Added by `/ll:refine-issue` — reduces implementation ambiguity:_

| Skill | Current Description (Summary Style) | Proposed Trigger Phrases |
|-------|-------------------------------------|--------------------------|
| `audit-claude-config` | "Comprehensive audit of Claude Code plugin configuration with parallel sub-agents" | "When the user asks to audit config, check plugin settings, review claude config, diagnose plugin issues, or 'is my config valid?'" |
| `audit-docs` | "Audit documentation for accuracy and completeness" | "When the user asks to audit docs, check documentation accuracy, verify docs are up to date, or 'are the docs correct?'" |
| `configure` | "Interactively configure specific areas in ll-config.json" | "When the user asks to configure ll, change settings, set up options, update ll-config, or 'how do I set X?'" |
| `create-loop` | "Create a new FSM loop configuration interactively..." | "When the user asks to create a loop, make a new loop, add an automation loop, set up FSM, or 'I want to automate X with a loop'" |
| `format-issue` | "Format issue files to align with template v2.0 structure..." | "When the user asks to format an issue, fix issue template, align issue to v2.0, or 'format this issue'" |
| `init` | "Initialize little-loops configuration for a project" | "When the user asks to initialize little-loops, set up ll for a project, bootstrap config, or 'how do I get started with ll?'" |
| `manage-issue` | "Autonomously manage issues - plan, implement, verify, and complete" | "When the user asks to implement an issue, work on a bug/feature, manage an issue end to end, or 'start implementing FEAT-NNN'" |

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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `CONTRIBUTING.md` | Development conventions — target for documenting skill description standards |
| `docs/reference/COMMANDS.md` | Command and skill documentation reference |

## Labels

`enhancement`, `skills`, `context-engineering`, `ux`

## Session Log
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:48:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6354e86b-8019-4171-939d-aba670876e1f.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Audited all 15 SKILL.md descriptions; identified 8 needing rewrite (summary-style) and 7 already trigger-phrase-oriented
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; research findings from 2026-02-25 remain current
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `CONTRIBUTING.md` and `docs/reference/COMMANDS.md` to Related Key Documentation
- `/ll:verify-issues` - 2026-03-03 - `workflow-automation-proposer/SKILL.md` already has trigger keywords; scope corrected from 8 → 7 skills needing rewrites
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: 7 skills still need description rewrites; removed stale Blocks ref ENH-502 (completed)
- `/ll:refine-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added proposed trigger phrase drafts for all 7 skills to reduce implementation ambiguity
- `/ll:confidence-check` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — readiness: 100/100 PROCEED, outcome: 71/100 MODERATE (up from 68 — ambiguity reduced by trigger phrase table; 7 files single subsystem shallow edits = 18/25 complexity)
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: 7 skills still need description rewrites
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: 7 skills still use summary-style descriptions
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — NEEDS_UPDATE: removed completed ENH-668 from Blocked By; skill count now 16 (was 15)

---

## Verification Notes

- **Date**: 2026-04-01
- **Verdict**: NEEDS_UPDATE
- Removed 3 completed blockers: FEAT-659, FEAT-638, FEAT-565 (all completed) — issue is now unblocked.
- Total skill count is now **21** (was 19). New skills since last audit: `cleanup-loops`, `review-loop`, `update-docs`, `update`. Scope of summary-style skills needing rewrites may have expanded further.

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocked By

## Blocks
- ENH-459

- ENH-494