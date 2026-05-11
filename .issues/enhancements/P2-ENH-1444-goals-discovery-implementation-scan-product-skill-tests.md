---
id: ENH-1444
priority: P2
type: ENH
parent: ENH-1442
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
completed_at: 2026-05-11T19:43:01Z
---

# ENH-1444: Goals Discovery — Implementation (scan-product, SKILL.md, wiring tests)

## Summary

Implement the `goals_discovery` fallback path in `commands/scan-product.md` and update `skills/product-analyzer/SKILL.md` to consume the synthesized goals context, including all wiring touchpoints from ENH-1442's Wiring Phase. When `ll-goals.md` is absent, synthesize a temporary goals context from discovered docs rather than hard-stopping.

## Current Behavior

When `/ll:scan-product` is invoked on a project without `ll-goals.md`, the command hard-exits at step 2 ("Check goals file exists") with `"Goals file not found: {{config.product.goals_file}}"`, producing no analysis output. Users who haven't yet created `ll-goals.md` get a dead-end error instead of useful findings.

## Expected Behavior

When `ll-goals.md` is absent, `scan-product` synthesizes a temporary goals context from discovered docs (README, ROADMAP, vision/goals/requirements/product files) and continues analysis with `goals_source: discovered` metadata. The output display reflects the actual source. If `required_files` entries are missing, a warning is shown but analysis proceeds. With an explicit `ll-goals.md`, behavior is unchanged (`goals_source: explicit`).

## Parent Issue

Decomposed from ENH-1442: Goals Discovery — Core Implementation (scan-product, product-analyzer, hooks, tests)

## Files to Modify

- `commands/scan-product.md` — replace hard-exit block at lines 73–88 with discovery logic; update output display at Steps 6.5 and 8
- `skills/product-analyzer/SKILL.md` — make `### 2. Load Product Goals` conditional; remove `goals_file_missing`; update `skipped_reason`, `analysis_metadata`, `## Context`, `## What NOT to Do`, evidence `file:` fields in Sections 3–5
- `scripts/tests/test_enh1442_doc_wiring.py` (new) — doc-wiring assertions

## Implementation Steps

1. **Update `commands/scan-product.md`** — Replace lines 73–88 hard-exit block ("Check goals file exists") with discovery logic:
   - Read `{{config.product.goals_discovery.max_files}}` (default 5) and `{{config.product.goals_discovery.required_files}}` (default `["README.md"]`) using same `{{config.*}}` pattern as `{{config.product.goals_file}}` at line ~67
   - Warn (but continue) if any `required_files` entry is absent — follow `skills/init/SKILL.md:339–392` warn-but-continue pattern
   - Discover candidate files in priority order:
     - `goals_discovery.required_files` entries
     - `**/ROADMAP*.md`, `**/roadmap*.md`
     - `**/vision*.md`, `**/goals*.md`
     - `**/requirements*.md`, `**/product*.md`
     - `README.md` (always included)
     - `CONTRIBUTING.md`
   - Read up to `max_files` files; synthesize `GOALS_CONTENT` (infer persona from README "for"/"who uses" language, infer priorities from headers/roadmap items)
   - Assign `GOALS_SOURCE=discovered` and `GOALS_DISCOVERED_FROM=[list]` alongside `GOALS_CONTENT`
   - When `ll-goals.md` exists, keep existing `cat {{config.product.goals_file}}` path and set `GOALS_SOURCE=explicit`

2. **Update `skills/product-analyzer/SKILL.md`**:
   - Remove `goals_file_missing` entry from Guardrails stop-list (lines 24–28)
   - Make `### 2. Load Product Goals` (lines 52–62) conditional: only read `.ll/ll-goals.md` when `GOALS_CONTENT` is absent from injected context; set `goals_source: explicit` in that branch, `goals_source: discovered` otherwise
   - **Preserve the `### 2. Load Product Goals` heading exactly** (required by `test_enh1402_doc_wiring.py` and `test_enh1403_doc_wiring.py`) and ensure `product.goals_file` reference remains in the conditional branch
   - Update `skipped_reason` (lines 45–48): replace `goals_file_missing` with `goals_content_missing` (triggered only when caller omits `GOALS_CONTENT` entirely)
   - Update `analysis_metadata` (lines 175–184): replace `goals_file: ".ll/ll-goals.md"` with `goals_source: [explicit|discovered]` and `discovered_from: [...]` (populated only when `goals_source: discovered`)
   - Update `## Context` section (line ~17): item 1 currently reads "**Product Goals** (`.ll/ll-goals.md`)"; update to reflect both explicit and discovered sources
   - Remove or soften "Don't proceed without `ll-goals.md`" in `## What NOT to Do` (line ~267)
   - Generalize evidence `file:` fields in `### 3. Goal-Gap Analysis`, `### 4. Persona Journey Analysis`, `### 5. Business Value Opportunities`: replace hardcoded `file: ".ll/ll-goals.md"` with actual source reference (reflect discovered vs explicit path)

