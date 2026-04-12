---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1067: Extract rubrics for audit-docs, audit-issue-conflicts, cleanup-loops, and map-dependencies

## Summary

Extract inline evaluation checklists, severity scoring matrices, and classification thresholds from four medium-density skills (`audit-docs`, `audit-issue-conflicts`, `cleanup-loops`, `map-dependencies`) into companion `rubric.md` files, update each SKILL.md to load its rubric, and add test files that verify rubric existence and content.

## Parent Issue

Sibling of ENH-1055, ENH-1056, ENH-1065, and ENH-1066: completes the rubric externalization sweep (established by ENH-1053) for the remaining skills with tunable inline criteria.

## Motivation

Four skills carry embedded evaluation criteria that projects may reasonably want to tune:

- **`audit-docs`**: Hard-codes a four-category checklist (accuracy / completeness / consistency / currency) with auto-fixable vs needs-issue classification. Teams with different doc standards want to adjust which checks are mandatory.
- **`audit-issue-conflicts`**: Hard-codes conflict severity levels (High / Medium / Low) and recommendation type mapping (merge / deprecate / split / add_dependency / update_scope). Teams with different conflict resolution policies want to reorder priorities.
- **`cleanup-loops`**: Hard-codes loop state classification categories and a 15-minute staleness threshold. Teams running long-lived loops need to raise this threshold.
- **`map-dependencies`**: Hard-codes dependency conflict scoring thresholds (HIGH ≥0.7, MEDIUM ≥0.4, LOW <0.4) and parallel-safety file overlap ratio logic. Teams want to tune sensitivity for their repo size.

## Expected Behavior

```
skills/<skill>/SKILL.md    ← logic only; loads rubric
skills/<skill>/rubric.md   ← default criteria/thresholds
.ll/rubrics/<skill>.md     ← project override (optional)
```

For each of the four skills, the load idiom (from `skills/review-loop/SKILL.md`):
```
Read `rubric.md` (this companion file) now — or `.ll/rubrics/<skill>.md` if it exists (project override takes precedence).
```

## Scope

**In scope (four skills):**

### `audit-docs`
- `skills/audit-docs/SKILL.md` — remove inline four-category checklist and auto-fixable classification, add load-rubric directive
- `skills/audit-docs/rubric.md` — new file: `## Accuracy Checks`, `## Completeness Checks`, `## Consistency Checks`, `## Currency Checks`, `## Auto-Fixable vs Needs-Issue` classification

### `audit-issue-conflicts`
- `skills/audit-issue-conflicts/SKILL.md` — remove inline conflict severity levels and recommendation type mapping, add load-rubric directive
- `skills/audit-issue-conflicts/rubric.md` — new file: `## Conflict Severity Levels` (High/Medium/Low definitions), `## Recommendation Types` (merge/deprecate/split/add_dependency/update_scope definitions)

### `cleanup-loops`
- `skills/cleanup-loops/SKILL.md` — remove inline state classification categories and 15-minute staleness threshold, add load-rubric directive
- `skills/cleanup-loops/rubric.md` — new file: `## Loop State Classifications` (stuck-running/stale-interrupted/abandoned-handoff/terminal/healthy), `## Staleness Threshold` (default 15 min with override guidance)

### `map-dependencies`
- `skills/map-dependencies/SKILL.md` — remove inline conflict scoring thresholds and parallel-safety ratio logic, add load-rubric directive
- `skills/map-dependencies/rubric.md` — new file: `## Conflict Score Thresholds` (HIGH ≥0.7, MEDIUM ≥0.4, LOW <0.4), `## Parallel-Safety Assessment` (file overlap ratio guidance)

### Tests (one file per skill)
- `scripts/tests/test_audit_docs_skill.py`
- `scripts/tests/test_audit_issue_conflicts_skill.py`
- `scripts/tests/test_cleanup_loops_skill.py`
- `scripts/tests/test_map_dependencies_skill.py`

Each test: verify SKILL.md references `rubric.md`, `rubric.md` exists, contains expected section headings. Pattern: `scripts/tests/test_improve_claude_md_skill.py`.

**Out of scope:** ENH-1065 (analyze-loop, review-loop); ENH-1066 (format-issue); documentation updates (ENH-1057)

## Implementation Steps

1. Read all four SKILL.md files to identify exact inline rubric content boundaries
2. Create four `rubric.md` files with appropriate sections per skill
3. Replace extracted content in each SKILL.md with load-rubric directives
4. Create four test files following the test pattern
5. Run `python -m pytest scripts/tests/test_audit_docs_skill.py scripts/tests/test_audit_issue_conflicts_skill.py scripts/tests/test_cleanup_loops_skill.py scripts/tests/test_map_dependencies_skill.py`

## Success Metrics

- All four skills produce identical outputs after rubric extraction
- Creating `.ll/rubrics/cleanup-loops.md` with a custom staleness threshold (e.g., 30 min) causes `cleanup-loops` to use the override
- Creating `.ll/rubrics/map-dependencies.md` with adjusted scoring thresholds (e.g., HIGH ≥0.6) causes `map-dependencies` to use the override
- All four test files pass `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1065: Extract rubrics for analyze-loop and review-loop (sibling)
- ENH-1066: Extract rubrics for format-issue (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after all extraction siblings complete)

## Integration Map

### Files to Modify
- `skills/audit-docs/SKILL.md`
- `skills/audit-issue-conflicts/SKILL.md`
- `skills/cleanup-loops/SKILL.md`
- `skills/map-dependencies/SKILL.md`

### Dependent Files (Callers/Importers)
- N/A — all four skills invoked directly by users

### Similar Patterns
- `skills/confidence-check/rubric.md` (created by ENH-1055) — follow same file structure
- `skills/issue-size-review/rubric.md` (created by ENH-1055) — table format reference

### Tests
- `scripts/tests/test_audit_docs_skill.py` — new file
- `scripts/tests/test_audit_issue_conflicts_skill.py` — new file
- `scripts/tests/test_cleanup_loops_skill.py` — new file
- `scripts/tests/test_map_dependencies_skill.py` — new file
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — `cleanup-loops` staleness threshold is the most immediately requested customization; others are lower urgency
- **Effort**: Medium — 4 new rubric files, 4 SKILL.md edits, 4 test files; no Python changes
- **Risk**: Low — content-only extraction for all four; fallback keeps behavior unchanged
- **Breaking Change**: No

## Scope Boundaries

- Does not change loop execution logic, issue conflict detection algorithms, or dependency graph traversal
- Does not add new classification categories or scoring dimensions — extraction only
- Can be split per-skill if needed; each skill is fully independent of the others in this batch

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `batch`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e3e6bb-79d7-4b14-9468-7b82778befaa.jsonl`
