---
id: FEAT-1389
type: FEAT
priority: P2
status: done
captured_at: '2026-05-09T20:26:09Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
relates_to:
- ENH-1390
- ENH-1391
- ENH-1392
- ENH-1393
decision_needed: false
confidence_score: 100
outcome_confidence: 43
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 0
size: Very Large
completed_at: 2026-05-09T00:00:00Z
---

# FEAT-1389: Add EPIC as a First-Class Issue Type

## Summary

Add `EPIC` as a new issue type alongside BUG, FEAT, and ENH. Epic files live in `.issues/epics/`, have their own EPIC-NNN ID namespace, and serve as container issues that group related work. This is the single biggest structural gap between little-loops and all major issue tracking platforms (GitHub Projects, JIRA, ADO, Linear), where a container tier is always first-class.

## Current Behavior

There is no EPIC type. Issue groupings are implied through `parent:` or `parent_issue:` references scattered across child issue frontmatter. No single file represents the epic's scope, goal, or child list — requiring consumers to invert the relationship by scanning all issues. The "parallel states" work is 27 files with no container; the session-continuity work is 11 files with no container.

## Expected Behavior

- A new `EPIC` issue type with `EPIC-NNN` IDs exists alongside BUG/FEAT/ENH
- Epic files live in `.issues/epics/`
- An epic file has its own priority, status, summary, scope, and a `children:` list of member issue IDs
- Child issues reference their epic via `epic: EPIC-NNN` in frontmatter (distinct from `parent:` which denotes decomposition parent within the same level)
- `ll-issues list` supports `--type epic` and shows child count per epic
- `ll-issues next-id` allocates EPIC-NNN from the same global counter as other types

## Motivation

Every major platform has a container tier:
- **JIRA**: Epic → Story → Sub-task
- **ADO**: Epic → Feature → User Story
- **Linear**: Project → Issue → Sub-issue
- **GitHub Projects**: Milestone/tracked issue → Issue → Sub-issue

Without a container tier, `ll-sync` cannot map epics to platform milestones or tracked parent issues. Sprint planning has no anchor for "this sprint completes epic X". The deferred backlog has no way to communicate that 27 parallel-state issues are one coherent body of work to defer or undefer together.

## Proposed Solution

1. Add `EPIC` to the recognized type set in issue parsing and validation
2. Create `.issues/epics/` directory and update directory routing in `issue_manager.py` and `ll-issues`
3. Define a new `epic-sections.json` template with scope, goal, `children:` list, and status tracking
4. Update `ll-issues next-id` to allocate from the global counter (EPIC-NNN shares the same number space as FEAT-NNN etc.)
5. Add `epic:` as a recognized frontmatter field on non-epic issues
6. Update `ll-sync` to map `epic:` field to platform-specific parent/milestone concepts

## Use Case

A user has 27 deferred issues for parallel FSM states. They create `EPIC-1400-parallel-fsm-states.md` in `.issues/epics/`, list all 27 as children, and mark the epic as `status: deferred`. The deferred/ backlog now shows one EPIC entry instead of 27 individual issues. When the team decides to start parallel states work, they update the epic to `status: open` and the sprint planner can see the full scope.

## Acceptance Criteria

- `EPIC` is a valid issue type recognized by all ll tooling (capture, manage, sync, verify, next-id)
- `.issues/epics/` directory is created and routing is updated
- `epic-sections.json` template exists with `children:` list support
- `ll-issues list --type epic` shows epics with child count
- `epic: EPIC-NNN` is a valid frontmatter field on BUG/FEAT/ENH issues
- Existing `parent:` field is NOT replaced — `epic:` and `parent:` serve distinct roles

## API/Interface

### New Frontmatter Fields

```yaml
# On EPIC issues (epic-sections.json defines these)
id: EPIC-NNN
type: EPIC
children: [FEAT-100, BUG-200, ENH-300]  # member issue IDs

# On BUG/FEAT/ENH issues (new optional field, distinct from parent:)
epic: EPIC-NNN
```

### New CLI Arguments

