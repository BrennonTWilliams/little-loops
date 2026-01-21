---
discovered_date: 2026-01-21
discovered_by: capture_issue
---

# ENH-100: Improve Key Documents Alignment Workflow

## Summary

Redesign the key documents alignment feature (FEAT-075) to be more practical and actionable. Add explicit document references to issue templates, match documents during issue capture/normalization, and replace subjective alignment scores with concrete relevance checks and actionable recommendations.

## Context

Audit of `/ll:align_issues` revealed the current implementation has issues:
- **Not dogfooded**: little-loops itself doesn't use the `documents` config
- **Subjective scoring**: 0-100% alignment scores are non-deterministic and hard to action
- **High friction, low signal**: Batch analysis produces noise rather than useful guidance
- **One-way inference**: Documents are matched at check time rather than explicitly linked

## Current Behavior

1. Issues have no explicit link to relevant documentation
2. `/ll:align_issues` reads all docs and all issues, produces subjective 0-100% scores
3. No integration with `/ll:capture_issue` or `/ll:normalize_issues`
4. Output is a score-based report without concrete next steps

## Expected Behavior

1. Issues explicitly list related key documents in a "Related Key Documentation" section
2. `/ll:capture_issue` suggests and links relevant docs at issue creation time
3. `/ll:normalize_issues` adds missing doc references during normalization
4. `/ll:align_issues` performs two concrete checks:
   - **Doc Relevance Check**: Are the linked docs actually relevant to this issue?
   - **Alignment Check**: Does the issue align with linked docs? If not, what specific changes are recommended?

## Proposed Solution

### 1. Issue Template Update

Add "Related Key Documentation" section to issue templates (both minimal and full):

```markdown
## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle patterns |
| product | .claude/ll-goals.md | Workflow automation goals |
```

When no docs linked yet:
```markdown
## Related Key Documentation

_No relevant documents identified. Run `/ll:normalize_issues` or `/ll:align_issues` to discover relevant docs._
```

### 2. Update `/ll:capture_issue`

Add Phase 4b after issue creation (when `documents.enabled` is true):

1. Load configured document categories and files
2. Read each document, extract key concepts (headers, terms, patterns)
3. Match issue content against documents, score relevance
4. Add top matches (max 3) to the "Related Key Documentation" section
5. Note linked docs in output report

### 3. Update `/ll:normalize_issues`

Add Section 7b after internal reference updates (when `documents.enabled` is true):

1. For issues missing "Related Key Documentation" section or with placeholder text
2. Read issue content and configured documents
3. Score relevance, select top matches
4. Add or update the section with matched documents
5. Track in normalization report

### 4. Rewrite `/ll:align_issues`

Replace scoring system with actionable checks:

**Doc Relevance Check** (per linked document):
- ✓ Relevant - Clear connection
- ⚠ Weak - Tangential connection
- ✗ Not Relevant - No meaningful connection
- Generate: "Remove from Related Key Documentation"

**Missing Documentation Check**:
- Scan unlinked docs for high relevance
- Generate: "Add X to Related Key Documentation"

**Alignment Check** (per relevant document):
- Extract constraints from document (patterns, conventions, goals, prohibitions)
- Compare against issue proposal
- ✓ Aligned / ⚠ Unclear / ✗ Misaligned
- Generate specific recommendations with document quotes

**Output format**:
```markdown
### FEAT-045: Add webhook retry logic

**Doc Relevance Check**
✓ docs/ARCHITECTURE.md - Relevant (webhook handling patterns)
✗ docs/ROADMAP.md - Not relevant
  → Recommend: Remove docs/ROADMAP.md from Related Key Documentation

**Alignment Check**
✗ Misaligned with docs/ARCHITECTURE.md Section 4.2

  Document states:
    "All retry logic must use exponential backoff with jitter"

  Issue proposes:
    "Fixed 5-second retry interval"

  → Recommend: Update Proposed Solution to use exponential backoff
    OR update docs/ARCHITECTURE.md if fixed interval is intentional
```

**Add `--fix` flag**:
- Auto-remove irrelevant docs
- Auto-add missing relevant docs
- DO NOT auto-fix alignment issues (require human decision)

## Location

- `commands/capture_issue.md` - Add Phase 4b
- `commands/normalize_issues.md` - Add Section 7b
- `commands/align_issues.md` - Complete rewrite
- `skills/capture-issue/SKILL.md` - Update skill to link docs

## Impact

- **Priority**: P2 - Improves usability of existing feature
- **Effort**: Medium - Four command updates, no schema changes needed
- **Risk**: Low - Enhances existing feature, backwards compatible

## Acceptance Criteria

- [ ] Issue template includes "Related Key Documentation" section
- [ ] `/ll:capture_issue` links relevant docs when `documents.enabled`
- [ ] `/ll:normalize_issues` adds missing doc refs when `documents.enabled`
- [ ] `/ll:align_issues` performs relevance check with recommendations
- [ ] `/ll:align_issues` performs alignment check with specific recommendations (no scores)
- [ ] `/ll:align_issues --fix` auto-fixes relevance issues
- [ ] Dogfood: Configure `documents` in little-loops' own ll-config.json

## Dependencies

- FEAT-075 (completed) - Provides `documents` config schema and initial `/ll:align_issues`

## Related

- FEAT-075: Document Category Tracking and Issue Alignment (supersedes alignment approach)
- `/ll:init` - Already has Round 5 for document tracking setup

## Labels

`enhancement`, `alignment`, `documentation`, `workflow`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-21
- **Status**: Completed

### Changes Made
- `commands/capture_issue.md`: Added "Related Key Documentation" section to both minimal and full issue templates; Added Phase 4b for document linking when `documents.enabled`
- `commands/normalize_issues.md`: Added Section 7b to add missing document references during normalization
- `commands/align_issues.md`: Complete rewrite replacing subjective 0-100% scoring with concrete relevance checks (✓/⚠/✗) and alignment checks with specific recommendations; Added `--fix` flag for auto-fixing relevance issues
- `skills/capture-issue/SKILL.md`: Added Document Linking section explaining the feature
- `.claude/ll-config.json`: Dogfooded documents config with architecture and guidelines categories

### Verification Results
- Tests: PASS (1442 tests)
- Lint: PASS
- Types: PASS
- JSON validation: PASS

---

## Status

**Completed** | Created: 2026-01-21 | Completed: 2026-01-21 | Priority: P2
