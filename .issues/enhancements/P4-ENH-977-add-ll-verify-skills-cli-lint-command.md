---
id: ENH-977
title: Add `ll-verify-skills` CLI Lint Command
type: ENH
priority: P4
discovered_date: 2026-04-07
discovered_by: split-from-ENH-494
captured_at: 2026-04-07 00:00:00+00:00
completed_at: 2026-06-03 04:02:01+00:00
status: done
parent: EPIC-1745
blocked_by: []
confidence_score: 80
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
size: Very Large
---

# ENH-977: Add `ll-verify-skills` CLI Lint Command

## Summary

Add a `ll-verify-skills` CLI tool that enforces the 500-line SKILL.md limit introduced by ENH-494. The tool scans all `skills/*/SKILL.md` files, flags any that exceed 500 lines, and exits non-zero if violations are found — enabling CI enforcement of the companion-file convention.

## Current Behavior

There is no automated check for SKILL.md file size. The 500-line convention (established by ENH-494) is documented in `CONTRIBUTING.md` but not machine-enforced. Violations can silently accumulate.

## Expected Behavior

- `ll-verify-skills` scans all `skills/*/SKILL.md` files
- Prints a violation line for each file over 500 lines (with actual line count)
- Exits 0 if all files are within limit; exits 1 if any exceed it
- Companion files (non-`SKILL.md` files in `skills/<name>/`) are not counted toward the limit
- Integrates into CI alongside `ll-verify-docs` and `ll-check-links`

## Motivation

ENH-494 establishes the 500-line convention and companion-file pattern, but only as a documented standard. Without a lint check, oversized skills can silently re-emerge (as already happened: `confidence-check` grew 60 lines between 2026-04-02 and 2026-04-07). A cheap automated check closes this loop.

## Proposed Solution

Extend `scripts/little_loops/doc_counts.py` with a `check_skill_sizes()` function and add a `main_verify_skills()` CLI entry point following the established patterns for `ll-verify-skill-budget`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Structural analog**: `check_skill_budget()` at `doc_counts.py:319` is the direct implementation model — it iterates `skills_dir.glob("*/SKILL.md")`, calls `_parse_skill_frontmatter()`, checks `fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1")` at line 350 to skip flagged skills, then accumulates results. `check_skill_sizes()` reuses the same skeleton but measures `len(text.splitlines())` against a `limit` instead of `len(description) // 4` against a token budget.
- **Frontmatter parsing**: `_parse_skill_frontmatter()` exists at `doc_counts.py:280` (private). A canonical public version `parse_skill_frontmatter()` is also available at `scripts/little_loops/frontmatter.py:122`. New code should prefer the public `frontmatter` module import.
- **`disable-model-invocation` exclusion**: The skip pattern is already established — 16 SKILL.md files carry this flag. `check_skill_sizes()` must apply the same skip to avoid flagging intentionally large skills that are excluded from the listing budget.
- **CLI entry point pattern**: `main_verify_skill_budget()` at `docs.py:111` is closer in spirit than `main_verify_docs()` at `docs.py:15` — it uses `add_json_arg(parser)`, prints results directly with `print()`/`logger`, and returns `0 if result.under_budget else 1`. `main_verify_skills()` should follow this simpler pattern (no `--format` or `--fix` flags needed).

## Implementation Steps

1. Add `check_skill_sizes(limit: int = 500) -> list[tuple[Path, int]]` to `scripts/little_loops/doc_counts.py` — insert after `check_skill_budget()` at line 366; use `skills_dir.glob("*/SKILL.md")` (not `rglob`) matching the existing pattern; call `_parse_skill_frontmatter(text)` and skip files where `fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1")` (same guard as `check_skill_budget()` at line 350); return `(path, line_count)` pairs where `len(text.splitlines()) > limit`

2. Add `main_verify_skills()` entry point in `scripts/little_loops/cli/docs.py` — insert after `main_verify_skill_budget()` (ends at line 234), before `main_check_links()` at line 237; model after `main_verify_skill_budget()` at `docs.py:111` (uses `add_json_arg(parser)`, lazy import inside `cli_event_context`, prints violations directly, returns `0 if not violations else 1`); arguments: `--limit N` (default 500), `-j/--json`, `-C/--directory`

