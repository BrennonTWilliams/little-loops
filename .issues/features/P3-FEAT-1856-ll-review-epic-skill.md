---
id: FEAT-1856
type: FEAT
priority: P3
status: done
captured_at: '2026-06-01T17:35:32Z'
completed_at: '2026-06-01T20:50:44Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- FEAT-1855
- FEAT-1737
parent: EPIC-1864
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1856: `/ll:review-epic` skill — stalled-children and scope-drift audit

## Summary

Add a `/ll:review-epic <EPIC-ID>` skill that audits an EPIC's children for (1) stalled status (open/blocked for N days with no activity), (2) scope drift (child summaries that no longer match the EPIC's stated scope), (3) missing coverage (EPIC scope mentions areas with no child issue), and (4) closure readiness (all children done → recommend marking EPIC done). Output is a structured health report plus actionable suggestions, mirroring the shape of `/ll:review-sprint`.

## Current Behavior

`/ll:confidence-check` validates that an EPIC *has* children. `/ll:link-epics` assigns parentless issues to EPICs. No skill audits whether existing children are *still aligned* with the EPIC goal or whether the EPIC has gone stale. `ll-issues epic-progress` (FEAT-1855) will report progress numerically but does not interpret or recommend.

## Expected Behavior

```
$ /ll:review-epic EPIC-1773

## EPIC-1773 Health Report

**Progress**: 8/12 done (67%) — see FEAT-1855 for raw aggregates

### Stalled children
- ENH-1641 — open 24 days, no commits referencing ID, no session-log entries since 2026-05-08
  Recommendation: defer or close

### Scope drift
- FEAT-1820 mentions "Codex CLI parity" but EPIC scope is "FSM loop simplification"
  Recommendation: reparent to EPIC-1713 (Codex parity) or detach

### Missing coverage
- EPIC scope mentions "shared fragments audit" — no child issue covers fragments/
  Recommendation: capture a new child issue

### Closure recommendation
- Not ready (4 active children)
```

Skill writes nothing without confirmation; user can run `/ll:capture-issue --parent EPIC-1773` or `/ll:manage-issue defer ENH-1641` from the recommendations.

## Motivation

EPICs accumulate children over time, and child scope drifts as the EPIC matures. Without a periodic audit, EPICs become misleading (claiming to track work they no longer cover, or missing work they should). `/ll:review-sprint` provides this for ephemeral sprints — EPICs need the long-running-container equivalent.

This pairs with FEAT-1855 (raw progress aggregation): 1855 surfaces *what* the numbers are, 1856 interprets *what to do about them*.

## Proposed Solution

Skill-only implementation (no new CLI):

1. **Load EPIC + resolve children** — call `ll-issues list --type EPIC --json` to get the EPIC record; enumerate children via the same union of `relates_to:` (forward) and `parent:` (backward) used by `compute_epic_progress()` in `scripts/little_loops/issue_progress.py`. Run `ll-issues list --status open,in_progress,blocked,done,cancelled,deferred --json` as the all-statuses dataset.
2. **Compute progress aggregates** — invoke `ll-issues epic-progress EPIC-NNN` (the `cmd_epic_progress()` CLI wrapper); parse JSON output for `by_status`, `percent_done`, `oldest_open_age_days`.
3. **Stall detection** (non-LLM) — for each `open`/`in_progress`/`blocked` child, use `_parse_updated_date(content, file_path)` from `scripts/little_loops/cli/issues/search.py` to get the last session-log timestamp (falling back to file mtime). Flag children with no activity in > `stale_days` days. Note: no existing `git log --grep=ISSUE-ID` utility exists in the codebase; the skill can run `git log --oneline --grep=CHILD-ID -- .` via Bash if implementing a git-activity signal, but this is optional and session-log recency is sufficient as a primary signal.
4. **Scope drift** (LLM pass) — read the EPIC's `## Summary` and each child's `## Summary`. Use a scoring-table-as-classifier (model from `skills/confidence-check/SKILL.md` Phase 2 criterion tables) to classify each child as `on-theme` / `tangential` / `off-theme` with rationale. Return only tangential/off-theme results.
5. **Missing coverage** (LLM pass) — parse the EPIC summary for named sub-areas or goals; compare against child summaries; flag sub-areas with no covering child.
6. **Closure check** (pure) — if all children have `status: done`, recommend `ll-issues set-status EPIC-NNN done`.
7. **Render report** — structured Markdown per the output shape in `## Expected Behavior`; include a `## Recommendations` section that maps each finding to a concrete runnable command.

