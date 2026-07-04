---
id: FEAT-1407
type: FEAT
priority: P2
status: done
testable: false

captured_at: '2026-05-09T00:00:00Z'
completed_at: 2026-05-10T03:57:02Z
discovered_date: '2026-05-09'
confidence_score: 100
outcome_confidence: 60
decision_needed: false
score_complexity: 0
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1389
---

# FEAT-1407: EPIC Type — Skills, Commands, and Documentation Updates

## Summary

Update all skills, commands, and documentation files that hardcode the `BUG|FEAT|ENH` type list. This child is largely independent of the code changes in FEAT-1405 and FEAT-1406 — text file updates can proceed in parallel. Covers 10 skill/command files and 7 documentation files plus `.claude/CLAUDE.md`.

## Current Behavior

All 10 skill/command files and 7 documentation files hardcode `BUG|FEAT|ENH` as the exhaustive type list. When EPIC issues exist in `.issues/epics/`, these files fail to recognize, route, or mention them — EPICs are flagged as invalid by `normalize-issues` regex patterns, absent from routing tables in `debug-loop-run` and `issue-workflow`, and undocumented in all reference material. The `capture-issue` skill has no EPIC creation flow, and `manage-issue` provides no guidance for epic-level coordination.

## Expected Behavior

After this feature:
- `skills/capture-issue/SKILL.md` and `commands/capture-issue.md` include an EPIC creation flow (produces `EPIC-NNN` in `.issues/epics/`)
- All 10 skill/command files include `EPIC` in type lists, routing tables, and regex patterns
- All 7 documentation files include EPIC wherever `BUG/FEAT/ENH` are listed
- `.claude/CLAUDE.md` issue type list includes `EPIC`
- `docs/ARCHITECTURE.md` shows epic tier in the issue hierarchy diagram
- `ll-auto` help text documents `--type BUG,FEAT,ENH` as the standard filter to skip unimplementable epics
- No skill, command, or doc file retains a hardcoded `BUG|FEAT|ENH` list that excludes EPIC

## Use Case

**Who**: A developer using little-loops after EPIC support is enabled (FEAT-1389)

**Context**: The developer creates an EPIC issue with `/ll:capture-issue` to track a large initiative. They then try to use `/ll:normalize-issues` to validate it, consult `/ll:issue-workflow` for guidance, and check the docs for EPIC type handling — but all of these fail or omit EPICs entirely.

**Goal**: Have all ll skills, commands, and documentation recognize EPIC as a valid type alongside BUG, FEAT, and ENH.

**Outcome**: EPIC issues flow through the full ll workflow without errors or missing routing — capture, normalize, format, prioritize, and documentation all work seamlessly with the EPIC type.

## Motivation

Completing EPIC type support in user-facing text is required for the FEAT-1389 initiative to be usable end-to-end:
- Without these updates, users encounter validation errors and missing routing even after the core infrastructure (FEAT-1389) lands
- All 21 file changes are mechanical text substitutions — low risk, high value, and independent of the Python code changes in FEAT-1405/FEAT-1406 (can be parallelized)
- Keeping the type list in sync across skills/docs prevents subtle bugs where a skill ignores EPICs silently

## Parent Issue

Decomposed from FEAT-1389: Add EPIC as a First-Class Issue Type

## Proposed Solution

### Step 7 — Update capture-issue and manage-issue skills/commands

- `skills/capture-issue/SKILL.md` — add EPIC creation flow (user can say "create an epic", produces `EPIC-NNN` in `.issues/epics/`)
- `commands/capture-issue.md` — same EPIC creation flow
- `skills/manage-issue/SKILL.md` — add epic management guidance (epics coordinate work, not directly implementable; direct implementation to child issues)

Also document `ll-auto` exclusion: `ll-auto` should be run with `--type BUG,FEAT,ENH` to skip epics, since epics are containers and not implementable units. Update `ll-auto` help text or default filter.

### Step 18 — Update 10 skills/commands with hardcoded type lists

Update each to include `EPIC` in all hardcoded type references:

1. `commands/normalize-issues.md` — six bash grep patterns with `(BUG|FEAT|ENH)`: scan regex, duplicate-ID grep, validation rule regex, category mapping table, misclassification heuristics table, directory structure rules
2. `skills/format-issue/SKILL.md` — Step 3 "Identify issue type from filename or ID prefix (BUG/FEAT/ENH)"; template filename note; placement rules headings "For BUGs", "For FEATs", "For ENHs" — add "For EPICs" branch
3. `skills/decide-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
4. `skills/wire-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
5. `skills/confidence-check/SKILL.md` — three type-specific scoring rubrics `**BUG**:`, `**FEAT**:`, `**ENH**:`; add `**EPIC**:` rubric covering coordination scope and child issue completeness criteria
6. `skills/issue-size-review/SKILL.md` — output template `type: [BUG|FEAT|ENH]` and dependency mention scoring rule referencing `BUG-/FEAT-/ENH-` — add EPIC
7. `skills/audit-issue-conflicts/SKILL.md` — card schema `- **Type** (\`BUG\`, \`FEAT\`, \`ENH\`)` and output templates `- **Type**: [BUG/FEAT/ENH]` — add EPIC
8. `skills/product-analyzer/SKILL.md` — `issue_type: [FEAT|ENH]` in YAML output description; add EPIC for strategic/container-level captures
9. `skills/issue-workflow/SKILL.md` — directory reference table `bugs/`, `features/`, `enhancements/`; add `epics/` row with EPIC type
10. `skills/debug-loop-run/SKILL.md` — `### 6b. Determine issue type and category` routing table; add EPIC row

### Step 19 — Update 7 documentation files

1. `docs/reference/CLI.md` — `--type` flag documented as "`BUG`, `FEAT`, `ENH`" in six places across `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-issues list/count/sequence/search/impact-effort/refine-status/anchor-sweep`; also the `Norm` column regex `^P[0-5]-(BUG|FEAT|ENH)-...`; add EPIC in all locations
2. `docs/reference/CONFIGURATION.md` — `cli.colors.type` table lists only BUG/FEAT/ENH; `label_mapping` default shows only three keys; `sync.github.label_mapping` description references `{"BUG": "bug", ...}`; add EPIC entries
3. `docs/reference/OUTPUT_STYLING.md` — type color table and `cmd_list` description list only three types; add EPIC row (color `35` / purple-magenta)
4. `docs/reference/ISSUE_TEMPLATE.md` — `### Type-Specific Sections` lists only "BUG", "FEAT", "ENH"; quality check checklists only cover those three; add EPIC section
5. `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "type: BUG, FEAT, or ENH" in `### Issue File Anatomy`; directory listing omits `epics/`; update both
6. `docs/guides/GETTING_STARTED.md` — "type: BUG, FEAT, or ENH" description; add EPIC
7. `.claude/CLAUDE.md` — `Types: \`BUG\`, \`FEAT\`, \`ENH\`` in `## Issue File Format`; add EPIC

Also update `docs/reference/API.md` — EPIC type, `epic:` field, `children:` field definitions; and `docs/ARCHITECTURE.md` — add epic tier to issue hierarchy diagram (following the JIRA Epic→Story / ADO Epic→Feature analogy).

## Implementation Steps

