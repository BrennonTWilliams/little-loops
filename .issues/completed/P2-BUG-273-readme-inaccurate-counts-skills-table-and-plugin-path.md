---
discovered_commit: 59ef770
discovered_branch: main
discovered_date: 2026-02-07T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-273: README has inaccurate counts, wrong skills table, and wrong plugin.json path

## Summary

Documentation issue found by `/ll:audit_docs`. Multiple inaccuracies in README.md:

1. **Command count** says "34 slash commands" — actual count is **35**
2. **Skills table** lists 4 agents as skills and includes `capture-issue` (a command) as a skill
3. **plugin.json path** in directory tree shows root — actual location is `.claude-plugin/plugin.json`

This is a **regression** of completed issues BUG-156 (plugin.json path) and BUG-161 (command count).

## Location

- **File**: `README.md`
- **Lines**: 25, 27, 369-377, 589

## Current Content

### Command count (line 25)
```markdown
- **34 slash commands** for development workflows
```

### Skills table (lines 369-377)
Lists `codebase-analyzer`, `codebase-locator`, `codebase-pattern-finder`, `workflow-pattern-analyzer` as skills — these are agents, not skills. Also lists `capture-issue` which is a command, not a skill.

### Directory tree (line 589)
```markdown
├── plugin.json           # Plugin manifest
```

## Expected Content

### Command count
```markdown
- **35 slash commands** for development workflows
```

### Skills table
The actual 6 skills are: `analyze-history`, `issue-size-review`, `issue-workflow`, `map-dependencies`, `product-analyzer`, `workflow-automation-proposer`.

### Directory tree
```markdown
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
```

## Files to Update

1. **README.md**
   - Line 25: Update command count to 35
   - Line 27: Fix skill description (replace "dependency mapping" with "map-dependencies")
   - Lines 369-377: Replace skills table — remove agents, add actual skills
   - Line 589: Fix plugin.json path in directory tree
   - Line 592: Update command count in directory tree comment

## Impact

- **Severity**: Medium (misleading documentation for users and contributors)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `regression`

---

## Status

**Completed** | Created: 2026-02-07 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `README.md`: Updated command count from 34 to 35 (line 25 and directory tree)
- `README.md`: Fixed skill description on line 27 ("workflow reference" → "issue workflow reference")
- `README.md`: Replaced incorrect skills table (removed 4 agents + 1 command, added actual 6 skills)
- `README.md`: Fixed plugin.json path in directory tree (root → `.claude-plugin/plugin.json`)

### Verification Results
- Command count: 35 (matches `ls commands/*.md | wc -l`)
- Skill count: 6 (matches `ls skills/*/SKILL.md | wc -l`)
- plugin.json location: `.claude-plugin/plugin.json` (confirmed exists)
- No stale references remain in README
