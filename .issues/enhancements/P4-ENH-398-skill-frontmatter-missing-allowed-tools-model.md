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

| Skill | Suggested model | Needs write tools? | Actual tools used |
|-------|----------------|-------------------|-------------------|
| `analyze-history` | haiku | No — CLI orchestration | Bash |
| `confidence-check` | sonnet | No — read-only evaluation | Glob, Grep |
| `issue-size-review` | sonnet | No — read + Bash for git mv | Glob, Bash |
| `issue-workflow` | haiku | No — reference-only, no tool calls | None |
| `loop-suggester` | sonnet | No — reads input files | Read |
| `map-dependencies` | sonnet | No — CLI orchestration | Bash |
| `product-analyzer` | sonnet | No — read-only analysis | Read, Glob, Grep |
| `workflow-automation-proposer` | sonnet | Yes — writes YAML output | Read, Write |

Example (note: `allowed-tools` uses comma-separated string format per `docs/claude-code/skills.md:167`):
```yaml
---
description: "..."
model: haiku
allowed-tools: Read, Glob, Grep, Bash
---
```

## Integration Map

### Files to Modify
- `skills/analyze-history/SKILL.md` — add `model: haiku`, `allowed-tools: Bash, Read, Glob, Grep`
- `skills/confidence-check/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`
- `skills/issue-size-review/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep, Bash`
- `skills/issue-workflow/SKILL.md` — add `model: haiku`, `allowed-tools: Read`
- `skills/loop-suggester/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`
- `skills/map-dependencies/SKILL.md` — add `model: sonnet`, `allowed-tools: Bash, Read, Glob, Grep`
- `skills/product-analyzer/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`
- `skills/workflow-automation-proposer/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Write, Glob, Grep`

### Similar Patterns
- `commands/scan_codebase.md:1-5` — uses `allowed-tools: [Bash(git:*, gh:*), Task, TodoWrite]` (command array format)
- `commands/analyze-workflows.md:1-9` — uses `allowed-tools: [Read, Write, Glob, Task, Bash, Skill, TodoWrite]`
- `docs/claude-code/skills.md:162-168` — canonical skill frontmatter example with comma-separated string format

### Dependent Files (Callers/Importers)
- `agents/plugin-config-auditor.md:39,74` — audits `allowed_tools` and `model` fields; will validate these additions
- `agents/consistency-checker.md` — cross-component validation may reference skill tool restrictions

### Tests
- N/A — skill markdown files are not Python-testable; verified via manual invocation
- Verify each skill still functions after adding restrictions by invoking it

### Documentation
- N/A — frontmatter-only changes to existing skill files
- `docs/claude-code/skills.md` — reference doc, no changes needed

## Implementation Steps

1. **Add frontmatter to reference-only skills** (no tool calls):
   - `skills/issue-workflow/SKILL.md` — add `model: haiku` and `allowed-tools: Read` (purely reference, no tool invocations in body)

2. **Add frontmatter to CLI-orchestration skills** (Bash-only):
   - `skills/analyze-history/SKILL.md` — add `model: haiku`, `allowed-tools: Bash, Read, Glob, Grep` (runs `ll-history` CLI commands)
   - `skills/map-dependencies/SKILL.md` — add `model: sonnet`, `allowed-tools: Bash, Read, Glob, Grep` (runs `ll-deps` CLI commands)

3. **Add frontmatter to read-only analysis skills**:
   - `skills/confidence-check/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`
   - `skills/product-analyzer/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`
   - `skills/loop-suggester/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep`

4. **Add frontmatter to skills requiring Bash or Write**:
   - `skills/issue-size-review/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Glob, Grep, Bash` (uses `git mv` for renaming)
   - `skills/workflow-automation-proposer/SKILL.md` — add `model: sonnet`, `allowed-tools: Read, Write, Glob, Grep` (writes step3-proposals.yaml)

5. **Test each skill** — invoke each skill to verify it still functions with restricted tools. Pay special attention to skills that spawn sub-agents (Task tool) — these may need `Task` in allowed-tools if Claude Code doesn't inherit it automatically

## Impact

- **Priority**: P4 - Security/cost improvement
- **Effort**: Small - Frontmatter additions to 8 files
- **Risk**: Low - Tool restrictions could break skills if too narrow
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding frontmatter fields to existing skill files
- **Out of scope**: Rewriting skill body content or changing skill behavior

## Blocked By

- ~~BUG-402: Commands reference $ARGUMENTS inconsistently~~ — **Resolved** (completed, in `.issues/completed/`)

## Labels

`enhancement`, `skills`, `security`, `configuration`

## Session Log
- /ll:format_issue --all --auto - 2026-02-13
- /ll:refine_issue - 2026-02-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f443c963-bde0-44b6-bee4-1a88f2ca6a7a.jsonl`

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
