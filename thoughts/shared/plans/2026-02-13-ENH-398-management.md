# ENH-398: Skill frontmatter missing allowed-tools and model fields - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-398-skill-frontmatter-missing-allowed-tools-model.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

8 of 16 skills have only `description` in their frontmatter. The other 8 already have `allowed-tools` using YAML array format. No skills currently use the `model` field.

### Key Discoveries
- All existing skills use YAML array format: `- ToolName` (one per line)
- Bash tools use parameterized format: `Bash(command:*)`
- `confidence-check` uses Bash (find), Glob, Grep, Read, AND Edit (updates frontmatter) — issue only listed Glob/Grep
- `issue-size-review` uses Glob, Read, Bash (ll-next-id, git mv)
- `loop-suggester` uses Bash (optional file load) — not just Read
- `map-dependencies` uses Bash (ll-deps CLI) — issue correctly identified
- `workflow-automation-proposer` uses Read and needs Write for YAML output

### Patterns to Follow
- YAML array format for `allowed-tools` (consistent with all 8 existing skills)
- `Bash(command:*)` parameterization pattern from `skills/create-loop/SKILL.md`
- `model` field: use short names (haiku, sonnet) matching agent frontmatter convention

## What We're NOT Doing
- Not changing skill body content
- Not adding `arguments` fields (separate concern)
- Not modifying the 8 skills that already have `allowed-tools`

## Implementation

### Phase 1: Add frontmatter to all 8 skills

Based on actual tool usage analysis (not just issue suggestions):

| Skill | model | allowed-tools |
|-------|-------|---------------|
| `analyze-history` | haiku | `Bash(ll-history:*)` |
| `confidence-check` | sonnet | `Read, Glob, Grep, Edit, Bash(find:*)` |
| `issue-size-review` | sonnet | `Read, Glob, Bash(ll-next-id:*, git:*)` |
| `issue-workflow` | haiku | (none — pure reference) |
| `loop-suggester` | sonnet | `Read, Glob, Grep, Bash(ll-messages:*)` |
| `map-dependencies` | sonnet | `Read, Glob, Grep, Bash(ll-deps:*, git:*)` |
| `product-analyzer` | sonnet | `Read, Glob, Grep` |
| `workflow-automation-proposer` | sonnet | `Read, Write, Glob, Grep` |

**Design decisions:**
- `issue-workflow`: No `allowed-tools` since it's purely reference text with no tool invocations
- `confidence-check`: Added Edit (writes confidence_score to frontmatter) and Bash(find:*) per actual usage
- `loop-suggester`: Added Bash for optional ll-messages file loading, plus Glob/Grep for analysis
- CLI wrapper skills: Bash restricted to specific CLI tool patterns

### Success Criteria
- [ ] All 8 skill files have `model` field added
- [ ] 7 of 8 skill files have `allowed-tools` added (issue-workflow excluded)
- [ ] YAML format matches existing skill patterns
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
