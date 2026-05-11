---
id: ENH-1421
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T21:02:24Z

decision_needed: false
missing_artifacts: false
confidence_score: 100
outcome_confidence: 81
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1390
---

# ENH-1421: Decouple Issue Status — Commands, Skills, and Documentation

## Summary

Update all 13 command files, 3 skill files, and 4 documentation files that reference `completed/` or `deferred/` directory patterns. The CRITICAL changes are `manage-release.md` (release detection strategy) and `manage-issue/SKILL.md` (git mv → frontmatter update). Can run in parallel with ENH-1418 and ENH-1419 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Current Behavior

All command files, skill files, and documentation reference `completed/` and `deferred/` directory paths to determine issue status. For example: `manage-release.md` uses `git log --diff-filter=A -- .issues/completed/` for release detection; `manage-issue/SKILL.md` instructs `git mv` to move issues into `completed/`; `align-issues.md`, `create-sprint.md`, and `sync-issues.md` all use `find -not -path "*/completed/*" -not -path "*/deferred/*"` to filter active issues. After ENH-1417 lands the authoritative model will be frontmatter `status`, but these 20 files will still drive behaviour from directory location.

## Expected Behavior

All 13 command files, 3 skill files, and 4 documentation files use the frontmatter `status` field rather than directory path as the source of truth. Specifically: `manage-release.md` detects completed issues via `status: done` + `completed_at` date range; `manage-issue/SKILL.md` performs a frontmatter update (`status: done`) instead of `git mv`; all `find`-based active-issue filters use a `--status` flag or equivalent frontmatter filter. The lifecycle documented in `ISSUE_MANAGEMENT_GUIDE.md` describes status values, not directory routing.

## Motivation

Once ENH-1417 lands the frontmatter-based status data model, any remaining directory references in commands/skills create a split-brain: the data model says status is in frontmatter but the tooling still relies on directory location. This causes release detection to miss issues, lifecycle commands to issue incorrect `git mv` instructions, and docs to contradict the new model. This ENH completes the decoupling for the user-facing layer so the entire stack is consistent after ENH-1390.

## Proposed Solution

### Step 12 — 13 command files

**CRITICAL changes:**

- `commands/manage-release.md`: replace `git log --diff-filter=A … -- .issues/completed/` release detection with frontmatter-based approach — query issues where `status: done` and `completed_at` falls between the previous tag's commit timestamp and HEAD. Use full ISO timestamp comparison (not date-only) to avoid BUG-942 off-by-one failure mode.
- `commands/normalize-issues.md`: ~30 references to `completed/`/`deferred/` directories throughout checks and auto-fix scripts; replace with status-field-based approach

**Standard updates (replace directory patterns with status-field equivalents):**

- `commands/review-sprint.md` — `completed/` directory glob → frontmatter filter
- `commands/tradeoff-review-issues.md` — 6 refs to `{{config.issues.completed_dir}}/` for exclusion and as destination
- `commands/align-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"` → `--status` filter
- `commands/create-sprint.md` — excludes `/completed/` and `/deferred/` path segments; checks blocker membership in completed dir
- `commands/prioritize-issues.md` — excludes `completed/`/`deferred/` from scanning
- `commands/verify-issues.md` — `find` with `-not -path "*/completed/*"`; move instructions to `completed/`
- `commands/sync-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"`
- `commands/ready-issue.md` — checks blocker membership in `completed/` directory
- `commands/audit-architecture.md` — references to `completed/` directory in shell patterns
- `commands/refine-issue.md` — line 29 reference to `{{config.issues.completed_dir}}`
- `.claude/CLAUDE.md` — Key Directories section shows `completed/` as a routing subdirectory

### Step 13 — Skills

**CRITICAL change:**

- `skills/manage-issue/SKILL.md` (section "Move to Completed" at line 448; code block lines 452–458): replace `CRITICAL: Move to {{config.issues.completed_dir}}/` with `git mv` examples → frontmatter update instructions (`update_frontmatter(path, {"status": "done"})`)

**Standard updates:**

