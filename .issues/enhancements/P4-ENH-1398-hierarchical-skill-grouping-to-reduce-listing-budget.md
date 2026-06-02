---
captured_at: '2026-05-09T20:48:12Z'
discovered_date: 2026-05-09
discovered_by: capture-issue
blocked_by:
- ENH-1394
decision_needed: false
missing_artifacts: false
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
status: done
closed_at: '2026-05-11'
close_reason: wont_do
completed_at: '2026-05-11T07:52:55Z'
---

# ENH-1398: Hierarchical Skill Grouping to Reduce Listing Budget

## Summary

Organize the 28 skills into ~6 named categories with a short category-level description each. If Claude Code supports multi-level skill listings (category → individual skills), this reduces the listing budget by ~75% and scales indefinitely as new skills are added. Requires investigation of Claude Code's plugin API to confirm feasibility.

## Current Behavior

All 28 skills are listed as a flat list in the listing budget. Each skill has its own description. The budget scales linearly with skill count: every new skill adds ~50-150 tokens to the listing footprint.

## Expected Behavior

Skills are grouped into categories (e.g., "Issue Management", "Code Quality", "Automation & Loops", "Session & Config", "Meta-Analysis", "Planning & Implementation"). The LLM sees category-level descriptions (~20-30 tokens each) in the primary listing. If it identifies a relevant category, it can request individual skill descriptions within that category.

**Proposed categories:**
- **Issue Management**: capture-issue, manage-issue, format-issue, wire-issue, ready-issue, refine-issue, verify-issues, normalize-issues, prioritize-issues, align-issues, decide-issue
- **Planning & Review**: create-sprint, review-sprint, go-no-go, confidence-check, tradeoff-review-issues, issue-size-review, map-dependencies, audit-issue-conflicts
- **Code & Docs**: check-code, run-tests, audit-docs, update-docs, audit-architecture, find-dead-code
- **Automation & Loops**: create-loop, review-loop, debug-loop-run, audit-loop-run, rename-loop, cleanup-loops, workflow-automation-proposer, loop-suggester
- **Session & Config**: init, configure, update, handoff, resume, toggle-autoprompt, help, issue-workflow
- **Analysis & Meta**: analyze-history, analyze-workflows, improve-claude-md, audit-claude-config, scan-codebase, scan-product, product-analyzer, create-eval-from-issues

## Success Metrics

- Investigation complete: definitive answer documented on whether Claude Code plugin API supports skill grouping (yes/no with evidence)
- If supported: listing footprint reduced from ~28 individual descriptions to ~6 category descriptions (~75% token reduction)
- If supported: all 28 skills assigned to a group and plugin listing reflects category-level display
- If not supported: feature request filed with Claude Code team and issue closed/deferred

## Motivation

ENH-1394 and ENH-1396 address the immediate problem with a tactical fix (tagging skills) and enforcement (budget validator). Hierarchical grouping is the architectural solution that eliminates the budget scaling problem entirely: adding 10 more skills doesn't increase the listing footprint at all if they fit into existing categories.

This is the only approach that scales past 50+ skills without ongoing manual curation.

## Proposed Solution

**Phase 1 (investigation):** Determine whether Claude Code's plugin API supports category grouping or `skill_group` frontmatter. Check plugin manifest schema and Claude Code changelog for relevant features.

**Phase 2 (if supported):** Add a `group` field to each SKILL.md frontmatter. Update the plugin manifest if required.

**Phase 3 (if not natively supported):** Consider a workaround using skill descriptions that reference group membership, or defer until the Claude Code API supports it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Phase 1 investigation result: NOT SUPPORTED.**

The Claude Code plugin API does not support skill grouping. `docs/claude-code/skills.md:175-186` is the authoritative frontmatter reference (scraped from Claude Code docs). It lists exactly 10 supported fields: `name`, `description`, `argument-hint`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `model`, `context`, `agent`, `hooks`. No `group`, `category`, or `skill_group` field exists. The plugin manifest (`.claude-plugin/plugin.json`) uses a flat `"skills": ["./skills"]` directory pointer with no category schema.