Model the skill on `commands/review-sprint.md` (6-phase structure: Load → Analyze → Recommend → Interactive → Apply) and follow skill frontmatter conventions from `skills/link-epics/SKILL.md` and `skills/confidence-check/SKILL.md`.

## Integration Map

### Files to Create
- `skills/review-epic/SKILL.md` (new skill, ~300 lines of instruction prose)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-epic/agents/openai.yaml` — Codex adapter; generated automatically by running `ll-adapt-skills-for-codex --apply` after SKILL.md is created; required by `TestRealSkillsIntegrationGuard.test_all_real_skills_have_openai_yaml`
- `skills/ll-review-epic/SKILL.md` — Codex bridge stub (parallel to `skills/ll-review-sprint/SKILL.md`); also generated by `ll-adapt-skills-for-codex --apply`
- `scripts/tests/test_feat1856_doc_wiring.py` — per-issue doc-wiring test convention (verify SKILL.md exists, `commands/help.md` mentions `review-epic`, `COMMANDS.md` has entry, `.claude/CLAUDE.md` mentions `review-epic`, `config-schema.json` has `commands.review_epic`)

### Files to Modify
- `config-schema.json` — add `commands.review_epic` object with `stale_days` (integer, default 14, minimum 1) and `enable_scope_drift_check` (boolean, default true); follow the `commands.confidence_gate` nested-object shape at ~line 408
- `commands/help.md` — add `/ll:review-epic` to the listing
- `.claude/CLAUDE.md` — Commands & Skills section listing

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — add `### /ll:review-epic` section under Sprint Management (or new Epic Management section) and a row in the `## Quick Reference` table adjacent to `review-sprint`
- `CONTRIBUTING.md` — increment skill count `31 skill definitions` → `32 skill definitions`; add `review-epic/` directory entry alphabetically between `rename-loop/` and `update/`
- `README.md` — increment skill count (currently `59 skills` → `60 skills` at line 161)
- `docs/ARCHITECTURE.md` — update skill count references (×2: Mermaid diagram and tree comment)

### Dependent Files (Callers/Importers)

**EPIC resolution & aggregation** (FEAT-1855 dependency):
- `scripts/little_loops/issue_progress.py` — `compute_epic_progress(epic_id, all_issues)` enumerates children via union of forward (`relates_to:`) and backward (`parent:`) links; `EpicProgress` dataclass holds `children`, `by_status`, `percent_done`, `oldest_open`; `_issue_age_days(issue)` returns days since `captured_at` / `discovered_date` / mtime
- `scripts/little_loops/cli/issues/epic_progress.py` — `cmd_epic_progress()` CLI wrapper; call pattern: `find_issues(config, status_filter=_ALL_STATUSES)` then `compute_epic_progress()`

**Issue model**:
- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass (fields: `issue_id`, `title`, `status`, `parent`, `relates_to`, `captured_at`, `session_commands`, `session_command_counts`, `path`); `find_issues(config, status_filter=...)` bulk loader; `IssueParser.parse_file(path)` single-file parser

**Last-activity staleness**:
- `scripts/little_loops/cli/issues/search.py` — `_parse_updated_date(content, file_path)` extracts the last timestamp from `## Session Log` entries; falls back to `file_path.stat().st_mtime`; this is the correct function for stall recency — use `_parse_updated_date`, not `captured_at`, to detect stalled children
- `scripts/little_loops/cli/issues/search.py` — `_parse_discovered_date(content, file_path)` parses `captured_at` ISO datetime → `discovered_date` → mtime; used inside `_issue_age_days()`

**Session log**:
- `scripts/little_loops/session_log.py` — `parse_session_log(content)` returns distinct command names from `## Session Log`; `count_session_commands(content)` returns per-command counts; `append_session_log_entry()` writes the standard log line format

