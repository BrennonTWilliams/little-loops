# ENH-464: Audit Missing Agent and Skill Frontmatter Field Validation

## Plan Summary

Extend `plugin-config-auditor` to validate 8 additional agent frontmatter fields and 4 additional skill frontmatter fields. Add 3 new cross-reference checks to `consistency-checker` for agent `skills`, skill `agent`, and agent `mcpServers` fields.

## Research Findings

### Current State
- **plugin-config-auditor** validates agents on 6 dimensions (description, triggers, examples, tools, model, system prompt) — no frontmatter field type/value validation
- **plugin-config-auditor** validates skills on 4 dimensions (description, content, structure, duplication) — no frontmatter field type/value validation
- **consistency-checker** has 13 cross-reference check types
- No existing agents/skills use the missing frontmatter fields yet, but validation should be in place for when they are added

### Files to Modify
1. `agents/plugin-config-auditor.md` — Add validation rules
2. `agents/consistency-checker.md` — Add cross-reference checks

## Implementation Phases

### Phase A: Extend plugin-config-auditor Agent Frontmatter Validation

Add to Core Responsibilities section 1 (Agent Definitions) and Audit Checklist "For Each Agent File":

**New agent field validation rules:**
1. `background` — boolean if present (WARNING if non-boolean)
2. `isolation` — must be `worktree` or absent (WARNING if other value)
3. `memory` — must be one of `user`, `project`, `local` if present; INFO if memory directory doesn't exist yet
4. `mcpServers` — entries must have `command` field (WARNING if malformed)
5. `skills` — references must be skill directory names (cross-ref in Wave 2)
6. `permissionMode` — must be one of `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` (WARNING if invalid)
7. `maxTurns` — positive integer if present (WARNING if non-positive or non-integer)
8. `disallowedTools` — entries must not overlap with `tools` entries (WARNING if overlap)

### Phase B: Extend plugin-config-auditor Skill Frontmatter Validation

Add to Core Responsibilities section 2 (Skill Definitions) and Audit Checklist "For Each Skill File":

**New skill field validation rules:**
1. `once` — boolean if present (WARNING if non-boolean)
2. `context` — must be `fork` or absent; if `fork`, should have corresponding `agent` field (WARNING if missing)
3. `agent` — must resolve to existing agent file (cross-ref in Wave 2)
4. `hooks` — entries must follow hook validation rules (same event types, handler types)

### Phase C: Add Cross-Reference Checks to consistency-checker

Add 3 new rows to Cross-Reference Matrix and corresponding collection/validation/output:

1. **Agent `skills` → Skill Directories**: `agents/*.md` skills field → `skills/X/` directory exists
2. **Skill `agent` → Agent Files**: `skills/*/SKILL.md` agent field → `agents/X.md` exists
3. **Agent `mcpServers` → Valid Structure**: `agents/*.md` mcpServers field → has `command` field, command is valid

### Phase D: Update Output Formats

- Add new columns/checks to agent audit table in plugin-config-auditor
- Add new check sections to consistency-checker output
- Add new rows to consistency-checker summary table

## Success Criteria

- [ ] plugin-config-auditor validates all 8 agent frontmatter fields
- [ ] plugin-config-auditor validates all 4 skill frontmatter fields
- [ ] consistency-checker has 3 new cross-reference checks
- [ ] Output formats updated to include new validations
- [ ] All validations use appropriate severity levels