3. Register entry point in `scripts/pyproject.toml:61` — add `ll-verify-skills = "little_loops.cli:main_verify_skills"` after `ll-verify-skill-budget` at line 61

4. Update `scripts/little_loops/cli/__init__.py` — add `main_verify_skills` to the import at line 43 (alongside `main_check_links, main_verify_docs, main_verify_skill_budget`); add `"main_verify_skills"` to `__all__` after `"main_verify_skill_budget"` at line 100

5. Add tests:
   - Add `TestMainVerifySkills` class to `scripts/tests/test_cli_docs.py` — follow the `TestMainVerifySkillBudget` pattern (lines 353+, `sys.argv`-patch + `capsys` for JSON tests); test exit 0 on clean, exit 1 on violation, `--limit` override, `--json` output, `--directory` passthrough; also update the import at line 9 (`from little_loops.cli.docs import ...`) to include `main_verify_skills`
   - Create `scripts/tests/test_skill_size_checker.py` — follow `TestCheckSkillBudget` at `test_doc_counts.py:702+` using the `_make_skill()` helper pattern (writes SKILL.md via `tmp_path`); test: SKILL.md > 500 lines is flagged, ≤ 500 passes, companion files alongside SKILL.md are not counted, skills with `disable-model-invocation: true` are skipped even if > 500 lines

6. Register in all CLI tool listings:
   - `commands/help.md:266` — insert `ll-verify-skills` after `ll-verify-skill-budget` at line 266 (currently `ll-check-links` is at line 267)
   - `.claude/CLAUDE.md:174` — insert `ll-verify-skills` line after `ll-verify-skill-budget` at line 174 (before `ll-check-links` at line 175)
   - `README.md:46` — update `"30 typed CLI tools"` → `"31 typed CLI tools"` (the count string at line 46; there is no per-tool listing entry for `ll-verify-docs` or `ll-verify-skill-budget` in README, just this count)
   - `docs/reference/CLI.md:1880` — add `ll-verify-skills` reference section after `ll-verify-skill-budget` (which ends at line 1880, with `### ll-check-links` at line 1882); follow the same section structure

7. Update skill templates that enumerate CLI tools:
   - `skills/init/SKILL.md:329,402,437` — three occurrences list `ll-verify-docs`; add `ll-verify-skills` at each (and optionally `ll-verify-skill-budget` if not already present)
   - `skills/configure/areas.md:813` — the current 28-tool enumeration string; add `ll-verify-skills` to the tool list and bump the count from `"Authorize all 28"` to `"Authorize all 29"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_create_extension_wiring.py` — after step 7 (`areas.md` update), fix the count assertion in:
   - `TestFeat1689HarnessWiring.test_configure_areas_count_updated_to_28` (line 373, assert at line 375): update `"Authorize all 28"` → `"Authorize all 29"`
   - `TestConfigureAreasWiring.test_count_updated_to_17` (line 55, assert at line 57): update `"Authorize all 28"` → `"Authorize all 29"`
   - `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` (line 194, assert at line 196): update `"Authorize all 28"` → `"Authorize all 29"`

9. Update `scripts/tests/test_create_extension_wiring.py` — after step 6 (`README.md` update), fix the README count assertion in:
   - `TestFeat1045DocUpdates.test_readme_tool_count_is_20` (line 77, assert at line 79): update `"30 typed CLI tools"` → `"31 typed CLI tools"`
   - `TestFeat1229LlActionWiring.test_readme_tool_count_is_20` (line 190, assert at line 192): update `"30 typed CLI tools"` → `"31 typed CLI tools"`

10. Update `CONTRIBUTING.md` — "New Skill Checklist" section (heading at line 582); insert new item after item 4 (`ll-verify-skill-budget` at line 594): "run `ll-verify-skills` to check that no SKILL.md exceeds 500 lines"

11. Update `scripts/tests/test_cli_docs.py:9` — add `main_verify_skills` to the existing import line when implementing step 5 (the `from little_loops.cli.docs import ...` line at line 9 must include the new entry point)

## Scope Boundaries

