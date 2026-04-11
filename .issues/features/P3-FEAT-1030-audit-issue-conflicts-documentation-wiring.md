---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 85
outcome_confidence: 80
parent_issue: FEAT-1029
blocked_by: FEAT-1028
testable: false
---

# FEAT-1030: audit-issue-conflicts — Documentation Wiring

## Summary

Update all registry files and documentation to expose the new `audit-issue-conflicts` skill after FEAT-1028 creates it. Depends on FEAT-1028 (skill file must exist first).

## Current Behavior

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill exists on disk but is absent from every documentation and discovery surface: not listed in `commands/help.md`, `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/reference/COMMANDS.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, or `.claude/CLAUDE.md`. The skill count reads 25 everywhere. Running `ll-verify-docs` fails with a count mismatch.

## Expected Behavior

The skill appears in all documentation surfaces under the "Issue Refinement" capability group. Skill count reads 26 in `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md`. Running `ll-verify-docs` passes. Users can discover the skill via `/ll:help` and all relevant command tables.

## Motivation

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill exists but is invisible — absent from help listings, README tables, all documentation surfaces, and uncovered by `ll-verify-docs`. This issue ensures full discoverability and registry consistency.

## Use Case

**Who**: A little-loops developer or plugin maintainer

**Context**: After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill works but is absent from every discovery surface.

**Goal**: Wire the new skill into all documentation files so users can find it and `ll-verify-docs` passes.

**Outcome**: `audit-issue-conflicts` appears in all expected places; skill count bumped 25→26 everywhere; `ll-verify-docs` passes.

## Parent Issue

Decomposed from FEAT-1029: audit-issue-conflicts — Wiring, Docs, and Tests

## Acceptance Criteria

- [ ] `commands/help.md` — `/ll:audit-issue-conflicts` added to ISSUE REFINEMENT block (lines 44–81) and Quick Reference Table (`Issue Refinement` entry, ~line 254)
- [ ] `README.md` — skill count bumped `25 → 26` (line 89); `/ll:audit-issue-conflicts` row added to Issue Refinement command table (lines 108–124); `/ll:audit-issue-conflicts`^ row added to Skills table (lines 207–235) with capability group "Issue Refinement"
- [ ] `CONTRIBUTING.md` — skill count bumped `25 → 26` (line 125); `audit-issue-conflicts/` added to skill directory tree after `audit-docs/`
- [ ] `docs/ARCHITECTURE.md` — skill count bumped `25 → 26` at lines 26 and 99; `├── audit-issue-conflicts/` added between `audit-claude-config/` and `audit-docs/` (lines 104–107)
- [ ] `docs/reference/COMMANDS.md` — `audit-issue-conflicts` in `--dry-run` consumer list (line 14) and `--auto` consumer list (line 15); `### /ll:audit-issue-conflicts` subsection added after `/ll:tradeoff-review-issues` (~line 204)
- [ ] `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `audit-issue-conflicts` added to "Plan a Feature Sprint" recipe (~line 484) as step 3.5 before `tradeoff-review-issues`; current steps 4–11 renumbered to 5–12
- [ ] `.claude/CLAUDE.md` — `audit-issue-conflicts`^ added to Issue Refinement section; skill count bumped `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
- [ ] `ll-verify-docs` passes after all changes

## Proposed Solution

### Wiring Steps

Work through each file in order. All changes are mechanical and well-specified:

**`commands/help.md`**
- Add `/ll:audit-issue-conflicts` entry to ISSUE REFINEMENT block (lines 44–81)
- Add entry to Quick Reference Table (`Issue Refinement:` entry, ~line 254)

**`README.md`**
- Bump skill count `25 → 26` at line 89
- Add `/ll:audit-issue-conflicts` row to Issue Refinement command table (lines 108–123)
- Add `/ll:audit-issue-conflicts`^ row to Skills table (lines 207–235, three-column format with `^` suffix and "Issue Refinement" capability group)

