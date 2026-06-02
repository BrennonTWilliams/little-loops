---
id: ENH-1802
title: audit-issue-conflicts re-appends Scope Boundary section on every run
type: ENH
priority: P3
status: done
captured_at: '2026-05-29T20:55:00Z'
completed_at: '2026-05-31T21:25:20Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
labels:
- enhancement
- skills
- audit-issue-conflicts
- idempotency
parent: EPIC-1745
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1802: audit-issue-conflicts re-appends Scope Boundary section on every run

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 4b's `split / update_scope` action appends a `## Scope Boundary` section to affected issue files without checking whether a prior audit run already added one. Repeated runs that surface the same scope-overlap conflict accumulate duplicate sections.

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md` Phase 4b unconditionally appends `## Scope Boundary` and `## Scope Addition` sections to affected issue files. When the same scope-overlap conflict resurfaces on a later audit run, a second identical section is appended, bloating the issue file with duplicate content.

## Reproduction

1. Run `/ll:audit-issue-conflicts`, approve a `split/update_scope` recommendation on ISSUE-X — appends a `## Scope Boundary` section
2. On a later run, the same conflict re-surfaces (because neither issue changed enough to dissolve it)
3. Approve again — a second identical `## Scope Boundary` section is appended

Observed in this run on 2026-05-29: ENH-1617 already had a Scope Boundaries section from a 2026-05-23 audit run with verbatim the recommendation this run produced. I detected the duplicate manually and skipped the body edit. Following the skill spec would have appended a second copy.

## Expected Behavior

Before appending, the skill scans the target file for an existing audit-authored Scope Boundary / Scope Addition note. If found and the proposed content matches (or is a superset), the skill skips the edit and logs `[idempotent: ScopeBoundary already present from <prior-audit-date>]`.

## Motivation

This enhancement would:
- Prevent issue file bloat from repeated `/ll:audit-issue-conflicts` runs on the same backlog
- Improve audit reliability by making Phase 4b actions safe to re-run
- Reduce manual cleanup effort — users shouldn't need to check for and remove duplicate sections

## Root Cause

`skills/audit-issue-conflicts/SKILL.md` Phase 4b lines 326–333 unconditionally append:

```markdown
---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): …
```

No pre-check. The `merge / deprecate` path has the same issue (appends `## Scope Addition` unconditionally).

## Proposed Solution

Before each Phase 4b append, grep the target file for an existing `## Scope Boundary` / `## Scope Addition` section authored by `/ll:audit-issue-conflicts`. If present:
- If the body of that section already mentions the conflicting issue ID → skip the append, log "idempotent skip"
- If not → append a follow-up paragraph inside the existing section instead of opening a duplicate section

Same logic for `## Scope Addition`, `## Resolution`, and any other audit-authored body section.

## Implementation Steps

1. **Add prose idempotency rules to Phase 4b in `skills/audit-issue-conflicts/SKILL.md`** (following the `decide-issue/SKILL.md:309` pattern):
   - Before `## Scope Addition` append (line 327): add rule — "Before appending, read the kept issue file and check if `## Scope Addition` already contains `[CLOSED-ID]`. If found, skip the append and log `[idempotent: Scope Addition for CLOSED-ID already present]`."
   - Before `## Resolution` append (line 340): add rule — "Before appending, check if `## Resolution` is already present in the closed issue file. If found, skip and log `[idempotent: Resolution already present]`."
   - Before `## Scope Boundary` append (line 390): add rule — "Before appending to each affected issue, check if `## Scope Boundary` is already present and already references `[OTHER-ID]`. If found, skip and log `[idempotent: Scope Boundary for OTHER-ID already present]`."

2. **Update the Phase 4b report output template** to distinguish "Applied" from "Skipped (idempotent)" outcomes (per Acceptance Criteria).

3. **Add doc-wiring test to `scripts/tests/test_audit_issue_conflicts_skill.py`** (following `test_decide_issue_skill.py:190`):
   ```python
   def test_phase4b_idempotency_guard_present(self) -> None:
       """Phase 4b must document idempotency rule for Scope Boundary/Addition/Resolution (ENH-1802)."""
       content = SKILL_FILE.read_text()
       phase4b_start = content.index("## Phase 4b")
       phase5_start = content.index("## Phase 5")
       phase4b_text = content[phase4b_start:phase5_start]
       assert "idempotent" in phase4b_text.lower(), (
           "Phase 4b must document idempotency pre-check for audit-authored section appends"
       )
   ```

