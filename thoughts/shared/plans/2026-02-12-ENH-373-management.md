# ENH-373: Add missing Examples sections to commit and tradeoff_review_issues commands - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-373-add-missing-examples-to-commit-and-tradeoff-review-commands.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `commands/commit.md` (90 lines) — has no `## Examples` section. Ends with `---` (line 79) then `## Integration` (line 81).
- `commands/tradeoff_review_issues.md` (332 lines) — has no `## Examples` section. `## Integration` starts at line 325 with no preceding `---`.
- 32 of 34 command files have `## Examples` sections; these two are the only exceptions.
- Neither command accepts arguments, so no `arguments` frontmatter field is needed (consistent with other no-argument commands like `scan_codebase.md`).

### Patterns to Follow
- `## Examples` sections use a single fenced `bash` code block with `#` comment lines describing each invocation.
- Section order: `## Examples` (preceded by `---`) then `## Integration` (preceded by `---`).
- No-argument commands show the bare invocation plus follow-up workflow steps (see `scan_codebase.md:322-333`).

## Desired End State

Both command files have `## Examples` sections matching the project's established pattern, placed before `## Integration`.

## What We're NOT Doing

- Not adding `arguments` frontmatter to either file (neither accepts arguments)
- Not restructuring or rewriting other sections
- Not modifying any other command files

## Implementation Phases

### Phase 1: Add Examples to commit.md

Insert `## Examples` section between the existing `---` (line 79) and `## Integration` (line 81).

**File**: `commands/commit.md`

```markdown
---

## Examples

```bash
# Commit changes from current session
/ll:commit
```

---
```

#### Success Criteria
- [x] `## Examples` section present before `## Integration`
- [x] Fenced bash code block with comment + invocation pattern

### Phase 2: Add Examples to tradeoff_review_issues.md

Insert `## Examples` section with `---` separators before `## Integration` (line 325).

**File**: `commands/tradeoff_review_issues.md`

```markdown
---

## Examples

```bash
# Review all active issues for utility vs complexity trade-offs
/ll:tradeoff-review-issues
```

---
```

#### Success Criteria
- [x] `## Examples` section present before `## Integration`
- [x] Fenced bash code block with comment + invocation pattern

## Testing Strategy

- Visual inspection: both files have `## Examples` sections matching the project pattern
- No automated tests needed (documentation-only change)