**Budget context (critically changed since issue was written):**

ENH-1394 is complete — 16 of 28 skills have `disable-model-invocation: true`. The budget checker (`scripts/little_loops/doc_counts.py:check_skill_budget()`) skips those skills. Current measured footprint is **283/2000 tokens (14% utilization)**, not the ~28-skill linear scaling the issue assumed. The budget scaling problem this issue was designed to solve is largely addressed.

**Remaining options (Phase 3):**

- **Option A — Workaround via description convention**: Prefix descriptions with a category shorthand (e.g., `[Issues]`, `[Loops]`). Adds grouping signal to the flat listing without API support. Low effort, but doesn't reduce token count — purely cosmetic grouping.
- **Option B — Close/defer**: Budget pressure is minimal (283/2000). ENH-1394 + ENH-1396 provide the enforcement mechanism. Revisit when Claude Code adds native grouping support or when skill count grows past ~50.

> **Selected:** Option B — Close/defer — budget is at 14% utilization (283/2000) with enforcement already live; prefix workaround would conflict with `_write_description_to_frontmatter` overwrite behavior and is purely cosmetic.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option B — Close/defer

**Reasoning**: The problem this issue was designed to solve — linear budget scaling from a flat 28-skill listing — has been structurally addressed by ENH-1394 (16/25 skills now excluded via `disable-model-invocation: true`) and ENH-1396 (`ll-verify-skill-budget` enforces budget at release time). The measured footprint is 283/2000 tokens (14% utilization). Option A is a cosmetic workaround that does not reduce token count and directly conflicts with `_write_description_to_frontmatter`'s regex overwrite (`generate_skill_descriptions.py:80–85`), which silently strips any manually-added prefix on every `--apply` run.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — description prefix | 0/3 | 1/3 | 2/3 | 1/3 | 4/12 |
| Option B — close/defer | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: `_write_description_to_frontmatter` regex (`^description:.*$`) unconditionally overwrites the full description line on `--apply`, silently stripping prefixes (`generate_skill_descriptions.py:80–85`); no existing prefix convention in any `skills/*/SKILL.md`; conflicts with CONTRIBUTING.md:508 description convention.
- **Option B**: Budget confirmed at 283/2000 (14%) by ENH-1396 smoke test; 16/25 skills excluded via `disable-model-invocation: true` (ENH-1394 complete 2026-05-11); `ll-verify-skill-budget` live in release toolchain; established defer precedent in `.issues/deferred/` (FEAT-1117, ENH-1122).

## Implementation Steps

1. ~~Investigate Claude Code plugin manifest schema for skill grouping support~~ **DONE** — not supported (see Proposed Solution → Codebase Research Findings)
2. ~~Check Claude Code changelog/docs for `skill_group`, `category`, or equivalent frontmatter fields~~ **DONE** — `docs/claude-code/skills.md:175-186` is definitive; no such field exists
3. Run `/ll:decide-issue ENH-1398` to choose between Option A (description prefix convention) and Option B (close/defer)
4. **If Option A**: For each `skills/*/SKILL.md` without `disable-model-invocation: true`, prepend a category prefix to the `description:` field. Follow `_write_description_to_frontmatter()` pattern in `scripts/little_loops/cli/generate_skill_descriptions.py:68-86` for in-place `re.sub` writes.
5. **If Option A**: Update `CONTRIBUTING.md` New Skill Checklist with the category prefix convention
6. **If Option B**: File a feature request with the Claude Code team and close this issue as deferred

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **[If Option A]** Update `generate_skill_descriptions.py:_write_description_to_frontmatter()` — the current `re.sub(r"^description:.*$", ...)` regex (lines 80–85) unconditionally overwrites the entire description line; if Option A prefixes are added manually, `ll-generate-skill-descriptions --apply` will silently strip them on the next run; either add prefix-preservation logic (detect and re-apply `[Category]` before writing) or add a `--preserve-prefix` flag
8. **[If Option A]** Update `CONTRIBUTING.md:Adding Skills` — the description convention paragraph currently states "Lead with trigger conditions ('Use when...')"; update to prefix-first convention (`[Category] Use when...`); clarify the 100-char limit includes prefix overhead (~9 chars); also update the `New Skill Checklist` accordingly
9. **[If Option A]** Update `docs/reference/CLI.md:1416-1439` — the `ll-generate-skill-descriptions` section must note that `--apply` strips category prefixes unless the script is updated; document the conflict with Option A prefix convention
10. Add unit tests to `scripts/tests/test_doc_counts.py` for `_parse_skill_frontmatter()` and `check_skill_budget()` — follow `TestProcessSkills` pattern in `test_generate_skill_descriptions.py`; use `tmp_path` fixtures; cover: plain description, `disable-model-invocation: true` skip logic, and (if Option A) prefixed description token counting

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — add `group:` frontmatter field (if supported)
- `.claude-plugin/plugin.json` — add category definitions (if required)

