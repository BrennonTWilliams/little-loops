---
discovered_date: 2026-05-09
discovered_by: audit
---

# ENH-1402: Fix product-analyzer output schema inconsistencies

## Summary

The `product-analyzer` skill has several output schema bugs found during audit that will cause models to produce inconsistent or hallucinated output. These should be fixed alongside ENH-1400 to make the skill reliable.

## Motivation

This enhancement would:
- Eliminate hallucinated `analysis_timestamp` values that directly violate the skill's own "No hallucination" CRITICAL rule
- Ensure consistent `goal_alignment_rating` across all finding types so `by_goal_alignment` summary counts are accurate
- Remove ambiguity in duplicate handling to make model output deterministic and parseable

## Issues

### 1. `analysis_timestamp` requires `Bash` but `Bash` is not in `allowed-tools`

The output format specifies `analysis_timestamp: [ISO 8601 timestamp]` but the skill only has `Read`, `Glob`, `Grep`. The model must approximate the time, violating the skill's own "No hallucination" CRITICAL rule.

**Fix**: Add `Bash(date:*)` to `allowed-tools`. In the output format section, instruct: `Run \`date -u +"%Y-%m-%dT%H:%M:%SZ"\` to populate analysis_timestamp`.

### 2. `goal_alignment_rating` missing from `ux_improvement` and `business_value` section templates

The consolidated output schema (line 207) includes `goal_alignment_rating` universally. But the per-section YAML templates for `ux_improvement` (Section 4) and `business_value` (Section 5) omit it. Models will inconsistently omit it for those types, making the `by_goal_alignment` summary counts undefined.

**Fix**: Add `goal_alignment_rating: [Strong|Partial|Weak|Missing]` to the output structure in both Section 4 and Section 5.

### 3. `duplicate_of` vs `skipped_issues` contradiction

Section 6 says "Skip findings that are exact duplicates." The output schema shows `duplicate_of: "[issue-id]"` as a field within `findings[]`. It is ambiguous whether duplicates appear in `findings` (with `duplicate_of` set) or only in `skipped_issues`.

**Fix**: Clarify the contract:
- Exact duplicates: appear only in `skipped_issues` with `reason: duplicate_of_NNN`
- Near-duplicates with overlap: appear in `findings` with `duplicate_of` field set (informational, not skipped)

### 4. Inconsistent `reason` enums

Early-exit `skipped_reason` (line 48): `enabled_missing|goals_file_missing|not_enabled`
Finding-level `skipped_issues[].reason` (line 222): `duplicate_of_xxx|insufficient_evidence|out_of_scope`

`enabled_missing` and `not_enabled` overlap semantically. With ENH-1400 removing `goals_file_missing` as a terminal condition, consolidate to: `not_enabled` (only valid early-exit reason after ENH-1400).

### 5. Hardcoded `.ll/ll-goals.md` path in skill body

Section 2 instructs `Read .ll/ll-goals.md` directly. The config field `product.goals_file` allows a custom path. The skill should read `product.goals_file` from config and use that path, falling back to `.ll/ll-goals.md` only if the config key is absent.

### 6. `skipped_reason` enum includes `goals_file_missing` as terminal state

After ENH-1400 implements discovery, `goals_file_missing` should no longer cause a full skip — it should trigger discovery instead. Remove it from the `skipped_reason` enum or reclassify as a warning in `analysis_metadata`.

## Implementation Steps

All fixes are in `skills/product-analyzer/SKILL.md`:

1. Add `Bash(date:*)` to frontmatter `allowed-tools`
2. Add `goal_alignment_rating` to Section 4 and Section 5 YAML blocks
3. Add clarifying note to Section 6 distinguishing exact vs near duplicates
4. Consolidate `skipped_reason` to just `not_enabled` (post-ENH-1400)
5. Change Section 2 path reference to use config value with fallback
6. Add `Run date -u...` instruction for `analysis_timestamp` population

## Success Metrics

- `analysis_timestamp` populated from `date` command in 100% of skill invocations (never approximated)
- All three finding types (`feature_gap`, `ux_improvement`, `business_value`) include `goal_alignment_rating`
- `skipped_reason` enum has exactly one value (`not_enabled`) with no semantic overlap

## Scope Boundaries

- **In scope**: `skills/product-analyzer/SKILL.md` frontmatter and schema fixes only (6 targeted edits)
- **Out of scope**: ENH-1400 goals discovery implementation, new skill features, changes to output format structure beyond the listed fixes

## Acceptance Criteria

- All three finding types include `goal_alignment_rating` in their section templates
- `analysis_timestamp` is always populated from `date` command output, never approximated
- Duplicate handling is unambiguous: exact → skipped_issues, near → findings with duplicate_of
- `skipped_reason` has no overlapping values
- Goals file path comes from config, not hardcoded

## Integration Map

### Files to Modify
- `skills/product-analyzer/SKILL.md` — frontmatter `allowed-tools`, Section 2 path reference, Section 4 YAML block, Section 5 YAML block, Section 6 duplicate note, `skipped_reason` enum

### Dependent Files (Callers/Importers)
- TBD - use grep: `grep -r "product-analyzer" skills/` to find callers

### Similar Patterns
- TBD - check other skills using `Bash(date:*)` for consistent timestamp pattern

### Tests
- TBD - identify test files covering product-analyzer output schema

### Documentation
- TBD - docs that reference the product-analyzer output format

### Configuration
- N/A

## Evidence

- `skills/product-analyzer/SKILL.md:4-7` — allowed-tools missing Bash
- `skills/product-analyzer/SKILL.md:114-129` — ux_improvement template missing goal_alignment_rating
- `skills/product-analyzer/SKILL.md:133-156` — business_value template missing goal_alignment_rating
- `skills/product-analyzer/SKILL.md:163-169` — ambiguous duplicate handling
- `skills/product-analyzer/SKILL.md:44-49` — skipped_reason enum with overlapping values
- `skills/product-analyzer/SKILL.md:55` — hardcoded `.ll/ll-goals.md` path


## Session Log
- `/ll:format-issue` - 2026-05-09T21:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32deefa2-352e-4fa9-a9df-ce9aad495a16.jsonl`
