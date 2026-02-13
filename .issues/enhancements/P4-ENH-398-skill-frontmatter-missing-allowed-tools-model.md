---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-398: Skill frontmatter missing allowed-tools and model fields

## Summary

All 8 skills in `skills/` have only `description` in their frontmatter. Per `docs/claude-code/skills.md`, skills support `allowed-tools` and `model` fields. Reference-only skills like `issue-workflow` and read-only CLI skills like `analyze-history` should restrict write tools. Simple reference skills could use `model: haiku` for cost savings.

## Current Behavior

Every skill SKILL.md has minimal frontmatter:
```yaml
---
description: "..."
---
```

No `allowed-tools` or `model` fields are specified.

## Motivation

This enhancement would:
- Improve security scoping by restricting each skill to only the tools it needs
- Business value: Cost optimization by using `haiku` for simple reference and CLI skills instead of defaulting to the parent model
- Technical debt: Aligns skill frontmatter with all documented fields in the skills reference

## Expected Behavior

Skills should specify tool restrictions where appropriate:

| Skill | Suggested model | Needs write tools? |
|-------|----------------|-------------------|
| `analyze-history` | haiku | No - read-only CLI analysis |
| `confidence-check` | sonnet | No - read-only evaluation |
| `issue-size-review` | sonnet | No - read-only analysis |
| `issue-workflow` | haiku | No - reference-only |
| `map-dependencies` | sonnet | Yes - writes dependency data |
| `product-analyzer` | sonnet | No - read-only analysis |
| `review-sprint` | sonnet | No - read-only review |
| `workflow-automation-proposer` | sonnet | Yes - writes YAML output |

Example:
```yaml
---
description: "..."
model: haiku
allowed-tools: ["Read", "Glob", "Grep", "Bash"]
---
```

## Integration Map

### Files to Modify
- `skills/analyze-history/SKILL.md`
- `skills/confidence-check/SKILL.md`
- `skills/issue-size-review/SKILL.md`
- `skills/issue-workflow/SKILL.md`
- `skills/map-dependencies/SKILL.md`
- `skills/product-analyzer/SKILL.md`
- `skills/review-sprint/SKILL.md`
- `skills/workflow-automation-proposer/SKILL.md`

### Tests
- Verify each skill still functions correctly after adding restrictions

## Implementation Steps

1. Review each skill's body to determine actual tool usage
2. Add `model` field (haiku for reference/simple skills, sonnet for analysis)
3. Add `allowed-tools` where skills don't need write access
4. Test each skill still works with restricted tools

## Impact

- **Priority**: P4 - Security/cost improvement
- **Effort**: Small - Frontmatter additions to 8 files
- **Risk**: Low - Tool restrictions could break skills if too narrow
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding frontmatter fields to existing skill files
- **Out of scope**: Rewriting skill body content or changing skill behavior

## Blocked By

- BUG-402: Commands reference $ARGUMENTS inconsistently — argument handling bug should be fixed before adding tool restrictions

## Labels

`enhancement`, `skills`, `security`, `configuration`

## Session Log
- /ll:format_issue --all --auto - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- **`review-sprint` is a command, not a skill** — listed in table but `skills/review-sprint/` does not exist; it is `commands/review_sprint.md`
- **`loop-suggester` missing from table** — exists at `skills/loop-suggester/SKILL.md` but not listed
- Correct 8 skills: `analyze-history`, `confidence-check`, `issue-size-review`, `issue-workflow`, `loop-suggester`, `map-dependencies`, `product-analyzer`, `workflow-automation-proposer`
- Core issue still valid: no skills have `allowed-tools` or `model` in frontmatter

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
