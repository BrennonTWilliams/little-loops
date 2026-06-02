---
id: ENH-1729
title: 'Add link-epics skill: core implementation and tests'
type: ENH
status: done
priority: P3
parent: ENH-1728
decision_needed: false
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-26 22:48:40+00:00
---

# ENH-1729: Add link-epics skill: core implementation and tests

## Summary

Create the `link-epics` skill with its core logic: orphan discovery, Jaccard scoring, proposal flow, apply step, and test coverage.

## Current Behavior

No `link-epics` skill exists. When issues are created without a `parent:` frontmatter field, there is no automated way to discover and link those orphaned issues to relevant open EPICs — users must manually edit each issue file.

## Expected Behavior

Running `/ll:link-epics` discovers open BUG/FEAT/ENH issues without a `parent:` field, scores each against open EPICs using Jaccard similarity on title + summary text, presents HIGH/MEDIUM/LOW-tier proposals via `AskUserQuestion` (or auto-applies HIGH-tier with `--auto`), and writes `parent: EPIC-NNN` to accepted child frontmatter while appending the child ID to the EPIC's `relates_to:` and `## Children` section.

## Parent Issue

Decomposed from ENH-1728: Add skill to link parentless open issues to open epics

## Scope

This child covers **Implementation Steps 1–6 and 7** from the parent:

1. Create `skills/link-epics/SKILL.md` with frontmatter: `name: link-epics`, `disable-model-invocation: true`, `model: sonnet`, `argument-hint: "[--auto] [--min-score 0.5]"`, `allowed-tools` including `AskUserQuestion`, `Edit`, `Bash(ll-issues:*)`, `Bash(git:*)`, `Read` (see `skills/rename-loop/SKILL.md` for reference frontmatter structure)
2. Implement orphan discovery: run `ll-issues list --status open --type {BUG,FEAT,ENH} --json` (three calls); for each returned `path` call `parse_frontmatter()` (`scripts/little_loops/frontmatter.py`) and keep those where `parent` key is absent or None
3. Implement scoring: use `extract_words()` and `calculate_word_overlap()` from `scripts/little_loops/text_utils.py` (Jaccard on title + summary words); bucket into HIGH (≥ 0.7) / MEDIUM (≥ 0.4) / LOW (< 0.4) confidence tiers
4. Implement proposal flow: `AskUserQuestion` with `multiSelect: true` presenting each proposed (orphan → epic) pair with confidence label; in `--auto` mode, apply only HIGH-tier (or all tiers at or above `--min-score`) without prompting
5. Implement apply step: for the child issue write `parent: EPIC-NNN` via `update_frontmatter(content, {"parent": epic_id})` (`scripts/little_loops/frontmatter.py`); for the epic reuse the Phase 4c Edit logic from `skills/capture-issue/SKILL.md` (3 cases for `relates_to:`, `## Children` insertion before `## Status`); stage both with `git add`
6. Add `link-epics`^ entry to Issue Refinement list in `.claude/CLAUDE.md` (no `plugin.json` change needed — directory scan auto-discovers)
7. Write `scripts/tests/test_link_epics_skill.py` (not `test_link_epics.py`) using skill-test pattern from `scripts/tests/test_audit_issue_conflicts_skill.py` plus `IssueParser`/`update_frontmatter` fixture patterns from `scripts/tests/test_issue_parser.py`; cover: skill file existence, frontmatter content assertions, parentless-issue detection, Jaccard scoring, `update_frontmatter` round-trip writing `parent:`

## Scope Boundaries

- Does not create new EPICs — only assigns orphaned issues to existing open EPICs
- Does not resolve dependency links (`blocked_by`, `depends_on`) — use `/ll:map-dependencies` for those
- Does not score issues against closed or done EPICs
- Does not auto-apply assignments below the configurable `--min-score` threshold in interactive mode
- Does not modify EPIC priority, status, or any frontmatter fields beyond `relates_to:` and `## Children`

## Impact

- **Priority**: P3 — Quality-of-life improvement for issue hygiene; non-blocking
- **Effort**: Medium — New skill with 7 implementation steps plus test suite
- **Risk**: Low — Additive only; no existing production code modified except `.claude/CLAUDE.md`
- **Breaking Change**: No

## Key Dependencies

### Files to Create
- `skills/link-epics/SKILL.md` — new skill

### Files to Modify
- `.claude/CLAUDE.md` — add `link-epics`^ to Issue Refinement command list

