---

discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
confidence_score: 88
outcome_confidence: 68
score_complexity: 25
score_test_coverage: 0
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-04-27T18:26:29Z
parent: ENH-1299
---

# ENH-1303: Fix `file:line` references in skill source files

## Summary

Edit `skills/wire-issue/SKILL.md` and `skills/manage-issue/templates.md` to replace all `file:line`-style references and template slots with anchor-based equivalents.

## Parent Issue

Decomposed from ENH-1299: Fix `file:line` references in issue-authoring pipeline source files

## Current Behavior

- **`skills/wire-issue/SKILL.md`**: Output templates under "Callers / importers", "Documentation", "Tests", and the Phase 10 report block show `path/to/caller.py:42` style (2 literal `file:line` phrases + 6 `:N`-style template entries = **8 total**).
- **`skills/manage-issue/templates.md`**: 18 raw occurrences of "with file:line references" and `[file:line]` placeholder slots across 17 lines (line 290 has 2 on one line).

## Expected Behavior

- `wire-issue/SKILL.md`: Output template entries updated from `path/to/caller.py:42 — calls affected_function()` to `path/to/caller.py — calls affected_function() in handle_request()`.
- `manage-issue/templates.md`: All "with file:line references" replaced with "with function/class anchors (e.g. `in function foo()`, `near class Bar`)"; `[file:line]` placeholder slots replaced with `[function/class anchor]`.

## Proposed Solution

1. **`skills/wire-issue/SKILL.md`**:
   - Update output template entries from `path/to/caller.py:42 — calls affected_function()` to `path/to/caller.py — calls affected_function() in handle_request()`

2. **`skills/manage-issue/templates.md`**:
   - Replace all "with file:line references" with "with function/class anchors (e.g. `in function foo()`, `near class Bar`)" — 18 instances across 17 lines
   - Replace `[file:line]` placeholder slots with `[function/class anchor]`

### Codebase Research Findings

**Established anchor patterns** (from `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`):
- Integration Map entries: `` `path/to/file.py` — calls `affected_function()` in `handle_request()` ``
- Function: `` `in function foo()` `` or `` `in method ClassName.method_name()` ``

**Exact occurrence counts (verified by grep):**
- `skills/wire-issue/SKILL.md`: 2 literal `file:line` phrases + 6 `:N`-style template entries = **8 total**
- `skills/manage-issue/templates.md`: 18 raw occurrences across 17 lines (line 290 has 2 on one line)

**`skills/wire-issue/SKILL.md` line-level breakdown:**

| Line | Type | Text |
|------|------|------|
| 176 | Literal phrase (agent 2 prompt) | `Return analysis with specific file:line references for each coupling found.` |
| 199 | Literal phrase (agent 3 prompt) | `Return examples with file:line references.` |
| 297 | `:N`-style template entry | `` `path/to/caller.py:42` — calls `affected_function()` `` |
| 298 | `:N`-style template entry | `` `path/to/importer.py:5` — imports `affected_module` `` |
| 314 | `:N`-style template entry | `` `docs/relevant.md:23` — describes `affected_function()`, needs updating `` |
| 326 | `:N`-style template entry (Tests section) | `` `tests/test_integration.py:88` — calls old API, will break — update `` |
| 416 | `:N`-style template entry (Phase 10 report) | `` `path/to/caller.py:42` — calls `affected_fn()` `` |
| 424 | `:N`-style template entry (Phase 10 report) | `` `docs/api.md:15` — describes changed interface `` |

**Anchor format reference** (from already-fixed `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`):
- Instruction text: `specific anchor-based references (function/class names)`
- Integration Map entry: `` `path/to/file.py` — calls `affected_function()` in `handle_request()` ``
- Doc entry: `` `docs/relevant.md` — describes `affected_function()` under section "Function Reference" ``

## Integration Map

### Files to Modify

