---
captured_at: '2026-05-22T19:19:39Z'
completed_at: '2026-05-23T06:29:52Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1616: Six bridge skills have broken pipe-character descriptions

## Summary

Six `ll-*` bridge skills have `description: |` (YAML block scalar indicator with no content) as their frontmatter description. The skill budget checker records them as 0-token entries, but they still consume listing slots in the flat skill registry. Claude receives no routing information for these skills — they are dead weight in the listing.

Affected skills: `ll-loop-suggester`, `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`.

## Current Behavior

`check_skill_budget()` in `doc_counts.py` reports these six skills with description `|` and 0 tokens. The YAML block scalar indicator was written to the frontmatter without a body value. These skills appear in the skill listing but provide no routing signal — Claude cannot match them to natural-language requests because the description field is effectively empty.

## Steps to Reproduce

1. Run `ll-verify-skill-budget` (or inspect `check_skill_budget()` in `scripts/little_loops/doc_counts.py`).
2. Open any of the six affected bridge skills, e.g. `skills/ll-loop-suggester/SKILL.md`.
3. Observe: the frontmatter `description:` field is a bare `|` block scalar indicator with no indented body, so the parsed description is an empty string and the budget checker records the skill as a 0-token entry.

## Expected Behavior

Each of the six skills has a valid single-line description (≤100 chars) following the trigger-first convention. Example for `ll-loop-suggester`: `Analyze user message history to suggest FSM loop configurations automatically.` (matching the existing `metadata.short-description`).

Alternatively, if ENH-1615 is implemented first (adding `disable-model-invocation: true` to all bridge skills), the description field becomes irrelevant for Claude Code routing and can be set to any valid value.

## Motivation

The skill listing has a finite token budget. Six skills currently occupy listing slots while contributing zero routing signal — pure waste with no benefit. Fixing the descriptions either restores model-invocation routing for six skills or, if ENH-1615 lands first, confirms the field is intentionally inert. Either way removes ambiguity from the registry.

## Root Cause

- **File**: `skills/ll-loop-suggester/SKILL.md` (and `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`)
- **Anchor**: frontmatter `description:` field
- **Cause**: a YAML block scalar indicator (`|`) was written without an indented body line, so the parser yields an empty string instead of a description. Likely introduced by a generator (e.g. `ll-adapt-skills-for-codex` or `ll-generate-skill-descriptions`) that emitted the indicator before the body value was available.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The original root-cause framing is incorrect. The six SKILL.md files are **well-formed** — each has a valid YAML block scalar `description: |` followed by an indented multi-line body. The bug is in the **parser**, not the data.

- **Primary defect**: `scripts/little_loops/doc_counts.py:268-280` `_parse_skill_frontmatter()` is a hand-rolled line-based parser that iterates `text[3:end].splitlines()` and calls `line.partition(":")` on every line containing `:`. For `description: |` it stores `fm["description"] = "|"`. The indented body lines are then re-parsed as garbage entries (any `:` inside the prose becomes a fake key).
- **Downstream effect** (`doc_counts.py:283-330` `check_skill_budget()`): `tokens = len("|") // 4 == 0`. Real descriptions for the 6 skills total hundreds of chars (e.g. `ll-tradeoff-review-issues` ~420 chars / ~105 tokens) but are reported as 0 — so the budget check **silently passes** while real listing mass is unaccounted for, and oversized descriptions are never flagged as `per_skill_warn_tokens` violations.
- **Same bug, two other parsers** (each must be considered in any fix):
  - `scripts/little_loops/cli/action.py:31-46` `_read_skill_description()` — uses `line.startswith("description:")`; for `description: |` returns `"|"`.
  - `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` `_parse_frontmatter()` — character-for-character identical to the `doc_counts.py` defect. Breaks `_extract_trigger_keywords()` (line 46) for all 6 affected skills (their `"Trigger keywords:"` lines are silently discarded during regeneration).
- **Correct exemplar already in the codebase**: `scripts/little_loops/cli/adapt_skills_for_codex.py:42-51` `_extract_short_desc()` uses `yaml.safe_load()` on the frontmatter block and handles block scalars correctly.
- **Why the existing tests didn't catch it**: `scripts/tests/test_doc_counts.py:538-546` `TestCheckSkillBudget._make_skill()` always writes `description: {description}` as a single-line scalar. The block-scalar code path is unexercised.