### Files to Read (no modification)
- `scripts/little_loops/text_utils.py` — `extract_words()` and `calculate_word_overlap()` (Jaccard); import, do not re-implement
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` for writing `parent:`; `parse_frontmatter()` for reading
- `scripts/little_loops/issue_parser.py` — `IssueInfo.parent` and `IssueInfo.relates_to` dataclass fields
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` handles `ll-issues list --type EPIC --status open --json`

### Similar Patterns
- `skills/capture-issue/SKILL.md` Phase 4c ("Wire Parent EPIC") — canonical `relates_to:` + `## Children` write pattern with 3 cases
- `skills/map-dependencies/SKILL.md` — `AskUserQuestion` proposal flow; HIGH/MEDIUM/LOW confidence tier conventions
- `scripts/little_loops/issue_discovery/search.py` `find_existing_issue()` — Jaccard > 0.7 duplicate threshold; scoring tier conventions

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — skill-test file pattern to model after
- `scripts/tests/test_issue_parser.py` — fixture patterns for issues with/without `parent:` frontmatter (`test_parse_parent_from_frontmatter` line 1660, `test_parse_no_epic` line 839, `test_parse_epic_from_frontmatter` line 819)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_skills_for_codex.py` — `TestRealSkillsIntegrationGuard.test_all_real_skills_have_name_field()` and `test_all_real_skills_have_metadata_short_description()` check every `SKILL.md` for `name:` and `metadata.short-description:` fields **regardless of `disable-model-invocation`**; CI will fail if either field is absent from `skills/link-epics/SKILL.md` [Agent 2 finding]
- `scripts/tests/test_text_utils.py` — `TestCalculateWordOverlap` — reference pattern for Jaccard bucket assertions (identical=1.0, disjoint=0.0, partial=intersection/union) [Agent 3 finding]
- `scripts/tests/test_frontmatter.py` — `TestUpdateFrontmatter` — reference pattern for `update_frontmatter` round-trip test: write `parent: EPIC-NNN` via `update_frontmatter`, read back via `parse_frontmatter`, assert `fm["parent"] == "EPIC-NNN"` and existing fields preserved [Agent 3 finding]
- `scripts/tests/test_cli_docs.py` — `TestDocCountVerification` — mirrors `ll-verify-docs`; will fail CI after ENH-1729 adds skill 31 while docs still read "30 skills"; expected gap, ENH-1730 handles the count bump [Agent 2 finding]
- `scripts/tests/test_feat1287_doc_wiring.py` — `TestReadmeSkillCount`, `TestContributingWiring` — assert `"30 skills"` and `"30 skill definitions"` in doc text; will continue to pass after ENH-1729 (docs unchanged), but ENH-1730 must update these assertions to "31" alongside the doc edits [Agent 2 finding]
- `scripts/tests/test_feat1447_doc_wiring.py` — `TestReadmeSkillCount`, `TestContributingWiring`, `TestArchitectureSkillCount` — same pattern as test_feat1287; assert "30" in README/CONTRIBUTING/ARCHITECTURE; ENH-1730 scope to update [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Summary extraction (critical):** `IssueInfo` does not expose a `summary` field — the parser captures only frontmatter metadata and the `# ID: Title` heading. To build Jaccard word sets from `title + summary`, the skill must:
1. Read file: `content = Path(issue_path).read_text()`
2. Strip frontmatter: `body = strip_frontmatter(content)` (`scripts/little_loops/frontmatter.py:144`)
3. Extract with regex: `re.search(r"## Summary\n(.+?)(?=\n##|\Z)", body, re.DOTALL)`
4. Concatenate: `score_text = issue_info.title + " " + (match.group(1).strip() if match else "")`

**Edit vs `update_frontmatter` for EPIC `relates_to:` field:** Phase 4c in `capture-issue/SKILL.md` uses the `Edit` tool directly — not `update_frontmatter` — for the EPIC `relates_to:` field. `update_frontmatter` serializes via `yaml.dump` which converts inline `[ENH-100, ENH-101]` notation to multi-line block sequences, breaking the format used in all EPIC files (confirmed in `.issues/epics/P2-EPIC-1663-codify-meta-loop-harness-design-rules.md`). Use `Edit` with the 3-case pattern (absent / empty-list / populated) for `relates_to:` and `## Children`.

**`--type` flag is single-valued:** `list_cmd.py:42` reads `type_filter` as a single string, confirming three separate `ll-issues list` Bash calls are needed (one each for BUG, FEAT, ENH). Alternative: use `find_issues(config, type_prefixes={"BUG", "FEAT", "ENH"}, status_filter={"open"})` from `scripts/little_loops/issue_parser.py:831` in a single Python call if the skill invokes Python logic.

