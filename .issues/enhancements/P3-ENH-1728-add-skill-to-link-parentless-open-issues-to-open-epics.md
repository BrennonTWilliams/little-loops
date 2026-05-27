---
id: ENH-1728
title: Add skill to link parentless open issues to open epics
type: ENH
status: done
priority: P3
captured_at: '2026-05-26T21:00:19Z'
discovered_date: 2026-05-26
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
implementation_order_risk: true
size: Very Large
---

# ENH-1728: Add skill to link parentless open issues to open epics

## Summary

Add a new skill (e.g., `link-epics` or `parent-issues`) that scans all open issues lacking a `parent:` frontmatter field, compares them against open epics by semantic title/description similarity, and proposes or applies `parent:` assignments — writing the child ID back into the epic's `relates_to:` list and `## Children` section.

## Current Behavior

There is no dedicated skill for this. The closest options are:
- `/ll:map-dependencies` — handles dependency links (`blocked_by`, `depends_on`) but is not focused on epic parenting
- `/ll:align-issues` — validates issues against documents, not epic relationships
- Manual `--parent EPIC-NNN` flag on `/ll:capture-issue` — works only at creation time, not retroactively

Open issues accumulate without a `parent:` field, making epic rollups incomplete and sprint planning noisier.

## Expected Behavior

Running the skill (e.g., `/ll:link-epics`) should:
1. Collect all open issues (BUG/FEAT/ENH) with no `parent:` frontmatter field
2. Collect all open EPICs
3. For each orphaned issue, score similarity against each EPIC (title + description overlap)
4. Present proposed parent assignments for user approval (interactive mode) or apply automatically with a `--auto` flag
5. For each accepted assignment: write `parent: EPIC-NNN` into the child issue's frontmatter, append the child ID to the epic's `relates_to:` list, and add a bullet to the epic's `## Children` section

## Scope Boundaries

- Does not create new EPICs — only assigns orphaned issues to existing open EPICs
- Does not resolve dependency links (`blocked_by`, `depends_on`) — use `/ll:map-dependencies` for those
- Does not score issues against closed or done EPICs
- Does not auto-apply assignments below the configurable `--min-score` threshold in interactive mode
- Does not modify EPIC priority, status, or any frontmatter fields beyond `relates_to:` and `## Children`

## Success Metrics

- Zero orphaned open issues (missing `parent:`) remain after a full `--auto` run, given at least one matching open EPIC exists
- High-confidence proposals (score ≥ configurable `--min-score`) produce no false positives on known (issue, epic) pairs in this repo
- Round-trip integrity: each accepted assignment writes `parent: EPIC-NNN` to the child frontmatter AND appends the child ID to the epic's `relates_to:` list and `## Children` section

## Motivation

Epic rollup is only useful if child issues are consistently linked. Without automation, new issues captured via `/ll:capture-issue` (without `--parent`) silently accumulate as orphans, reducing the value of epic-level planning and reporting.

## Proposed Solution

New skill `skills/link-epics/SKILL.md`. Core flow:

1. Three separate `ll-issues list --status open --type {BUG,FEAT,ENH} --json` calls — `--type` is single-value only; for each returned `path`, call `parse_frontmatter()` (`scripts/little_loops/frontmatter.py`) and filter to those where the `parent` key is absent or None
2. `ll-issues list --status open --type EPIC --json` → collect open epics (fields: `id`, `title`, `path`)
3. Score each (orphan, epic) pair using existing `calculate_word_overlap(extract_words(title_a), extract_words(title_b))` from `scripts/little_loops/text_utils.py` — Jaccard on significant words; HIGH ≥ 0.7 / MEDIUM ≥ 0.4 / LOW < 0.4
4. Group proposals by confidence tier (high / medium / low)
5. Present for approval via `AskUserQuestion` (multiSelect) or skip prompt if `--auto`
6. Apply accepted assignments using `Edit` on both child and epic files; stage via `git add`

## Integration Map

