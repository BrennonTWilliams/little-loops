---
id: ENH-791
title: "normalize-issues: detect and fix type misclassifications"
type: ENH
priority: P3
status: open
discovered_date: 2026-03-17
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 68
---

# ENH-791: normalize-issues: detect and fix type misclassifications

## Summary

Add a new check step to `/ll:normalize-issues` that reads each active issue's content and detects when the type prefix (BUG/FEAT/ENH) doesn't match the actual nature of the issue. Reclassification is a filename rename + directory move — exactly the same operation normalize-issues already does — so the infrastructure is already there.

## Current Behavior

`/ll:normalize-issues` validates and fixes issue filenames for missing IDs, duplicate IDs, and priority ordering, but does not inspect issue content. Issues where the type prefix (BUG/FEAT/ENH) contradicts the actual content go undetected — e.g., an ENH that describes a defect regression, or a BUG that describes a missing capability.

## Expected Behavior

`/ll:normalize-issues` inspects issue content and detects when the type prefix doesn't match the nature of the issue. Misclassified issues are:
- Shown in the rename plan with `[old-type] → [inferred-type]` reason and confidence score
- Moved to the correct directory via `git mv` (cross-directory)
- Counted in `--check` mode violations
- Reported in the Step 8 normalization report under "Type Mismatch Fixes"

## Motivation

Issue backlogs accumulate type drift over time. ENH issues that describe defects/regressions should be BUGs; BUG issues that describe missing capabilities should be FEATs. Misclassified issues affect automation tooling (e.g., `ll-auto` priority ordering), sprint planning heuristics, and history analysis. This check completes the "filename metadata is correct" guarantee that normalize-issues already provides for IDs and priorities.

## Implementation Steps

### 1. Add Step 1c: Detect Type Mismatches

Insert a new step between the existing "1b. Detect Cross-Type Duplicate IDs" and "2. Determine Category Mapping" steps in `commands/normalize-issues.md`.

**Implementation pattern**: Follow the content-reading approach already used in Step 7b (`commands/normalize-issues.md:278–328`), which reads issue files via the `Read` tool and processes content inline. No Python helper needed — Claude applies the heuristics as instruction prose.

**Detection heuristics** (read issue content, check against type prefix):

| Signal | Suggests |
|--------|----------|
| Mentions "broken", "regression", "error", "crash", "fails", "wrong behavior", "should not" | BUG |
| Mentions "new capability", "users can't currently", "add support for", "implement" | FEAT |
| Mentions "improve", "optimize", "enhance", "refactor", "better UX" | ENH |

For each active issue:
1. Read file content (using `Read` tool, same as Step 7b)
2. Extract signals from Summary, Motivation/Current Pain Point, and Root Cause sections
3. Compute a confidence score for the inferred type vs. the filename prefix
4. Flag issues where inferred type differs with confidence >= threshold (**starting default: 0.7** — document as a value to validate against the real backlog before treating as fixed; tune conservatively to avoid false positives)

### 2. Include in Rename Plan Table

Misclassified issues are added to the existing rename plan table (`commands/normalize-issues.md:220–256`) with a "Type mismatch" change description. The file must also move directories (e.g., `enhancements/` → `bugs/`).

Add a new **"Type Mismatch Fixes"** sub-table to Step 5's plan, following the same column structure as the "Duplicate ID Renames" table:

| Current Filename | New Filename | Change |
|-----------------|-------------|--------|
| `P3-ENH-NNN-foo.md` (enhancements/) | `P3-BUG-NNN-foo.md` (bugs/) | ENH → BUG (0.82 confidence) |

The `git mv` in Step 6 must handle cross-directory moves for these (currently Step 6 only renames within the same directory — the template at line ~259 needs a cross-directory variant).

### 3. Update --check Mode

`--check` mode (`commands/normalize-issues.md:63–70`) should also emit `[ID] normalize: type mismatch (ENH → BUG)` lines for detected misclassifications and count them in the violation total. Format matches the existing `--check` line patterns:

```
[ID] normalize: type mismatch (ENH → BUG)
```

**Out of scope**: the three loops that invoke `normalize-issues` (`loops/issue-discovery-triage.yaml`, `loops/issue-size-split.yaml`, `loops/backlog-flow-optimizer.yaml`) route on exit-code only (0 = clean, 1 = violations). Since exit-code behavior is unchanged, no loop updates are needed.

### 4. Update Report Section

Add a "Type Mismatch Fixes" table to the normalization report (`commands/normalize-issues.md:329–372`) alongside "Missing ID Fixes" and "Duplicate ID Fixes":

| Original | New Filename | Inferred Type | Confidence |
|----------|-------------|---------------|-----------|
| `P3-ENH-NNN-foo.md` | `P3-BUG-NNN-foo.md` | BUG | 0.82 |

Also update the Step 8 summary block to include a "type mismatches detected/fixed" count.

## Acceptance Criteria

- [ ] `normalize-issues` detects ENH/FEAT/BUG issues whose content signals a different type
- [ ] Detected issues are shown in the rename plan with `[old-type] → [inferred-type]` reason
- [ ] Files are moved to the correct directory (e.g., `enhancements/` → `bugs/`) via `git mv`
- [ ] `--check` mode includes type mismatches in violation count and exit code
- [ ] Report includes a "Type Mismatch Fixes" section
- [ ] No false positives for issues with ambiguous signals (confidence threshold prevents spurious reclassifications)
- [ ] `--auto` mode applies reclassifications without prompting

