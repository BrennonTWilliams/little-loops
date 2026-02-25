---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-502: Skill Design Traceability Documents (WHY.md per Skill)

## Summary

Add optional `WHY.md` files to skill directories documenting the design rationale, key decisions, and measured outcomes for each skill. This mirrors the `HOW-SKILLS-BUILT-THIS.md` pattern from the source repo, which traces each design decision to a specific principle and records quantified results (e.g., "87% token reduction per content task").

## Current Behavior

Skills exist as `SKILL.md` files with operational instructions but no record of why design decisions were made. When a skill is modified, the original intent and tradeoffs that shaped the design may be lost. Contributors making changes have no way to know which decisions were deliberate vs. incidental.

## Expected Behavior

High-value or complex skills have a `skills/<name>/WHY.md` file containing:

```markdown
# Why <skill-name> Works This Way

## Design Goals
- Goal 1
- Goal 2

## Key Decisions
| Decision | Rationale | Alternative Considered |
|----------|-----------|----------------------|
| ...      | ...       | ...                  |

## Measured Outcomes (if available)
- Metric: result

## Known Limitations
- ...
```

This is not required for all skills — prioritize the most complex or frequently modified ones.

## Motivation

This is low-cost documentation that pays dividends during future modification. When ENH-493 (trigger descriptions) or ENH-494 (line limit) changes are implemented, contributors will benefit from knowing why specific wording was chosen. For skills like `manage-issue` and `confidence-check` that encode significant design thought, a `WHY.md` preserves institutional knowledge.

Secondary benefit: if we ever publish this plugin to a marketplace (as the source repo does), traceability documents significantly improve the professional quality of the project.

## Proposed Solution

1. Start with 3–5 highest-value skills: `manage-issue`, `confidence-check`, `handoff`, `review-sprint`, `create-sprint`
2. For each, create `skills/<name>/WHY.md` with the template above
3. Add a note in `CONTRIBUTING.md` recommending WHY.md for complex skills
4. This is a living document — update it when significant changes are made

## Scope Boundaries

- **In scope**: Creating WHY.md files for 3–5 selected skills; adding CONTRIBUTING.md note
- **Out of scope**: Requiring WHY.md for all skills, automating generation, connecting to issue tracking

## Implementation Steps

1. Select 3–5 highest-value skills based on complexity and modification frequency
2. For each, review the SKILL.md and reconstruct design rationale from content
3. Write `skills/<name>/WHY.md` using the template
4. Add a sentence to `CONTRIBUTING.md` recommending WHY.md for complex skills

## Integration Map

### New Files
- `skills/<name>/WHY.md` — per selected skill

### Files to Modify
- `CONTRIBUTING.md` — add WHY.md recommendation

## Impact

- **Priority**: P5 — Very low urgency; purely additive documentation
- **Effort**: Low — Writing only
- **Risk**: None
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `skills`, `traceability`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P5

## Blocked By

- ENH-494

- ENH-493
- ENH-491
- ENH-496
- FEAT-441