1. Update `capture-issue` and `manage-issue` skills/commands with EPIC creation flow and epic coordination guidance (Step 7)
2. Update skills/commands with hardcoded `BUG|FEAT|ENH` type references — the original 10 (normalize-issues, format-issue, decide-issue, wire-issue, confidence-check, issue-size-review, audit-issue-conflicts, product-analyzer, issue-workflow, debug-loop-run) plus additional files found by research: `skills/audit-loop-run/SKILL.md`, `skills/format-issue/templates.md`, `commands/refine-issue.md`, `commands/tradeoff-review-issues.md`, `commands/open-pr.md`, `commands/manage-release.md`, `commands/create-sprint.md`, `commands/scan-product.md`; also add `commands/audit-architecture.md`, `commands/sync-issues.md`, `commands/scan-codebase.md`, `skills/analyze-history/SKILL.md`, `skills/configure/show-output.md` (Step 18 + wiring additions)
3. Update documentation files — the original 7 plus `docs/guides/SPRINT_GUIDE.md` — plus `API.md`, `ARCHITECTURE.md`, and `.claude/CLAUDE.md`; also add `CONTRIBUTING.md`, `docs/development/TROUBLESHOOTING.md`, `docs/guides/EXAMPLES_MINING_GUIDE.md` (Step 19 + wiring additions)
4. Update templates and config — add `epics` category to all 9 project-type templates (`templates/generic.json` and 8 language templates); update `_meta.description` in `templates/bug-sections.json`, `templates/feat-sections.json`, `templates/enh-sections.json`; update `config-schema.json` categories description at line 74 (Wiring Phase)
5. Add `scripts/tests/test_feat1407_doc_wiring.py` — verify key skill/command `.md` files contain `EPIC` (follow pattern of existing `test_*_doc_wiring.py` files) (Wiring Phase)
6. Verify: grep for remaining `BUG|FEAT|ENH` hardcoded patterns across all updated files to confirm no missed occurrences

## Acceptance Criteria

- `skills/capture-issue/SKILL.md` includes EPIC creation flow
- All 10 skill/command files include EPIC in type lists/routing tables
- All 7 documentation files include EPIC where BUG/FEAT/ENH are listed
- `.claude/CLAUDE.md` issue type list includes EPIC
- `docs/ARCHITECTURE.md` shows epic tier in issue hierarchy
- No skill, command, or doc file retains a hardcoded `BUG|FEAT|ENH` list that excludes EPIC

## API/Interface

N/A — No public Python API changes. All changes are to Markdown skill/command/documentation files. The `ll-issues` and `ll-auto` CLI changes are covered in FEAT-1406.

## Files to Touch

**Skills (13 files):**
- `skills/capture-issue/SKILL.md`
- `skills/manage-issue/SKILL.md`
- `skills/format-issue/SKILL.md`
- `skills/format-issue/templates.md` _(additional — 3 occurrences of `Type: [BUG|FEAT|ENH]`)_
- `skills/decide-issue/SKILL.md`
- `skills/wire-issue/SKILL.md`
- `skills/confidence-check/SKILL.md`
- `skills/issue-size-review/SKILL.md`
- `skills/audit-issue-conflicts/SKILL.md`
- `skills/product-analyzer/SKILL.md`
- `skills/issue-workflow/SKILL.md`
- `skills/debug-loop-run/SKILL.md`
- `skills/audit-loop-run/SKILL.md` _(additional — grep at line 246 missing `.issues/epics/`)_

**Commands (9 files):**
- `commands/normalize-issues.md`
- `commands/refine-issue.md` _(additional — 3 occurrences: lines 95, 161, 410)_
- `commands/tradeoff-review-issues.md` _(additional — line 139 output template)_
- `commands/open-pr.md` _(additional — line 105 bash grep pattern)_
- `commands/manage-release.md` _(additional — line 196 prose)_
- `commands/create-sprint.md` _(additional — line 148 normalized regex)_
- `commands/scan-product.md` _(additional — line 418 workflow diagram)_
- ~~`commands/capture-issue.md`~~ — **does not exist**; capture-issue is skill-only. Drop this from scope.

**Documentation (10 files):**
- `docs/reference/CLI.md`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/OUTPUT_STYLING.md`
- `docs/reference/ISSUE_TEMPLATE.md`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- `docs/guides/GETTING_STARTED.md`
- `docs/guides/SPRINT_GUIDE.md` _(additional — line 321 prose)_
- `docs/reference/API.md`
- `docs/ARCHITECTURE.md`
- `.claude/CLAUDE.md`

**Additional Commands (3 files — wiring pass):**
- `commands/audit-architecture.md` — "Issue Type Guide" section lists only BUG/ENH/FEAT; `# [BUG|ENH|FEAT]-XXX:` template header; workflow description says "create BUG/ENH/FEAT"
- `commands/sync-issues.md` — push step: "Type from issue ID prefix (BUG, FEAT, ENH)" excludes EPIC; pull label mapping omits EPIC
- `commands/scan-codebase.md` — line 243: `{type} is bug, feat, or enh`; output report has three sections (Bugs / Enhancements / Features) with no Epics row