- `skills/init/SKILL.md` — line 148 reference to `issues.completed_dir` in config generation logic
- `skills/init/interactive.md` — lines 248, 342 references to `completed_dir` in config generation instructions

### Step 7 — Documentation

- `docs/ARCHITECTURE.md` (lines 41–59) — remove state directories from directory structure diagram; describe `status:` field lifecycle
- `docs/reference/CONFIGURATION.md` — update `completed_dir`/`deferred_dir` table entries to document new `status` field approach
- `docs/reference/API.md` — update `status` field documentation and valid values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — CRITICAL: full rewrite of lifecycle diagram and frontmatter status table; remove "Directory location determines CLI bucketing" statement (lines directly contradicting ENH-1390's goal)

### Test to Update

- `scripts/tests/test_feat1172_doc_wiring.py` — `test_completed_at_row_describes_completed_dir` asserts docs mention `completed` directory; update assertion to match new status field documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed API surface for replacement patterns:**

- `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` — `scripts/little_loops/frontmatter.py:110`. Merges into existing YAML block; used for all frontmatter writes. The `manage-issue/SKILL.md` replacement: instruct Claude to read the file, apply `status: done` + `completed_at: <ISO-Z-timestamp>` via the Edit tool (same pattern as Phase 1.6 which already writes `completed_at` at lines 436–446).
- `ll-issues list --status done` — confirmed (`cli/issues/__init__.py:124`). Scans only type directories (`bugs/`, `features/`, etc.) for issues with matching frontmatter `status`; `--status` choices (current order in file): `open | in_progress | blocked | deferred | done | cancelled | all`.
- `ll-issues list --json` (default `--status open`) — the canonical active-issue filter replacement for `find -not -path "*/completed/*" -not -path "*/deferred/*"`.

**Per-pattern replacement guidance:**

| Pattern | Location | Replacement |
|---------|----------|-------------|
| Active-issue `find` filter | align-issues, sync-issues, prioritize-issues, verify-issues, create-sprint | `ll-issues list --json` (default status: open) or `ll-issues list --format path` |
| Blocker membership check | `ready-issue.md:156,210`, `create-sprint.md` | Check `status: done` or `status: cancelled` frontmatter directly — `commands/create-sprint.md:416` already updated by ENH-1424; follow that pattern |
| Release detection | `manage-release.md:193` — `git log --diff-filter=A -- .issues/completed/` | Scan type dirs for issues where `status: done` AND `completed_at >= git log -1 --format="%aI" <PREV_TAG>`; use full ISO timestamp comparison per BUG-942 |
| `git mv` to completed/ | `manage-issue/SKILL.md:452-458` (code block; section heading at 448) | Remove `git mv`; update frontmatter `status: done` (Phase 1.6 already writes `completed_at`; Phase 5 Step 2 need only add `status: done` and drop the mv) |
| Config generation | `init/SKILL.md:148`, `init/interactive.md:248,342` | Remove `completed_dir`/`deferred_dir` from generated config block — marked deprecated in `config-schema.json:106-115` |
| `{{config.issues.completed_dir}}` template var | refine-issue.md:29, tradeoff-review-issues.md (×6), others | Replace with `status: done`/`status: deferred` filter text |

**Reference implementations (ENH-1423/ENH-1424 precedents):**
- `commands/create-sprint.md:416` — already uses `status: done` or `status: cancelled` frontmatter check for blocker; follow for `ready-issue.md`
- `scripts/little_loops/sync.py:1075` — `update_frontmatter(content, {"status": "open"})` — same call shape for `status: done`
- `scripts/little_loops/cli/issues/search.py:106` — `_load_issues_with_status()` — canonical type-dir scan with frontmatter status filter

**Scope verification (2026-05-10 refine pass):** A broad locator sweep flagged additional files containing the string `completed/` or `completed_dir` outside the listed scope (e.g., `skills/capture-issue/SKILL.md`, `skills/issue-workflow/SKILL.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/development/SPRINT_GUIDE.md`, `.claude/commands/analyze_log.md`). Many of these are `completed_at` field references or narrative past-tense uses, NOT directory-routing patterns. Before each file is closed out during implementation, run a per-file grep filtered to `'completed/\|deferred/\|completed_dir\|deferred_dir'` (excluding `completed_at`) to confirm in/out of scope. Add to scope only if a directory-routing reference is present.

**normalize-issues.md complexity note:** Sections 0a/0b/0c check the physical shape of the `completed/` directory (nested subdirs, flat layout). After ENH-1421 these should be *inverted*: warn if `completed/` or `deferred/` still exist as non-empty directories (migration artifact), rather than enforcing their internal structure. The ~30 references are concentrated in: scan exclusion (Steps 1/1b/1c), structural validation (0a/0b/0c), and documentation sections.

**Test assertion change (`test_feat1172_doc_wiring.py:38`, test method defined at line 30: `test_completed_at_row_describes_completed_dir`):**
- Current: `assert "completed" in row.lower()` — asserts `completed_at` table row references the completed *directory* path
- After ENH-1421: update to `assert "status" in row.lower() or "frontmatter" in row.lower()` — the docs should describe `completed_at` as recording a timestamp in the frontmatter status lifecycle, not a directory-move marker

## Acceptance Criteria

- `manage-release.md` uses `completed_at` date range for release detection (full ISO timestamps)
- `normalize-issues.md` uses status-field patterns, not directory patterns
- All 13 command files and 3 skill files no longer reference `completed/` or `deferred/` as active-use directories
- `ISSUE_MANAGEMENT_GUIDE.md` lifecycle section accurately describes frontmatter-based status model
- `ARCHITECTURE.md` directory structure diagram reflects type-dirs-only layout
- `test_feat1172_doc_wiring.py` passes

## Scope Boundaries

- **In scope**: `.md` command files (`commands/`), skill `.md` files (`skills/`), and documentation files (`docs/`) that reference `completed/` or `deferred/` directory patterns
- **Out of scope**: Python CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync`, etc.) — covered by ENH-1419
- **Out of scope**: Python data model, `IssueStatus` enum, frontmatter read/write utilities — covered by ENH-1417
- **Out of scope**: Discovery and lifecycle hooks (`ll-issues refine-status`) — covered by ENH-1418
- **Out of scope**: Session log format or JSONL schema changes

## Integration Map

### Files to Modify

_Frozen file list — verified by grep `completed_dir|deferred_dir|completed/|deferred/` (excluding `completed_at`) on 2026-05-10. Add to scope only if a directory-routing reference is confirmed present._

**Already done:**
- ~~`commands/sync-issues.md`~~ — confirmed 0 routing references remaining ✓

**CRITICAL changes:**
- `commands/manage-release.md` — rewrite release detection from `git log --diff-filter=A -- .issues/completed/` to frontmatter query (`status: done` + `completed_at` ISO range)
- `commands/normalize-issues.md` — ~30 references to `completed/`/`deferred/` in checks and auto-fix scripts → status-field approach
- `skills/manage-issue/SKILL.md` — replace `git mv → completed/` with frontmatter update (`status: done`); Phase 1.6 already writes `completed_at`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — rewrite lifecycle diagram and frontmatter status table; remove "Directory location determines" statement

**Standard command updates:**
- `commands/align-issues.md` — `find -not -path "*/completed/*" -not -path "*/deferred/*"` → `ll-issues list --json`
- `commands/audit-architecture.md` — `completed/` directory shell patterns
- `commands/create-sprint.md` — `/completed/`/`/deferred/` path exclusions; blocker membership check
- `commands/prioritize-issues.md` — `completed/`/`deferred/` scan exclusions
- `commands/ready-issue.md` — blocker membership check against `completed/` directory
- `commands/refine-issue.md` — line 29 `{{config.issues.completed_dir}}` reference
- `commands/review-sprint.md` — `completed/` directory glob → frontmatter filter
- `commands/tradeoff-review-issues.md` — 6 refs to `{{config.issues.completed_dir}}/`
- `commands/verify-issues.md` — `find -not -path "*/completed/*"`; move-to-completed instructions
- `.claude/CLAUDE.md` — Key Directories section lists `completed/` as routing subdirectory

**Standard skill updates:**
- `skills/init/SKILL.md` — `issues.completed_dir` config generation reference (line 148)
- `skills/init/interactive.md` — `completed_dir` in config generation instructions (lines 248, 342)
- `skills/audit-issue-conflicts/SKILL.md` — `completed_dir` as destination/filter pattern
- `skills/capture-issue/SKILL.md` — `completed_dir` directory filter in scan loop (lines 152–153, 187–188)
- `skills/capture-issue/templates.md` — `{{config.issues.completed_dir}}` path template (line 96)
- `skills/format-issue/SKILL.md` — `completed_dir` directory filter in scan loop (line 90)
- `skills/issue-size-review/SKILL.md` — `completed/` as move target (line 307)
- `skills/issue-workflow/SKILL.md` — lifecycle diagram showing completed/ as routing destination (lines 35, 37, 52, 153, 172)
- `skills/manage-issue/templates.md` — `{{config.issues.completed_dir}}` path template (line 413)
- `.claude/commands/analyze_log.md` — `{{config.issues.completed_dir}}` + `find -not -path "*/completed/*"` (lines 18, 174–175)

**Standard doc updates:**
- `docs/ARCHITECTURE.md` — remove state directories from directory structure diagram; remove `COMPLETED[.issues/completed/]` mermaid node; describe `status:` lifecycle
- `docs/reference/CONFIGURATION.md` — update `completed_dir`/`deferred_dir` table entries (already marked deprecated; update description to reference status field)
- `docs/reference/API.md` — update `get_completed_dir`/`get_deferred_dir` documentation and `status` field valid values
- `docs/development/MERGE-COORDINATOR.md` — function table row (line 161), troubleshooting item (line 493), BUG-968 note (line 559)
- `docs/guides/GETTING_STARTED.md` — file layout section (lines 74–75, 141, 144, 183)
- `docs/guides/LOOPS_GUIDE.md` — recursive-refine narrative (~lines 400, 586) describing moves to `.issues/completed/`
- `docs/reference/CLI.md` — `ll-issues path` description (line 659)
- `docs/reference/COMMANDS.md` — CLOSE verdict row (line 293)
- `docs/reference/ISSUE_TEMPLATE.md` — `completed_at` field description "Set when issue is moved to `completed/`" → "Set when issue status is updated to `done`"

**Hook:**
- ~~`hooks/scripts/issue-completion-log.sh`~~ — already updated (2026-05-10, likely ENH-1418): hook now triggers on `Write` calls that set `status: done` in frontmatter (line 26 reads `TOOL_NAME` from PostToolUse stdin); `git mv` trigger pattern is gone ✓

**Verified out of scope (narrative/historical — do not modify):**
- `docs/demo/scenarios.md` — example invocation path (narrative)
- `docs/development/TROUBLESHOOTING.md` — "Check issue moved to completed/ directory" (narrative)
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — `.issues/completed/*.md` in table (pattern example)
- `docs/guides/SPRINT_GUIDE.md` — "remove completed/invalid refs" (narrative)
- `docs/reference/EVENT-SCHEMA.md` — path-based event docs (covered by ENH-1419 Python layer)
- `skills/audit-docs/SKILL.md` — example output narrative
- `skills/confidence-check/SKILL.md` — reads completed/ to check for prior resolutions (still valid post-decoupling)
- `skills/configure/areas.md` / `skills/configure/show-output.md` — deprecated config display only
- `skills/create-eval-from-issues/SKILL.md` — narrative
- `skills/map-dependencies/SKILL.md` — config reference display
- `skills/update-docs/SKILL.md` — reads completed/, not routing to it
- `skills/wire-issue/SKILL.md` — decision context, not routing

### Dependent Files (Callers/Importers)
- N/A — command/skill `.md` files are leaf consumers, not imported by other code

### Hook Coupling (CRITICAL)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/issue-completion-log.sh` — line 26 fires on `grep -qE 'git mv .+completed/'`; when `manage-issue/SKILL.md` switches from `git mv` to `update_frontmatter`, this hook's trigger regex will silently stop detecting issue completions triggered via the skill path. Must be updated alongside the SKILL.md change to detect `status: done` frontmatter writes (e.g., trigger on `PostToolUse` for Edit/Write calls that set `status: done`) or the completion log will go dark.

### Similar Patterns
- All files using `{{config.issues.completed_dir}}` or `{{config.issues.deferred_dir}}` template vars
- Search: `grep -r "completed_dir\|deferred_dir\|completed/\|deferred/" commands/ skills/ docs/ .claude/`

### Tests

- `scripts/tests/test_enh1421_doc_wiring.py` — **written** (2026-05-10); 11 pre-implementation failures; covers:
  - `manage-release.md` contains `status: done` and `completed_at` (not `git log --diff-filter=A … .issues/completed/`)
  - `manage-issue/SKILL.md` does NOT contain `git mv … completed/`; DOES contain `status: done`
  - `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` contains `status:` but not "Directory location determines"
  - `docs/ARCHITECTURE.md` does NOT contain `COMPLETED[.issues/completed/]` mermaid node
  - `skills/init/SKILL.md` does NOT contain `completed_dir` or `deferred_dir`
  - `skills/init/interactive.md` does NOT contain `completed_dir` or `deferred_dir`
  - `test_feat1172_doc_wiring.py` uses updated `"status" in row.lower() or "frontmatter" in row.lower()` assertion
- `scripts/tests/test_feat1172_doc_wiring.py` — update `test_completed_at_row_describes_completed_dir` assertion: `assert "completed" in row.lower()` → `assert "status" in row.lower() or "frontmatter" in row.lower()`
- `scripts/tests/test_skill_expander.py:test_manage_issue_expansion_has_no_raw_tokens` (line 241) — existing test; catches leftover `{{config.issues.completed_dir}}` tokens in SKILL.md; run to verify passes after changes
- `scripts/tests/test_hooks_integration.py:TestIssueCompletionLog.test_single_quote_in_transcript_path_appends_log` (line 1056) — simulates `git mv … completed/`; update if hook moves to dual-trigger or frontmatter-only detection

### Documentation

- All four `docs/` files listed above are themselves part of this ENH's scope

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GETTING_STARTED.md` — "File Layout" section shows `completed/` and `deferred/` in directory tree with labels "← ALL completed issues" and "← parked issues"; narrative sentences describe "moves issue to `.issues/completed/`"; update directory tree and narrative to describe type-dir-based status [Agent 2 finding]
- `docs/development/MERGE-COORDINATOR.md` — `_is_lifecycle_file_move()` function table row (line 161) describes detecting renames to `completed/` or `deferred/`; troubleshooting item (line 493) says "Look for `.issues/completed/` files in `git status`"; BUG-968 note (line 559) describes `startswith` anchoring for `completed/` paths — update to reflect that the Python code itself still uses directory detection (scope note) but narrative should acknowledge the decoupling direction [Agent 2 finding]
- `docs/reference/COMMANDS.md` — line 293: `CLOSE` verdict description mentions "Close or move to `completed/`"; update to "Close (set `status: done` in frontmatter)" [Agent 2 finding]
- `docs/reference/ISSUE_TEMPLATE.md` — line 883: `completed_at` field description says "Set when issue is moved to `completed/`"; update to "Set when issue status is updated to `done`" [Agent 2 finding]
- `docs/reference/CLI.md` — line 659: `ll-issues path` description states "exits with error for `completed/` or `deferred/`" inputs; update to reflect that `ll-issues path` works against type dirs by frontmatter status [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — two references (~lines 400, 586) describe `recursive-refine` moving decomposed parents to `.issues/completed/`; update to describe frontmatter `status: done` update [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. After ENH-1417 merges, update `commands/manage-release.md` (frontmatter-based release detection with full ISO `completed_at` range)
2. Update `commands/normalize-issues.md` (~30 directory references → status-field equivalents)
3. Update remaining 11 command files and `.claude/CLAUDE.md` with standard directory→status-filter replacements
4. Update `skills/manage-issue/SKILL.md` (`git mv` → `update_frontmatter(path, {"status": "done"})`)
5. Update `skills/init/SKILL.md` and `skills/init/interactive.md`
6. Rewrite `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` lifecycle section; update remaining 3 primary doc files
7. Update `test_feat1172_doc_wiring.py` assertion and verify suite passes

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. ~~Update `hooks/scripts/issue-completion-log.sh`~~ — already done; hook already triggers on `status: done` frontmatter writes (confirmed 2026-05-10). Verify `test_hooks_integration.py:TestIssueCompletionLog.test_single_quote_in_transcript_path_appends_log` still passes.
9. Update 6 additional doc files (all `completed/` references per scope): `docs/guides/GETTING_STARTED.md` (file layout section), `docs/development/MERGE-COORDINATOR.md` (function table + troubleshooting), `docs/reference/COMMANDS.md` (CLOSE verdict row), `docs/reference/ISSUE_TEMPLATE.md` (`completed_at` field description), `docs/reference/CLI.md` (`ll-issues path` note), `docs/guides/LOOPS_GUIDE.md` (`recursive-refine` narrative)
10. Write `scripts/tests/test_enh1421_doc_wiring.py` — new doc-wiring test file covering acceptance criteria assertions (see Tests section above); run full suite and verify `test_skill_expander.py:test_manage_issue_expansion_has_no_raw_tokens` passes

## Impact

- **Priority**: P2 — Blocks ENH-1390 from being functionally complete; commands will misbehave after ENH-1417 if directory references remain
- **Effort**: Large — 20 files across commands, skills, and docs; 2 critical rewrites plus 18 standard pattern replacements
- **Risk**: Low — pure text changes to `.md` command/skill/doc files; no new logic or runtime code introduced
- **Breaking Change**: No (internal tooling only; `.md` command files are instruction text)

## Labels

`enhancement`, `refactor`, `issue-management`, `documentation`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-10 (levers applied: test file written + file list frozen)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 81/100 → HIGH CONFIDENCE

### Outcome Risk Factors
- **Wide file surface (34 confirmed sites) despite low per-site complexity**: Breadth penalty reflects volume, not difficulty — this is a wide-shallow sweep. File list is now frozen (verified grep 2026-05-10); explicit out-of-scope list in Integration Map. Use the verification grep after each step to confirm completeness.
- **Hook update requires dual-trigger**: issue-completion-log.sh must support both `git mv → completed/` (Python CLI path, until ENH-1419 lands) and `status: done` frontmatter write (skill path). Implement dual-trigger; update test_hooks_integration.py accordingly.

## Session Log
- `/ll:manage-issue enh implement ENH-1421` - 2026-05-10T21:02:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0101930c-df19-4f81-9d12-75e7fa7087b2.jsonl`
- `/ll:ready-issue` - 2026-05-10T20:47:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb1d2fd0-4726-47a2-b646-495d2a6783f5.jsonl`
- `/ll:confidence-check` (levers: test file + frozen scope) - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41b29ce-483f-4fdd-acc3-ac8cc4c756d4.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41b29ce-483f-4fdd-acc3-ac8cc4c756d4.jsonl`
- `/ll:refine-issue` - 2026-05-10T19:57:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cad08df-f749-4472-a03d-b9e1388f620c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:43:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:confidence-check` - 2026-05-10T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:wire-issue` - 2026-05-10T19:25:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed9a9795-a7b0-47a3-97cf-548f6a30ffc0.jsonl`
- `/ll:refine-issue` - 2026-05-10T19:18:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d50dc5b-3010-4dbf-b8c8-0d07870901cd.jsonl`
- `/ll:format-issue` - 2026-05-10T15:21:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/293739bc-9ebc-4dac-a29c-99529166ae17.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Completed** | Created: 2026-05-10 | Completed: 2026-05-10 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): This issue and ENH-1418 both replace git-log-based `completed/` detection with frontmatter-based status queries, but at different layers — ENH-1418 rewrites `_batch_completion_dates()` in `issue_history/parsing.py` (Python backend), while this issue updates `manage-release.md` (command layer). Before merging this issue, verify that the timestamp comparison logic in `manage-release.md` (full ISO `completed_at:` range comparison) is consistent with ENH-1418's `_batch_completion_dates()` fallback strategy. If they diverge, extract a shared utility or document the intentional difference. Related: ENH-1418.