### Dependent Files (Callers/Importers)
- Claude Code harness — reads skill frontmatter for listing generation (opaque; this project has no code that touches the listing generation itself)
- `scripts/little_loops/doc_counts.py:_parse_skill_frontmatter()` — flat key-value parser; would need to extract a `group:` field if added; shares logic duplication with `generate_skill_descriptions._parse_frontmatter()`
- `scripts/little_loops/doc_counts.py:check_skill_budget()` — currently skips `disable-model-invocation: true` skills; would need group-aware budget counting to report per-category footprints
- `scripts/little_loops/cli/docs.py:main_verify_skill_budget()` — CLI entry point; reads threshold from `skill_budget.threshold_tokens` in `.ll/ll-config.json` (undocumented in `config-schema.json`)
- `scripts/little_loops/cli/generate_skill_descriptions.py:_process_skills()` — iterates `skills/*/SKILL.md`; skips `disable-model-invocation: true` skills; would need update for group-aware processing
- `scripts/little_loops/skill_expander.py:expand_skill()` — strips entire frontmatter block before passing to subprocess; `group:` would be silently ignored here (no change needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — exports `main_verify_skill_budget` and `main_generate_skill_descriptions` as package-level CLI entry points; registers both in `__all__`
- `scripts/little_loops/issue_history/quality.py` — iterates `skills/*/SKILL.md` to build the current skill list for coverage analysis; description field changes are transparent here but skill counts are affected if files move
- `scripts/little_loops/cli/action.py` — imports `_find_plugin_root` from `skill_expander`; affected if `SKILL.md` structure or plugin root detection changes

### Similar Patterns
- N/A — novel pattern; no existing example in this project

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py` — NO coverage for `_parse_skill_frontmatter()` or `check_skill_budget()`; new unit tests needed following the `TestProcessSkills` pattern in `test_generate_skill_descriptions.py`; test plain description, `disable-model-invocation: true` skip logic, and (if Option A) prefixed description token counting
- `scripts/tests/test_generate_skill_descriptions.py` — if Option A: `TestWriteDescriptionToFrontmatter` and `TestProcessSkills` need prefix-aware test variants verifying that `--apply` truncation respects the `[Category] ` prefix overhead (~9 chars against the 100-char budget)
- `scripts/tests/test_cli_docs.py` — existing `TestMainVerifySkillBudget` mocks `check_skill_budget` entirely; no direct test of budget counting with real SKILL.md files (existing gap, not new)

### Documentation
- `CONTRIBUTING.md` — note group field convention for new skills

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1248-1267` — `ll-verify-skill-budget` reference section; does not mention prefix token overhead; if Option A increases measured footprint, update the description
- `docs/reference/CLI.md:1416-1439` — `ll-generate-skill-descriptions` reference section; states `--apply` generates clean descriptions; if Option A, must note that `--apply` strips category prefixes unless `_write_description_to_frontmatter()` is updated to preserve them

### Configuration
- `.claude-plugin/plugin.json` — potentially

## Scope Boundaries

- Out of scope: changes to skill execution behavior or how Claude invokes skills
- Out of scope: changes to the listing budget validator (covered by ENH-1394/ENH-1396)
- Out of scope: lazy-loading runtime mechanisms — this is a static metadata approach only
- Out of scope: changes to skill discovery, registration, or SKILL.md content beyond the `group:` frontmatter field
- Out of scope: cross-repo or multi-product category taxonomies

## Impact

- **Priority**: P4 — depends on Claude Code API support; may not be actionable today
- **Effort**: Low (if supported) to Blocked (if not)
- **Risk**: Low — additive frontmatter field
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `investigation`

## Status

**Closed - Won't Do** | Created: 2026-05-09 | Closed: 2026-05-11 | Priority: P4

**Closure note**: Claude Code plugin API does not support hierarchical skill grouping (Phase 1 investigation confirmed no `group`, `category`, or `skill_group` field exists). Budget problem already solved: ENH-1394 reduced footprint to 283/2000 tokens (14% utilization), ENH-1396 enforces the budget at release time. `/ll:decide-issue` selected Option B (close/defer) on 2026-05-11.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 33/100 → VERY LOW

### Concerns
- `decision_needed: true` is already flagged — the Option A vs Option B choice must be resolved via `/ll:decide-issue ENH-1398` before any implementation can begin.
- If Option A is chosen: `generate_skill_descriptions.py:_write_description_to_frontmatter()` (lines 80–85) will silently strip category prefixes on every `--apply` run — this conflict requires a design decision before implementation.

### Outcome Risk Factors
- Unresolved decision between Option A (prefix convention) and Option B (close/defer) — resolve before implementing; the entire implementation trajectory hinges on this choice.
- If Option A: broad enumeration across 12+ SKILL.md sites plus Python function body changes in `_write_description_to_frontmatter()` — two distinct complexity tiers in the same implementation batch.
- No test coverage for `check_skill_budget()` or `_parse_skill_frontmatter()` in `test_doc_counts.py`; prefix-aware test variants not yet created.
- Pattern B fanout lacks a verification grep and automated completeness assertion — fanout completeness unproven.

## Session Log
- `/ll:ready-issue` - 2026-05-11T07:52:42 - `74410fc5-0a6e-4493-812b-5832276da15a.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `e326117e-0746-47d3-84c2-93f9a0b27108.jsonl`
- `/ll:decide-issue` - 2026-05-11T07:49:52 - `e1575310-6cd5-453c-9aa0-bb8f4b0ba6a6.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `e97c98b0-5ab4-4e62-8b46-c727a398629c.jsonl`
- `/ll:wire-issue` - 2026-05-11T07:42:40 - `cb2a48aa-f559-4e82-865b-513513644a6d.jsonl`
- `/ll:refine-issue` - 2026-05-11T07:38:23 - `f37c974b-82d4-4403-959e-e2dbb76905b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:28:00 - `87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:format-issue` - 2026-05-10T14:11:25 - `2742a4a6-4542-41b3-948f-519f214763d4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue builds on ENH-1394 (already a formal blocker). If both ENH-1394 and ENH-1398 are implemented, skills tagged `disable-model-invocation: true` by ENH-1394 should be **excluded from all category views** in the hierarchical listing — they should not appear under any category heading, as their purpose is to be absent from the LLM's listing budget entirely. The hierarchical grouping design must account for this exclusion rule or it will partially undermine ENH-1394's budget reduction. Related: ENH-1394.


---

## Resolution

- **Status**: Closed - Won't Do
- **Closed**: 2026-05-11
- **Reason**: wont_do
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