**Additional Skills (2 files — wiring pass):**
- `skills/analyze-history/SKILL.md` — "Type Distribution - BUG/ENH/FEAT breakdown" analysis category label
- `skills/configure/show-output.md` — sync configuration block displays `BUG→bug, FEAT→enhancement, ENH→enhancement` with no EPIC→epic

**Additional Documentation (3 files — wiring pass):**
- `CONTRIBUTING.md` — "Issue Template (v2.0)" section: "20 sections across BUG, FEAT, and ENH types"; type-specific quality checklist enumerates only BUG/FEAT/ENH
- `docs/development/TROUBLESHOOTING.md` — "Duplicate issue ID not detected" section: "across all types (BUG, FEAT, ENH)" omits EPIC; subdirectory list omits `epics/`
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — `Diversify` state: "At least 2 examples per represented issue type (BUG / FEAT / ENH)"

**Templates and Config (12 files — wiring pass):**
- `config-schema.json` — `issues.categories.description` (line 74): "Required categories (bugs, features, enhancements)" — does not mention epics (even though `epics` default is already present at line 97)
- `templates/generic.json` — `issues.categories` block lists only bugs/features/enhancements; missing `epics` entry
- `templates/typescript.json`, `templates/python-generic.json`, `templates/javascript.json`, `templates/java-gradle.json`, `templates/java-maven.json`, `templates/rust.json`, `templates/dotnet.json`, `templates/go.json` — all 8 project-type templates missing `epics` category in `issues.categories` block
- `templates/bug-sections.json`, `templates/feat-sections.json`, `templates/enh-sections.json` — `_meta.description` reads "Shared section requirements for BUG, FEAT, and ENH issue types" (omits EPIC)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Python infrastructure already complete (do not re-implement):**
- `scripts/little_loops/issue_parser.py:29` — `_NORMALIZED_RE` already includes EPIC: `r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$"`
- `scripts/little_loops/cli_args.py:266` — `VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH", "EPIC"}` (canonical four-type set)
- `scripts/little_loops/config/features.py:17` — `"epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"}`
- `scripts/little_loops/cli/output.py:45,87` — `"EPIC": "35"` (purple-magenta ANSI color)
- `scripts/little_loops/sync.py:1081` — `{"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}` (canonical dir mapping)
- `.issues/epics/` — directory exists (has `.gitkeep` only)
- `templates/epic-sections.json` — already exists; reference it in capture-issue skill update

**Key per-file locations for implementer:**

