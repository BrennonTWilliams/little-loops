---
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 43
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/ARCHITECTURE.md` — add `rubric.md` (or `agent-prompts.md`) entries under `confidence-check/`, `go-no-go/`, and `issue-size-review/` directory trees; add `audit-criteria.md` to `audit-claude-config/` block alongside existing `report-template.md`
7. Update `docs/reference/CONFIGURATION.md` — add new section documenting `.ll/rubrics/<skill>.md` project override path, fallback behavior, and FEAT-948 integration point
8. Create `scripts/tests/test_confidence_check_skill.py` — verify SKILL.md references `rubric.md` and the file exists; assert rubric contains readiness + outcome-confidence criterion headings; follow pattern in `scripts/tests/test_improve_claude_md_skill.py`
9. Create `scripts/tests/test_issue_size_review_skill.py` — same pattern; assert `rubric.md` exists and contains scoring heuristic table and threshold section
10. Create `scripts/tests/test_go_no_go_skill.py` — same pattern; assert `rubric.md` exists and contains judge verdict taxonomy (CLOSE/REFINE/SKIP)
11. Create `scripts/tests/test_audit_claude_config_skill.py` — verify SKILL.md references `audit-criteria.md` and it exists; also assert `report-template.md` is still referenced after refactor
12. Review `docs/reference/COMMANDS.md:237-243`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:336-337`, and `docs/guides/LOOPS_GUIDE.md:332` — update threshold values and criterion names only if they change during rubric extraction; no-op if defaults are preserved verbatim

## API/Interface

New files introduced:
- `skills/confidence-check/rubric.md`
- `skills/issue-size-review/rubric.md`
- `skills/go-no-go/rubric.md`
- `skills/audit-claude-config/rubric.md`

New project override path:
- `.ll/rubrics/<skill-name>.md`

No Python code changes expected. Load instructions are Markdown-level directives in SKILL.md.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — remove inline rubric (lines 181–376), add load-rubric directive
- `skills/issue-size-review/SKILL.md` — remove inline scoring heuristic table (lines 112–124), add load-rubric directive
- `skills/go-no-go/SKILL.md` — remove adversarial review dimensions (lines 160–335), add load-rubric directive
- `skills/audit-claude-config/SKILL.md` — remove inline audit criteria, add load-rubric directive

### New Files (to create)
- `skills/confidence-check/rubric.md` — default readiness + outcome-confidence rubric
- `skills/issue-size-review/rubric.md` — default 11-point scoring heuristic table + thresholds
- `skills/go-no-go/rubric.md` — default adversarial review dimensions and novelty heuristic
- `skills/audit-claude-config/rubric.md` — default audit pass/fail criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected and expanded line ranges with insertion points:**

| Skill | Rubric Content | Exact Lines | Insertion Point |
|---|---|---|---|
| `confidence-check/SKILL.md` | 9 criteria blocks (5 readiness × 0-20pts + 4 outcome × 0-25pts) + 2 threshold tables | Lines 181–373 (criteria); 380–394 (threshold tables) | Insert `See [rubric.md](rubric.md) for all criterion definitions and scoring tables.` at line 180, before `#### Criterion 1` |
| `issue-size-review/SKILL.md` | 5-row scoring heuristics table (+2/+2/+3/+2/+2 per signal, max 11) + 4-tier threshold table | Lines 112–124 (scoring table); 326–332 (threshold section) | Insert `See [rubric.md](rubric.md) for scoring heuristics and size thresholds.` at line 112 (replaces table); line 326 section also moves to rubric |
| `go-no-go/SKILL.md` | **Agent prompt templates** (not a scoring table): Pro agent prompt (6 directives + 5 output sections), Con agent prompt (6 directives + 5 output sections), Judge prompt (4 dimensions + CLOSE/REFINE/SKIP verdict taxonomy) | Lines 148–290 | Insert `Read [rubric.md](rubric.md) for the pro, con, and judge agent prompt templates.` after line 143 (after `**IMPORTANT**` note) |
| `audit-claude-config/SKILL.md` | Distributed within 3 Task prompts: CLAUDE.md audit dimensions (lines 126–186), plugin component checklists (lines 195–229), settings key validation list + deprecated/managed-only keys (lines 262–330) | Lines 126–186, 195–229, 262–330 (non-contiguous) | Reference inside each Task prompt; output format already externalized to `report-template.md` |

**Naming note for `audit-claude-config`:** This skill already has a `report-template.md` companion. The new companion should be named `audit-criteria.md` (not `rubric.md`) to distinguish criteria (what to check) from report format (how to output). Rename accordingly in New Files list above.

