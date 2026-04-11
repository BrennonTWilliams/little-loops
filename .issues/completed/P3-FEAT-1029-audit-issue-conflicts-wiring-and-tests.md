---
discovered_date: 2026-04-10
discovered_by: issue-size-review
confidence_score: 80
outcome_confidence: 70
parent_issue: FEAT-1027
blocked_by: FEAT-1028
---

# FEAT-1029: audit-issue-conflicts — Wiring, Docs, and Tests

## Summary

Wire the new `audit-issue-conflicts` skill into all registry files and documentation, and write the structural test file. Depends on FEAT-1028 (skill file must exist first).

## Motivation

This feature ensures:
- **Discoverability**: The new `audit-issue-conflicts` skill appears in help, README, and all documentation surfaces so users can find and use it
- **Registry consistency**: Skill count discrepancies across docs are corrected, preventing confusion about the number of available skills
- **Test coverage**: Structural tests verify the skill file's contract, catching regressions if the skill file is removed or malformed

## Use Case

**Who**: A little-loops developer or plugin maintainer

**Context**: After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill exists but is invisible — absent from help listings, README tables, all doc references, and uncovered by tests

**Goal**: Wire the new skill into every discovery surface and add structural tests that verify the skill file's contract

**Outcome**: `audit-issue-conflicts` appears in all expected places; `ll-verify-docs` passes; the 7-assertion test suite confirms the skill file is present and well-formed

## Parent Issue

Decomposed from FEAT-1027: Issue Conflict Audit Skill with Auto-Apply

## Current Behavior

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill works but is absent from:
- `commands/help.md` (hardcoded skill listing)
- `README.md` (skill count + command table)
- `CONTRIBUTING.md` (skill count + directory tree)
- `docs/ARCHITECTURE.md` (skill count + directory listing)
- `docs/reference/COMMANDS.md` (`--auto`/`--dry-run` consumer lists + subsection)
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` ("Plan a Feature Sprint" recipe)
- `.claude/CLAUDE.md` (command list)
- No structural tests exist

## Expected Behavior

All registry files and documentation reflect the new skill. Structural tests verify the skill file's contract.

## Acceptance Criteria

- [ ] `commands/help.md` — `/ll:audit-issue-conflicts` added to ISSUE REFINEMENT block (lines 44–81) and Quick Reference Table (`Issue Refinement` entry, ~line 254)
- [ ] `README.md` — skill count bumped `25 → 26` (line 89); `/ll:audit-issue-conflicts` row added to Issue Refinement command table (lines 108–124); `/ll:audit-issue-conflicts`^ row added to Skills table (lines 207–235) with capability group "Issue Refinement"
- [ ] `CONTRIBUTING.md` — skill count bumped `25 → 26` (line 125); `audit-issue-conflicts/` added to skill directory tree after `audit-docs/`
- [ ] `docs/ARCHITECTURE.md` — skill count bumped `25 → 26` at lines 26 and 99; `├── audit-issue-conflicts/` added between `audit-claude-config/` and `audit-docs/` (lines 104–107)
- [ ] `docs/reference/COMMANDS.md` — `audit-issue-conflicts` in `--dry-run` consumer list (line 14) and `--auto` consumer list (line 15); `### /ll:audit-issue-conflicts` subsection added after `/ll:tradeoff-review-issues` (~line 204)
- [ ] `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `audit-issue-conflicts` added to "Plan a Feature Sprint" recipe (~line 484) as step 3.5 before `tradeoff-review-issues`
- [ ] `.claude/CLAUDE.md` — `audit-issue-conflicts`^ added to Issue Refinement or Meta-Analysis section; skill count bumped `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
- [ ] `scripts/tests/test_audit_issue_conflicts_skill.py` exists and asserts: (1) `skills/audit-issue-conflicts/SKILL.md` exists, (2) `--dry-run` token present, (3) `--auto` token present, (4) severity labels (`high`, `medium`, `low`) present, (5) conflict type tokens (`requirement`, `objective`, `architecture`, `scope`) present, (6) `"No conflicts found"` path documented, (7) `{{config.issues.base_dir}}` glob pattern referenced
- [ ] `ll-verify-docs` passes after all changes

## API/Interface

N/A - No public API changes. This issue is purely documentation wiring and structural test creation.

## Proposed Solution

### Wiring Steps

Work through each file in order. All changes are mechanical and well-specified:

**`commands/help.md`**
- Add `/ll:audit-issue-conflicts` entry to ISSUE REFINEMENT block (lines 44–81)
- Add entry to Quick Reference Table (`Issue Refinement:` entry, ~line 254)

**`README.md`**
- Bump skill count `25 → 26` at line 89
- Add `/ll:audit-issue-conflicts` row to Issue Refinement command table (lines 108–123)