**Skill frontmatter reference (`rename-loop/SKILL.md`):** Complete structure: `name`, `description`, `disable-model-invocation: true`, blank line, `argument-hint`, `model: sonnet`, `allowed-tools` (using `Bash(tool:*)` scoping), `arguments` block with `required:` per arg, `metadata.short-description` mirroring `description`.

**`AskUserQuestion` format (interactive proposal flow):** Use the YAML `questions:` block pattern from `skills/capture-issue/SKILL.md` (lines 139–149), **not** the prose-description style used in `map-dependencies`. Each proposal should be one option with the orphan ID + proposed epic as the label and confidence tier as the description. Example structure:

```yaml
questions:
  - question: "Link these orphaned issues to their proposed epics?"
    header: "Proposals"
    multiSelect: true
    options:
      - label: "ENH-123 → EPIC-42 (HIGH 0.82)"
        description: "title-of-ench-123 — title-of-epic-42"
      - label: "BUG-55 → EPIC-42 (MEDIUM 0.51)"
        description: "title-of-bug-55 — title-of-epic-42"
```

**Test token checklist for `test_link_epics_skill.py`** (modeled on `test_audit_issue_conflicts_skill.py`):
- `SKILL_FILE = PROJECT_ROOT / "skills" / "link-epics" / "SKILL.md"` (`PROJECT_ROOT = Path(__file__).parent.parent.parent`)
- Class `TestLinkEpicsSkillExists`; each method re-asserts `SKILL_FILE.exists()`
- Content tokens to assert: `"--auto"`, `"--min-score"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`, `"parent:"`, `"{{config.issues.base_dir}}"` (or equivalent config template expression)
- `update_frontmatter` round-trip test: write `parent: EPIC-NNN` to a tmp file and assert it reads back correctly via `parse_frontmatter`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Ensure `skills/link-epics/SKILL.md` frontmatter includes both `name: link-epics` **and** `metadata.short-description:` — `TestRealSkillsIntegrationGuard` in `test_adapt_skills_for_codex.py` checks these fields for every skill file including `disable-model-invocation: true` skills; CI fails if either is absent
2. Note: `ll-verify-docs` will exit 1 after this issue lands (actual skill count increments from 30→31, documented counts unchanged) — expected; ENH-1730 handles the count bump; the corresponding test is `scripts/tests/test_cli_docs.py::TestDocCountVerification`
3. `scripts/tests/test_feat1287_doc_wiring.py` and `scripts/tests/test_feat1447_doc_wiring.py` hard-code `"30 skills"` counts and will NOT break from ENH-1729 alone (docs still say "30"), but ENH-1730 must update them to "31" alongside README/CONTRIBUTING/ARCHITECTURE edits

## Acceptance Criteria

- `/ll:link-epics` is invokable and lists orphaned open issues
- Jaccard scoring correctly buckets proposals into HIGH/MEDIUM/LOW tiers
- `--auto` applies only HIGH-tier (or above `--min-score`) without prompting
- Round-trip integrity: accepted assignment writes `parent: EPIC-NNN` to child frontmatter AND appends child ID to epic's `relates_to:` and `## Children`
- `scripts/tests/test_link_epics_skill.py` passes with `python -m pytest scripts/tests/test_link_epics_skill.py`

## Labels

`enhancement`, `skill`, `issue-management`

## Session Log
- `/ll:ready-issue` - 2026-05-26T22:43:20 - `dc36846e-baec-42bd-9d58-05cd135984c1.jsonl`
- `/ll:confidence-check` - 2026-05-26T23:00:00 - `47b95967-38f4-40e5-b64b-5d171aef9a13.jsonl`
- `/ll:wire-issue` - 2026-05-26T22:38:06 - `47b95967-38f4-40e5-b64b-5d171aef9a13.jsonl`
- `/ll:refine-issue` - 2026-05-26T22:31:39 - `36e49e4d-9e76-4dcd-8eb9-1eaddf63be71.jsonl`
- `/ll:wire-issue` - 2026-05-26T22:06:12 - `2f281563-3617-4295-8dad-fb6c9082c9d2.jsonl`
- `/ll:refine-issue` - 2026-05-26T22:00:35 - `22e83cb1-28b3-4cdf-bb09-7c4511b532a6.jsonl`
- `/ll:issue-size-review` - 2026-05-26T22:30:00Z - `d2480abd-758c-47ca-aa87-454ae8a76200.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