- **In scope**: New CLI tool, tests, registration in all tool listings
- **Out of scope**: Changing the 500-line limit itself (change `CONTRIBUTING.md` instead), modifying skill content

## Integration Map

### Files to Modify
- `scripts/little_loops/doc_counts.py:366` — add `check_skill_sizes()` after `check_skill_budget()` (which ends at line 366)
- `scripts/little_loops/cli/docs.py:234` — add `main_verify_skills()` after `main_verify_skill_budget()` (ends at line 234), before `main_check_links()` at line 237
- `scripts/pyproject.toml:61` — add `ll-verify-skills` entry after `ll-verify-skill-budget` at line 61
- `scripts/little_loops/cli/__init__.py:43` — add `main_verify_skills` to import; add to `__all__` after line 100
- `scripts/tests/test_cli_docs.py` — update import at line 9; add `TestMainVerifySkills` class
- `commands/help.md:266` — add `ll-verify-skills` after `ll-verify-skill-budget` at line 266
- `.claude/CLAUDE.md:174` — add `ll-verify-skills` after `ll-verify-skill-budget` at line 174
- `README.md:46` — update `"30 typed CLI tools"` → `"31 typed CLI tools"` (count string only; no per-tool listing section)
- `docs/reference/CLI.md:1880` — add `ll-verify-skills` reference section after `ll-verify-skill-budget` (ends at line 1880, before `### ll-check-links` at line 1882)
- `skills/init/SKILL.md:329,402,437` — add `ll-verify-skills` at three template locations listing `ll-verify-docs`
- `skills/configure/areas.md:813` — add `ll-verify-skills` to enumeration string; bump count from `"Authorize all 28"` to `"Authorize all 29"`
- `CONTRIBUTING.md:594` — "New Skill Checklist" section; add `ll-verify-skills` item after item 4 (`ll-verify-skill-budget` at line 594)
- `scripts/tests/test_create_extension_wiring.py` — update count assertions for `areas.md` (steps 8) and `README.md` (step 9)