### Similar Patterns
- `commands/review-sprint.md` — the actual 6-phase review workflow (Phase 1 Load, Phase 2 Backlog Scan, Phase 3 Analysis [3a–3d], Phase 4 Recommendations, Phase 5 Interactive Approval, Phase 6 Apply); the bridge stub at `skills/ll-review-sprint/SKILL.md` is Codex-only frontmatter, not implementation
- `skills/confidence-check/SKILL.md` — scoring-table-as-classifier pattern (`| Finding | Score |` table per criterion) and EPIC-branch in Phase 2 Criterion 3
- `skills/link-epics/SKILL.md` — skill frontmatter pattern: `name`, `description`, `model: sonnet`, `allowed-tools`, `metadata.short-description`

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py` — `TestRealSkillsIntegrationGuard` has 3 auto-discovering tests that **will fail** unless SKILL.md has `name: review-epic`, `metadata.short-description: ≤80 chars`, and `agents/openai.yaml` exists; note: the issue's reference to `test_skills_metadata.py` is incorrect — that file does not exist as standalone; this is the actual frontmatter validation coverage [update — will break without proper frontmatter]
- `scripts/tests/test_config_schema.py` — add `test_commands_review_epic_in_schema` (follow `test_commands_recursive_refine_in_schema` pattern at lines 75–96; assert `stale_days` integer minimum=1 default=14 and `enable_scope_drift_check` boolean default=true) [new test to write]
- `scripts/tests/test_issue_progress.py` — `_make_issue()` fixture builder for any Python-level stall/progress logic; `TestComputeEpicProgress` (15 existing tests pass as-is; stall-detection logic lives in SKILL.md prose, so no new Python tests needed here unless a stall utility is extracted to Python)
- `scripts/tests/test_feat1447_doc_wiring.py` and `scripts/tests/test_feat1287_doc_wiring.py` — both contain hardcoded skill count assertions (`"31 skills"`, `"31 skill definitions"`) that **will fail** once skill count docs are updated; update these alongside the doc edits [update — will break when CONTRIBUTING/README/ARCHITECTURE counts are updated]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1856_doc_wiring.py` — new file to create (see Files to Create above)
- Live-LLM eval (out of scope for capture; track separately)

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — structural model for `docs/guides/EPIC_GUIDE.md` (if created alongside this skill)

### Configuration
- `config-schema.json` → `commands.review_epic.stale_days` (integer, default 14, minimum 1)
- `config-schema.json` → `commands.review_epic.enable_scope_drift_check` (boolean, default true)
- Access in skill via `{{config.commands.review_epic.stale_days}}` and `{{config.commands.review_epic.enable_scope_drift_check}}`

## Implementation Steps

1. **Scaffold skill** — create `skills/review-epic/SKILL.md`; use frontmatter from `skills/link-epics/SKILL.md` as template (fields: `name: review-epic`, `description`, `model: sonnet`, `allowed-tools`, `metadata.short-description`); add `allowed-tools: [Read, Glob, Grep, Bash(ll-issues:*), Bash(git:*), AskUserQuestion]`.
2. **Phase 1 — Load + children resolution** — run `ll-issues list --status open,in_progress,blocked,done,cancelled,deferred --json`; call `ll-issues epic-progress EPIC-NNN` for progress aggregates; enumerate children via union of forward `relates_to:` and backward `parent:` (same logic as `compute_epic_progress()` in `scripts/little_loops/issue_progress.py`).
3. **Phase 2 — Stall detection** (non-LLM) — for open/blocked children read each file, extract the last `## Session Log` timestamp using the pattern from `_parse_updated_date()` in `scripts/little_loops/cli/issues/search.py`; compute days-since-activity; flag children exceeding `{{config.commands.review_epic.stale_days}}` (default 14).
4. **Phase 3 — Scope drift** (LLM pass) — compare EPIC `## Summary` against each child's `## Summary` using a `| Finding | Classification |` scoring table (model from `skills/confidence-check/SKILL.md` Criterion 3); emit `on-theme` / `tangential` / `off-theme` with rationale.
5. **Phase 4 — Missing coverage** (LLM pass) — parse EPIC summary for named sub-areas; cross-reference against child summaries; flag uncovered sub-areas.
6. **Phase 5 — Closure check** — if all children `status: done`, emit `ll-issues set-status EPIC-NNN done` as the recommendation.
7. **Phase 6 — Report + recommendations** — render the Markdown health report (see `## Expected Behavior` for the exact block structure); add a `## Recommendations` section mapping each finding to a concrete runnable command; follow the output banner pattern from `commands/review-sprint.md` (` === SPRINT REVIEW ===` → `=== EPIC HEALTH REPORT ===`).
8. **Wire docs** — add `/ll:review-epic` to `commands/help.md` and the Commands & Skills section in `.claude/CLAUDE.md`.
9. **Configuration** — add `commands.review_epic` object to `config-schema.json` with `stale_days` (integer, default 14, minimum 1) and `enable_scope_drift_check` (boolean, default true); follow the `commands.confidence_gate` nested-object shape (~line 408); add a sentinel test in `scripts/tests/test_config_schema.py` following `test_commands_recursive_refine_in_schema`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/reference/COMMANDS.md` — add `### /ll:review-epic` section under Sprint Management (or new Epic Management section) with description and usage; add row to `## Quick Reference` table adjacent to `| review-sprint |`
11. Update `CONTRIBUTING.md` — increment `31 skill definitions` → `32 skill definitions`; add `│   ├── review-epic/` entry alphabetically between `rename-loop/` and `update/`
12. Update `README.md` and `docs/ARCHITECTURE.md` — increment skill count in all three locations (README line 161; ARCHITECTURE Mermaid and tree entries)
13. Run `ll-adapt-skills-for-codex --apply` — generates `skills/review-epic/agents/openai.yaml` and `skills/ll-review-epic/SKILL.md`; required before `test_all_real_skills_have_openai_yaml` will pass
14. Create `scripts/tests/test_feat1856_doc_wiring.py` — verify skill file exists, help.md mentions `review-epic`, COMMANDS.md has entry, CLAUDE.md mentions `review-epic`, config-schema has `commands.review_epic`
15. Update `scripts/tests/test_feat1447_doc_wiring.py` and `test_feat1287_doc_wiring.py` — fix hardcoded `"31 skills"` / `"31 skill definitions"` strings to match updated counts

