---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-279: Audit skill vs command allocation

## Summary

Review the current 6 skills against the "proactive discovery" criterion: skills should be things Claude auto-discovers and uses proactively, while commands are for user-invoked actions. SuperClaude validates this distinction — they have only 1 skill (confidence-check) and 30 commands. Some of our skills may be better as commands.

## Current Behavior

We have 6 skills, each consuming character budget in the system prompt and signaling to Claude to consider them proactively. However, several skills are only invoked when a user explicitly asks:

| Skill | Proactive? | Assessment |
|---|---|---|
| `workflow-automation-proposer` | No — Step 3 of a pipeline, always user-invoked | Candidate for command |
| `product-analyzer` | No — Requires explicit user intent | Candidate for command |
| `analyze-history` | No — User asks for it | Candidate for command |
| `issue-workflow` | No — Reference doc, user asks for it | Candidate for command |
| `issue-size-review` | Yes — Could be proactive during sprint planning | Keep as skill |
| `map-dependencies` | Yes — Could be proactive during sprint planning | Keep as skill |

## Expected Behavior

Evaluate each skill and migrate candidates from `skills/` to `commands/` where appropriate:

1. Apply the criterion: "Would Claude proactively invoke this without the user asking?"
2. Consider character budget impact — skills and commands consume budget equally, but skills add context load by signaling proactive consideration
3. Migrate 4 candidates (`workflow-automation-proposer`, `product-analyzer`, `analyze-history`, `issue-workflow`) to commands if analysis confirms they are always user-initiated
4. Keep `issue-size-review` and `map-dependencies` as skills

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

1. Validate the proactive discovery criterion for each of the 6 skills
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
- Verify migrated commands are accessible after migration

### Documentation
- `docs/ARCHITECTURE.md` - Update skill/command listing

### Configuration
- `.claude-plugin/plugin.json` - Remove migrated skill entries

## Impact

- **Priority**: P4
- **Effort**: Medium
- **Risk**: Low — current allocation works, this is optimization

## Blocked By

- ENH-368: plugin-config-auditor missing hook event and handler types (shared docs/ARCHITECTURE.md)

## Blocks

- ENH-366: add agents directory to plugin.json (shared plugin.json)

## Labels

`enhancement`, `skills`, `commands`, `architecture`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P4

---

## Verification Notes

- **Verified**: 2026-02-12
- **Verdict**: NEEDS_UPDATE
- **Skills count changed**: Now 8 skills exist (was 6 at time of writing). Two new skills added since issue creation:
  - `confidence-check` — likely a strong "keep as skill" candidate (Claude could proactively invoke before implementation)
  - `loop-suggester` — needs proactive-discovery assessment
- Assessment table should be updated to include both new skills
- The 4 migration candidates (`workflow-automation-proposer`, `product-analyzer`, `analyze-history`, `issue-workflow`) still exist in `skills/` — none have been migrated
- The 2 "keep as skill" recommendations (`issue-size-review`, `map-dependencies`) still exist

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