## Proposed Solution

For each of the six `skills/ll-*/SKILL.md` files, replace the empty `description: |` with a valid ≤100-char single-line, trigger-first description. Reuse the existing `metadata.short-description` value where present to keep the two fields consistent.

If ENH-1615 (adding `disable-model-invocation: true` to all bridge skills) is implemented first, the description still needs a non-empty valid value but its routing content no longer matters — coordinate ordering with that issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. Three distinct options now exist; see `decision_needed: true` in frontmatter:_

**Option A — Fix `_parse_skill_frontmatter()` in `doc_counts.py` only (minimum-surface fix)**

> **Selected:** Option A — Fix `_parse_skill_frontmatter()` in `doc_counts.py` only — yaml.safe_load matches 9 existing call sites; parser-level fix survives adapter regeneration.

Replace the line loop at `scripts/little_loops/doc_counts.py:268-280` with `yaml.safe_load()` on the frontmatter block. Pattern to follow: `scripts/little_loops/cli/adapt_skills_for_codex.py:42-51` `_extract_short_desc()`. PyYAML is already a declared runtime dependency (`scripts/pyproject.toml:38` `pyyaml>=6.0`), so no new dependency.

- Pros: zero SKILL.md edits; restores real token counts and routing visibility for all 6 skills immediately; small diff (~12 lines).
- Cons: leaves the identical defect in `cli/action.py` and `cli/generate_skill_descriptions.py` for the next person to discover.