## Impact

- **Priority**: P3 — Quality-of-life for EPIC maintainers; depends on FEAT-1855 landing first.
- **Effort**: Medium — Skill + 2 LLM passes + 1 non-LLM pass; reuses existing resolution and aggregation.
- **Risk**: Low — Read-only audit, never mutates issues.
- **Breaking Change**: No

## Use Case

Before a quarterly planning session the user runs `/ll:review-epic` on each of the 13 active EPICs. The skill flags EPIC-1713 as having drifted (4 children now belong under a sibling EPIC) and EPIC-1622 as ready to close (all children done). The user re-parents and closes accordingly in ~10 minutes instead of opening 50+ child files.

## Acceptance Criteria

- [ ] `/ll:review-epic EPIC-NNN` produces a Markdown report with progress, stalled children, scope-drift findings, missing-coverage findings, and closure recommendation.
- [ ] Stalled detection uses configurable threshold (`epics.stale_days`, default 14).
- [ ] Scope-drift classification returns `on-theme` / `tangential` / `off-theme` with rationale per child.
- [ ] Skill writes nothing without user invocation of a follow-up command (audit-only).
- [ ] Each finding maps to a concrete runnable command in the recommendations list.
- [ ] Empty EPIC (no children) emits a clear message, no LLM passes, exit clean.
- [ ] EPIC not found exits with a clear error.
- [ ] Documented in `/ll:help`, CLAUDE.md skills section, and a guide page.

## API/Interface

Skill invocation:

```bash
/ll:review-epic EPIC-NNN
/ll:review-epic EPIC-NNN --skip-drift   # non-LLM mode (fast, structural only)
```

No Python API.

## Related Key Documentation

- `commands/review-sprint.md` — primary model: 6-phase audit-and-recommend workflow, output banner format, interactive approval pattern
- `skills/confidence-check/SKILL.md` — scoring-table-as-classifier pattern (Phase 2 Criterion 3 EPIC branch); frontmatter conventions
- `skills/link-epics/SKILL.md` — skill frontmatter template; EPIC child resolution in prose
- `scripts/little_loops/issue_progress.py` — `compute_epic_progress()`, `EpicProgress`, `_issue_age_days()` — FEAT-1855 implementation
- `scripts/little_loops/cli/issues/search.py` — `_parse_updated_date()`, `_parse_discovered_date()` — staleness timestamp helpers
- `docs/guides/SPRINT_GUIDE.md` — structural model for a potential `docs/guides/EPIC_GUIDE.md`

## Labels

`enhancement`, `epics`, `skill`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-01T20:33:24 - `1c02ebee-da6d-4506-ae06-aeb102a1c9df.jsonl`
- `/ll:confidence-check` - 2026-06-01T21:00:00 - `aad0ee9c-8434-4485-8146-3413341c2be4.jsonl`
- `/ll:wire-issue` - 2026-06-01T20:29:33 - `585d1302-ddc0-4253-8714-8796ad7687e8.jsonl`
- `/ll:refine-issue` - 2026-06-01T20:23:38 - `77ea0545-6144-4266-a5c4-0bfff8650779.jsonl`
- `/ll:format-issue` - 2026-06-01T17:45:19 - `f9321137-9371-4510-85ad-95b0940c3c6f.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
