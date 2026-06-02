---
id: ENH-1324
priority: P3
type: ENH
captured_at: "2026-05-02T15:21:00Z"
completed_at: "2026-05-02T15:43:47Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1324: Define `parent_issue` Frontmatter Field for Child Issues Created by `issue-size-review`

## Summary

When `issue-size-review` decomposes a large issue into child issues, it says "Write issue content with parent reference in frontmatter" (Phase 6, step 2) but never defines the frontmatter field name or format. The only concrete parent link specified is a `## Parent Issue` body section. This leaves the parent→child relationship non-machine-readable and inconsistent across decompositions.

## Current Behavior

Phase 6, step 2 of `skills/issue-size-review/SKILL.md` says:

> Write issue content with parent reference in frontmatter

But the frontmatter field name is never specified. The Phase 4 draft template includes a `## Parent Issue` body section (`Decomposed from [PARENT-ID]: [Parent Title]`) but no frontmatter field. Implementations may or may not add a frontmatter field, and if they do, the field name is arbitrary.

## Expected Behavior

The skill should explicitly define a `parent_issue` frontmatter field (or similarly named field) with a concrete format, e.g.:

```yaml
---
id: ENH-1325
priority: P3
type: ENH
parent_issue: ENH-179
---
```

This field should be:
- Added to the frontmatter of every child issue at creation time
- Set to the parent issue's bare ID (e.g., `ENH-179`, not a path or full title)
- Documented in the Phase 4 draft template and Phase 6 execution step

## Motivation

The parent→child relationship is currently only stored in free-text body prose. Tools like `ll-issues`, `ll-deps`, and dependency analysis cannot reliably extract it without parsing human-readable markdown. A structured frontmatter field makes the relationship available to any tool that reads YAML frontmatter, enables `ll-issues` to display decomposition trees, and ensures consistency across all decompositions.

## Proposed Solution

1. Add `parent_issue: [PARENT-ID]` to the Phase 4 child issue draft template frontmatter block
2. Update Phase 6, step 2 to explicitly state the field name and format
3. Keep the `## Parent Issue` body section as human-readable context (do not remove it)

Updated Phase 4 draft template:
```markdown
---
id: [TYPE]-[NNN]
priority: [P0-P5]
type: [BUG|FEAT|ENH]
parent_issue: [PARENT-ID]
---

# [TYPE]-[NNN]: [Specific Title]

## Summary
[Focused description from parent issue]

## Parent Issue
Decomposed from [PARENT-ID]: [Parent Title]
```

## API/Interface

New frontmatter field added to child issues created by `issue-size-review`:

```yaml
parent_issue: ENH-179  # bare issue ID (type-NNN format, e.g. BUG-042, FEAT-225)
```

No code API changes — this is a SKILL.md prose/template update only.

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — Phase 4 draft template (add `parent_issue` to frontmatter) and Phase 6 step 2 (specify field name/format)

### Dependent Files (Callers/Importers)
- N/A — no code parses this field yet (this issue introduces the convention)

### Similar Patterns
- Other issue frontmatter fields (`id`, `priority`, `type`, `captured_at`) as model for field naming

### Tests
- N/A — skill is prose/markdown, no automated tests

### Documentation
- `docs/reference/API.md` — may need note about the new frontmatter field if it documents issue schema

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Phase 4 draft template location**: `skills/issue-size-review/SKILL.md` "Phase 4: Decomposition Proposal", step 5 — the template currently starts with `# [TYPE]-[NNN]: [Specific Title]` with **no frontmatter block at all**; `parent_issue` must be added in a new `---` block before the heading
- **Phase 6 step 2 location**: `skills/issue-size-review/SKILL.md` "Phase 6: Execution", step 2 — contains the exact text "Write issue content with parent reference in frontmatter" that needs to be updated to name `parent_issue` and its format
- **`autodev.yaml` dependency**: `scripts/little_loops/loops/autodev.yaml:detect_children` uses `grep -q "Decomposed from $PARENT_ID" "$child_file"` to detect child issues — it reads **body text**, not frontmatter; this confirms the `## Parent Issue` body section must NOT be removed (it is load-bearing for the autodev FSM loop)
- **Field name confirmed by existing issues**: Many completed child issues already carry `parent_issue` in frontmatter (e.g., `FEAT-1285`, `FEAT-1078`, `ENH-1249`, `ENH-1302`) confirming `parent_issue` is the established field name
- **`IssueInfo` dataclass** (`scripts/little_loops/issue_parser.py:IssueInfo`): No `parent_issue` attribute defined — `parse_frontmatter()` would surface the key if written, but `parse_file()` never reads it; tools will silently ignore the field until a follow-up issue adds support (explicitly out of scope here)

## Implementation Steps

1. Update Phase 4 child issue draft template in `SKILL.md` to include `parent_issue` in frontmatter
2. Update Phase 6 step 2 wording to specify the exact field name and format
3. Verify the body `## Parent Issue` section is preserved (both representations coexist)

## Impact

- **Priority**: P3 — Improves machine-readability and tooling consistency; no blocking impact
- **Effort**: Small — Two targeted edits to one SKILL.md file
- **Risk**: Low — Additive change, no existing tooling depends on the current (undefined) behavior
- **Breaking Change**: No

## Scope Boundaries

- Out of scope: updating `ll-issues` or `ll-deps` to consume `parent_issue` (separate issue)
- Out of scope: retroactively adding `parent_issue` to existing child issues created before this fix
- Out of scope: changing the `## Parent Issue` body section format

## Success Metrics

- All new child issues from `issue-size-review` include `parent_issue` in frontmatter: 0% → 100%
- SKILL.md Phase 4 template and Phase 6 step 2 unambiguously name the field and format (verifiable by reading the file)

## Labels

`enhancement`, `issue-size-review`, `frontmatter`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-02T15:42:39 - `9af83f74-9a87-4225-aae0-40159b7f2c9f.jsonl`
- `/ll:confidence-check` - 2026-05-02T16:00:00Z - `1a9c71c0-adf7-40bc-837d-16a2416a35a6.jsonl`
- `/ll:refine-issue` - 2026-05-02T15:29:43 - `b933433e-a2ea-4542-b73a-fc38fe8430f2.jsonl`
- `/ll:format-issue` - 2026-05-02T15:23:28 - `9e175d4b-c038-412d-b640-89e2a9e307d0.jsonl`
- `/ll:capture-issue` - 2026-05-02T15:21:00Z - `1002d85e-8f72-4c5a-a1cd-606b98a6a4f5.jsonl`

---

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-05-02
- **Changes**: Two targeted edits to `skills/issue-size-review/SKILL.md`:
  1. Phase 4 draft template: added full frontmatter block with `parent_issue: [PARENT-ID]` before the `#` heading
  2. Phase 6 step 2: replaced vague "parent reference in frontmatter" with explicit `parent_issue: [PARENT-ID]` field name, format (bare issue ID), and machine-readability rationale

**Closed** | Created: 2026-05-02 | Completed: 2026-05-02 | Priority: P3