**Option B — Flatten the six descriptions to single-line scalars (issue's original framing)**

For each of the 6 SKILL.md files, rewrite `description: |\n  <body>` as `description: <one-line summary>` (≤100 chars). Discards the well-formed multi-line content.

- Pros: no Python changes; works around all three buggy parsers simultaneously.
- Cons: throws away curated trigger-keyword content; doesn't fix the underlying parser bugs (next block-scalar description will silently break again); doesn't restore the silent budget undercount caused by the parser itself.

**Option C — Consolidate to a single shared YAML-aware helper (comprehensive fix)**

Extract a shared `_parse_skill_frontmatter()` (or reuse `little_loops.frontmatter`-style helper) backed by `yaml.safe_load()`, then replace the three buggy implementations:

  - `scripts/little_loops/doc_counts.py:268-280` `_parse_skill_frontmatter()`
  - `scripts/little_loops/cli/action.py:31-46` `_read_skill_description()`
  - `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` `_parse_frontmatter()`

- Pros: kills the bug class everywhere; fixes the silent failure in `_extract_trigger_keywords()` regeneration; matches the existing `yaml.safe_load` pattern used in `learning_tests.py:82-87`, `goals_parser.py:125-136`, and `adapt_skills_for_codex.py:42-51`.
- Cons: largest diff; touches three modules with separate test files.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-23.

**Selected**: Option A — Fix `_parse_skill_frontmatter()` in `doc_counts.py` only

**Reasoning**: Option A replaces the hand-rolled line loop with `yaml.safe_load`, exactly matching the pattern used at `adapt_skills_for_codex.py:42-51` and 8 other production call sites — the established codebase convention. The parser-level fix means block-scalar descriptions work correctly even if `ll-adapt-skills-for-codex --apply` regenerates the SKILL.md files, making the fix self-sustaining; Option B's data-only workaround is silently reverted by the generator. Two known remaining buggy parsers (`action.py:31-46`, `generate_skill_descriptions.py:29-43`) are a deliberate scope trade-off best handled as a follow-up if needed.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B | 3/3 | 3/3 | 3/3 | 1/3 | 10/12 |
| Option C | 3/3 | 1/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: `adapt_skills_for_codex.py:42-51` is a working proof-of-concept for the exact fix — same `str.find("---", 3)` boundary, same field, same `try/except yaml.YAMLError` guard; negligible risk since it only touches one private function.
- Option B: All 22 other bridge skills use single-line format (reuse score 3/3), but `_synthesized_skill_md()` at `adapt_skills_for_codex.py:194-199` regenerates block-scalar format on re-run — the fix is silently revertible.
- Option C: Strongest long-term fix (kills the bug class) but highest complexity — three modules, three test files; better suited to a follow-up issue.

## Integration Map

### Files to Modify
- `skills/ll-loop-suggester/SKILL.md`
- `skills/ll-manage-release/SKILL.md`
- `skills/ll-open-pr/SKILL.md`
- `skills/ll-review-sprint/SKILL.md`
- `skills/ll-sync-issues/SKILL.md`
- `skills/ll-tradeoff-review-issues/SKILL.md`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/doc_counts.py` — **Option A primary target**: replace `_parse_skill_frontmatter()` (lines 268-280) with `yaml.safe_load`; add `import yaml` at module top (already a declared dependency via `pyyaml>=6.0` in `pyproject.toml`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/doc_counts.py` — `check_skill_budget()` reads these descriptions (no code change required)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/docs.py` — `main_verify_skill_budget()` at line 107 imports and calls `check_skill_budget()`; no change needed but validates the call-chain is unchanged after the fix
- `scripts/little_loops/cli/__init__.py` — re-exports `main_verify_skill_budget` at line 41, listed in `__all__` at line 94; no change needed

### Similar Patterns
- Other `skills/ll-*/SKILL.md` bridge skills — verify none share the same empty-description defect

### Tests
- `ll-verify-skill-budget` — should be re-run after the fix; confirm the six skills no longer report 0 tokens

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py::TestCheckSkillBudget` — add a new test method `test_block_scalar_description_parsed_correctly`; the existing `_make_skill()` helper writes only single-line scalars and never exercises the `description: |` path. New test to write (follow `test_counts_tokens_for_enabled_skills` pattern):

  ```python
  def test_block_scalar_description_parsed_correctly(self, tmp_path: Path) -> None:
      """Block-scalar description: | is resolved to its string content, not '|'."""
      skills_dir = tmp_path / "skills"
      skills_dir.mkdir()
      skill_dir = skills_dir / "block-skill"
      skill_dir.mkdir()
      (skill_dir / "SKILL.md").write_text(
          "---\ndescription: |\n  Real multi-line content here\n  Trigger keywords: foo\n---\n# block-skill\n"
      )
      result: SkillBudgetResult = check_skill_budget(base_dir=tmp_path)
      assert len(result.skill_breakdown) == 1
      _, desc, tokens = result.skill_breakdown[0]
      assert desc != "|"                        # regression guard: old parser returned literal "|"
      assert "Real multi-line content" in desc
      assert tokens > 0
  ```

- `scripts/tests/test_cli_docs.py::TestMainVerifySkillBudget` — no changes needed; all tests mock `check_skill_budget` and never invoke the parser

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. Most of these apply if Option A or C is chosen (parser fix); the SKILL.md file list above applies if Option B is chosen (flatten descriptions)._

**Parser-fix targets (Options A / C):**
- `scripts/little_loops/doc_counts.py:268-280` — `_parse_skill_frontmatter()` (always needs fixing)
- `scripts/little_loops/cli/action.py:31-46` — `_read_skill_description()` (same defect; only in Option C)
- `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` — `_parse_frontmatter()` (same defect; only in Option C)

**Dependent files (callers of buggy parsers):**
- `scripts/little_loops/doc_counts.py:283-330` — `check_skill_budget()` consumes `_parse_skill_frontmatter()` output
- `scripts/little_loops/cli/docs.py:107` — `main_verify_skill_budget()` CLI entry point (registered in `scripts/pyproject.toml:60`)
- `scripts/little_loops/cli/generate_skill_descriptions.py:46` — `_extract_trigger_keywords()` silently drops trigger keywords for block-scalar skills
- `scripts/little_loops/cli/action.py` — `_read_skill_description()` callers (affects `ll-action` skill resolution)

**Reference patterns to follow:**
- `scripts/little_loops/learning_tests.py:82-87` — `_read_frontmatter_yaml()` regex + `yaml.safe_load`
- `scripts/little_loops/goals_parser.py:125-136` — `split("---", 2)` + `yaml.safe_load` with `yaml.YAMLError` guard
- `scripts/little_loops/cli/adapt_skills_for_codex.py:42-51` — `_extract_short_desc()` (closest structural analogue: same `text.find("---", 3)` fence detection on a SKILL.md, but uses `yaml.safe_load`)
- `scripts/little_loops/frontmatter.py:70-75` — already explicitly detects `|` / `>` indicators (different failure mode: sets value to `None` instead of corrupting); consider whether to consolidate here

**Tests to update:**
- `scripts/tests/test_doc_counts.py:538-546` — `TestCheckSkillBudget._make_skill()` only writes single-line scalars; add a helper or test that writes `description: |` with indented body and asserts non-zero `tokens` and the resolved description string in `result.skill_breakdown`
- `scripts/tests/test_cli_docs.py` — `TestMainVerifySkillBudget` (CLI integration tests for `ll-verify-skill-budget`)
- `scripts/tests/test_generate_skill_descriptions.py` — if Option C, add block-scalar test for `_parse_frontmatter()` and `_extract_trigger_keywords()`

**Dependencies:**
- `pyyaml>=6.0` already declared at `scripts/pyproject.toml:38` — no new dependency required.

## Implementation Steps

1. Confirm the existing `metadata.short-description` value for each of the six skills.
2. Replace the empty `description: |` frontmatter field with a valid ≤100-char trigger-first description.
3. Re-run `ll-verify-skill-budget` to confirm non-zero token counts and that the listing budget is still within limits.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps per option. Run `/ll:decide-issue BUG-1616` first to pick._

**If Option A (fix parser in `doc_counts.py` only):**

1. Edit `scripts/little_loops/doc_counts.py:268-280` `_parse_skill_frontmatter()`. Replace the line loop with `yaml.safe_load(text[3:end])`, guarded by `try/except yaml.YAMLError`, returning `{}` on parse failure. Add `import yaml` at the top if not already present. Normalize the return type — `safe_load` yields `Any`; coerce non-`dict` results to `{}` and stringify values so downstream `fm.get("description", "")` still returns a `str`.
2. Add a regression test in `scripts/tests/test_doc_counts.py::TestCheckSkillBudget`: extend `_make_skill()` (or add `_make_skill_block_scalar()`) to write `description: |\n  Real multi-line content here\n  Trigger keywords: foo`, then assert `result.skill_breakdown` contains the resolved description string and `tokens > 0`.
3. Run `python -m pytest scripts/tests/test_doc_counts.py scripts/tests/test_cli_docs.py -v` to confirm no regressions.
4. Run `ll-verify-skill-budget` and visually verify the 6 affected skills (`ll-loop-suggester`, `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`) now report non-zero tokens with their real descriptions; verify the total budget number changed (it will increase, since 6 skills' real token mass was previously hidden as 0).
5. Re-check budget headroom — if the now-visible mass pushes total over `per_skill_warn_tokens` or the overall budget, surface that as a follow-up (likely a related issue to ENH-1370 / BUG-1379).

**If Option B (flatten descriptions in 6 SKILL.md files):**

1. For each of the six `skills/ll-*/SKILL.md` files, read the existing block-scalar body and the `metadata.short-description` field (if present).
2. Edit each frontmatter to replace `description: |\n  <body>` with a single-line `description: <≤100-char trigger-first summary>`. Reuse `metadata.short-description` verbatim when it fits.
3. Run `ll-verify-skill-budget` to confirm non-zero tokens.
4. Do NOT close the issue without noting: the parser at `doc_counts.py:268-280` remains broken and will silently corrupt any future block-scalar description — file a follow-up if Option C is not taken.

**If Option C (consolidate to shared YAML-aware helper):**

1. Add (or extend) a shared helper — recommended location: `scripts/little_loops/frontmatter.py` (already has block-scalar awareness at line 70-75). Expose a `parse_skill_frontmatter(text: str) -> dict[str, Any]` backed by `yaml.safe_load`.
2. Replace the three buggy implementations with calls to the shared helper:
   - `scripts/little_loops/doc_counts.py:268-280` `_parse_skill_frontmatter()`
   - `scripts/little_loops/cli/action.py:31-46` `_read_skill_description()`
   - `scripts/little_loops/cli/generate_skill_descriptions.py:29-43` `_parse_frontmatter()`
3. Add block-scalar regression tests in `scripts/tests/test_doc_counts.py`, `scripts/tests/test_cli_docs.py`, and `scripts/tests/test_generate_skill_descriptions.py` matching the `_make_skill()` fixture style.
4. Run full test suite: `python -m pytest scripts/tests/ -v`.
5. Run `ll-verify-skill-budget` and (if practical) re-run `ll-generate-skill-descriptions --dry-run` on one of the 6 affected skills to confirm `_extract_trigger_keywords()` now sees the keywords.

## Impact

- **Priority**: P3 — wastes listing slots but doesn't block functionality
- **Effort**: Small — fix 6 description fields in `skills/ll-*/SKILL.md`
- **Risk**: Low — frontmatter-only edits to six files, verifiable with `ll-verify-skill-budget`
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `skills`, `context-engineering`, `data-quality`

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-05-22

- The six skills are real and do report 0 tokens in `check_skill_budget()`.
- HOWEVER, the descriptions are NOT empty: each of the six SKILL.md files has a proper YAML `description: |` block scalar with multi-line content (e.g. `skills/ll-loop-suggester/SKILL.md:3-5` has a full description plus trigger keywords).
- Root cause is in the **parser**, not the skill files: `scripts/little_loops/doc_counts.py:268-280` contains a naive line-based `_parse_skill_frontmatter()` that returns the literal `'|'` indicator instead of consuming the indented block scalar body.
- Two viable fixes:
  1. Fix the parser (`doc_counts.py`) to handle YAML block scalars properly — restores routing info from the existing content with no SKILL.md edits.
  2. Flatten the six descriptions to inline single-line strings — matches the issue's proposed solution, but discards existing well-formed content.
- Recommendation: fix the parser first; option (2) is unnecessary if the parser does its job. The issue's framing ("broken descriptions") should be updated to "parser does not read block-scalar descriptions."

## Session Log
- `/ll:manage-issue` - 2026-05-23T06:29:52Z - `111182d8-94d8-4805-a59e-95797a4cc7e6.jsonl`
- `/ll:ready-issue` - 2026-05-23T06:22:23 - `ee89d3b0-3ebe-456c-beda-8434eb76e869.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `29031fad-bb1d-4723-8ce9-fd7709708f7a.jsonl`
- `/ll:wire-issue` - 2026-05-23T05:27:59 - `6a25d47f-eb12-4ba8-b0ff-4dec62b2a053.jsonl`
- `/ll:decide-issue` - 2026-05-23T05:23:28 - `2cd9991e-4e31-4055-ae7c-4cb812fac965.jsonl`
- `/ll:refine-issue` - 2026-05-23T05:10:25 - `222e4590-5233-47fc-bd93-c624dbea2958.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:format-issue` - 2026-05-22T22:12:28 - `da2cdb66-57d9-4b9e-ad13-a2228c32b4d3.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Done** | Created: 2026-05-22 | Completed: 2026-05-23 | Priority: P3

## Resolution

Implemented Option A: replaced the hand-rolled line loop in `_parse_skill_frontmatter()` at `scripts/little_loops/doc_counts.py` with `yaml.safe_load`, guarded by `yaml.YAMLError`. A line-based fallback handles existing SKILL.md files whose frontmatter contains unquoted colons (e.g. `review-loop`, `update-docs`, `manage-issue`) so they are not regressed to empty parses. Added a regression test `test_block_scalar_description_parsed_correctly` in `scripts/tests/test_doc_counts.py::TestCheckSkillBudget`.

Verified with `ll-verify-skill-budget`: the six affected skills now report real token counts (`ll-loop-suggester` 143, `ll-review-sprint` 123, `ll-tradeoff-review-issues` 116, `ll-manage-release` 74, `ll-sync-issues` 52, `ll-open-pr` 44). Total budget is 1262/2000 tokens — still well under threshold. Full test suite passes (7363 passed, 5 skipped). The two known sibling parsers in `cli/action.py` and `cli/generate_skill_descriptions.py` are intentionally out of scope (Option C follow-up).