**`CONTRIBUTING.md`**
- Bump skill count `25 → 26` at line 125
- Add `audit-issue-conflicts/` to skill directory tree after `audit-docs/` (lines 125–148)

**`docs/ARCHITECTURE.md`**
- Bump skill count `25 → 26` at lines 26 and 99
- Add `├── audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` (lines 104–107)

**`docs/reference/COMMANDS.md`**
- Append `, \`audit-issue-conflicts\`` to `--dry-run` consumer cell (line 14)
- Append `, \`audit-issue-conflicts\`` to `--auto` consumer cell (line 15)
- Add `### /ll:audit-issue-conflicts` subsection after `/ll:tradeoff-review-issues` (~line 204):
  ```
  Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types detected: requirement contradictions, conflicting objectives, architectural disagreements, and scope overlaps.

  **Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written)

  **Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"
  ```

**`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`**
- "Plan a Feature Sprint" heading at line 475; recipe block runs lines 479–492 with steps 1–11
- Insert `/ll:audit-issue-conflicts` between step 3 (`prioritize-issues`) and current step 4 (`tradeoff-review-issues`), renumbering all subsequent steps (4→5, 5→6, … 11→12)

**`.claude/CLAUDE.md`**
- Add `audit-issue-conflicts`^ to Issue Refinement section in command list
- Bump skill count `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
- Note: `ll-verify-docs` does NOT scan `.claude/CLAUDE.md`, so this drift is silent — must be caught manually

## Integration Map

### Files to Modify

- `commands/help.md` — ISSUE REFINEMENT block + Quick Reference Table
- `README.md` — skill count (line 89) + Issue Refinement command table row (lines 108–124) + Skills table row (lines 207–235)
- `CONTRIBUTING.md` — skill count + directory tree entry
- `docs/ARCHITECTURE.md` — skill count (×2) + directory listing entry
- `docs/reference/COMMANDS.md` — `--dry-run` list (line 14) + `--auto` list (line 15) + new subsection after `tradeoff-review-issues`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "Plan a Feature Sprint" recipe (insert at step 4, renumber 4–11 to 5–12)
- `.claude/CLAUDE.md` — command list (Issue Refinement section) + skill count bump

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/docs-sync.yaml` — FSM `verify_docs` state calls `ll-verify-docs 2>&1`; `fix_docs` state prompts on skill-count mismatches. Will surface a count mismatch while FEAT-1030 is in progress (after FEAT-1028 lands). Not a file to modify — informational only. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — describes `ll-verify-docs` behavior and skill count verification. Check for any hardcoded `25` count reference; if present, bump to `26`. Not in `DOC_FILES` so `ll-verify-docs` will not auto-fix it — must be verified manually. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py` — existing coverage for `doc_counts.py`; all tests use `tmp_path` isolation with synthetic counts. **No changes needed** — will not break regardless of real skill count. [Agent 3 finding]
- `scripts/tests/test_cli_docs.py` — existing coverage for `cli/docs.py` (the `ll-verify-docs` CLI entry); mocks `verify_documentation`. **No changes needed.** [Agent 3 finding]
- **No test in the suite runs against the real project root** — the acceptance criterion `ll-verify-docs passes` (step 9) is the effective integration gate and must be run manually after all edits are complete. [Agent 3 finding]
- **New skill structural test** (`scripts/tests/test_audit_issue_conflicts_skill.py`) — scoped to FEAT-1031, not this issue. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Blocker status**: `skills/audit-issue-conflicts/SKILL.md` does NOT exist — FEAT-1028 is an unmet prerequisite. Do not begin FEAT-1030 implementation until FEAT-1028 is complete and the skill file is on disk.

**Alphabetical ordering correction**: The Acceptance Criteria and Proposed Solution state adding `audit-issue-conflicts/` "between `audit-claude-config/` and `audit-docs/`" in `docs/ARCHITECTURE.md`. This is incorrect — alphabetically `audit-issue-conflicts` sorts AFTER `audit-docs` (`audit-d` < `audit-i`). The correct insertion point is **after `audit-docs/`** in both `CONTRIBUTING.md` and `docs/ARCHITECTURE.md`.

**Line number correction for `docs/reference/COMMANDS.md`**: Acceptance Criteria and Proposed Solution state `--dry-run` is at line 14 and `--auto` at line 15. **This is wrong.** Verified live: `--dry-run` is at **line 13**, `--auto` is at **line 14**.

**`ll-verify-docs` scope** (`scripts/little_loops/doc_counts.py:12-16`): Only checks `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` for numeric skill counts. It does NOT scan `commands/help.md`, `docs/reference/COMMANDS.md`, or `.claude/CLAUDE.md` — those must be updated and verified manually.

**Existing tree inconsistency**: Both `CONTRIBUTING.md:126-148` and `docs/ARCHITECTURE.md:100-157` currently list only 23 skill directories (missing `wire-issue` and `rename-loop` from their trees). After FEAT-1028 and FEAT-1030, the skill count will be 26 on disk but only 24 will be listed in those trees. This is pre-existing drift — document it in the PR but do not fix it as part of this issue.

**Verified exact insertion points** (verified against live files 2026-04-11):

| File | Exact anchor | Insertion |
|------|-------------|-----------|
| `commands/help.md:80` | `ready-issue` block ends line 80; `PLANNING & IMPLEMENTATION` begins line 82 | Insert new entry before line 81 |
| `commands/help.md:254` | Line ends with `` `ready-issue` `` | Append `, \`audit-issue-conflicts\`` |
| `README.md:89` | `25 skills` | Increment `25` → `26` |
| `README.md:123-124` | `wire-issue` row at line 123; blank line 124 | Insert new row between 123 and 124 |
| `README.md:235-236` | `wire-issue`^ at line 235; blank line 236 | Insert new row between 235 and 236 |
| `CONTRIBUTING.md:125` | `25 skill definitions` | Increment `25` → `26` |
| `CONTRIBUTING.md:129-130` | `audit-docs/` at line 129; `capture-issue/` at line 130 | Insert between 129 and 130 |
| `docs/ARCHITECTURE.md:26` | `25 composable skills` (in diagram) | Increment `25` → `26` |
| `docs/ARCHITECTURE.md:99` | `# 25 skill definitions` | Increment `25` → `26` |
| `docs/ARCHITECTURE.md:109-110` | `audit-docs/` block ends line 109; `capture-issue/` at line 110 | Insert 2-line entry between 109 and 110 |
| `docs/reference/COMMANDS.md:13` | `--dry-run` consumer list (NOT line 14) | Append `, \`audit-issue-conflicts\`` |
| `docs/reference/COMMANDS.md:14` | `--auto` consumer list (NOT line 15) | Append `, \`audit-issue-conflicts\`` |
| `docs/reference/COMMANDS.md:207-209` | `tradeoff-review-issues` content ends line 207; `### /ll:product-analyzer` at line 209 | Insert new subsection between 207 and 209 |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:482-483` | step 3=`prioritize-issues` at line 482; step 4=`tradeoff-review-issues` at line 483 | Insert new step 4 at line 483, renumber old 4–11 to 5–12 |
| `.claude/CLAUDE.md:38` | `# Skill definitions (25 skills)` | Increment `25` → `26` |
| `.claude/CLAUDE.md:52` | Issue Refinement line ends with `` `map-dependencies`^ `` | Append `, \`audit-issue-conflicts\`^` |

