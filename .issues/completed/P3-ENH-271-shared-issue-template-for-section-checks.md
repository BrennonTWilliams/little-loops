---
discovered_date: 2026-02-07
discovered_by: capture_issue
---

# ENH-271: Extract Issue Section Checks into Shared Template File

## Summary

The issue management commands (`refine_issue`, `normalize_issues`, `capture_issue`, `ready_issue`, `scan_codebase`) each hard-code their own understanding of what sections an issue should contain per type (BUG/FEAT/ENH). This leads to drift between commands — one command may require "Steps to Reproduce" for BUGs while another checks for "Reproduction Steps". Extract these section definitions into a shared template file that all issue management commands reference consistently.

## Context

Identified from conversation analyzing where `/ll:refine_issue` gets its section checks. The checks are entirely inline in `commands/refine_issue.md` (lines 52-130) as markdown tables. Similarly, `capture_issue` has its own hard-coded "full" and "minimal" templates. There is no single source of truth for what sections each issue type should have.

The `templates/` directory currently only contains project-type config templates (e.g., `typescript.json`, `python-generic.json`) — not issue structure templates.

## Current Behavior

- `refine_issue` defines BUG/FEAT/ENH section checklists inline (required, conditional, nice-to-have)
- `capture_issue` defines "full" and "minimal" issue templates inline
- `ready_issue` presumably has its own inline validation expectations
- `scan_codebase` creates issues with its own inline structure
- `normalize_issues` checks filenames but has no shared section awareness
- No single source of truth for issue structure per type

## Expected Behavior

- A shared template file (e.g., `templates/issue-schemas.json` or `templates/issue-types.yaml`) defines per-type section requirements
- All issue management commands reference this shared template
- Adding a new required section to BUG issues updates behavior across all commands simultaneously
- Template includes: section name, required/conditional/nice-to-have classification, description, and default prompt question

## Proposed Solution

TBD - requires investigation into:
1. Template format (JSON vs YAML vs markdown)
2. How commands currently consume their inline definitions
3. Whether `{{config.*}}` interpolation can reference template files
4. Which commands need updating (at minimum: `refine_issue`, `capture_issue`, `ready_issue`, `scan_codebase`)

## Impact

- **Priority**: P3
- **Effort**: Medium — touching multiple command definitions
- **Risk**: Low — internal refactor, no user-facing behavior change

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Plugin structure and command system |
| guidelines | .claude/CLAUDE.md | Issue file format specification |

## Labels

`enhancement`, `captured`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `templates/issue-sections.json`: Created shared issue section definitions file with common_sections, type_sections (BUG/FEAT/ENH), creation_variants (full/minimal), and quality_checks
- `commands/refine_issue.md`: Replaced inline BUG/FEAT/ENH section tables and quality checks with references to shared template
- `commands/capture_issue.md`: Replaced inline "full" and "minimal" issue templates with shared template reference using creation_variants
- `commands/ready_issue.md`: Replaced inline Required Sections checklist with shared template reference
- `commands/scan_codebase.md`: Replaced inline issue creation template with shared template reference, standardized section names (e.g., "Steps to Reproduce" not "Reproduction Steps")

### Verification Results
- Tests: PASS (2607 passed)
- Lint: PASS (3 pre-existing unrelated warnings)
- Types: PASS

---

## Status

**Completed** | Created: 2026-02-07 | Completed: 2026-02-07 | Priority: P3