4. **Run `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py -v`** to confirm the new test passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `CHANGELOG.md` — add `### Fixed` entry for ENH-1802 under the current release section (follow pattern of BUG-1799 / BUG-1800 entries under `## [1.113.0]`)

## Acceptance Criteria

- Running `/ll:audit-issue-conflicts` twice on an unchanged backlog produces zero duplicate Scope Boundary / Scope Addition sections
- Final report distinguishes "Applied" from "Skipped (idempotent)" outcomes
- Pytest fixture covers the double-run case

## Scope Boundaries

- **In scope**: Add idempotency pre-check to Phase 4b append operations (`split/update_scope`, `merge/deprecate`), covering Scope Boundary, Scope Addition, and Resolution sections
- **Out of scope**: Full deduplication of all audit-authored content across all phases; changes to non-audit skills

## Success Metrics

- Duplicate Scope Boundary/Scope Addition sections after 2 audit runs on unchanged backlog: **0**
- Final report distinguishes "Applied" from "Skipped (idempotent)" outcomes
- Pytest fixture covers the double-run idempotency case

## API/Interface

N/A — No public API changes. Internal skill logic update only.

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 4b: add prose idempotency rule before each unconditional append:
  - `## Scope Addition` append: lines 327–338 (merge/deprecate, kept issue)
  - `## Resolution` append: lines 340–352 (merge/deprecate, closed issue)
  - `## Scope Boundary` append: lines 390–399 (split/update_scope, each affected issue)

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — add doc-wiring test asserting idempotency prose exists in Phase 4b (follows pattern in `test_audit_issue_conflicts_skill.py:62` for Phase 5 and `test_decide_issue_skill.py:190` for decide-issue)
- No new fixture-based double-run tests needed: doc-wiring test is the established pattern for skill files

### Similar Patterns

#### Closest analogue — prose idempotency rule in a skill file
- `skills/decide-issue/SKILL.md:309` — `**Idempotency rule**: if the issue already contains a \`### Decision Rationale\` section, skip the annotation write and log \`⚠ Decision already annotated — skipping annotation (idempotent)\`.`
- `skills/decide-issue/SKILL.md:324` — second idempotency rule guarding frontmatter write
- `skills/init/SKILL.md:590–593` — prose duplicate guard: "check whether `## little-loops` section is already present; if found, skip writing and log `Skipped: CLAUDE.md already contains a ## little-loops section`"
- Doc-wiring test: `scripts/tests/test_decide_issue_skill.py:190` — asserts "Idempotency" text appears in Phase 7

#### Reference implementations for the underlying check logic
- `scripts/little_loops/issue_lifecycle.py:280` — `_prepare_issue_content()`: simplest pattern — `if "## Resolution" not in content: content += resolution` (bare `not in` guard)
- `scripts/little_loops/session_log.py:114–129` — `append_session_log_entry()`: section-exists check + `rfind("## Session Log\n")` to insert within section rather than create duplicate
- `scripts/little_loops/issue_discovery/search.py:485–491` — `update_existing_issue()`: `if f"## {section_name}" not in content:` with logger warning on skip

### Callers / Entry Points
- `/ll:audit-issue-conflicts` slash command — sole entry point; no Python callers or importers

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add `### Fixed` entry for ENH-1802 under current release section (BUG-1799 and BUG-1800 precedents already under `## [1.113.0] - 2026-05-31`) [Agent 2 finding]

## Impact

- **Priority**: P3 — quality-of-life; doesn't break the issue but bloats files over time
- **Effort**: Small — helper + pre-check in 2–3 Phase 4b sites
- **Risk**: Low
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-05-31T21:25:31 - `96597c52-680e-4455-b715-f1845a4e8889.jsonl`
- `/ll:ready-issue` - 2026-05-31T21:23:38 - `dfcabcfb-6151-4ce1-919e-6296517f5b3f.jsonl`
- `/ll:confidence-check` - 2026-05-31T22:00:00 - `aade4da1-60b0-46d7-b294-7d72f9c03e68.jsonl`
- `/ll:wire-issue` - 2026-05-31T21:20:16 - `530e032e-6ec4-4e57-b963-0844a5d722fc.jsonl`
- `/ll:refine-issue` - 2026-05-31T21:16:28 - `ed8bf88c-845f-4d06-bbaa-2e9b3f0f286d.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T21:12:47 - `d42814df-045f-41ae-b065-5f4d670ef04d.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P3