## Scope Boundaries

- **In scope**: Detection and reclassification of BUG/FEAT/ENH type mismatches; updating filename prefix and moving to correct directory; `--check` mode integration; normalization report updates
- **Out of scope**: Updating loop configs (`loops/issue-discovery-triage.yaml`, `loops/issue-size-split.yaml`, `loops/backlog-flow-optimizer.yaml`) — they route on exit-code only, no changes needed; modifying Python infrastructure (`issue_parser.py`, `text_utils.py`) — Claude applies heuristics as instruction prose, no new helpers needed; tuning the 0.7 confidence threshold (starting value to validate against real backlog)

## Integration Map

### Files to Modify
- `commands/normalize-issues.md` — insert Step 1c (between 1b and Step 2); extend Step 5 rename plan with type-mismatch table; add cross-directory `git mv` to Step 6; extend Step -0.5 `--check` with mismatch line format; extend Step 8 report with "Type Mismatch Fixes" table

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key anchors in `commands/normalize-issues.md`:**
- Lines 63–70 — Step -0.5: `--check` mode (add `[ID] normalize: type mismatch (ENH → BUG)` format and violation count)
- Lines 220–256 — Step 5: rename plan table (add "Type Mismatch Fixes" sub-table with confidence column)
- Lines 259–267 — Step 6: `git mv` renames (currently within-directory only; add cross-directory variant for type reclassifications)
- Lines 278–328 — Step 7b: **reference pattern** for inline content processing; uses `grep -q` on issue files (line 290) and `Read` tool on document files (line 301) — Step 1c should use the `Read` tool directly on each issue file to extract signals from Summary and Motivation sections, since grep is insufficient for multi-signal heuristic scoring
- Lines 329–372 — Step 8: normalization report (add "Type Mismatch Fixes" table and update summary counts)

**Related Python infrastructure (read-only reference — not modified by this issue):**
- `scripts/little_loops/issue_parser.py` — `_NORMALIZED_RE`, `_ISSUE_TYPE_RE` regex patterns; `_parse_section_items()` for section extraction; `is_normalized()` for filename validation
- `scripts/little_loops/text_utils.py` — `extract_words()` (stop-word-filtered word set) and `calculate_word_overlap()` (Jaccard similarity) — reference these when designing the confidence scoring prose in Step 1c
- `scripts/little_loops/issue_discovery/matching.py:63–139` — `FindingMatch` with `match_score: float` and threshold properties — reference for how 0.0–1.0 confidence scoring is structured and surfaced
- `scripts/little_loops/frontmatter.py:13–51` — `parse_frontmatter()` — Step 1c must compare the `type` frontmatter field against the filename prefix (these should agree; a mismatch is a secondary signal of misclassification)
- `config-schema.json` — defines `bugs/BUG`, `features/FEAT`, `enhancements/ENH` directory-to-prefix mapping

### Dependent Files (Callers/Importers)
- `loops/issue-discovery-triage.yaml`, `loops/issue-size-split.yaml`, `loops/backlog-flow-optimizer.yaml` — invoke `normalize-issues`; routing is exit-code only (0/1, unchanged)

### Similar Patterns
- N/A — this is a command file modification; no parallel command follows this content-reading pattern

### Tests
- `scripts/tests/test_issue_parser.py` — existing tests for `_NORMALIZED_RE`, `_ISSUE_TYPE_RE`
- `scripts/tests/test_issue_discovery.py:533–615` — `TestMatchesIssueType` — reference pattern for type-detection tests
- No unit test file exists for `commands/normalize-issues.md` (command files are not unit-tested)

### Documentation
- N/A — no user-facing docs reference the normalize-issues command's check steps

### Configuration
- N/A — no config changes needed; confidence threshold default (0.7) is documented inline in Step 1c

## Impact

- **Priority**: P3 — Addresses backlog hygiene; not blocking but meaningfully improves automation accuracy and sprint planning heuristics
- **Effort**: Small — Modifies one command file (`commands/normalize-issues.md`) by inserting a new step and extending three existing tables; follows the established Step 7b content-reading pattern
- **Risk**: Low — Additive only; confidence threshold prevents false positives; loop callers are unchanged; exit-code contract (0/1) is preserved
- **Breaking Change**: No

## Labels

enhancement, issue-management, normalize-issues

## Status

**Open** | Created: 2026-03-17 | Priority: P3

---

## Session Log
- `/ll:refine-issue` - 2026-03-17T03:31:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d69eb77-324d-4fd6-bf7c-1a2adec7fe53.jsonl`
- `/ll:format-issue` - 2026-03-17T03:28:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/087addd7-5cf0-461a-b862-113d6f2a30cd.jsonl`
- `/ll:refine-issue` - 2026-03-17T03:07:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9bf31b0a-cfc9-42ad-a35f-c71298680f5c.jsonl`
- `/ll:capture-issue` - 2026-03-17T02:38:35Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/532865b2-afcc-4542-a851-1511b776f7cd.jsonl`