3. **Update output display in `commands/scan-product.md`** Steps 6.5 and 8: change `**Goals File**: {{config.product.goals_file}}` to show actual source — explicit path when `GOALS_SOURCE=explicit`, or `auto-discovered from N files ({{GOALS_DISCOVERED_FROM}})` when in discovery mode

4. **Create `scripts/tests/test_enh1442_doc_wiring.py`** — Follow `scripts/tests/test_enh1362_doc_wiring.py` class-per-surface structure (`PROJECT_ROOT = Path(__file__).parent.parent.parent`, one class per surface area). Assertions:
   - `goals_file_missing` absent from `skills/product-analyzer/SKILL.md`
   - `goals_content_missing` present as a `skipped_reason` in `SKILL.md`
   - `### 2. Load Product Goals` does not unconditionally contain `Read .ll/ll-goals.md`
   - `goals_source` and `discovered_from` appear in the `analysis_metadata` block of `SKILL.md`
   - `{{config.product.goals_discovery.max_files}}` and `{{config.product.goals_discovery.required_files}}` present in `commands/scan-product.md`
   - `"Goals file not found"` hard-exit block absent from `commands/scan-product.md`

5. **Verify `scripts/tests/test_enh1402_doc_wiring.py` and `test_enh1403_doc_wiring.py` survive Section 2 rewrite** — both use `content.index("### 2. Load Product Goals")` to scope assertions; `product.goals_file` reference must remain in the conditional branch so `test_section2_references_product_goals_file_config` passes; additionally verify `TestScanProductNoReDedup.test_trust_skill_deduplication_present` survives: `"sole responsible party for deduplication"` must remain in `commands/scan-product.md` (currently at line 191, not in any replacement zone)

6. **Run tests**: `python -m pytest scripts/tests/test_enh1402_doc_wiring.py scripts/tests/test_enh1403_doc_wiring.py scripts/tests/test_enh1442_doc_wiring.py -v`

## Acceptance Criteria

- `/ll:scan-product` on a project with only `README.md` and no `ll-goals.md` produces meaningful findings
- Output metadata clearly indicates `goals_source: discovered`
- If `required_files` are missing, a warning is shown but analysis still proceeds
- `max_files` limit is respected
- With an explicit `ll-goals.md`, behavior is unchanged (`goals_source: explicit`)
- All new wiring test assertions pass; `test_enh1402` and `test_enh1403` still pass

## Scope Boundaries

- **In scope**: Fallback discovery logic in `commands/scan-product.md`; conditional loading in `skills/product-analyzer/SKILL.md`; new `scripts/tests/test_enh1442_doc_wiring.py`
- **Out of scope**: Auto-creating or populating `ll-goals.md` — users must still create it manually for the explicit path
- **Out of scope**: Schema changes to `config-schema.json` — the `goals_discovery` block is already defined (no schema work needed)
- **Out of scope**: Changes to skills other than `product-analyzer`
- **Out of scope**: Persisting the synthesized goals context to disk; discovery is ephemeral per-run

## Integration Map

### Files to Modify
- `commands/scan-product.md` — Replace hard-exit block (lines 73–88) with discovery logic; set `GOALS_SOURCE` and `GOALS_DISCOVERED_FROM` alongside `GOALS_CONTENT` (near lines 105–110); update Steps 6.5 (line 291) and 8 (line 346) output display
- `skills/product-analyzer/SKILL.md` — Guardrails stop-list (line ~32); `skipped_reason` enum (line ~53); last line of Section 2 (line ~73); Context item 1 (line 18); `analysis_metadata` block (lines 190–200); `## What NOT to Do` (line 282)
- `scripts/tests/test_enh1442_doc_wiring.py` — **New file**; model after `test_enh1403_doc_wiring.py` (uses `_section()` helper, same two-file surface area)

### Dependent Files (Must Not Break)
- `scripts/tests/test_enh1402_doc_wiring.py` — `TestGoalsFilePathFromConfig.test_section2_references_product_goals_file_config` asserts `"product.goals_file" in section`; at least one `product.goals_file` reference must remain inside `### 2. Load Product Goals`
- `scripts/tests/test_enh1403_doc_wiring.py` — `TestSkillSection2ConditionalGoalsRead` asserts both `"GOALS_CONTENT"` and `"product.goals_file"` in the section; preserve both strings in Section 2

### Integration Points
- `commands/scan-product.md:148` — `{{GOALS_CONTENT}}` injection site; `GOALS_SOURCE` and `GOALS_DISCOVERED_FROM` must be set before this point in the command flow
- `commands/scan-product.md:105–110` — where `GOALS_CONTENT` is currently stored after reading; set `GOALS_SOURCE=discovered` and `GOALS_DISCOVERED_FROM=[list]` here in the discovery branch, `GOALS_SOURCE=explicit` in the existing branch