### Files to Modify
- `skills/link-epics/SKILL.md` — new skill (create)
- `.claude/CLAUDE.md` — add entry under Issue Refinement command list
- `skills/capture-issue/SKILL.md` — add `link-epics` as follow-up step in `## Integration` section
- `skills/issue-workflow/SKILL.md` — add `link-epics` to `### 2. Refinement Phase` sequence and `## Related Skills` table
- `commands/help.md` — add `link-epics` stanza to `ISSUE REFINEMENT` block (static file, not auto-discovered by `/ll:help`)
- `docs/reference/CLI.md` — add `link-epics` invocation example (already in Documentation section)
- `docs/reference/COMMANDS.md` — add `### /ll:link-epics` section, Quick Reference table row, and `--auto` flag table entry
- `README.md` — increment `30 skills` → `31 skills` (enforced by `ll-verify-docs` CI gate via `doc_counts.py`)
- `CONTRIBUTING.md` — increment `30 skill definitions` → `31` in directory tree
- `docs/ARCHITECTURE.md` — increment `SKL[Skills<br/>30 composable skills]` → `31` (Mermaid) and `30 skill definitions` → `31` (directory tree)
- `.claude-plugin/plugin.json` — no per-skill entry needed; `"skills": ["./skills"]` directory scan auto-discovers new subdirs automatically

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — may reference `link-epics` as a follow-up step
- `scripts/little_loops/text_utils.py` — `extract_words()` and `calculate_word_overlap()` (Jaccard) already implemented; import, do not re-implement
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` for writing `parent:` into child frontmatter; `parse_frontmatter()` for reading each file's frontmatter to check `parent:` field absence
- `scripts/little_loops/issue_parser.py` — `IssueInfo.parent` (str|None) and `IssueInfo.relates_to` (list[str]) dataclass fields; `IssueParser.parse_file()` for structured reads
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` handles `ll-issues list --type EPIC --status open --json`

### Similar Patterns
- `skills/capture-issue/SKILL.md` Phase 4c ("Wire Parent EPIC") — canonical `relates_to:` + `## Children` write pattern with 3 cases (absent/empty/populated list); reuse this exact Edit logic for the apply step
- `skills/map-dependencies/SKILL.md` — `AskUserQuestion` apply-all / select-individually / skip-all proposal flow; HIGH ≥ 0.7 / MEDIUM ≥ 0.4 confidence tier conventions
- `skills/rename-loop/SKILL.md` — skill SKILL.md frontmatter structure reference (`name:`, `description:`, `disable-model-invocation: true`, `argument-hint:`, `arguments:`, `allowed-tools:`)
- `scripts/little_loops/issue_discovery/search.py` `find_existing_issue()` — multi-pass matching; Jaccard > 0.7 duplicate threshold; scoring tier conventions
- `scripts/little_loops/issue_discovery/matching.py` `FindingMatch` — dataclass pattern with `should_skip`/`should_update`/`should_create` properties as model for tiered proposal objects

### Tests
- `scripts/tests/test_issue_parser.py` — fixture pattern for creating issues with/without `parent:` frontmatter field
- `scripts/tests/test_issues_cli.py` — fixture pattern for `ll-issues list --type --status --json` output validation
- `scripts/tests/test_text_utils.py` — `extract_words`/`calculate_word_overlap` already fully tested; no update needed
- `scripts/tests/test_frontmatter.py` — `update_frontmatter` (including writing new scalar keys) already tested; no update needed
- No dedicated test file yet; create `scripts/tests/test_link_epics_skill.py` (naming convention: `test_<skill-name-underscored>_skill.py`; model after `test_audit_issue_conflicts_skill.py` + `test_issue_parser.py` fixture patterns); cover: skill file existence, frontmatter content assertions, parentless-issue detection, Jaccard scoring, `update_frontmatter` round-trip writing `parent:`

_Wiring pass added by `/ll:wire-issue`:_
- Correct test filename from `test_link_epics.py` → `test_link_epics_skill.py` to match skill-test naming convention (`test_<name>_skill.py`)

### Documentation
- `.claude/CLAUDE.md` — Issue Refinement section (covered in "Files to Modify" above)
- `docs/reference/CLI.md` — add `link-epics` skill invocation example (covered in "Files to Modify" above)
- `docs/reference/COMMANDS.md` — add `### /ll:link-epics` section + Quick Reference row + `--auto` flag table entry (covered in "Files to Modify" above)
- `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` — skill count increment from 30 → 31 (covered in "Files to Modify" above; enforced by `ll-verify-docs` CI gate)

### Configuration
- N/A — no new config keys required

## Implementation Steps

