---
discovered_date: 2026-02-06
discovered_by: capture_issue
---

# ENH-260: Fix align_issues Workflow and Argument Handling

## Summary

Fix incorrect guidance in `/ll:capture_issue` that tells users to run `/ll:align_issues` to discover relevant docs (it should reference `/ll:normalize_issues`), and update `/ll:align_issues` to support: (1) no-argument mode that checks each active issue against its already-linked Key Documents, and (2) document-path argument mode that checks all active issues against a specific document regardless of linked docs.

## Context

User description: "Currently, when we capture a new Issue, we tell the user to 'Run `/ll:align_issues` to discover relevant docs.' - this is NOT what `/ll:align_issues` is for! If Key Document tracking is enabled in `ll-config`, then `/ll:normalize_issues` should automatically link relevant key documents to Issues and add them to the Issue file's frontmatter. When we run `/ll:align_issues` with no argument provided, it should check each active Issue's alignment against its linked Key Document(s) (if present). Alternatively, the user can run `/ll:align_issues` with an argument like `/ll:align_issues docs/architecture-rules.md` or `/ll:align_issues architecture-rules.md`, and it will review each Active Issue against alignment to the passed document, regardless of each issue's linked Key Documents."

## Current Behavior

1. `capture_issue.md` lines 368 and 420 contain placeholder text: `_No documents linked. Run /ll:align_issues to discover relevant docs._` — this is incorrect since `align_issues` validates alignment, not discovers/links documents.
2. `/ll:align_issues` requires a **category** argument (e.g., `architecture`, `product`, `--all`) — it cannot run without an argument, and it cannot accept a specific document path.
3. `/ll:normalize_issues` already has Section 7b to auto-link documents when `documents.enabled` — this is the correct tool for document discovery.

## Expected Behavior

1. `capture_issue.md` placeholder text should reference `/ll:normalize_issues` for document linking, not `/ll:align_issues`.
2. `/ll:align_issues` with **no argument**: Check each active issue against its own linked Key Documents (from the "Related Key Documentation" section in the issue file). Skip issues with no linked documents.
3. `/ll:align_issues` with a **document path** argument (e.g., `docs/architecture-rules.md`): Check all active issues against alignment with the specified document, regardless of each issue's linked Key Documents.
4. `/ll:align_issues` with a **category** argument (existing behavior): Continue to work as today — check all issues against all documents in that category.

## Proposed Solution

### 1. Fix `capture_issue.md` placeholder text

Change both occurrences (lines 368, 420) from:
```
_No documents linked. Run `/ll:align_issues` to discover relevant docs._
```
To:
```
_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._
```

### 2. Update `align_issues.md` argument handling

Change the `category` argument from **required** to **optional** and add document path support:

- **No argument**: Iterate active issues, read each issue's "Related Key Documentation" section, perform alignment checks against those specific linked documents. Skip issues with no linked docs (report them as "no linked docs — run `/ll:normalize_issues` first").
- **Document path argument** (detected by `.md` extension or `/` in argument): Read the specified document, check all active issues against it.
- **Category argument** (existing): Unchanged behavior.
- **`--all`**: Unchanged behavior.

### 3. Argument detection logic

```
IF no argument provided:
  MODE = "linked-docs"  # Check each issue against its own linked docs
ELIF argument ends in ".md" OR contains "/":
  MODE = "specific-doc"  # Check all issues against this document
ELIF argument == "--all":
  MODE = "all-categories"  # Existing behavior
ELSE:
  MODE = "category"  # Existing behavior
```

## Impact

- **Priority**: P3
- **Effort**: Small — Two command file edits, no schema or Python changes
- **Risk**: Low — Backwards compatible, existing category-based usage unchanged

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Command definition patterns |
| guidelines | CONTRIBUTING.md | Development conventions |

## Labels

`enhancement`, `alignment`, `commands`, `workflow`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `commands/capture_issue.md`: Changed both placeholder text occurrences (lines 368, 420) from referencing `/ll:align_issues` to `/ll:normalize_issues`
- `commands/align_issues.md`: Made `category` argument optional, added mode detection logic (linked-docs, specific-doc, category, all-categories), updated argument docs and examples

### Verification Results
- Tests: PASS (2455 passed)
- Lint: PASS
- Types: N/A (markdown command files only)