**`CONTRIBUTING.md`**
- Bump skill count `25 → 26` at line 125
- Add `audit-issue-conflicts/` to skill directory tree after `audit-docs/` (lines 125–148)

**`docs/ARCHITECTURE.md`**
- Bump skill count `25 → 26` at lines 26 and 99
- Add `├── audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` (lines 104–107)

**`docs/reference/COMMANDS.md`**
- Append `audit-issue-conflicts` to `--dry-run` consumer list (line 14)
- Append `audit-issue-conflicts` to `--auto` consumer list (line 15)
- Add `### /ll:audit-issue-conflicts` subsection after `/ll:tradeoff-review-issues` (~line 204)
  - Subsection description to use:
    ```
    Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types detected: requirement contradictions, conflicting objectives, architectural disagreements, and scope overlaps.

    **Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written)

    **Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"
    ```

**`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`**
- The "Plan a Feature Sprint" heading is at line 475; the recipe block runs lines 479–492 with steps 1–11
- Insert `/ll:audit-issue-conflicts` between step 3 (`prioritize-issues`) and current step 4 (`tradeoff-review-issues`), renumbering all subsequent steps (4→5, 5→6, … 11→12):
  ```
  3. /ll:prioritize-issues           ← assign P0-P5 to all issues
  4. /ll:audit-issue-conflicts       ← detect conflicting requirements
  5. /ll:tradeoff-review-issues      ← prune low-value issues
  6. /ll:format-issue --auto         ← promote survivors to v2.0 template
  ...
  12. /ll:create-sprint              ← curate and sequence the sprint
  ```

**`.claude/CLAUDE.md`**
- Add `audit-issue-conflicts`^ to Issue Refinement section in command list

### Test File

Follow exact pattern from `scripts/tests/test_improve_claude_md_skill.py`. 7 assertions:

```python
# scripts/tests/test_audit_issue_conflicts_skill.py

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = ROOT / "skills/audit-issue-conflicts/SKILL.md"

def test_skill_file_exists():
    assert SKILL_FILE.exists()

def test_dry_run_flag():
    assert "--dry-run" in SKILL_FILE.read_text()

def test_auto_flag():
    assert "--auto" in SKILL_FILE.read_text()

def test_severity_labels():
    content = SKILL_FILE.read_text()
    for label in ("high", "medium", "low"):
        assert label in content

def test_conflict_types():
    content = SKILL_FILE.read_text()
    for ctype in ("requirement", "objective", "architecture", "scope"):
        assert ctype in content

def test_no_conflicts_path():
    assert "No conflicts found" in SKILL_FILE.read_text()

def test_config_issues_base_dir_glob():
    assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()
```

> **Note on path resolution**: The actual `test_improve_claude_md_skill.py` uses `Path(__file__).parent.parent.parent` to resolve the project root absolutely — not a relative `Path("skills/...")`. Always use the ROOT-anchored form above, or tests will break when pytest is run from a different working directory.

## Integration Map

### Files to Modify

- `commands/help.md` — ISSUE REFINEMENT block + Quick Reference Table
- `README.md` — skill count (line 89) + Issue Refinement command table row (lines 108–124) + Skills table row (lines 207–235, three-column format with `^` suffix and "Issue Refinement" capability group)
- `CONTRIBUTING.md` — skill count + directory tree entry
- `docs/ARCHITECTURE.md` — skill count (×2) + directory listing entry
- `docs/reference/COMMANDS.md` — `--dry-run` list (line 14) + `--auto` list (line 15) + new subsection after `tradeoff-review-issues`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "Plan a Feature Sprint" recipe (insert at step 4, renumber 4–11 to 5–12)
- `.claude/CLAUDE.md` — command list (Issue Refinement or Meta-Analysis section)

### New Files to Create

- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural test file

### Similar Patterns

- `scripts/tests/test_improve_claude_md_skill.py` — structural test pattern to follow exactly

### Dependent Files (Callers/Importers)

- N/A — registry and doc files are terminal; no code imports them

### Tests

- `scripts/tests/test_audit_issue_conflicts_skill.py` — new structural test file (7 assertions)

### Documentation