### New Files
- `scripts/tests/test_skill_size_checker.py` — unit tests for `check_skill_sizes()`

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/doc_counts.py:319` — `check_skill_budget()` is the **structural template** for `check_skill_sizes()`; reuse its `glob("*/SKILL.md")` iteration, `_parse_skill_frontmatter()` call, and `disable-model-invocation` skip guard at line 350
- `scripts/little_loops/doc_counts.py:280` — `_parse_skill_frontmatter()` is the private frontmatter parser; alternative: `scripts/little_loops/frontmatter.py:122` has `parse_skill_frontmatter()` as the canonical public version (new code should prefer the public module)
- `scripts/little_loops/cli/docs.py:111` — `main_verify_skill_budget()` is the closer implementation pattern (simpler than `main_verify_docs()`): no `--format`, uses `add_json_arg()`, prints directly via `logger`
- `scripts/tests/test_doc_counts.py:702` — `TestCheckSkillBudget` class has a `_make_skill()` helper at line 705 (writes SKILL.md with frontmatter to `tmp_path`) to model `test_skill_size_checker.py` after

### Skills with `disable-model-invocation: true` (must be excluded from violations)

_Added by `/ll:refine-issue` — 16 skills currently carry this flag:_

`audit-claude-config`, `audit-docs`, `audit-issue-conflicts`, `audit-loop-run`, `analyze-history`, `cleanup-loops`, `debug-loop-run`, `improve-claude-md`, `issue-size-review`, `issue-workflow`, `link-epics`, `map-dependencies`, `rename-loop`, `review-loop`, `update`, `update-docs`

### Tests

_Wiring pass added by `/ll:wire-issue`; line numbers verified by `/ll:refine-issue` 2026-06-03:_
- `scripts/tests/test_create_extension_wiring.py` — **WILL BREAK** (3 assertions): `TestFeat1689HarnessWiring.test_configure_areas_count_updated_to_28` (line 373, assert at 375), `TestConfigureAreasWiring.test_count_updated_to_17` (line 55, assert at 57), and `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` (line 194, assert at 196) all assert `"Authorize all 28"` in `skills/configure/areas.md`; must update to `"Authorize all 29"` after step 7
- `scripts/tests/test_create_extension_wiring.py` — **WILL BREAK** (2 assertions): `TestFeat1045DocUpdates.test_readme_tool_count_is_20` (line 77, assert at 79) and `TestFeat1229LlActionWiring.test_readme_tool_count_is_20` (line 190, assert at 192) assert `"30 typed CLI tools"` in `README.md`; must update to `"31 typed CLI tools"` after step 6
- `scripts/tests/test_cli_docs.py:9` — add `main_verify_skills` to existing `from little_loops.cli.docs import ...` line when adding `TestMainVerifySkills` class in step 5

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — "New Skill Checklist" section (line 582); item 4 (line 594) references only `ll-verify-skill-budget`; add new item for `ll-verify-skills` and the 500-line SKILL.md limit
- `docs/claude-code/skills.md` — `<Tip>Keep SKILL.md under 500 lines...` block; add "Enforce with `ll-verify-skills`" cross-reference (informational, not a breaking gap)

## Impact

- **Priority**: P4 — CI hygiene; not blocking
- **Effort**: Low — Pure addition; follows a well-established pattern
- **Risk**: Low — New tool, no changes to existing behavior
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `testing`, `skills`, `context-engineering`

## Verification Notes

**Verdict**: VALID — Re-verified 2026-06-02

- ENH-494 is `status: done` — blocker cleared; removed from `blocked_by` frontmatter
- All 6 former SKILL.md violators now under 500 lines: audit-claude-config (470), confidence-check (499), init (497), manage-issue (496), debug-loop-run (426), review-loop (444) — threshold remains meaningful (files are close to the limit, not trivially far below it)
- "Lint will fail on day 1" warning from earlier passes is resolved — companion files are in place
- CONTRIBUTING.md line numbers updated: section heading drifted to 582 (was 538), `ll-verify-skill-budget` item to 594 (was 550)
- All other line references verified accurate: doc_counts.py (319, 350, 366), docs.py (111, 234, 237), cli/__init__.py (43, 100), test_doc_counts.py (702, 705), test_cli_docs.py (9, 353)

**Verdict**: VALID — Re-verified 2026-05-22

- No `check_skill_sizes()` function in `scripts/little_loops/doc_counts.py` ✓
- No `main_verify_skills()` in `scripts/little_loops/cli/docs.py` ✓
- No `ll-verify-skills` entry point in `scripts/pyproject.toml` ✓
- BUG-1600 is now `status: done` — removed from `depends_on` frontmatter (only ENH-494 remains as live blocker)
- Note: ENH-494 scope expanded to 6 violators (2 new: `debug-loop-run`, `review-loop`). Watch that this issue is not implemented before ENH-494 fully extracts companion files, or the lint will fail on day 1.

**Verdict**: VALID — Re-verified 2026-05-17

- No `check_skill_sizes()` function in `scripts/little_loops/doc_counts.py` ✓
- No `main_verify_skills()` in `scripts/little_loops/cli/docs.py` ✓
- No `ll-verify-skills` entry point in `scripts/pyproject.toml` ✓
- ENH-1038 is now `status: done` — removed from `blocked_by`; only ENH-494 remains as blocker

**Verdict**: VALID — Verified 2026-04-11; re-verified 2026-05-14

- No `check_skill_sizes()` function in `scripts/little_loops/doc_counts.py`
- No `main_verify_skills()` in `scripts/little_loops/cli/docs.py`
- No `ll-verify-skills` entry point in `scripts/pyproject.toml`
- Blocked by ENH-494 (500-line convention not yet established) and ENH-1038 (sequencing for `doc_counts.py` changes)
- **Disambiguation (2026-05-14)**: A separate tool `ll-verify-skill-budget` already exists (cli/docs.py:107, pyproject.toml:59). It checks the *description token footprint* against the Claude Code listing budget — **not** SKILL.md line count. Do not conflate the two. `ll-verify-skills` (this issue) is a complementary line-count linter for the 500-line convention.

## Status

**Open** | Created: 2026-04-07 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-02_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **ENH-494 is open (blocker unresolved)**: The issue's own verification notes warn "lint will fail on day 1" if implemented before ENH-494 extracts companion files from large SKILL.md files (`confidence-check`, `init`, `manage-issue`, `audit-claude-config`). The tool can be coded, but it must not be deployed to CI until ENH-494 ships.
- **5 breaking test assertions pre-identified**: `test_create_extension_wiring.py` contains 5 assertions that will break: 3 asserting `"Authorize all 28"` (lines 57, 196, 375) and 2 asserting `"30 typed CLI tools"` (lines 79, 192). Steps 8–9 in the implementation plan address these.

## Session Log
- `/ll:ready-issue` - 2026-06-03T03:48:30 - `2ac8bc42-fa7c-4c87-bcc5-c8727999a2e0.jsonl`
- `/ll:refine-issue` - 2026-06-03T03:45:06 - `1c5f3489-3162-4e2a-b587-f77e2b02980f.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-06-03T01:55:51 - `7d84a3c4-7800-4b5a-b1f1-cde3fa604493.jsonl`
- `/ll:refine-issue` - 2026-06-03T02:00:00 - `unknown`
- `/ll:confidence-check` - 2026-06-02T00:00:00 - `263863b8-87b8-4fba-b1e0-6d95a9692874.jsonl`
- `/ll:wire-issue` - 2026-06-03T01:45:26 - `8825a95c-36f5-45b4-ae94-d53d479c18e5.jsonl`
- `/ll:refine-issue` - 2026-06-03T01:37:02 - `390f7054-9a2a-4fb2-be7b-c2245668d370.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:01:18 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:verify-issues` - 2026-05-17T17:04:58 - `907d2d29-7e38-4120-a77d-deb597ac2df4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:02:32 - `75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:04 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:45:22 - `6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:15 - `e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:01:00 - `1085382e-e53c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:59 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-908d-52f82f68d5fa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:03 - `4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-1038 (ll-verify-docs should track FSM loop counts) both modify `scripts/little_loops/doc_counts.py` and `scripts/little_loops/cli/docs.py`. Changes are additive in different sections (ENH-977 adds `check_skill_sizes()` and `main_verify_skills()`; ENH-1038 adds to `COUNT_TARGETS`), but they should be sequenced or merged to avoid conflicts in the same PR. Related: ENH-1038.

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): The "companion files alongside `SKILL.md` are not counted toward the 500-line limit" test case (Implementation Step 5) explicitly assumes ENH-494's flat-companion-file pattern landed first. ENH-977's `rglob('SKILL.md')` walk is robust to the alternative subdirectory pattern, but the test fixtures are not — keep `blocked_by: [ENH-494]` and re-validate the fixture layout if ENH-494's companion-file decision ever changes.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04; resolved 2026-06-02): After ENH-494 ships and extracts overflow content from `audit-claude-config`, `confidence-check`, `init`, and `manage-issue` SKILL.md files, re-verify that the 500-line threshold is still meaningful (i.e., the remaining SKILL.md files are not all trivially under 500 lines). **RESOLVED**: ENH-494 is `status: done`. All 6 violators are now at 426–499 lines — close to the 500-line ceiling, confirming the threshold is meaningful. No adjustment needed.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): Once ENH-1394 ships, skills tagged `disable-model-invocation: true` in their frontmatter are intentionally excluded from the Claude Code listing budget and may legitimately exceed 500 lines (since they are never loaded into the prompt token budget). The `ll-verify-skills` lint tool MUST skip (or report in a separate informational category, not as a violation) any SKILL.md that has `disable-model-invocation: true`. Implement this exclusion rule at the same time as or after ENH-1394 lands. Related: ENH-1394, ENH-1398.

**Sequencing confirmed** (added by `/ll:audit-issue-conflicts` 2026-05-14): ENH-1038 MUST land before this issue. Both touch `doc_counts.py` and `cli/docs.py` — ENH-1038 adds to `COUNT_TARGETS` while ENH-977 adds `check_skill_sizes()` + `main_verify_skills()`. Concurrent PRs in overlapping file regions cause near-certain merge conflicts. The `blocked_by: [ENH-1038]` in frontmatter enforces this order in sprint wave planning.