```bash
ll-issues list --type epic        # filter to epics; shows child count per row
ll-issues next-id                 # already allocates from global counter; EPIC-NNN follows same rules
ll-issues show EPIC-NNN           # display epic with children summary
```

### Config Schema Addition

```json
{
  "issue_types": ["BUG", "FEAT", "ENH", "EPIC"]
}
```

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — add EPIC to type enum/routing
- `scripts/little_loops/cli/issues.py` — list/show/next-id for EPIC type
- `scripts/little_loops/sync/` — map `epic:` to platform parent concepts
- `skills/capture-issue/SKILL.md` and `commands/capture-issue.md` — EPIC creation flow
- `skills/manage-issue/SKILL.md` — epic management
- `config-schema.json` — add `epic` to recognized issue types

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli_args.py` — **CRITICAL**: add `"EPIC"` to `VALID_ISSUE_TYPES` constant and error message in `parse_issue_types()`; without this, `--type EPIC` is rejected by argparse before any code runs
- `scripts/little_loops/config/cli.py` — add `EPIC: str` field to `CliColorsTypeConfig` dataclass and `from_dict()` key lookup; `output.py`'s `configure_output()` reads named attributes from this dataclass — the `output.py` update is a no-op without this
- `scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` dict in `count_cmd()`; EPIC issues currently silently drop from JSON count output
- `scripts/little_loops/cli/history.py` — add `"EPIC"` to `--type` argument `choices=["BUG", "FEAT", "ENH"]` for `ll-history export`

### Files to Create
- `templates/epic-sections.json` — epic template
- `.issues/epics/` — directory (create with a placeholder or first real epic)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — uses issue type routing; EPIC type should not be auto-processed like regular issues
- `scripts/little_loops/cli/sprint.py` — sprint planner references issue types; epic-awareness needed
- grep: `grep -r "IssueType\|issue_type\|type_dir\|ISSUE_TYPES" scripts/`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/deps.py` — `_load_issues_and_contents()` uses `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)`; EPIC completed files are excluded from dependency tracking
- `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()` uses the same hardcoded regex; EPIC IDs excluded from dependency graph
- `scripts/little_loops/workflow_sequence/analysis.py` — `ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)` at module level; EPIC IDs not detected in workflow message analysis
- `scripts/little_loops/cli/sprint/edit.py` — `re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)` when scanning completed directory during sprint edit; EPIC completed files ignored
- `scripts/little_loops/loops/recursive-refine.yaml` — inline `re.search(r'(BUG|FEAT|ENH)-(\d+)', ...)` in YAML loop script block; EPIC files not matched during loop execution
- `scripts/little_loops/issue_history/quality.py` — `detect_quality_hotspots()` calls `hotspot.issue_types.get("BUG", 0)` with hardcoded key (informational; EPIC excluded from hotspot stats)
- `scripts/little_loops/issue_history/formatting.py` — `format_analysis_text()` calls `type_counts.get("BUG", 0)` with hardcoded key (informational; EPIC excluded from formatted summary)

### Similar Patterns
- `scripts/little_loops/issue_manager.py` — existing BUG/FEAT/ENH directory routing; EPIC follows same pattern
- `templates/feat-sections.json` — structural model for new `templates/epic-sections.json`
- grep: `grep -r '\.issues/bugs\|\.issues/features\|\.issues/enhancements' scripts/`