**Exact current content of `docs/reference/COMMANDS.md:13-14`**:
```
| `--dry-run` | Show what would happen without making changes | `manage-issue`, `align-issues`, `refine-issue`, `format-issue`, `manage-release` |
| `--auto` | Non-interactive mode (no prompts) | `commit`, `refine-issue`, `prioritize-issues`, `format-issue`, `confidence-check`, `verify-issues`, `map-dependencies`, `issue-size-review` |
```

**Exact current content of `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` recipe steps (lines 479–492)**:
```
1. /ll:scan-codebase               ← find issues you didn't know existed
   /ll:scan-product                ← find feature gaps against goals
2. /ll:normalize-issues            ← fix any naming problems
3. /ll:prioritize-issues           ← assign P0-P5 to all issues
4. /ll:tradeoff-review-issues      ← prune low-value issues
5. /ll:format-issue --auto         ← promote survivors to v2.0 template
6. /ll:refine-issue [issue-id]     ← enrich with codebase research (run per issue)
7. /ll:verify-issues               ← test claims against code
8. /ll:ready-issue                 ← validate quality gate
9. /ll:map-dependencies            ← identify ordering constraints
10. /ll:issue-size-review          ← decompose anything too large
11. /ll:create-sprint              ← curate and sequence the sprint
    ll-sprint run sprint-name      ← execute
```

