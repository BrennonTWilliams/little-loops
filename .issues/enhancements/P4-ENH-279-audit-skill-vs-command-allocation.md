---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-279: Audit skill vs command allocation

## Summary

Review the current 16 skills against the "proactive discovery" criterion: skills should be things Claude auto-discovers and uses proactively, while commands are for user-invoked actions. SuperClaude validates this distinction — they have only 1 skill (confidence-check) and 30 commands. Some of our skills may be better as commands.

## Current Behavior

We have 16 skills, each consuming character budget in the system prompt and signaling to Claude to consider them proactively. However, several skills are only invoked when a user explicitly asks:

| Skill | Proactive? | Assessment |
|---|---|---|
| `analyze-history` | No — User asks for it | Candidate for command |
| `audit-claude-config` | No — User-invoked audit action | Candidate for command |
| `audit-docs` | No — User-invoked audit action | Candidate for command |
| `capture-issue` | Yes — Could be proactive when bugs are discovered | Keep as skill |
| `confidence-check` | Yes — Could be proactive before implementation | Keep as skill |
| `configure` | No — User-invoked setup action | Candidate for command |
| `create-loop` | No — User-invoked creation action | Candidate for command |
| `format-issue` | No — User-invoked formatting action | Candidate for command |
| `init` | No — User-invoked setup action | Candidate for command |
| `issue-size-review` | Yes — Could be proactive during sprint planning | Keep as skill |
| `issue-workflow` | No — Reference doc, user asks for it | Candidate for command |
| `loop-suggester` | No — User asks for automation suggestions | Candidate for command |
| `manage-issue` | No — User-invoked issue management | Candidate for command |
| `map-dependencies` | Yes — Could be proactive during sprint planning | Keep as skill |
| `product-analyzer` | No — Requires explicit user intent | Candidate for command |
| `workflow-automation-proposer` | No — Step 3 of a pipeline, always user-invoked | Candidate for command |

## Expected Behavior

Evaluate each skill and migrate candidates from `skills/` to `commands/` where appropriate:

1. Apply the criterion: "Would Claude proactively invoke this without the user asking?"
2. Consider character budget impact — skills and commands consume budget equally, but skills add context load by signaling proactive consideration
3. Migrate 12 candidates to commands if analysis confirms they are always user-initiated
4. Keep 4 proactive skills (`capture-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`)

### Migration steps per skill:
- Move `skills/<name>/SKILL.md` content to `commands/<name>.md` format
- Update any references in other commands or documentation
- Remove the skill directory
- Update plugin.json if needed

## Files to Modify

- `skills/workflow-automation-proposer/SKILL.md` — Potential move to `commands/`
- `skills/product-analyzer/SKILL.md` — Potential move to `commands/`
- `skills/analyze-history/SKILL.md` — Potential move to `commands/`
- `skills/issue-workflow/SKILL.md` — Potential move to `commands/`
- System prompt descriptions and plugin.json as needed

## Motivation

This enhancement would:
- Reduce system prompt bloat: skills consume character budget and signal proactive consideration
- Improve clarity: users-initiated actions should be commands, not skills
- Follow established patterns: SuperClaude uses 1 skill vs 30 commands

## Scope Boundaries

- **In scope**: Evaluating 4 candidate skills for migration to commands, migrating confirmed candidates
- **Out of scope**: Changing skill/command functionality, redesigning the skill system

## Implementation Steps

1. Validate the proactive discovery criterion for each of the 16 skills
2. Migrate confirmed candidates from `skills/` to `commands/` format
3. Update references in other commands and documentation
4. Update plugin.json if needed
5. Remove migrated skill directories

## Integration Map

### Files to Modify
- `skills/workflow-automation-proposer/SKILL.md` - Potential migration to `commands/`
- `skills/product-analyzer/SKILL.md` - Potential migration to `commands/`
- `skills/analyze-history/SKILL.md` - Potential migration to `commands/`
- `skills/issue-workflow/SKILL.md` - Potential migration to `commands/`

### Dependent Files (Callers/Importers)
- `.claude-plugin/plugin.json` - skill registrations
- Other commands referencing these skills

### Similar Patterns
- N/A

### Tests
- N/A — skill/command markdown migrations are not Python-testable; verified by invoking migrated commands post-migration

### Documentation
- `docs/ARCHITECTURE.md` — update skill/command listing with final allocations
- `.claude/CLAUDE.md` — update skills and commands counts if allocations change

### Configuration
- `.claude-plugin/plugin.json` - Remove migrated skill entries

## Impact

- **Priority**: P4
- **Effort**: Medium
- **Risk**: Low — current allocation works, this is optimization

## Blocked By

- ENH-368: plugin-config-auditor missing hook event and handler types (shared docs/ARCHITECTURE.md)

## Blocks

_None — ENH-366 closed (won't-fix)._

## Labels

`enhancement`, `skills`, `commands`, `architecture`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P4

---

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- **Skills count significantly changed**: Now **16 skills** exist (was 6 at time of writing, 8 at last review). Current skills: `analyze-history`, `audit-claude-config`, `audit-docs`, `capture-issue`, `confidence-check`, `configure`, `create-loop`, `format-issue`, `init`, `issue-size-review`, `issue-workflow`, `loop-suggester`, `manage-issue`, `map-dependencies`, `product-analyzer`, `workflow-automation-proposer`
- Assessment table needs complete rework to evaluate all 16 skills against the proactive-discovery criterion
- The original 4 migration candidates still exist in `skills/` — none have been migrated
- **BUG-364 blocker resolved**: marketplace version mismatch fixed, should be removed from Blocked By

---

## Tradeoff Review Note

**Reviewed**: 2026-02-11 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - The "proactive discovery" criterion needs validation with evidence:
1. Test whether Claude actually invokes these skills without user prompting
2. Provide evidence for why `issue-size-review` is proactive but `workflow-automation-proposer` is not
3. Measure actual token cost difference between skills and commands
4. Consider reviewing usage data from `ll-messages` logs before proceeding

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first - Assessment is stale (6 skills now 8, two new skills need evaluation). Lacks empirical evidence. Consistent recommendation across two reviews to validate assumptions with usage data first.
