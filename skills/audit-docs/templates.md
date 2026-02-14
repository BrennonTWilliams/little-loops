# Audit Docs Templates

This file contains templates and format specifications for the audit_docs skill.

## Issue File Template

```markdown
---
discovered_commit: [GIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [ISO_TIMESTAMP]
discovered_by: audit_docs
doc_file: [path/to/doc.md]
---

# [BUG|ENH]-XXX: [Title describing doc issue]

## Summary

Documentation issue found by `/ll:audit-docs`.

## Location

- **File**: `README.md`
- **Line(s)**: 45
- **Section**: Installation

## Current Content

```markdown
pip install old-package --deprecated-flag
```

## Problem

The install command uses a deprecated flag that no longer works.

## Expected Content

```markdown
pip install new-package
```

## Impact

- **Severity**: High (blocks new user setup)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug|enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: [DATE] | Priority: P1
```

## Auto-Fixable Findings Format

When presenting auto-fixable findings to the user:

```markdown
## Auto-Fixable Findings (N)

These can be corrected directly:

| # | File:Line | Finding | Fix |
|---|-----------|---------|-----|
| 1 | README.md:45 | Outdated install command | `old-syntax` → `new-syntax` |
| 2 | README.md:72 | Broken relative link | `docs/guide.md` → `docs/user-guide.md` |

## Findings Needing Issues (M)

These require investigation or design:

| # | File:Line | Finding | Suggested Issue Type |
|---|-----------|---------|---------------------|
| 3 | README.md:100 | Missing example output | ENH (P4) |
| 4 | docs/api.md:30 | Incomplete API docs | ENH (P3) |
```

## Proposed Issue Changes Format

Present this summary before making any changes:

```markdown
## Proposed Issue Changes

Based on documentation audit findings:

### New Issues to Create (N)

| Type | Priority | Title | File:Line |
|------|----------|-------|-----------|
| BUG | P1 | Outdated install command | README.md:45 |
| BUG | P2 | Broken link to guide.md | README.md:72 |
| ENH | P4 | Add example output for CLI | README.md:100 |

### Existing Issues to Update (N)

| Issue | Update Reason |
|-------|---------------|
| BUG-023 | Found additional broken link in same file |

### Completed Issues to Reopen (N)

| Issue | Reopen Reason |
|-------|---------------|
| BUG-015 | Link broken again after previous fix |

---

```

## Reopened Section Template

When reopening a completed issue, append this section:

```markdown
---

## Reopened

- **Date**: [TODAY]
- **By**: audit_docs
- **Reason**: Documentation issue recurred

### New Findings

The same broken link issue was found again at README.md:72.
This may indicate the fix was incomplete or regressed.
```

## Audit Report Format

```markdown
# Documentation Audit Report

## Summary
- **Files audited**: X
- **Issues found**: Y
  - Critical: N
  - Warning: N
  - Info: N

## Results by File

### README.md

| Check | Status | Details |
|-------|--------|---------|
| Code examples | PASS | All examples run |
| File paths | WARN | 2 broken links |
| API refs | PASS | Match codebase |
| Commands | FAIL | Install command outdated |

#### Issues
1. **[CRITICAL]** Line 45: Install command uses deprecated flag
2. **[WARNING]** Line 72: Link to docs/guide.md is broken
3. **[INFO]** Line 100: Consider adding example output

### docs/api.md
[Similar breakdown]

## Recommended Fixes

### Critical (Must Fix)
1. Update install command in README.md:45
   - Old: `pip install old-syntax`
   - New: `pip install new-syntax`

### Warnings (Should Fix)
2. Fix broken link in README.md:72
3. Update version number in docs/install.md

### Suggestions
4. Add example output for commands
5. Include troubleshooting section

## Auto-Fixable Issues
The following can be automatically corrected:
- [ ] Update version numbers
- [ ] Fix relative links
- [ ] Format code blocks

Run with `--fix` to apply automatic corrections.
```

## Finding Classification Table

| Category | Criteria | Examples |
|----------|----------|----------|
| **Auto-fixable** | Specific old/new content known, mechanical replacement | Wrong counts, outdated paths, broken relative links, incorrect version numbers, wrong command syntax |
| **Needs issue** | Requires investigation, writing, or design decisions | Missing sections, incomplete docs, content rewrites, new examples needed |

## Finding-to-Issue Mapping

| Finding Severity | Finding Type | Issue Type | Priority |
|-----------------|--------------|------------|----------|
| CRITICAL | Wrong/outdated command | BUG | P1 |
| CRITICAL | Incorrect API reference | BUG | P1 |
| CRITICAL | Broken installation steps | BUG | P1 |
| WARNING | Broken link | BUG | P2 |
| WARNING | Outdated version number | BUG | P2 |
| WARNING | Missing error handling docs | ENH | P3 |
| INFO | Missing example output | ENH | P4 |
| INFO | Could add troubleshooting | ENH | P4 |

**Rule of thumb**:
- **BUG**: Information is *wrong* or *broken* - needs fixing to be accurate
- **ENH**: Information is *missing* or *incomplete* - needs addition to be complete
