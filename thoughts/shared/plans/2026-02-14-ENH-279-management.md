# ENH-279: Audit Skill vs Command Allocation — Implementation Plan

## Research Findings Summary

### Key Discovery: `disable-model-invocation` Is the Right Mechanism

The Claude Code skills documentation (`docs/claude-code/skills.md`) reveals that skills and commands are **functionally identical** in Claude Code. The documentation states:

> "Custom slash commands have been merged into skills. A file at `.claude/commands/review.md` and a skill at `.claude/skills/review/SKILL.md` both create `/review` and work the same way."

The real mechanism to control proactive invocation is the **`disable-model-invocation: true`** frontmatter field:
- When set to `true`: Only the user can invoke the skill (description not loaded into context)
- When not set (default `false`): Both user and Claude can invoke it (description always in context)

**Currently: NONE of the 16 skills use `disable-model-invocation: true`**, meaning all 16 descriptions are consuming character budget in Claude's context for proactive consideration.

### Why NOT to Migrate Skills Back to Commands

The original ENH-279 proposal to move skills to `commands/` is **the wrong approach** for three reasons:

1. **ENH-400 already migrated 8 oversized commands INTO skills** for subdirectory support. Moving them back would reverse that work and lose the ability to split large files.
2. **Skills support subdirectories** for reference material (templates.md, areas.md, etc.). Commands are flat single files. 8 of our skills use this subdirectory feature.
3. **`disable-model-invocation: true`** solves the actual problem (proactive context loading) without file moves.

### Current State

| Skill | Has Subdirectory Files | Should Be Proactive | Action |
|-------|----------------------|---------------------|--------|
| `analyze-history` | No (1 file) | No — user-initiated | Add `disable-model-invocation: true` |
| `audit-claude-config` | Yes (2 files) | No — user-initiated | Add `disable-model-invocation: true` |
| `audit-docs` | Yes (2 files) | No — user-initiated | Add `disable-model-invocation: true` |
| `capture-issue` | Yes (2 files) | **Yes** — proactive when bugs discovered | Keep as-is |
| `confidence-check` | No (1 file) | **Yes** — proactive before implementation | Keep as-is |
| `configure` | Yes (3 files) | No — user-initiated setup | Add `disable-model-invocation: true` |
| `create-loop` | Yes (4 files) | No — user-initiated creation | Add `disable-model-invocation: true` |
| `format-issue` | Yes (2 files) | No — user-initiated formatting | Add `disable-model-invocation: true` |
| `init` | Yes (3 files) | No — user-initiated setup | Add `disable-model-invocation: true` |
| `issue-size-review` | No (1 file) | **Yes** — proactive during sprint planning | Keep as-is |
| `issue-workflow` | No (1 file) | No — reference doc, user asks | Add `disable-model-invocation: true` |
| `loop-suggester` | No (1 file) | No — user-initiated | **Remove** (duplicate of command) |
| `manage-issue` | Yes (2 files) | No — user-initiated | Add `disable-model-invocation: true` |
| `map-dependencies` | No (1 file) | **Yes** — proactive during sprint planning | Keep as-is |
| `product-analyzer` | No (1 file) | No — invoked by `scan-product` command | Add `disable-model-invocation: true` |
| `workflow-automation-proposer` | No (1 file) | No — Step 3 of pipeline | Add `disable-model-invocation: true` |

### Summary of Changes

- **Keep proactive (4 skills)**: `capture-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`
- **Add `disable-model-invocation: true` (11 skills)**: `analyze-history`, `audit-claude-config`, `audit-docs`, `configure`, `create-loop`, `format-issue`, `init`, `issue-workflow`, `manage-issue`, `product-analyzer`, `workflow-automation-proposer`
- **Remove duplicate (1 skill)**: `loop-suggester` skill (command version exists at `commands/loop-suggester.md`)

---

## Implementation Phases

### Phase 1: Add `disable-model-invocation: true` to 11 Skills

For each of these 11 skills, add `disable-model-invocation: true` to the YAML frontmatter:

1. `skills/analyze-history/SKILL.md`
2. `skills/audit-claude-config/SKILL.md`
3. `skills/audit-docs/SKILL.md`
4. `skills/configure/SKILL.md`
5. `skills/create-loop/SKILL.md`
6. `skills/format-issue/SKILL.md`
7. `skills/init/SKILL.md`
8. `skills/issue-workflow/SKILL.md`
9. `skills/manage-issue/SKILL.md`
10. `skills/product-analyzer/SKILL.md`
11. `skills/workflow-automation-proposer/SKILL.md`

### Phase 2: Remove Duplicate `loop-suggester` Skill

The `commands/loop-suggester.md` already exists and references `skills/loop-suggester/SKILL.md` for templates. Since the skill is a single file (no subdirectory supporting files), inline any unique template content from the skill into the command, then delete `skills/loop-suggester/`.

**Steps:**
1. Compare `skills/loop-suggester/SKILL.md` with `commands/loop-suggester.md`
2. Inline any unique YAML templates from the skill into the command
3. Remove the `skills/loop-suggester/` directory
4. Update `commands/loop-suggester.md` to remove references to the deleted skill file

### Phase 3: Update Documentation

1. **`docs/ARCHITECTURE.md`** — Update skills directory tree to reflect actual 15 skills (was stale at "8 skill definitions")
2. **`commands/help.md`** — No changes needed (lists commands, not skills)
3. **Issue file** — Update ENH-279 with resolution notes

### Phase 4: Verification

- `python -m pytest scripts/tests/` — Tests pass
- `ruff check scripts/` — Lint clean
- `python -m mypy scripts/little_loops/` — Types pass
- Manual: Verify `/ll:help` still works, verify proactive skills still show in context

---

## Success Criteria

- [ ] 11 skills have `disable-model-invocation: true` in frontmatter
- [ ] 4 proactive skills (`capture-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`) remain unchanged
- [ ] `loop-suggester` skill directory removed; command has all needed content
- [ ] `docs/ARCHITECTURE.md` skills tree is accurate
- [ ] All tests pass
- [ ] All lint/type checks pass

---

## Risk Assessment

- **Risk**: Low — adding frontmatter fields is non-breaking
- **Rollback**: Remove the `disable-model-invocation: true` lines to restore previous behavior
- **Impact**: Reduces context budget consumption by ~11 skill descriptions, improving Claude's ability to focus on the 4 genuinely proactive skills
