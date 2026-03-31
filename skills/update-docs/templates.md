# Update Docs Templates

This file contains templates and format specifications for the update-docs skill.

## Gap Report Format

```markdown
# Documentation Gap Report

## Change Window
- **Since**: [git-ref or date] ([commit message or date description])
- **Through**: HEAD ([current HEAD short hash])
- **Generated**: [ISO timestamp]

## Summary
- **Source files changed**: N across M modules
- **Completed issues**: N
- **Documentation gaps found**: N
  - High priority: N (completed features with no doc coverage)
  - Medium priority: N (changed APIs/CLI with no doc update)
  - Low priority: N (internal changes that may affect docs)

---

## Gaps from Completed Issues (N)

These shipped features/changes have no documentation coverage:

| Priority | Issue | Title | Missing Coverage |
|----------|-------|-------|-----------------|
| High | ENH-740 | Add --elide flag to ll-loop show | No mention of `--elide` in docs/ or README.md |
| High | FEAT-721 | Add mcp_tool action type | `action_type: mcp_tool` undocumented in loop config docs |
| Medium | BUG-715 | Fix ll-issues show pagination | Pagination behavior not documented |

### ENH-740: Add --elide flag to ll-loop show

- **Completed**: 2026-03-10
- **Changed files**: `scripts/little_loops/cli/loop.py`
- **Search result**: No matches for "elide" or "--elide" in doc files
- **Suggested doc location**: `docs/reference/API.md` or `README.md` CLI section
- **Stub preview**: See stub template below

---

## Gaps from Source Changes (N)

These source files changed but no corresponding doc update was found:

| Priority | Module | Changed File | Last Change | Suspected Doc Gap |
|----------|--------|-------------|-------------|-------------------|
| Medium | ll-loop CLI | `scripts/little_loops/cli/loop.py` | 2026-03-10 | New flags not in README |
| Low | issue_history | `scripts/little_loops/issue_history/parsing.py` | 2026-03-08 | API docs may be stale |

### scripts/little_loops/cli/loop.py

- **Commits since ref**: `feat: add --elide flag`, `fix: handle empty state`
- **Affected doc files**: None updated since these commits
- **Suggested doc location**: `docs/reference/API.md`

---

## No Gaps Found (N)

The following completed issues and changed files appear to have adequate documentation coverage:

- ENH-730: All changed behavior documented in README.md
```

## Action Prompt Format

When presenting gaps for action selection (without `--fix` flag):

```markdown
## Documentation Gaps — Action Required

Found N gaps. For each gap, choose: Draft stub | Create issue | Skip

---

### [1/N] ENH-740: --elide flag undocumented

**Source**: Completed issue ENH-740 (2026-03-10)
**Gap**: `--elide` flag added to `ll-loop show` — no doc coverage found
**Suggested location**: `docs/reference/API.md` → `ll-loop show` section

Options:
- Draft stub → inserts placeholder in docs/reference/API.md
- Create issue → creates ENH issue for doc gap
- Skip → ignore this gap
```

## Stub Section Template

When drafting an inline documentation stub:

```markdown
<!-- TODO: update-docs stub — ENH-740 — drafted 2026-03-15 -->
### `--elide` Flag

> **Stub**: This section was auto-drafted by `/ll:update-docs`. Fill in details.

The `--elide` flag controls [describe behavior here].

**Usage:**
```bash
ll-loop show [loop-name] --elide
```

**Example output:**
```
[Add example output here]
```

**See also**: [related command or option]
<!-- END TODO stub -->
```

Adapt the stub to match the surrounding documentation style. Insert at the most logical location within the target doc file (e.g., after the existing option description for the same command).

## Doc Issue Template

When creating an issue for a documentation gap:

```markdown
---
discovered_date: [ISO_TIMESTAMP]
discovered_by: update-docs
source_issue: [ENH/BUG/FEAT-NNN or "git-change"]
since_ref: [git-ref or date used for analysis]
---

# ENH-NNN: Document [feature/component] in [doc-file]

## Summary

Documentation gap identified by `/ll:update-docs`. The [feature/component] introduced in [issue or commit] has no documentation coverage.

## Source

- **Type**: Completed issue | Git change
- **Issue/Commit**: [ENH-740 | abc1234]
- **Completed/Changed**: [date]
- **Changed files**: `scripts/little_loops/cli/loop.py`

## Gap Description

The `--elide` flag was added to `ll-loop show` in ENH-740 (2026-03-10). No existing documentation mentions this flag.

## Suggested Location

`docs/reference/API.md` in the `ll-loop show` options section.

## Suggested Content

Document the following:
- What the flag does
- Example usage
- Example output (if applicable)
- Any related flags or options

## Impact

- **Priority**: P3 - Undocumented user-facing feature
- **Effort**: Small — single section stub needed
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: [DATE] | Priority: P3
```

## Watermark File Format

`.ll/ll-update-docs.watermark` is a plain-text file containing a single git commit hash:

```
abc1234def5678
```

When this file exists and no `--since` argument is provided, the skill uses this hash as the since-ref, treating it as "last time update-docs was run." After a successful run, the file is updated to the current HEAD.