**Naming note for `go-no-go`:** The "rubric" is three verbatim agent prompt templates with a verdict taxonomy (`CLOSE`/`REFINE`/`SKIP`), not a scored table. Consider naming `agent-prompts.md` for clarity, or keep `rubric.md` for consistency with other skills. Either works; rubric.md is simpler.

### Dependent Files (Callers/Importers)
- N/A — rubric loading is Markdown-level directive; no Python imports or callers to update

### Similar Patterns
- `skills/format-issue/templates/` — existing example of companion artifact files per skill
- `skills/format-issue/templates.md` — pattern for skill-level reference documents
- `skills/review-loop/SKILL.md:67-69` — **most directly applicable load pattern**: `Read \`reference.md\` (this companion file) now. You will need the check definitions in Step 2b.` — explicit imperative load with stated purpose; follow this idiom for rubric loading
- `skills/audit-claude-config/report-template.md` — confirms companion file externalization works in audit-config specifically; new `audit-criteria.md` follows the same convention already established here
- `skills/improve-claude-md/algorithm.md`, `skills/configure/areas.md` — additional examples of named companion files beyond `templates.md` / `reference.md` naming

### Tests
- Manual verification per Verification section (rubric extraction, override, fallback)
- No automated test suite for Markdown rubric loading

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — new test file needed: verify `SKILL.md` references `rubric.md` and `rubric.md` exists; follow pattern in `scripts/tests/test_improve_claude_md_skill.py`
- `scripts/tests/test_issue_size_review_skill.py` — new test file needed: same pattern; assert `rubric.md` exists and contains scoring heuristic table
- `scripts/tests/test_go_no_go_skill.py` — new test file needed: same pattern; assert `rubric.md` (or `agent-prompts.md`) exists and contains judge verdict taxonomy
- `scripts/tests/test_audit_claude_config_skill.py` — new test file needed: verify `SKILL.md` references `audit-criteria.md`, `audit-criteria.md` exists, and `report-template.md` is still referenced after refactor
- `scripts/tests/test_skill_expander.py` — existing; no changes needed (relative companion-file link expansion already covered by `test_converts_relative_refs` at line 122)

### Documentation
- `docs/reference/` or `docs/guides/` — new section explaining rubric override system and `.ll/rubrics/` convention
- Reference from FEAT-948 issue as integration target

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:117-118,133-134,141-142` — directory tree lists only `SKILL.md` for `confidence-check`, `go-no-go`, `issue-size-review`; must add `rubric.md` (or `agent-prompts.md`) entries; `audit-claude-config` block (lines 105-106) already shows `report-template.md` and needs `audit-criteria.md` added alongside it
- `docs/reference/CONFIGURATION.md` — no current section for `.ll/rubrics/` override convention; add new section documenting the project override path, fallback behavior, and FEAT-948 integration point
- `docs/reference/COMMANDS.md:237-243` — documents `issue-size-review` thresholds ("1–10 scale", "≥8 = Very Large") as hard facts; **conditional**: update only if the default `rubric.md` changes these threshold values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:336-337` — names `confidence-check` criterion labels verbatim; **conditional**: update only if criterion names are reorganized during extraction
- `docs/guides/LOOPS_GUIDE.md:332` — hard-codes "Very Large issues (score ≥ 8)"; **conditional**: update only if the default `issue-size-review/rubric.md` changes the decomposition threshold

### Configuration
- N/A — no Python config changes; `.ll/rubrics/<skill-name>.md` is the project-level override path (gitignored or committed per project)

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
- ENH-494: Enforce 500-line skill limit with flat companion files (companion file pattern enforcement — the externalization this ENH performs directly supports the 500-line goal)

---

## Impact

- **Priority**: P3 - Medium priority; no current breakage, but blocks FEAT-948 integration
- **Effort**: Medium - Four skills to refactor; new file convention to document
- **Risk**: Low - Rubric extraction is content-only; no Python changes; fallback to defaults keeps behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `feat-948-integration`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-12
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- ENH-1055: Extract rubrics for confidence-check and issue-size-review
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config
- ENH-1057: Documentation updates for rubric externalization system

---

## Status

**Decomposed** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-04-12T15:58:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96afaf36-7dd4-49ed-8232-94d176c382a2.jsonl`
- `/ll:refine-issue` - 2026-04-12T15:52:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86b7b5dd-cea4-46f8-bb9b-d32d83b0a4cc.jsonl`
- `/ll:format-issue` - 2026-04-12T15:49:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b96ea76c-80f0-4bd0-9834-8417deac9b30.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15f15737-f071-4acd-b0d6-e63041f51d03.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