### Tests
- `scripts/tests/test_issue_manager.py` — EPIC type routing, directory creation, ID allocation
- `scripts/tests/test_issues_cli.py` — `ll-issues list --type epic`, child count display, `next-id` EPIC allocation
- `scripts/tests/test_sync.py` — `epic:` frontmatter field mapping to platform parent/milestone

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_args.py` — **WILL BREAK**: `TestValidIssueTypes.test_contains_expected_types` asserts `VALID_ISSUE_TYPES == {"BUG", "FEAT", "ENH"}` (exact equality); update to include `"EPIC"`; also add `test_parse_epic_type` following pattern in `TestParseIssueTypes`
- `scripts/tests/test_cli_output.py` — **WILL BREAK (partial)**: `TestConfigureOutput.setup_method` and `teardown_method` call `TYPE_COLOR.update({"BUG":..., "FEAT":..., "ENH":...})`; when EPIC is added to module dict, this reset is incomplete and leaves EPIC dirty between tests; update both to include `"EPIC"` reset; add `TestOrangeDefaultColors.test_type_epic_has_color` asserting `TYPE_COLOR["EPIC"] == "35"`
- `scripts/tests/test_issues_search.py` — add `TestSearchTypeFilter.test_filter_epic` passing `--type EPIC` to `ll-issues search`; follows pattern of `test_filter_bug` and `test_filter_feat`
- `scripts/tests/test_issue_template.py` — `TestLoadIssueSections.test_load_default` is `@pytest.mark.parametrize("issue_type", ["BUG", "FEAT", "ENH"])`; add `"EPIC"` to parametrize list (requires `templates/epic-sections.json` to exist first)
- `scripts/tests/test_loops_recursive_refine.py` — mirrors the hardcoded regex in `recursive-refine.yaml`; update if that regex is changed

### Documentation
- `docs/reference/API.md` — EPIC type, `epic:` field, `children:` field definitions
- `docs/ARCHITECTURE.md` — epic tier in issue hierarchy diagram
- `CONTRIBUTING.md` — epic creation workflow

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `--type` flag documented as "`BUG`, `FEAT`, `ENH`" in six places across `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-issues list/count/sequence/search/impact-effort/refine-status/anchor-sweep`; also the `Norm` column regex `^P[0-5]-(BUG|FEAT|ENH)-...`; add EPIC in all locations
- `docs/reference/CONFIGURATION.md` — `cli.colors.type` table lists only BUG/FEAT/ENH; `label_mapping` default shows only three keys; `sync.github.label_mapping` description references `{"BUG": "bug", ...}`; add EPIC entries
- `docs/reference/OUTPUT_STYLING.md` — type color table and `cmd_list` description list only three types; add EPIC row
- `docs/reference/ISSUE_TEMPLATE.md` — `### Type-Specific Sections` lists only "BUG", "FEAT", "ENH"; quality check checklists only cover those three; add EPIC section
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "type: BUG, FEAT, or ENH" in `### Issue File Anatomy`; directory listing omits `epics/`; update both
- `docs/guides/GETTING_STARTED.md` — "type: BUG, FEAT, or ENH" description; add EPIC
- `.claude/CLAUDE.md` — `Types: \`BUG\`, \`FEAT\`, \`ENH\`` in `## Issue File Format`; add EPIC

### Configuration
- `config-schema.json` — `epic` in recognized issue types; `epic:` as valid frontmatter field on BUG/FEAT/ENH; also `cli.colors.type.properties` block has `"additionalProperties": false` — add `"EPIC"` property or user config will be schema-rejected; `label_mapping.default` hardcodes three keys — add EPIC default

### Skills/Commands (Type-Aware)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/normalize-issues.md` — bash grep patterns `(BUG|FEAT|ENH)` appear six times: scan regex, duplicate-ID grep, validation rule regex, category mapping table, misclassification heuristics table, directory structure rules; update all
- `skills/format-issue/SKILL.md` — Step 3 "Identify issue type from filename or ID prefix (BUG/FEAT/ENH)"; template filename note; placement rules headings "For BUGs", "For FEATs", "For ENHs" — add EPIC branch
- `skills/decide-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
- `skills/wire-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
- `skills/confidence-check/SKILL.md` — three type-specific scoring rubrics `**BUG**:`, `**FEAT**:`, `**ENH**:`; EPIC gets no rubric — add EPIC rubric covering coordination scope and child issue completeness criteria
- `skills/issue-size-review/SKILL.md` — output template `type: [BUG|FEAT|ENH]` and dependency mention scoring rule referencing `BUG-/FEAT-/ENH-` — add EPIC
- `skills/audit-issue-conflicts/SKILL.md` — card schema `- **Type** (\`BUG\`, \`FEAT\`, \`ENH\`)` and output templates `- **Type**: [BUG/FEAT/ENH]` — add EPIC
- `skills/product-analyzer/SKILL.md` — `issue_type: [FEAT|ENH]` in YAML output description; EPIC excluded from product analyzer output type set — add EPIC for strategic/container-level captures
- `skills/issue-workflow/SKILL.md` — directory reference table `bugs/`, `features/`, `enhancements/`; missing `epics/` entry — add EPIC row
- `skills/debug-loop-run/SKILL.md` — `### 6b. Determine issue type and category` routing table maps only BUG and ENH; add EPIC for completeness as a reference table

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Primary type registry** (the real "type enum") is `REQUIRED_CATEGORIES` in `scripts/little_loops/config/features.py`, not `issue_manager.py`. `issue_manager.py` is the automation manager for sequential processing. The primary change is:
```python
# scripts/little_loops/config/features.py
REQUIRED_CATEGORIES = {
    "bugs":         {"prefix": "BUG",  "dir": "bugs",         "action": "fix"},
    "features":     {"prefix": "FEAT", "dir": "features",     "action": "implement"},
    "enhancements": {"prefix": "ENH",  "dir": "enhancements", "action": "improve"},
    # ADD:
    "epics":        {"prefix": "EPIC", "dir": "epics",        "action": "coordinate"},
}
```