### Similar Patterns
- `skills/init/SKILL.md:218–247` — tool-availability warn-but-continue: declares check "non-blocking" in prose, uses `Warning: '...' — <consequence>` format, closes with `**Always proceed to Step N regardless of results.**`
- `skills/init/SKILL.md:340–401` — hook-dependency warn-but-continue: same shape for required-files existence check
- `skills/audit-docs/SKILL.md:38–56` — `find`-based glob collection with path exclusions for markdown file discovery
- `scripts/tests/test_enh1403_doc_wiring.py` — most direct test model; covers same two surface files (`SKILL.md`, `scan-product.md`), uses `_section()` helper

### Tests
- `scripts/tests/test_enh1402_doc_wiring.py` — existing coverage that must survive (section 2 `product.goals_file` reference)
- `scripts/tests/test_enh1403_doc_wiring.py` — existing coverage that must survive; `_section()` helper (lines 19–26) to copy into new test
- `scripts/tests/test_enh1442_doc_wiring.py` — new file to create

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1403_doc_wiring.py:TestScanProductNoReDedup.test_trust_skill_deduplication_present` — asserts `"sole responsible party for deduplication"` in `commands/scan-product.md`; this text is at line 191, between the hard-exit block (lines 73–88) and the Steps 6.5/8 output display (lines 291/346); confirm the replacement does not remove it [Agent 3 finding]

## Codebase Reference

- Integration Map anchors: `commands/scan-product.md:73–88` (hard-exit block); `skills/product-analyzer/SKILL.md` lines 17, 24–28, 45–48, 52–62, 175–184, ~267
- Similar patterns: `skills/init/SKILL.md:339–392` (warn-but-continue), `skills/audit-docs/SKILL.md:43–56` (glob collection)
- Test pattern: `scripts/tests/test_enh1362_doc_wiring.py`
- Config schema: `config-schema.json:767–786` — `goals_discovery` already defined (no schema changes needed)
- `commands/scan-product.md` line ~67 — `{{config.product.goals_file}}` interpolation pattern to follow

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Hard-exit block exact content** (`commands/scan-product.md:73–88`): heading `2. **Check goals file exists**:`, followed by `get goals file path … verify … if missing exit with "Goals file not found: {{config.product.goals_file}}"` block. Line 88 (`If either check fails, stop execution`) applies jointly to the `product.enabled` check and this goals-file check — replace the goals-file branch only, keep the `product.enabled` guard.

- **SKILL.md Section 2 current state**: The GOALS_CONTENT conditional table (rows: injected → use directly; standalone → read from file) is already present and satisfies `test_enh1403`. The only remaining hard-stop is the **last line of the section**: `"If goals file is missing or malformed, return empty findings."` — this must change to set `goals_source: discovered` and continue rather than returning empty findings.

- **Guardrail actual line range**: Issue says "lines 24–28" but the `## Guardrails` heading is at line 29 and the goals-file stop condition (`The goals file (`.ll/ll-goals.md`) does not exist`) is at line 32. The `goals_file_missing` token is absent from `skipped_reason` already (ENH-1402 removed it); only `"not_enabled"` is there now. ENH-1444 must add `goals_content_missing` as a second valid value.

- **`analysis_metadata` actual location**: Lines 190–200, not 175–184. Contains `goals_file: ".ll/ll-goals.md"` — replace with `goals_source: [explicit|discovered]` plus conditional `discovered_from: [...]`.

- **`## What NOT to Do` exact text** (line 282): `"Don't proceed without `ll-goals.md`"` — the exact string to remove or soften.

- **`_section()` helper** from `test_enh1403_doc_wiring.py:19–26` — copy verbatim into `test_enh1442_doc_wiring.py`:
  ```python
  def _section(content: str, heading: str) -> str:
      start = content.index(heading)
      try:
          end = content.index("\n### ", start + len(heading))
      except ValueError:
          end = len(content)
      return content[start:end]
  ```

## Impact

- **Priority**: P2 — Meaningfully improves usability for new projects and CI/product-analysis runs where `ll-goals.md` hasn't been created; unblocks scan-product for the majority of users hitting this cold-start failure
- **Effort**: Medium — Two files modified (one command, one skill) plus one new test file; logic is fully researched and line-accurate (ENH-1442 wiring pass complete)
- **Risk**: Low — Strictly additive; explicit `ll-goals.md` path is preserved unchanged; new test file validates both the additions and no regressions in existing tests
- **Breaking Change**: No

## Labels

`enhancement`, `product-analyzer`, `scan-product`, `goals-discovery`, `testing`

## Status

**Open** | Created: 2026-05-11 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-11T19:37:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c984546c-e62c-4780-a6c4-d72868cd7c66.jsonl`
- `/ll:wire-issue` - 2026-05-11T19:33:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16d22494-51db-49e4-bb68-3443c39e1947.jsonl`
- `/ll:refine-issue` - 2026-05-11T19:29:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f3d74a5-38bd-4987-8f50-aad3be854863.jsonl`
- `/ll:issue-size-review` - 2026-05-11T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0abadba2-fa26-422a-8f2e-9ed2d2744c98.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95b38d3a-7295-43c9-a930-6c4e10c89d2b.jsonl`
- `/ll:manage-issue` - 2026-05-11T19:43:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