- `skills/wire-issue/SKILL.md`
- `skills/manage-issue/templates.md`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/skill_expander.py` — dynamically loads `skills/*/SKILL.md` via `expand_skill()` / `_resolve_content_path()`; no code change needed, but is the runtime consumer of this file's content

### Tests

- `scripts/tests/test_enh1299_doc_wiring.py` (written by ENH-1304) — includes assertions for these two files
- `scripts/tests/test_feat1172_doc_wiring.py` — reference pattern to follow (`TestManageIssueSkillWiring` class, `PROJECT_ROOT = Path(__file__).parent.parent.parent`, `assert "string" not in content` style) [Agent 3 finding]

### Verification

```bash
grep -n "file:line\|\.[a-z]*:[0-9]" skills/wire-issue/SKILL.md skills/manage-issue/templates.md
# Should return zero matches
```

## Implementation Steps

1. Edit `skills/wire-issue/SKILL.md` — 8 occurrences across 2 change types:
   - Lines 176 and 199: replace `file:line references` with `anchor-based references (function/class names)`
   - Lines 297–298: replace `` `path/to/caller.py:42` — calls `affected_function()` `` → `` `path/to/caller.py` — calls `affected_function()` in `handle_request()` ``; `` `path/to/importer.py:5` — imports `affected_module` `` → `` `path/to/importer.py` — imports `affected_module` in `module_init()` ``
   - Line 314: replace `` `docs/relevant.md:23` — describes `affected_function()` `` → `` `docs/relevant.md` — describes `affected_function()` under section "Function Reference" ``
   - Line 326: replace `` `tests/test_integration.py:88` — calls old API, will break — update `` → `` `tests/test_integration.py` — calls old API in `test_handle_request()`, will break — update ``
   - Lines 416, 424: apply same `:N` removal to Phase 10 report block entries

2. Edit `skills/manage-issue/templates.md` — 18 occurrences across 17 lines:
   - Lines 28, 32, 47, 124 (instruction text): replace `with file:line references` / `with file:line refs` → `with function/class anchors (e.g. \`in function foo()\`, \`near class Bar\`)`; replace `file:line references.` → `anchor-based references (function/class names).`
   - Lines 56, 57, 65, 68, 69, 95, 96, 208, 209, 280, 281, 290, 299 (placeholder slots): replace `[file:line]` / `[file:line reference]` → `[function/class anchor]`; replace `file:line refs` → `anchor-based references (function/class names)`

3. Verify: `grep -n "file:line\|\.[a-z]*:[0-9]" skills/wire-issue/SKILL.md skills/manage-issue/templates.md` should return zero matches.

## Impact

- **Priority**: P2
- **Effort**: Small — pure text edits to 2 markdown files
- **Risk**: Very low — reversible; changes only affect skill prompts
- **Breaking Change**: No

## Success Metrics

- Zero `file:line` and `:N`-style occurrences in `skills/wire-issue/SKILL.md` and `skills/manage-issue/templates.md`.

## Labels

`enhancement`, `reference-cleanup`, `authoring-pipeline`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-27_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- **Missed occurrence at line 326**: `skills/wire-issue/SKILL.md` line 326 contains `` `tests/test_integration.py:88` `` — a `:N`-style template entry. The issue breakdown counts 7 occurrences (2 literal + 5 `:N`) but grep finds 8; line 326 is absent from the implementation steps.
- **Verification command gap**: `grep -n "file:line"` checks only the literal text, not `:N`-style entries (`:42`, `:88`). A passing verification run does not confirm all `:N` patterns were removed.

### Outcome Risk Factors
- No test coverage until ENH-1304 lands: `test_enh1299_doc_wiring.py` does not exist yet — the modified areas have zero automated validation. Regressions in skill output templates will go undetected if ENH-1303 lands first.
- Line 326 (`tests/test_integration.py:88`) in `skills/wire-issue/SKILL.md` is a `:N`-style entry absent from the implementation steps; the verification command will not flag it.

## Resolution

Fixed all 8 `file:line`-style references in `skills/wire-issue/SKILL.md` and all 18 occurrences across 17 lines in `skills/manage-issue/templates.md`. Replaced with anchor-based equivalents (function/class names, section names) per the patterns established in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`.

Verification: `grep -n "file:line\|\.[a-z]*:[0-9]" skills/wire-issue/SKILL.md skills/manage-issue/templates.md` returns zero matches.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-27T18:26:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fb744a8-b2be-4d39-8257-09822848481b.jsonl`
- `/ll:manage-issue` - 2026-04-27T18:26:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-04-27T18:23:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de4fdc2b-6d52-4b83-bb5c-58243af7b0e0.jsonl`
- `/ll:wire-issue` - 2026-04-27T17:13:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70909210-c44c-42bd-b735-0b69ffacb590.jsonl`
- `/ll:refine-issue` - 2026-04-27T17:08:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41cff0a5-6278-4376-b590-c89c125b07be.jsonl`
- `/ll:issue-size-review` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0236c-552d-443a-b7cc-ca1f237e6953.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e600d60-a7e4-40c6-9cdc-c101988d3673.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
