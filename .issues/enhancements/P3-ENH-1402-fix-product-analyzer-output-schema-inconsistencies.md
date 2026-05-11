---
discovered_date: 2026-05-09
discovered_by: audit
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-11T09:23:46Z
status: done
---

# ENH-1402: Fix product-analyzer output schema inconsistencies

## Summary

The `product-analyzer` skill has several output schema bugs found during audit that will cause models to produce inconsistent or hallucinated output. These should be fixed alongside ENH-1400 to make the skill reliable.

## Current Behavior

`skills/product-analyzer/SKILL.md` has six schema inconsistencies that produce unreliable model output:
1. `analysis_timestamp` is required in output but `Bash` is not in `allowed-tools`, forcing the model to approximate or hallucinate the value
2. `goal_alignment_rating` is present in the `feature_gap` template and consolidated schema (line 207) but absent from the `ux_improvement` (Section 4) and `business_value` (Section 5) templates
3. The deduplication contract is ambiguous: Section 6 says "skip exact duplicates" but the schema also shows `duplicate_of` as a field within `findings[]`
4. `skipped_reason` enum has overlapping values: `enabled_missing` and `not_enabled` are semantically equivalent; `goals_file_missing` is now a stale terminal state after ENH-1400
5. Section 2 hardcodes `Read .ll/ll-goals.md` despite the config key `product.goals_file` supporting a custom path
6. `goals_file_missing` remains in the `skipped_reason` enum as a terminal state, but ENH-1400 (now completed) made it a discovery trigger instead

## Expected Behavior

After the fix:
- `analysis_timestamp` is always populated from `date -u +"%Y-%m-%dT%H:%M:%SZ"` output, never approximated
- All three finding types (`feature_gap`, `ux_improvement`, `business_value`) include `goal_alignment_rating`
- Deduplication contract is unambiguous: exact duplicates → `skipped_issues`, near-duplicates → `findings` with `duplicate_of` set
- `skipped_reason` has a single value `not_enabled` with no semantic overlap
- Section 2 reads `product.goals_file` from config, falling back to `.ll/ll-goals.md`

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