| File | Section / Anchor | What to change |
|------|-----------------|----------------|
| `skills/capture-issue/SKILL.md` | Type inference table (~line 67) | Add EPIC keyword row (`"epic"`, `"initiative"`, `"milestone"`) |
| `skills/capture-issue/SKILL.md` | Conversation Mode type table (~line 101) | Add EPIC column |
| `skills/capture-issue/SKILL.md` | Directory routing (~line 204) | Add `EPIC -> .../epics/` row |
| `skills/capture-issue/SKILL.md` | Template loading (~line 228) | Add `epic` to valid `{type}` values |
| `skills/capture-issue/SKILL.md` | Reopen category mapping (~line 306) | Add `EPIC->epics` |
| `skills/manage-issue/SKILL.md` | case statement (~line 65) | Add `epic) SEARCH_DIR="$ISSUE_DIR/epics" ;;` |
| `skills/manage-issue/SKILL.md` | `issue_type` argument docs (~line 487) | Add `epic` valid value + coordination note |
| `skills/manage-issue/SKILL.md` | Directory listing (~line 44) | Add `epics/` to `.issues/` tree |
| `commands/normalize-issues.md` | Scan grep (~line 148) | `(BUG\|FEAT\|ENH)` → `(BUG\|FEAT\|ENH\|EPIC)` |
| `commands/normalize-issues.md` | Duplicate-ID grep (~line 166) | Same |
| `commands/normalize-issues.md` | Category mapping table (~line 232) | Add `epics/ | EPIC` row |
| `commands/normalize-issues.md` | Validation regex (~line 451) | Add `\|EPIC` |
| `commands/normalize-issues.md` | Directory structure diagram (~line 467) | Add `epics/` row |
| `skills/format-issue/SKILL.md` | Placement rules (~line 297) | Add `For EPICs:` branch after `For ENHs` |
| `skills/format-issue/SKILL.md` | Bash glob (~line 115) | Add `epics/` to `{bugs,features,enhancements}` |
| `skills/debug-loop-run/SKILL.md` | grep commands (~lines 246, 378) | Add `.issues/epics/` to dir list |
| `skills/debug-loop-run/SKILL.md` | Routing table (~lines 452–453) | Add EPIC row |
| `skills/issue-workflow/SKILL.md` | Directory structure table (~lines 148–153) | Add `epics/ # EPIC-NNN issues` row |
| `skills/confidence-check/SKILL.md` | Scoring rubrics (~lines 237–259) | Add `**EPIC**:` rubric (coverage: child issue completeness, coordination scope) |
| `docs/reference/CLI.md` | `--type` tables + `Norm` regex (~multiple) | Add EPIC to 10+ occurrences |
| `docs/reference/CONFIGURATION.md` | `cli.colors.type` table (~line 651) | Add `EPIC: "35"` row |
| `docs/reference/CONFIGURATION.md` | `label_mapping` default (~line 143) | Add `"EPIC": "epic"` |
| `docs/reference/ISSUE_TEMPLATE.md` | Type-Specific Sections (~line 36) | Add EPIC entry |
| `docs/ARCHITECTURE.md` | `.issues/` hierarchy diagram (~line 42) | Add `epics/` |
| `.claude/CLAUDE.md` | Types list (line 91) | `BUG`, `FEAT`, `ENH` → add `EPIC` |

**EPIC coordination semantics for `manage-issue` update:**
> "If the issue type is EPIC, it is a coordination container — not directly implementable. Redirect the user to child issues for implementation. Use `/ll:create-sprint` to run child issues as a group."

**Verification command (run after implementation):**
```bash
grep -rn 'BUG|FEAT|ENH' skills/ commands/ docs/ .claude/ | grep -v 'EPIC' | grep -v '.issues/'
```
Should return only lines where excluding EPIC is intentional (e.g., `--type BUG,FEAT,ENH` in `ll-auto` help text documenting the epic-skip filter).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

**Python infrastructure — already EPIC-aware (no changes needed for FEAT-1407):**
- `scripts/little_loops/issue_parser.py:29` — `_NORMALIZED_RE` already includes EPIC
- `scripts/little_loops/cli_args.py:266` — `VALID_ISSUE_TYPES = {"BUG", "FEAT", "ENH", "EPIC"}`
- `scripts/little_loops/cli/issues/__init__.py` — all argparse `choices` already include EPIC
- `scripts/little_loops/cli/issues/list_cmd.py` — `type_labels` dict includes EPIC
- `scripts/little_loops/cli/issues/count_cmd.py` — `by_type` dict includes EPIC
- `scripts/little_loops/cli/issues/search.py` — `type_labels` dict includes EPIC
- `scripts/little_loops/cli/history.py` — argparse `choices` includes EPIC
- `hooks/scripts/check-duplicate-issue-id.sh` — already uses `(BUG|FEAT|ENH|EPIC)` regex
- `hooks/scripts/check-duplicate-issue-id-post.sh` — already uses `(BUG|FEAT|ENH|EPIC)` regex

**Python gaps outside FEAT-1407 scope (separate issues required):**
- `scripts/little_loops/workflow_sequence/analysis.py:28` — `ISSUE_PATTERN = (?:BUG|FEAT|ENH)-\d+` excludes EPIC from workflow sequence parsing
- `scripts/little_loops/dependency_mapper/operations.py:280` and `scripts/little_loops/cli/deps.py:50` — `(BUG|FEAT|ENH)-(\d+)` pattern excludes EPIC from dependency scans

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests — already cover EPIC in CLI layer (no changes needed):**
- `scripts/tests/test_issues_cli.py` — `test_list_filter_by_type_epic`, `test_sequence_type_filter_epic`, `test_count_filter_by_type_epic`, `test_count_json_output` all exercise EPIC paths
- `scripts/tests/test_issues_search.py` — `TestSearchTypeFilter.test_filter_epic` covers EPIC search
- `scripts/tests/test_cli_args.py` — `TestParseIssueTypes.test_parse_epic_type` and `TestValidIssueTypes.test_contains_expected_types` verify EPIC in `VALID_ISSUE_TYPES`
- `scripts/tests/conftest.py` — `sample_config` fixture includes `epics` category; `issues_dir` fixture creates `epics/` directory

