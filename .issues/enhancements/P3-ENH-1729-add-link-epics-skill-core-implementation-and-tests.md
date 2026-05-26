---
id: ENH-1729
title: Add link-epics skill: core implementation and tests
type: ENH
status: open
priority: P3
parent: ENH-1728
---

# ENH-1729: Add link-epics skill: core implementation and tests

## Summary

Create the `link-epics` skill with its core logic: orphan discovery, Jaccard scoring, proposal flow, apply step, and test coverage.

## Parent Issue

Decomposed from ENH-1728: Add skill to link parentless open issues to open epics

## Scope

This child covers **Implementation Steps 1–5 and 7** from the parent:

1. Create `skills/link-epics/SKILL.md` with frontmatter: `name: link-epics`, `disable-model-invocation: true`, `model: sonnet`, `argument-hint: "[--auto] [--min-score 0.5]"`, `allowed-tools` including `AskUserQuestion`, `Edit`, `Bash(ll-issues:*)`, `Bash(git:*)`, `Read` (see `skills/rename-loop/SKILL.md` for reference frontmatter structure)
2. Implement orphan discovery: run `ll-issues list --status open --type {BUG,FEAT,ENH} --json` (three calls); for each returned `path` call `parse_frontmatter()` (`scripts/little_loops/frontmatter.py`) and keep those where `parent` key is absent or None
3. Implement scoring: use `extract_words()` and `calculate_word_overlap()` from `scripts/little_loops/text_utils.py` (Jaccard on title + summary words); bucket into HIGH (≥ 0.7) / MEDIUM (≥ 0.4) / LOW (< 0.4) confidence tiers
4. Implement proposal flow: `AskUserQuestion` with `multiSelect: true` presenting each proposed (orphan → epic) pair with confidence label; in `--auto` mode, apply only HIGH-tier (or all tiers at or above `--min-score`) without prompting
5. Implement apply step: for the child issue write `parent: EPIC-NNN` via `update_frontmatter(content, {"parent": epic_id})` (`scripts/little_loops/frontmatter.py`); for the epic reuse the Phase 4c Edit logic from `skills/capture-issue/SKILL.md` (3 cases for `relates_to:`, `## Children` insertion before `## Status`); stage both with `git add`
7. Write `scripts/tests/test_link_epics_skill.py` (not `test_link_epics.py`) using skill-test pattern from `scripts/tests/test_audit_issue_conflicts_skill.py` plus `IssueParser`/`update_frontmatter` fixture patterns from `scripts/tests/test_issue_parser.py`; cover: skill file existence, frontmatter content assertions, parentless-issue detection, Jaccard scoring, `update_frontmatter` round-trip writing `parent:`

## Scope Boundaries

- Does not create new EPICs — only assigns orphaned issues to existing open EPICs
- Does not resolve dependency links (`blocked_by`, `depends_on`) — use `/ll:map-dependencies` for those
- Does not score issues against closed or done EPICs
- Does not auto-apply assignments below the configurable `--min-score` threshold in interactive mode
- Does not modify EPIC priority, status, or any frontmatter fields beyond `relates_to:` and `## Children`

## Key Dependencies

### Files to Create
- `skills/link-epics/SKILL.md` — new skill

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

**Test token checklist for `test_link_epics_skill.py`** (modeled on `test_audit_issue_conflicts_skill.py`):
- `SKILL_FILE = PROJECT_ROOT / "skills" / "link-epics" / "SKILL.md"` (`PROJECT_ROOT = Path(__file__).parent.parent.parent`)
- Class `TestLinkEpicsSkillExists`; each method re-asserts `SKILL_FILE.exists()`
- Content tokens to assert: `"--auto"`, `"--min-score"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`, `"parent:"`, `"{{config.issues.base_dir}}"` (or equivalent config template expression)
- `update_frontmatter` round-trip test: write `parent: EPIC-NNN` to a tmp file and assert it reads back correctly via `parse_frontmatter`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Ensure `skills/link-epics/SKILL.md` frontmatter includes both `name: link-epics` **and** `metadata.short-description:` — `TestRealSkillsIntegrationGuard` in `test_adapt_skills_for_codex.py` checks these fields for every skill file including `disable-model-invocation: true` skills; CI fails if either is absent
2. Note: `ll-verify-docs` will exit 1 after this issue lands (actual skill count increments from 30→31, documented counts unchanged) — expected; ENH-1730 handles the count bump

## Acceptance Criteria

- `/ll:link-epics` is invokable and lists orphaned open issues
- Jaccard scoring correctly buckets proposals into HIGH/MEDIUM/LOW tiers
- `--auto` applies only HIGH-tier (or above `--min-score`) without prompting
- Round-trip integrity: accepted assignment writes `parent: EPIC-NNN` to child frontmatter AND appends child ID to epic's `relates_to:` and `## Children`
- `scripts/tests/test_link_epics_skill.py` passes with `python -m pytest scripts/tests/test_link_epics_skill.py`

## Session Log
- `/ll:wire-issue` - 2026-05-26T22:06:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f281563-3617-4295-8dad-fb6c9082c9d2.jsonl`
- `/ll:refine-issue` - 2026-05-26T22:00:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22e83cb1-28b3-4cdf-bb09-7c4511b532a6.jsonl`
- `/ll:issue-size-review` - 2026-05-26T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2480abd-758c-47ca-aa87-454ae8a76200.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