**Pattern templates for new entries** (verified against live file content):

`commands/help.md` entry (modeled on `wire-issue` at lines 66-69):
```
/ll:audit-issue-conflicts [flags]
    Scan all open issues for conflicting requirements, objectives, or
    architectural decisions — outputs a ranked conflict report
    Flags: --auto (non-interactive), --dry-run (report only)
```

`README.md` command table row (modeled on `wire-issue` at line 123):
```
| `/ll:audit-issue-conflicts` | Scan open issues for conflicting requirements, objectives, or architectural decisions |
```

`README.md` Skills table row (modeled on `wire-issue`^ at line 235):
```
| `audit-issue-conflicts`^     | Issue Refinement           | Scan open issues for conflicting requirements and architectural decisions |
```

`docs/ARCHITECTURE.md` tree entry (2-line block, no templates.md — modeled on `analyze-loop` at lines 102-103):
```
│   ├── audit-issue-conflicts/ # User-invoked
│   │   └── SKILL.md
```

`CONTRIBUTING.md` tree entry (modeled on `audit-docs/` at line 129):
```
│   ├── audit-issue-conflicts/            # Detect conflicts across open issues
```

`docs/reference/COMMANDS.md` subsection (modeled on `tradeoff-review-issues` at lines 204-207):
```markdown
### `/ll:audit-issue-conflicts`
Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types: requirement contradictions, conflicting objectives, architectural disagreements, scope overlaps.

**Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written)

**Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"
```

## Implementation Steps

1. **Verify FEAT-1028 is complete** — confirm `skills/audit-issue-conflicts/SKILL.md` exists before proceeding
2. **Update `commands/help.md`** — ISSUE REFINEMENT block entry + Quick Reference Table entry
3. **Update `README.md`** — skill count `25→26`; Issue Refinement command table row; Skills table row
4. **Update `CONTRIBUTING.md`** — skill count `25→26`; directory tree entry
5. **Update `docs/ARCHITECTURE.md`** — skill count `25→26` at lines 26 and 99; directory listing entry
6. **Update `docs/reference/COMMANDS.md`** — `--dry-run` list, `--auto` list, new subsection
7. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — insert step 4, renumber 4–11 to 5–12
8. **Update `.claude/CLAUDE.md`** — `audit-issue-conflicts`^ to Issue Refinement section; skill count bump
9. **Run `ll-verify-docs`** — confirm passes

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Check `docs/reference/CLI.md`** — scan for any hardcoded `25` skill count; bump to `26` if present. Not auto-fixed by `ll-verify-docs`.

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Small - Mechanical wiring; no logic to implement
- **Risk**: Very Low - Documentation changes only
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `wiring`, `docs`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-04-11T05:33:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/662113a3-6b97-409a-b517-fd8a66d0944f.jsonl`
- `/ll:format-issue` - 2026-04-11T05:28:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b982ec8-95f6-4b13-b508-3b8cbabc3437.jsonl`
- `/ll:refine-issue` - 2026-04-11T05:26:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4511a1b9-2134-43ca-95d4-393029988442.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
- `/ll:wire-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4511a1b9-2134-43ca-95d4-393029988442.jsonl`
