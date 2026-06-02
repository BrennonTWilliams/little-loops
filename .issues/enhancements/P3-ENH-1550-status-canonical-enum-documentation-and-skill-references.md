---
id: ENH-1550
type: enhancement
priority: P3
status: done
parent: ENH-1539
size: Small
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-17T08:59:04Z
---

# ENH-1550: Status canonical enum — documentation and skill references

## Summary

Document the canonical `status:` enum in `.claude/CLAUDE.md` and add one-line references in the five issue-touching skill files and two guide/reference docs, so coding agents stop generating synonym drift in the first place.

## Parent Issue

Decomposed from ENH-1539: Normalize status synonyms and document canonical enum

## Proposed Solution

### 1. `.claude/CLAUDE.md` — canonical enum subsection

Add a short subsection (≤5 lines) under "Issue File Format" (between the `Priorities` bullet and `## Important Files`, near line 95):

> **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace. Synonyms are coerced to canonical values on read, but writing canonical values avoids ambiguity.

### 2. Issue-touching skills — one-line reference

Add a single line to each of the following skill files, in their "frontmatter" or "issue format" sections:

- `skills/capture-issue/SKILL.md`
- `skills/ready-issue/SKILL.md`
- `skills/manage-issue/SKILL.md`
- `skills/format-issue/SKILL.md`
- `skills/refine-issue/SKILL.md`

Line to add (after any existing status mention):
> Status enum: see `.claude/CLAUDE.md` § Issue File Format — Status values.

### 3. `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

The file already has a `### Frontmatter status Values` table at lines 106-119. Add a one-liner after the table:

> Synonyms (`complete`, `completed`, `finished`, `wip`, `in-progress`) are silently coerced to canonical values on read; authors don't need to worry about fixing them manually.

### 4. `docs/reference/CLI.md`

At ~line 557 where `--status {open,in_progress,...}` filter choices are documented, add a one-liner:

> Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs).

## Files to Modify

- `.claude/CLAUDE.md` — add "Status values" subsection
- `skills/capture-issue/SKILL.md` — add one-line enum reference
- `skills/ready-issue/SKILL.md` — add one-line enum reference
- `skills/manage-issue/SKILL.md` — add one-line enum reference
- `skills/format-issue/SKILL.md` — add one-line enum reference
- `skills/refine-issue/SKILL.md` — add one-line enum reference
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — add synonym coercion note
- `docs/reference/CLI.md` — add CLI input note

## Acceptance Criteria

1. `.claude/CLAUDE.md` names all 6 canonical status values and explicitly lists forbidden synonyms
2. Each of the 5 skill files has a one-line pointer to the canonical enum location
3. `ISSUE_MANAGEMENT_GUIDE.md` mentions synonym coercion in the status table section
4. `CLI.md` clarifies that `--status` input must be canonical even though on-disk synonyms are coerced

## Impact

- **Effort**: Very small — 8 files, 1-5 lines each; no code changes
- **Risk**: None — documentation only
- **Can be done in parallel with ENH-1549**

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Completion Status (as of wiring pass)

The following targets were already implemented (likely via the ENH-1549 PR):

| File | Status |
|------|--------|
| `.claude/CLAUDE.md` | ✅ Done — "Status values" subsection at line 96 |
| `skills/format-issue/SKILL.md` | ✅ Done — Status enum line at line 31 |
| `skills/capture-issue/SKILL.md` | ✅ Done — Status enum line at line 33 |
| `skills/manage-issue/SKILL.md` | ✅ Done — Status enum line at line 35 |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | ✅ Done — Synonym coercion note at line 119 |
| `docs/reference/CLI.md` | ✅ Done — CLI notes at lines 557, 571 |
| `commands/ready-issue.md` | ✅ Done — Status enum line at line 33 |
| `commands/refine-issue.md` | ✅ Done — Status enum line at line 30 |

### Path Corrections

The issue listed `skills/ready-issue/SKILL.md` and `skills/refine-issue/SKILL.md` — those directories do not exist. The actual files are:

- **`commands/ready-issue.md`** — the full skill content file; already has the Status enum reference ✅
- **`commands/refine-issue.md`** — the full skill content file; already has the Status enum reference ✅
- `skills/ll-ready-issue/SKILL.md` — bridge stub (3 lines, redirects to `commands/ready-issue.md`); Status enum line absent but stub inherits command content at invocation
- `skills/ll-refine-issue/SKILL.md` — bridge stub (3 lines, redirects to `commands/refine-issue.md`); Status enum line absent but stub inherits command content at invocation

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1550_doc_wiring.py` — **new test file needed**; no doc-wiring regression guard exists. Follow pattern in `scripts/tests/test_enh1130_doc_wiring.py` (`TestClaudeMdScratchPadWiring`) for CLAUDE.md assertions and `scripts/tests/test_enh1442_doc_wiring.py` (`TestSkillGuardrails`) for skill file assertions. Should assert:
  1. `.claude/CLAUDE.md` contains `**Status values**:` and lists all 6 canonical values
  2. `skills/capture-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/manage-issue/SKILL.md`, `commands/ready-issue.md`, `commands/refine-issue.md` each contain `**Status enum**:`
  3. `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` contains `silently coerced to canonical values`
  4. `docs/reference/CLI.md` contains `argparse validates choices before normalization runs`

## Implementation Steps

_Wiring pass added by `/ll:wire-issue`:_

Most file changes are already complete. Remaining work:

1. **Write `scripts/tests/test_enh1550_doc_wiring.py`** — regression guard for all acceptance criteria (see Tests subsection above). Use `PROJECT_ROOT = Path(__file__).parent.parent.parent` and `file.read_text()` with bare `assert "token" in content, "message"` pattern.
2. (Optional) Add Status enum one-liner to `skills/ll-ready-issue/SKILL.md` and `skills/ll-refine-issue/SKILL.md` stubs for agents that load only SKILL.md without following the command redirect.

## Resolution

All 8 target files were already updated (via ENH-1549 PR). This session added:
- `scripts/tests/test_enh1550_doc_wiring.py` — 10-test regression guard covering all 4 acceptance criteria
- Status enum one-liner to `skills/ll-ready-issue/SKILL.md` and `skills/ll-refine-issue/SKILL.md` stubs

All tests pass; linting clean.

## Session Log
- `/ll:ready-issue` - 2026-05-17T08:57:36 - `abad3125-c8ee-44d0-9e7e-8741bca591a3.jsonl`
- `/ll:wire-issue` - 2026-05-17T08:54:13 - `2c7af1f0-785c-4246-b8f4-e589af74715d.jsonl`
- `/ll:refine-issue` - 2026-05-17T08:46:24 - `62133301-4ad5-4919-b84e-bd24f7339162.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
- `/ll:confidence-check` - 2026-05-17T09:00:00Z - `63bf52fe-2295-42e9-8150-e3e59380f655.jsonl`
