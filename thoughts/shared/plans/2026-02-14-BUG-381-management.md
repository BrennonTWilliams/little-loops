# BUG-381: README skills count wrong and table missing loop-suggester

## Plan

### Problem
The README.md Skills table (lines 187-196) lists only 8 entries, but there are 15 skill directories under `skills/`. Additionally, `loop-suggester` is listed in the table but has no `skills/loop-suggester/` directory (it's a command only).

### Changes

**File: `README.md` (lines 185-196)**

1. Remove `loop-suggester` row (no skill directory exists)
2. Add 8 missing skills with descriptions from their SKILL.md files:
   - `audit-claude-config` → Meta-Analysis → Comprehensive audit of Claude Code plugin configuration
   - `audit-docs` → Code Quality → Audit documentation for accuracy and completeness
   - `capture-issue` → Issue Discovery → Capture issues from conversation or description
   - `configure` → Session & Config → Interactively configure specific areas in ll-config.json
   - `create-loop` → Automation & Loops → Create new FSM loop configuration interactively
   - `format-issue` → Issue Refinement → Format issue files to align with template v2.0 structure
   - `init` → Session & Config → Initialize little-loops configuration for a project
   - `manage-issue` → Planning & Implementation → Autonomously manage issues - plan, implement, verify, and complete
3. Verify final table has exactly 15 entries matching the count on line 86

### Success Criteria
- [ ] Skills table has 15 rows (matching "15 skills" on line 86)
- [ ] `loop-suggester` removed from Skills table
- [ ] All 15 skill directories represented in table
- [ ] Tests pass
- [ ] Lint passes