1. **Frontmatter** (lines 4–7): Add `- Bash(date:*)` to `allowed-tools`, following the one-per-line style used in `skills/go-no-go/SKILL.md:8-11`
2. **Output Format** (line 178, `analysis_timestamp` in `analysis_metadata` block): Add a prose instruction immediately before or after the output schema — e.g., "Run `date -u +\"%Y-%m-%dT%H:%M:%SZ\"` to populate `analysis_timestamp`" — mirroring `skills/manage-issue/SKILL.md:441`
3. **Section 4 ux_improvement** (lines 116–129): Insert `goal_alignment_rating: [Strong|Partial|Weak|Missing]` after `goal_alignment:` to match the `feature_gap` template and the consolidated schema at line 207
4. **Section 5 business_value** (lines 142–156): Same insertion — add `goal_alignment_rating: [Strong|Partial|Weak|Missing]` after `goal_alignment:`
5. **Section 6 Deduplication** (lines 163–169): Replace the ambiguous Step 3 with explicit contract: exact duplicates go to `skipped_issues` with `reason: duplicate_of_NNN`; near-duplicates stay in `findings` with `duplicate_of:` set (informational only)
6. **`skipped_reason` enum** (line 48): Consolidate from `[enabled_missing|goals_file_missing|not_enabled]` to just `[not_enabled]`; `enabled_missing` and `goals_file_missing` are redundant post-ENH-1400
7. **Section 2** (line 55): Replace hardcoded `Read \`.ll/ll-goals.md\`` with `Read the goals file path resolved in step 1 (\`product.goals_file\`, default: \`.ll/ll-goals.md\`)`
8. **New test file** `scripts/tests/test_enh1402_doc_wiring.py`: Assert `Bash(date` in frontmatter (using `content.index("---", 3)` pattern from `test_issue_size_review_skill.py`), `goal_alignment_rating` appears in both Section 4 and Section 5 blocks, `goals_file_missing` is absent from `skipped_reason`, `product.goals_file` referenced in Section 2

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
- `commands/scan-product.md:74` — reads `product.goals_file` with fallback and calls skill at Step 4 (lines 146–175); also generates `analysis_timestamp` at line 118 using `date -u +"%Y-%m-%dT%H:%M:%SZ"` — the same pattern needed in the skill
- `commands/create-sprint.md:198` — references `product.goals_file` with default fallback

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/session-start.sh` `validate_enabled_features()` lines 134–143 — reads `product.goals_file` via jq (`'.product.goals_file // ".ll/ll-goals.md"'`) and warns if file absent; reads same config key this issue makes the skill use — context-only, no change needed for ENH-1402 (ENH-1442 owns downgrading the warning)
- `skills/init/SKILL.md` line 182 — writes `product.goals_file: .ll/ll-goals.md` into generated config during init (producer of the config key the skill now reads); context-only, no change needed
- `skills/init/interactive.md` lines 245, 458 — references `.ll/ll-goals.md` in product setup round; context-only, no change needed

### Similar Patterns
- `skills/go-no-go/SKILL.md:8-11` — one-per-line `Bash(<cmd>:*)` allowed-tools pattern to follow for adding `Bash(date:*)`
- `skills/capture-issue/SKILL.md:9` — comma-list alternative: `Bash(ll-issues:*, git:*)` (both styles are valid)
- `skills/manage-issue/SKILL.md:441` — `date -u +"%Y-%m-%dT%H:%M:%SZ"` used in body prose as the canonical ISO timestamp instruction
- `commands/scan-product.md:118` — `date -u +"%Y-%m-%dT%H:%M:%SZ"` in a `bash` code block (direct model to replicate)

### Tests
- `scripts/tests/test_enh1401_doc_wiring.py` — existing product-analyzer wiring test; pattern to follow for new `test_enh1402_doc_wiring.py`
- `scripts/tests/test_issue_size_review_skill.py:test_edit_in_allowed_tools` — pattern for asserting a specific tool is present in a skill's frontmatter (uses `content.index("---", 3)` to isolate frontmatter)
- No existing test covers ENH-1402 changes; a new `scripts/tests/test_enh1402_doc_wiring.py` should assert: `Bash(date` in frontmatter, `goal_alignment_rating` in Section 4 and Section 5 blocks, `not_enabled` as sole `skipped_reason` value, `product.goals_file` referenced in Section 2

### Documentation
- `docs/reference/COMMANDS.md` — documents `/ll:scan-product` which invokes the skill
- `docs/reference/CONFIGURATION.md` — documents `product.goals_file` config key; may note the skill now uses it directly

### Configuration
- N/A

## Impact

- **Priority**: P3 — Schema inconsistencies cause unreliable model output but do not block core functionality
- **Effort**: Small — 6 targeted edits to `skills/product-analyzer/SKILL.md` plus one new test file
- **Risk**: Low — Changes are to instruction markdown and output schema definitions; no runtime code modified
- **Breaking Change**: No

## Labels

`schema-fix`, `product-analyzer`, `skill`

## Status

**Open** | Created: 2026-05-09 | Priority: P3

## Evidence

- `skills/product-analyzer/SKILL.md:4-7` — allowed-tools missing Bash
- `skills/product-analyzer/SKILL.md:114-129` — ux_improvement template missing goal_alignment_rating
- `skills/product-analyzer/SKILL.md:133-156` — business_value template missing goal_alignment_rating
- `skills/product-analyzer/SKILL.md:163-169` — ambiguous duplicate handling
- `skills/product-analyzer/SKILL.md:44-49` — skipped_reason enum with overlapping values
- `skills/product-analyzer/SKILL.md:55` — hardcoded `.ll/ll-goals.md` path


## Resolution

All 6 schema inconsistencies fixed in `skills/product-analyzer/SKILL.md`:
1. Added `Bash(date:*)` to `allowed-tools` + timestamp instruction in Output Format
2. Added `goal_alignment_rating` to Section 4 (ux_improvement) and Section 5 (business_value) templates
3. Clarified Section 6 deduplication: exact → `skipped_issues`, near-duplicate → `findings` with `duplicate_of`
4. Consolidated `skipped_reason` to single value `not_enabled` (removed `enabled_missing` and `goals_file_missing`)
5. Section 2 now reads `product.goals_file` from config (fallback: `.ll/ll-goals.md`)

New test file: `scripts/tests/test_enh1402_doc_wiring.py` (10 tests, all passing).

## Session Log
- `/ll:manage-issue` - 2026-05-11T09:23:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-05-11T09:20:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44bef13b-8bdc-4f03-9dfc-922b26a07e7b.jsonl`
- `/ll:wire-issue` - 2026-05-11T09:16:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c92fb3c-1d74-4212-ac94-4410cd334f33.jsonl`
- `/ll:refine-issue` - 2026-05-11T09:11:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/019fcd74-1050-4fd5-851e-08b328a97d7d.jsonl`
- `/ll:format-issue` - 2026-05-09T21:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32deefa2-352e-4fa9-a9df-ce9aad495a16.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8554078b-0de3-40fb-98fe-4b27b53363fa.jsonl`