**Hardcoded type-name locations** that need `EPIC` added (all others are config-driven and require no change):

| File | Location | Pattern to update |
|------|----------|-------------------|
| `scripts/little_loops/issue_parser.py` | `_NORMALIZED_RE` (module level) | `r"^P[0-5]-(BUG\|FEAT\|ENH)-..."` → add `EPIC` |
| `scripts/little_loops/issue_parser.py` | `_ISSUE_TYPE_RE` (module level) | `r"-(BUG\|FEAT\|ENH)-"` → add `EPIC` |
| `scripts/little_loops/cli/issues/show.py` | `_resolve_issue_id()` | Two regex literals with `(BUG\|FEAT\|ENH)` alternation |
| `scripts/little_loops/cli/issues/show.py` | `_parse_card_fields()` | One regex literal with `(BUG\|FEAT\|ENH)` |
| `scripts/little_loops/sync.py` | `_extract_issue_id()` | `r"(BUG\|FEAT\|ENH)-(\d+)"` |
| `scripts/little_loops/sync.py` | `reopen_issues()` | Hard-coded `category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}` |

**Config-driven locations (no changes needed)**:
- `get_next_issue_number()` in `issue_parser.py` — already reads prefixes from config dynamically; EPIC is included automatically once added to `REQUIRED_CATEGORIES`
- `IssueParser._build_prefix_map()` — config-driven; no change needed
- `AutoManager._get_next_issue()` in `cli/auto.py` — prefix string comparison, not enum; EPIC filtered out if user doesn't pass `--type EPIC`