1. Create `skills/link-epics/SKILL.md` with frontmatter: `name: link-epics`, `disable-model-invocation: true`, `model: sonnet`, `argument-hint: "[--auto] [--min-score 0.5]"`, `allowed-tools` including `AskUserQuestion`, `Edit`, `Bash(ll-issues:*)`, `Bash(git:*)`, `Read` (see `skills/rename-loop/SKILL.md` for reference frontmatter structure)
2. Implement orphan discovery: run `ll-issues list --status open --type {BUG,FEAT,ENH} --json` (three calls); for each returned `path` call `parse_frontmatter()` (`scripts/little_loops/frontmatter.py`) and keep those where `parent` key is absent or None
3. Implement scoring: use `extract_words()` and `calculate_word_overlap()` from `scripts/little_loops/text_utils.py` (Jaccard on title + summary words); bucket into HIGH (≥ 0.7) / MEDIUM (≥ 0.4) / LOW (< 0.4) confidence tiers
4. Implement proposal flow: `AskUserQuestion` with `multiSelect: true` presenting each proposed (orphan → epic) pair with confidence label; in `--auto` mode, apply only HIGH-tier (or all tiers at or above `--min-score`) without prompting
5. Implement apply step: for the child issue write `parent: EPIC-NNN` via `update_frontmatter(content, {"parent": epic_id})` (`scripts/little_loops/frontmatter.py`); for the epic reuse the Phase 4c Edit logic from `skills/capture-issue/SKILL.md` (3 cases for `relates_to:`, `## Children` insertion before `## Status`); stage both with `git add`
6. Add `link-epics`^ entry to Issue Refinement list in `.claude/CLAUDE.md`; no `plugin.json` change needed
7. Write `scripts/tests/test_link_epics_skill.py` (not `test_link_epics.py`) using skill-test pattern from `scripts/tests/test_audit_issue_conflicts_skill.py` plus `IssueParser`/`update_frontmatter` fixture patterns from `scripts/tests/test_issue_parser.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `skills/capture-issue/SKILL.md` — add `link-epics` as a follow-up in `## Integration` section ("After capturing issues, run `/ll:link-epics` to assign parentless issues to epics")
9. Update `skills/issue-workflow/SKILL.md` — add `link-epics` to `### 2. Refinement Phase` command sequence and `## Related Skills` table
10. Update `commands/help.md` — add `link-epics` stanza to `ISSUE REFINEMENT` block (static file; not auto-discovered by `/ll:help`)
11. Update `docs/reference/COMMANDS.md` — add `### /ll:link-epics` section with `--auto`/`--min-score` flags, Quick Reference table row, and append `link-epics` to the `--auto`-supported skills row in the Flag Conventions table
12. Increment skill counts in count-tracking docs (all enforced by `ll-verify-docs` CI gate via `scripts/little_loops/doc_counts.py`):
    - `README.md`: `30 skills` → `31 skills`
    - `CONTRIBUTING.md`: `30 skill definitions` → `31`
    - `docs/ARCHITECTURE.md`: `SKL[Skills<br/>30 composable skills]` → `31` (Mermaid) AND `30 skill definitions` → `31` (directory tree)

## Impact

- **Priority**: P3 — quality-of-life for issue hygiene; no blocking use cases
- **Effort**: Small/Medium — ~200-300 lines of skill YAML/markdown; reuses capture-issue wiring logic
- **Risk**: Low — read-heavy with targeted `Edit` writes; no destructive operations
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`skill`, `issue-management`, `epics`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-26_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Wide wiring surface**: 6 doc/skill wiring sites beyond the primary deliverable — each is a small mechanical edit, but all must be completed consistently; `ll-verify-docs` CI gate validates the skill count increments in README/CONTRIBUTING/ARCHITECTURE
- **Tests are co-deliverables**: `scripts/tests/test_link_epics_skill.py` doesn't exist yet — implement test file alongside the skill to validate orphan detection, Jaccard scoring, and write-back round-trip

## Session Log
- `/ll:issue-size-review` - 2026-05-26T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2480abd-758c-47ca-aa87-454ae8a76200.jsonl`
- `/ll:confidence-check` - 2026-05-26T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e7f375b-aa7e-40e4-a08a-dc68993ce43d.jsonl`
- `/ll:wire-issue` - 2026-05-26T21:49:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f1d0a8b-d785-46af-9c9e-524304f1c1a9.jsonl`
- `/ll:refine-issue` - 2026-05-26T21:44:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06dde0bf-4d88-452e-bb84-dad578cf427a.jsonl`
- `/ll:format-issue` - 2026-05-26T21:02:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ed30089-38b6-4a6b-aabb-647e6b346ac3.jsonl`

- `/ll:capture-issue` - 2026-05-26T21:00:19Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b930ee27-2d55-47e0-828a-6533b49e3b89.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-26
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1729: Add link-epics skill: core implementation, CLAUDE.md entry, and tests (Steps 1–7)
- ENH-1730: Add link-epics skill: wiring and documentation updates (Steps 8–12)

---

## Status

**Done** | Created: 2026-05-26 | Priority: P3