- `commands/help.md`, `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/reference/COMMANDS.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `.claude/CLAUDE.md` — all updated as part of this issue

### Configuration

- N/A

## Implementation Steps

1. **Verify FEAT-1028 is complete** — confirm `skills/audit-issue-conflicts/SKILL.md` exists before proceeding; this issue has no output otherwise
2. **Update `commands/help.md`** — add ISSUE REFINEMENT block entry + Quick Reference Table entry (line 254, backtick-wrapped name without `/ll:` prefix in the comma list)
3. **Update `README.md`** — bump skill count `25→26` (line 89); add Issue Refinement command table row (after line 124); add Skills table row (lines 207–235, three-column: name^, "Issue Refinement", one-line description)
4. **Update `CONTRIBUTING.md`** — bump skill count `25→26` (line 125); add `audit-issue-conflicts/` to directory tree after `audit-docs/`
5. **Update `docs/ARCHITECTURE.md`** — bump skill count `25→26` at lines 26 and 99; add `├── audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` in the tree
6. **Update `docs/reference/COMMANDS.md`** — append to `--dry-run` list (line 14) and `--auto` list (line 15); add `### /ll:audit-issue-conflicts` subsection after `### /ll:tradeoff-review-issues` (~line 204) using the description in the Proposed Solution above
7. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — insert step 4 (`audit-issue-conflicts`) and renumber current steps 4–11 to 5–12
8. **Update `.claude/CLAUDE.md`** — add `audit-issue-conflicts`^ to Issue Refinement section; bump skill count `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
9. **Write `scripts/tests/test_audit_issue_conflicts_skill.py`** — 7 assertions using ROOT-anchored path (see Proposed Solution)
10. **Run `ll-verify-docs`** — confirm passes
11. **Run `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py`** — confirm all 7 assertions pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- `.claude/CLAUDE.md:38` — bump skill count `25 → 26` (`# Skill definitions (25 skills)` → `# Skill definitions (26 skills)`). **Note:** `ll-verify-docs` does NOT scan `.claude/CLAUDE.md` (only README, CONTRIBUTING, ARCHITECTURE), so this drift is silent — it must be caught manually as part of step 8.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- All line numbers verified accurate as of 2026-04-11; one shift corrected (see below)
- `docs/reference/COMMANDS.md` line 14 = `--dry-run` consumer list, line 15 = `--auto` consumer list (original issue had these reversed; corrected above). Current exact content:
  - Line 14: `| \`--dry-run\` | Show what would happen without making changes | \`manage-issue\`, \`align-issues\`, \`refine-issue\`, \`format-issue\`, \`manage-release\` |`
  - Line 15: `| \`--auto\` | Non-interactive mode (no prompts) | \`commit\`, \`refine-issue\`, \`prioritize-issues\`, \`format-issue\`, \`confidence-check\`, \`verify-issues\`, \`map-dependencies\`, \`issue-size-review\` |`
  - Append `, \`audit-issue-conflicts\`` to the pipe-delimited consumer cell in each row
- `README.md` has two distinct skill tables: the command table (lines 108–124) and a separate Skills table (lines 207–235) — both need entries
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` "Plan a Feature Sprint" heading is at line **475** (not 476 as originally stated — 1-line drift corrected); recipe block runs lines 479–492 with steps 1–11; inserting before step 4 (`tradeoff-review-issues` at line 484) requires renumbering steps 4–11 to 5–12
- `scripts/tests/test_improve_claude_md_skill.py` (the pattern file) uses `Path(__file__).parent.parent.parent` to anchor to the project root; the proposed test code in this issue must follow the same pattern
- `skills/audit-issue-conflicts/SKILL.md` does not exist yet (FEAT-1028 is a hard dependency); the test suite will fail until FEAT-1028 is implemented

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Small - Mechanical wiring; no logic to implement
- **Risk**: Very Low - Documentation and test changes only
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `wiring`, `docs`, `tests`

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-11_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- **Blocking dependency unresolved**: `FEAT-1028` is still open; `skills/audit-issue-conflicts/SKILL.md` does not exist. Implementation step 1 requires the skill file be present — tests will fail and wiring references a non-existent artifact. Begin implementation only after FEAT-1028 is merged.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-11
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1030: audit-issue-conflicts — Documentation Wiring
- FEAT-1031: audit-issue-conflicts — Structural Tests

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-11T05:19:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/502be2da-c708-44be-93ab-a5693b2c18e1.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
- `/ll:refine-issue` - 2026-04-11T05:13:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98cc2915-f99b-40c4-872b-99d0ab8d13b6.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9e9e621-2fe5-49ab-a375-f7eb546e2244.jsonl`
- `/ll:wire-issue` - 2026-04-11T05:08:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c18a2cf-6ce9-466b-8f19-3016436ecd9d.jsonl`
- `/ll:refine-issue` - 2026-04-11T05:05:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68098040-1f88-46a0-b16a-7451614f377b.jsonl`
- `/ll:format-issue` - 2026-04-11T05:00:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9aecef0c-ff24-4be0-8fdf-2ff69523276c.jsonl`
- `/ll:issue-size-review` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1583f95-f6e7-426b-b174-369fd745725e.jsonl`