**Display and CLI additions needed**:
- `scripts/little_loops/cli/output.py` — `TYPE_COLOR` dict; add `"EPIC": "35"` (purple/magenta) for terminal display
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` has hardcoded `buckets = {"BUG": [], "FEAT": [], "ENH": []}` and `type_labels` dict; EPIC issues are silently dropped from grouped display without this addition
- `scripts/little_loops/cli/issues/search.py` — same hardcoded `buckets` pattern; same silent-drop issue
- `scripts/little_loops/cli/issues/__init__.py` — `--type` argument `choices=["BUG", "FEAT", "ENH"]`; add `"EPIC"` to allow type-filtering

**`IssueInfo` dataclass** in `scripts/little_loops/issue_parser.py`: needs `epic: str | None = None` field so `IssueParser.parse_file()` can read `epic: EPIC-NNN` from child issue frontmatter. The `blocked_by`/`blocks` fields show the existing pattern for optional frontmatter list fields.

**Template loader** (`scripts/little_loops/issue_template.py` — `load_issue_sections()`) derives the filename as `f"{issue_type.lower()}-sections.json"` — no code change needed; creating `templates/epic-sections.json` is sufficient.

**`auto.py` EPIC exclusion**: The `ll-auto` command processes issues by type prefix via `--type` filter. If no `--type` is specified, it processes all types from all category directories. Add `"epics"` to an exclusion list (or document that `ll-auto` should be run with `--type BUG,FEAT,ENH` to skip epics, since epics are containers, not implementable units).

**`sprint.py`**: No changes needed — sprint planning is ID-list driven and type-agnostic. The `config.get_category_action("epics")` call will return `"coordinate"` once the category is registered.

## Implementation Steps

1. **Register EPIC type**: Add `"epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"}` to `REQUIRED_CATEGORIES` in `scripts/little_loops/config/features.py`; create `.issues/epics/` directory
2. **Create template**: Add `templates/epic-sections.json` modeled after `templates/feat-sections.json` with `type_sections`: goal (required), scope (required), `children:` list (required), and success metrics (conditional)
3. **Fix hardcoded regexes** (6 locations):
   - `scripts/little_loops/issue_parser.py`: extend `_NORMALIZED_RE` and `_ISSUE_TYPE_RE` with `EPIC` alternation
   - `scripts/little_loops/cli/issues/show.py`: extend `_resolve_issue_id()` (2 regexes) and `_parse_card_fields()` (1 regex)
   - `scripts/little_loops/sync.py`: extend `_extract_issue_id()` regex and `reopen_issues()` `category_map` dict
4. **Fix CLI display**:
   - `scripts/little_loops/cli/issues/list_cmd.py`: add `"EPIC"` to `buckets` and `type_labels` dicts in `cmd_list()`
   - `scripts/little_loops/cli/issues/search.py`: same `buckets`/`type_labels` update
   - `scripts/little_loops/cli/issues/__init__.py`: add `"EPIC"` to `--type` argument `choices`
   - `scripts/little_loops/cli/output.py`: add `"EPIC": "35"` to `TYPE_COLOR` dict
5. **Add `epic:` frontmatter field**: Add `epic: str | None = None` to `IssueInfo` dataclass in `issue_parser.py`; update `IssueParser.parse_file()` to read it from frontmatter; add to `config-schema.json` as optional field on BUG/FEAT/ENH issues
6. **Update `ll-sync`**: Add `"EPIC"` to `label_mapping` default in `config-schema.json`; update `GitHubSyncManager` to map `epic:` field to GitHub milestone concept in push/pull paths
7. **Update skills/commands**: Add EPIC creation flow to `skills/capture-issue/SKILL.md` and `commands/capture-issue.md`; document that `ll-auto` should use `--type BUG,FEAT,ENH` to exclude epics from auto-processing
8. **Add tests** following patterns in `scripts/tests/test_issue_parser.py` (`test_parse_feature_issue`) and `scripts/tests/test_config.py` (`test_required_categories_merged_with_custom`):
   - EPIC type routing and directory creation in `test_issue_parser.py`
   - `ll-issues list --type EPIC` and child count display in `test_issues_cli.py`
   - `next-id` includes EPIC in global counter in `test_issues_cli.py`
   - `epic:` frontmatter round-trip on child issues in `test_issue_parser.py`
9. **Update docs**: `docs/reference/API.md` (EPIC type, `epic:` field, `children:` field); `docs/ARCHITECTURE.md` (epic tier diagram)
10. **Verify**: `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py scripts/tests/test_sync.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/little_loops/cli_args.py` — add `"EPIC"` to `VALID_ISSUE_TYPES` set and the error message string in `parse_issue_types()`; do this **before** Step 4 (CLI display), or any `--type EPIC` invocation will be rejected
12. Update `scripts/little_loops/config/cli.py` — add `EPIC: str = "35"` field to `CliColorsTypeConfig` dataclass and `data.get("EPIC", "35")` in `from_dict()`; required for Step 4's `output.py` update to take effect
13. Update `scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` dict in `count_cmd()` so EPIC issues appear in JSON count output
14. Update `scripts/little_loops/cli/history.py` — add `"EPIC"` to `--type` argument `choices` list for `ll-history export`
15. Update regex-based callers — extend `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)` in:
    - `scripts/little_loops/cli/deps.py` → `_load_issues_and_contents()`
    - `scripts/little_loops/dependency_mapper/operations.py` → `gather_all_issue_ids()`
    - `scripts/little_loops/workflow_sequence/analysis.py` → `ISSUE_PATTERN`
    - `scripts/little_loops/cli/sprint/edit.py` → completed directory scan
    - `scripts/little_loops/loops/recursive-refine.yaml` → inline regex script block
16. Fix breaking tests before running CI:
    - `scripts/tests/test_cli_args.py` → update `test_contains_expected_types` to include `"EPIC"` in the expected set
    - `scripts/tests/test_cli_output.py` → add `"EPIC"` reset to `setup_method`/`teardown_method`; add `test_type_epic_has_color`
17. Add new tests:
    - `scripts/tests/test_issues_search.py` → `TestSearchTypeFilter.test_filter_epic`
    - `scripts/tests/test_issue_template.py` → add `"EPIC"` to `test_load_default` parametrize list (after `templates/epic-sections.json` is created)
18. Update 10 skills/commands with hardcoded type lists: `commands/normalize-issues.md`, `skills/format-issue/SKILL.md`, `skills/decide-issue/SKILL.md`, `skills/wire-issue/SKILL.md`, `skills/confidence-check/SKILL.md`, `skills/issue-size-review/SKILL.md`, `skills/audit-issue-conflicts/SKILL.md`, `skills/product-analyzer/SKILL.md`, `skills/issue-workflow/SKILL.md`, `skills/debug-loop-run/SKILL.md`
19. Update 7 documentation files: `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/OUTPUT_STYLING.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `docs/guides/GETTING_STARTED.md`, `.claude/CLAUDE.md`
20. **Extended verify**: `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py scripts/tests/test_sync.py scripts/tests/test_cli_args.py scripts/tests/test_cli_output.py scripts/tests/test_issues_search.py scripts/tests/test_issue_template.py scripts/tests/test_config.py -v`