**New test to write — skill/command markdown coverage:**
- `scripts/tests/test_feat1407_doc_wiring.py` — follow pattern of existing `test_*_doc_wiring.py` files (e.g., `test_enh1130_doc_wiring.py`); assert that key skill `.md` files (capture-issue, normalize-issues, format-issue) include the string `EPIC` in their type references

### Codebase Research Findings

_Added by `/ll:refine-issue` — confirmed test pattern from `test_enh1130_doc_wiring.py`:_

Concrete template for `scripts/tests/test_feat1407_doc_wiring.py`:

```python
"""Tests for FEAT-1407: EPIC type wiring in skills, commands, and docs.

Verifies that key skill/command/doc .md files include EPIC in type lists.
"""

from __future__ import annotations
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_CAPTURE = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"
SKILL_NORMALIZE = PROJECT_ROOT / "commands" / "normalize-issues.md"
SKILL_FORMAT = PROJECT_ROOT / "skills" / "format-issue" / "SKILL.md"
SKILL_ISSUE_WORKFLOW = PROJECT_ROOT / "skills" / "issue-workflow" / "SKILL.md"
DOC_CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
DOC_ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"

class TestCaptureIssueEpicWiring:
    """skills/capture-issue/SKILL.md must include EPIC creation flow."""

    def test_epic_in_type_inference(self) -> None:
        content = SKILL_CAPTURE.read_text()
        assert "EPIC" in content, "capture-issue SKILL.md must include EPIC type"

    def test_epics_dir_routing(self) -> None:
        content = SKILL_CAPTURE.read_text()
        assert "epics/" in content, "capture-issue must route EPICs to .issues/epics/"

class TestNormalizeIssuesEpicWiring:
    """commands/normalize-issues.md must include EPIC in validation regex."""

    def test_epic_in_validation_regex(self) -> None:
        content = SKILL_NORMALIZE.read_text()
        assert "EPIC" in content, "normalize-issues.md must include EPIC in validation patterns"

class TestFormatIssueEpicWiring:
    """skills/format-issue/SKILL.md must include For EPICs placement branch."""

    def test_epic_type_branch(self) -> None:
        content = SKILL_FORMAT.read_text()
        assert "EPIC" in content, "format-issue SKILL.md must include EPIC type branch"

class TestIssueWorkflowEpicWiring:
    """skills/issue-workflow/SKILL.md must list epics/ directory."""

    def test_epics_dir_in_table(self) -> None:
        content = SKILL_ISSUE_WORKFLOW.read_text()
        assert "epics/" in content, "issue-workflow must list epics/ in directory table"

class TestClaudeMdEpicWiring:
    """.claude/CLAUDE.md issue type list must include EPIC."""

    def test_epic_in_type_list(self) -> None:
        content = DOC_CLAUDE_MD.read_text()
        assert "EPIC" in content, ".claude/CLAUDE.md must list EPIC as a valid issue type"

class TestArchitectureEpicWiring:
    """docs/ARCHITECTURE.md must show epics/ in issue hierarchy."""

    def test_epics_in_hierarchy(self) -> None:
        content = DOC_ARCHITECTURE.read_text()
        assert "epics/" in content, "ARCHITECTURE.md must show epics/ in issue hierarchy diagram"
```

**Template epics entry format** (add to every template JSON `issues.categories` block):
```json
"epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"}
```
This matches the canonical definition in `scripts/little_loops/config/features.py:17`.

**Status confirmation**: As of 2026-05-09, none of the 16 skill/command files checked contain `EPIC` — all 43 files listed in _Files to Touch_ still need updating.

