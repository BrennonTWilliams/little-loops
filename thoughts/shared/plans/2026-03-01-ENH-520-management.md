# ENH-520: Deprecate and Remove ll-next-id

## Plan Summary

Remove the standalone `ll-next-id` CLI tool which is redundant with `ll-issues next-id`. Both call `get_next_issue_number()` — only the unified form should remain.

## Changes

### 1. Core Removal
- **Delete** `scripts/little_loops/cli/next_id.py`
- **Remove** `ll-next-id` entry from `scripts/pyproject.toml` line 58
- **Remove** `main_next_id` import/export from `scripts/little_loops/cli/__init__.py` (lines 15, 25, 42)
- **Delete** `scripts/tests/test_cli_next_id.py`
- **Update** `scripts/tests/test_issues_cli.py` — remove parity test `test_next_id_matches_ll_next_id` (lines 59-83)

### 2. Documentation Updates (remove `ll-next-id` references)
- `.claude/CLAUDE.md` line 115 — remove from CLI Tools list
- `commands/help.md` line 198 — remove from CLI tools section
- `README.md` lines 337-344 — remove `### ll-next-id` section; update `ll-issues next-id` description (remove "(same as ll-next-id)")

### 3. Command/Skill Updates (replace `ll-next-id` → `ll-issues next-id`)
- `commands/scan-codebase.md` lines 228, 230
- `commands/scan-product.md` lines 207, 209
- `commands/normalize-issues.md` line 7 (allowed-tools) and line 165 (bash)
- `commands/find-dead-code.md` line 253
- `skills/capture-issue/SKILL.md` line 12 (allowed-tools) and line 201 (bash)
- `skills/issue-size-review/SKILL.md` line 10 (allowed-tools) and line 119 (bash)

## Success Criteria
- [ ] `ll-next-id` entry point removed from pyproject.toml
- [ ] `next_id.py` module deleted
- [ ] `main_next_id` removed from cli/__init__.py
- [ ] Tests deleted/updated
- [ ] All doc references updated to `ll-issues next-id`
- [ ] All allowed-tools updated from `ll-next-id` to `ll-issues`
- [ ] Tests pass
- [ ] Lint passes
