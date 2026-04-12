---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1053: Externalize scoring rubrics in audit/review skills into project-tailorable artifacts

## Summary

Core `/ll:` skills that score, audit, or review issues — `confidence-check`, `issue-size-review`, `go-no-go`, and `audit-claude-config` — embed their scoring rubrics, criteria tables, and checklists directly inside `SKILL.md`. Extracting these into separate companion artifacts (e.g., `rubric.md` or `criteria.md` per skill) would allow projects to tailor them without touching the shared skill definition. Once FEAT-948 (rules-and-decisions log) is complete, rubric files can also be kept consistent with and updated from each project's rules and decisions.

## Motivation

Rubrics embedded in `SKILL.md` files have two friction points:

1. **Non-tailorable**: A project may want to raise the confidence threshold for FSM routing, add domain-specific size-scoring heuristics, or replace the default go/no-go checklist with org-specific review criteria. Today the only option is to fork the skill.
2. **Drift from project decisions**: When FEAT-948 lands, ll will maintain a rules-and-decisions log per project. Scores and criteria that live inside monolithic `SKILL.md` files cannot be automatically synchronized with those project-level decisions.

Extracting rubrics into separate files solves both problems: projects can override per-skill rubrics via `.ll/rubrics/<skill>.md`, and FEAT-948 can update those files as rules evolve.

## Current Behavior

All scoring logic is inline in `SKILL.md`:

- **`confidence-check`**: 5 readiness criteria (0–20 pts each) + 4 outcome-confidence criteria (0–25 pts each) defined at `SKILL.md:181–376`
- **`issue-size-review`**: 11-point scoring heuristic table defined inline; thresholds (`≥5 = Large`, `≥8 = Very Large`) hardcoded at `SKILL.md:112–124`
- **`go-no-go`**: adversarial review dimensions (novelty heuristic, pro/con scoring) embedded across `SKILL.md:160–335`
- **`audit-claude-config`**: audit pass/fail criteria embedded in skill body

Projects cannot override any of these without modifying the plugin itself.

## Expected Behavior

Each affected skill reads its rubric from a companion artifact file. A project-level override in `.ll/rubrics/<skill-name>.md` (or equivalent) takes precedence over the default. The SKILL.md contains only the logic for *loading* and *applying* the rubric, not the rubric itself.

```
skills/confidence-check/SKILL.md    ← logic only; loads rubric
skills/confidence-check/rubric.md   ← default criteria (checked in)
.ll/rubrics/confidence-check.md     ← project override (gitignored or committed per project)
```

When FEAT-948 is complete, project rules and decisions can update `.ll/rubrics/<skill>.md` automatically.

## Scope Boundaries

- **In scope**: Extracting rubric/criteria content from `confidence-check`, `issue-size-review`, `go-no-go`, and `audit-claude-config` into companion files; adding load-rubric instructions to each affected SKILL.md; defining the `.ll/rubrics/` override convention; documenting the format
- **Out of scope**: Implementing the FEAT-948 integration itself (that is FEAT-948's responsibility); adding rubrics for skills that do not have scoring/criteria (e.g., `commit`, `capture-issue`); building a UI for rubric editing

## Success Metrics

- Each affected skill reads its rubric from a file, not from inline SKILL.md content
- Deleting `.ll/rubrics/<skill>.md` falls back to the default companion file transparently
- A project can customize the `confidence-check` thresholds or `issue-size-review` heuristic without modifying any file in `skills/`
- FEAT-948 issue references this ENH as the integration target for rubric synchronization

## Implementation Steps

### 1. Audit affected skills

Identify all skills with inline scoring rubrics, checklists, or criteria tables. Confirmed candidates:
- `skills/confidence-check/SKILL.md` — readiness + outcome confidence rubrics
- `skills/issue-size-review/SKILL.md` — size scoring heuristic table + thresholds
- `skills/go-no-go/SKILL.md` — adversarial review dimensions and novelty heuristic
- `skills/audit-claude-config/SKILL.md` — audit pass/fail criteria

### 2. Define rubric artifact format

Establish a canonical format for rubric files (Markdown tables or YAML frontmatter + sections). Document the override convention:
- Default: `skills/<name>/rubric.md` (shipped with the plugin)
- Project override: `.ll/rubrics/<skill-name>.md`

### 3. Extract rubrics per skill

For each affected skill:
- Move criteria/rubric content into `skills/<name>/rubric.md`
- Replace the inline content in SKILL.md with a load instruction:
  ```
  Load rubric from: `.ll/rubrics/confidence-check.md` (if exists) else `skills/confidence-check/rubric.md`
  ```

### 4. Update skill instructions

Update each SKILL.md to:
- Reference the rubric file at the point where criteria are applied
- Document the project override path

### 5. Document in docs/

Add a section to `docs/reference/` or `docs/guides/` explaining the rubric override system and FEAT-948 integration point.

## API/Interface

New files introduced:
- `skills/confidence-check/rubric.md`
- `skills/issue-size-review/rubric.md`
- `skills/go-no-go/rubric.md`
- `skills/audit-claude-config/rubric.md`

New project override path:
- `.ll/rubrics/<skill-name>.md`

No Python code changes expected. Load instructions are Markdown-level directives in SKILL.md.

## Edge Cases

- **Missing override file**: If `.ll/rubrics/<skill>.md` doesn't exist, fall back silently to the default companion file — no error.
- **Partial rubric overrides**: If a project only overrides some criteria, decide whether the file must be complete (safest) or supports partial merging (more flexible but complex). Default to complete-file replacement to avoid partial-merge bugs.
- **FEAT-948 integration**: Once FEAT-948 writes project rules, it should update `.ll/rubrics/` files — not `skills/` files. The shipped defaults in `skills/` remain stable.

## Verification

1. For `confidence-check`: delete inline rubric, add `skills/confidence-check/rubric.md`, confirm `/ll:confidence-check` produces identical scores on a known issue
2. Create `.ll/rubrics/issue-size-review.md` with a custom threshold (e.g., `≥4 = Large`) and confirm `/ll:issue-size-review` applies the override
3. Remove `.ll/rubrics/confidence-check.md` and confirm fallback to default with no error
4. Check that all four affected skills pass `/ll:check-code` after the refactor

## Related Issues

- FEAT-948: Rules-and-decisions log for issue compliance (integration target — rubric sync)
- ENH-418: Confidence check type-specific criterion labels and rubrics (completed; narrower fix within one skill — this issue generalizes the pattern)

---

## Impact

- **Priority**: P3 - Medium priority; no current breakage, but blocks FEAT-948 integration
- **Effort**: Medium - Four skills to refactor; new file convention to document
- **Risk**: Low - Rubric extraction is content-only; no Python changes; fallback to defaults keeps behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `feat-948-integration`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15f15737-f071-4acd-b0d6-e63041f51d03.jsonl`