## Impact

- **Priority**: P2 — Core consistency fix; EPIC support is incomplete and confusing to users until all text references are updated
- **Effort**: Medium — 21 files to touch, but all changes are mechanical text substitutions (`BUG|FEAT|ENH` → `BUG|FEAT|ENH|EPIC`, add `epics/` directory rows, add EPIC routing branches)
- **Risk**: Low — Text-only changes to Markdown skill/command/documentation files; no Python code changes; child of FEAT-1389 which provides the infrastructure
- **Breaking Change**: No

## Labels

`feature`, `epic-type`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09; re-confirmed 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **Large file surface (43 files)**: High likelihood of missing at least one pattern instance; run the verification grep from Implementation Step 6 after every batch of edits, not just at the end.
- **Test coverage is post-implementation**: `test_feat1407_doc_wiring.py` will catch misses but only after it's written; write it early and run it incrementally.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T03:57:36 - `7976ca7b-d514-438d-82f3-244e955401a6.jsonl`
- `/ll:ready-issue` - 2026-05-10T00:30:40 - `c43beac8-bd79-4b68-905a-853d64991190.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `f3b84938-07de-47b8-b9ad-5293b008ac32.jsonl`
- `/ll:refine-issue` - 2026-05-10T00:24:01 - `a40250de-47d0-4467-868b-1f06fd02da59.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `7c262b73-6b33-437f-a273-e367811f5b3b.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:07:38 - `7b3a8486-5a08-451e-8be4-9c4b483297e5.jsonl`
- `/ll:refine-issue` - 2026-05-09T23:59:43 - `a9ca0d07-7cd0-4bb4-a1eb-809c460b7e5c.jsonl`
- `/ll:format-issue` - 2026-05-09T23:01:30 - `fee7c6fa-dd24-4633-b895-fd894d07e7e2.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`
- `/ll:manage-issue` - 2026-05-10T03:57:02Z - `7976ca7b-d514-438d-82f3-244e955401a6.jsonl`

## Resolution

EPIC type fully wired into all skills, commands, docs, and config templates. The Python infrastructure already supported EPIC (FEAT-1405/1406); this issue completed the surface-level mechanical fanout across ~50 markdown/JSON files in two sessions.

**Files updated** (cumulative across both sessions):
- **Skills (12)**: `capture-issue`, `manage-issue`, `format-issue` (+ `templates.md`), `decide-issue`, `wire-issue`, `confidence-check`, `issue-size-review`, `audit-issue-conflicts`, `product-analyzer`, `issue-workflow`, `debug-loop-run`, `audit-loop-run`, `analyze-history`, `configure/show-output`
- **Commands (9)**: `normalize-issues`, `refine-issue`, `tradeoff-review-issues`, `open-pr`, `manage-release`, `create-sprint`, `scan-product`, `audit-architecture`, `sync-issues`, `scan-codebase`
- **Reference docs (5)**: `CLI.md`, `CONFIGURATION.md`, `OUTPUT_STYLING.md`, `ISSUE_TEMPLATE.md`, `API.md`
- **Guide docs (8)**: `ISSUE_MANAGEMENT_GUIDE.md`, `GETTING_STARTED.md`, `SPRINT_GUIDE.md`, `ARCHITECTURE.md`, `.claude/CLAUDE.md`, `CONTRIBUTING.md`, `TROUBLESHOOTING.md`, `EXAMPLES_MINING_GUIDE.md`
- **Config (10)**: `config-schema.json` + 9 project templates (`generic`, `typescript`, `python-generic`, `javascript`, `java-gradle`, `java-maven`, `rust`, `dotnet`, `go`)

**Test coverage**: Added `scripts/tests/test_feat1407_doc_wiring.py` with 7 wiring assertions (all passing). Validation grep `BUG|FEAT|ENH` against `EPIC` returns clean.

**Test suite**: 6006 passed, 2 pre-existing failures (`TestMarketplaceVersionSync`) unrelated to this work — confirmed by re-running on stash.

---

**Completed** | Created: 2026-05-09 | Completed: 2026-05-10 | Priority: P2