## Impact

- **Priority**: P2 — foundational change needed before issue sync is meaningful
- **Effort**: Medium — mostly additive; no existing files need to move
- **Risk**: Low — new directory + new type; existing issues are unaffected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `epic-system`, `sync-compatibility`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 43/100 → LOW

### Outcome Risk Factors
- **Broad file scope (48+ files)**: Python source, tests, skills/commands, docs, and config all need updates. Sequence Python changes first, then docs/skills, to maintain focus.
- **Wide change surface on issue_parser.py**: 134+ importers in the codebase. The two regex changes are additive-only, but a mistake here will silently break issue parsing across the entire toolchain. Write the test first.
- **Hardcoded-regex sprawl**: At least 11 `(BUG|FEAT|ENH)` regex literals across 8 files. A missed location causes EPIC IDs to silently drop from that code path. Use the wiring pass checklist and grep to verify after implementation.
- **Test breakage before first run**: `test_cli_args.py::test_contains_expected_types` and `test_cli_output.py` setup/teardown will fail immediately; fix these first or CI blocks all other validation.

## Session Log
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`
- `/ll:wire-issue` - 2026-05-09T21:57:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7544439b-419c-4586-b140-ffaab75f3733.jsonl`
- `/ll:refine-issue` - 2026-05-09T21:46:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4dc81de5-5bdf-4f30-9119-d45cc81ad80c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T20:39:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf87852d-ec5b-4a4d-959f-57a040534f19.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/235810f3-1406-4664-ab0d-c24db173c550.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-09
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-1405: EPIC Type — Core Registration and Parsing
- FEAT-1406: EPIC Type — CLI Display, Sync, and Tooling Integration
- FEAT-1407: EPIC Type — Skills, Commands, and Documentation Updates

---

**Open** | Created: 2026-05-09 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): FEAT-1389 is the formal owner of the `epic:` frontmatter field definition, including its config-schema registration and tooling wiring in `issue_manager.py`. ENH-1391 (Standardize Issue Relationship Fields) also lists `epic:` in its canonical vocabulary table for platform-mapping purposes. Coordinate with ENH-1391 so the field validation and `config-schema.json` entry is implemented once here, then referenced (not re-implemented) in ENH-1391's migration pass.
