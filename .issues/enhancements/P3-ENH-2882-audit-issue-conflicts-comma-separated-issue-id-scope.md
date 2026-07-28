---
id: ENH-2882
title: audit-issue-conflicts should accept a comma-separated issue-ID list as an optional
  scope argument
type: ENH
priority: P3
status: open
captured_at: '2026-07-28T02:15:38Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- ENH-2634
- ENH-1801
- ENH-1802
confidence_score: 98
outcome_confidence: 92
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 24
---

# ENH-2882: audit-issue-conflicts should accept a comma-separated issue-ID list as an optional scope argument

## Summary

`/ll:audit-issue-conflicts` currently supports an optional positional
`EPIC-NNNN` scope (added by ENH-2634) that restricts the audit to an EPIC's
transitive children. There is no way to scope the audit to an arbitrary,
user-picked set of issues that don't share a common EPIC parent. Add a second
optional positional form: a comma-separated list of issue IDs, e.g.
`BUG-123,ENH-456,ENH-054,FEAT-555` or the bare-digit form `123,456,054,555`.

## Motivation

- Users sometimes want to check a hand-picked cluster of issues for conflicts
  (e.g. issues touching the same subsystem but filed under different EPICs, or
  no EPIC at all) without paying for a full-backlog scan or being forced to
  create/assign an EPIC first just to get a scoped audit.
- Complements ENH-2634's EPIC scoping rather than duplicating it — EPIC scope
  answers "audit this EPIC's children"; this answers "audit exactly these
  issues".

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md` Phase 0 parses at most one positional
token into `SCOPE_EPIC` (normalizing `EPIC-NNNN` or bare `NNNN`, validating it
resolves to an existing EPIC file). A comma-separated token like
`BUG-123,ENH-456` fails EPIC validation and aborts with "not a valid EPIC",
even though every ID in the list may be perfectly valid individually.

## Expected Behavior

The positional argument should accept three forms:
1. Omitted — full-backlog scan (unchanged).
2. Single `EPIC-NNNN` / bare `NNNN` resolving to an EPIC — existing ENH-2634
   transitive-children scope (unchanged).
3. **New**: a comma-separated list of issue IDs (`TYPE-NNN` or bare `NNN` per
   item, mixed types allowed) — scope the audit to exactly those issues (no
   transitive expansion). Each ID is normalized/validated independently;
   an unresolvable ID aborts with a clear message naming the offending token.

## Proposed Solution

In Phase 0, after the existing EPIC-normalization branch fails to resolve the
raw positional as a single EPIC, check whether it contains a comma. If so,
split on `,`, normalize each token the same way `_resolve_issue_id()`-style
logic does (case-insensitive, `TYPE-NNN` or bare `NNN`), and validate each
resolves via `ll-issues show <ID> --json` (or `ll-issues path <ID>`). Collect
resolved paths into a new `SCOPE_ISSUE_LIST` array; leave `SCOPE_EPIC` empty
in this mode. In Phase 1, when `SCOPE_ISSUE_LIST` is non-empty, set
`ISSUE_FILES` directly from it instead of the EPIC-transitive-children query
or full-backlog glob.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact Phase 0 code to extend** (`skills/audit-issue-conflicts/SKILL.md:54-94`,
  section "Positional EPIC scope (optional)"): a `for tok in $ARGUMENTS; do
  case "$tok" in --*) continue ;; *) ... esac; done` loop that normalizes a
  single token via `up=$(printf '%s' "$tok" | tr '[:lower:]' '[:upper:]')`,
  branches on `EPIC-*` / `*[!0-9]*` / bare digits, validates against
  `ll-issues list --type EPIC --json` piped to a `python3 -c` set-membership
  check, and `break`s after the first non-flag token — so today only one
  positional token is ever consumed. The comma-branch must sit as a sibling
  case inside this same loop, before the `break`.
- **Exact Phase 1 branch to extend** (`skills/audit-issue-conflicts/SKILL.md:98-157`):
  `if [[ -n "$SCOPE_EPIC" ]]; then ... else ... fi` — the EPIC branch resolves
  children via `ll-issues list --parent "$SCOPE_EPIC" --status all --json`
  piped to a `python3` active-status filter (`{'open','in_progress','blocked'}`),
  then appends the EPIC file itself via `ll-issues path "$SCOPE_EPIC"`. This
  `--parent`-based query has no equivalent for an arbitrary ID set, confirming
  Implementation Step 1's approach of per-ID `ll-issues path` resolution
  rather than a single bulk list query.
- **Exact log line to mirror** (line 128): `echo "Scoped to $SCOPE_EPIC:
  ${#ISSUE_FILES[@]} issues (transitive children + EPIC file)"`. The new
  `SCOPE_ISSUE_LIST` branch should follow the same `"Scoped to <label>: <N>
  issues (<parenthetical>)"` shape, e.g. `"Scoped to N explicit issue IDs:
  ${#ISSUE_FILES[@]} issues"`.
- **No comma-separated-list parser exists anywhere in `skills/`** to copy
  wholesale. The closest analog is `skills/create-eval-from-issues/SKILL.md:39-78`,
  which accepts *space*-separated issue IDs into an `ISSUE_IDS=()` bash array
  and resolves each with a plain `for ID in "${ISSUE_IDS[@]}"; do ll-issues
  show "$ID" --json; done` loop (no bare-digit normalization — it defers
  entirely to `ll-issues show`). ENH-2882's implementation should combine
  Pattern 1's bare-digit→`TYPE-NNN` case-normalization (per comma-split
  token, since a comma list has no single fixed type prefix) with this
  per-ID `ll-issues show`/`path` resolution loop.
- **Test model to mirror**: `scripts/tests/test_audit_issue_conflicts_skill.py:213-255`,
  class `TestAuditIssueConflictsEpicScoping`. It uses a `_phase(start_header,
  end_header)` helper that slices `SKILL.md` content between `## Phase N`
  headers by string index, then asserts on substrings (e.g. `"SCOPE_EPIC" in
  phase1`, `"--parent" in phase1`) — none of the existing tests execute the
  bash; all are static content assertions. A sibling
  `TestAuditIssueConflictsCommaScope` class following the same idiom (asserting
  `"SCOPE_ISSUE_LIST" in phase1`, comma-split logic present in phase0, abort
  message substring present) is the direct model for Implementation Step 5.
- **Additional companion files not yet listed in Integration Map** that may
  need no changes but are adjacent to Phase 0/1 logic:
  `skills/audit-issue-conflicts/interactive-prompts.md`,
  `skills/audit-issue-conflicts/verbatim-output.md`,
  `skills/audit-issue-conflicts/conflict-detection-prompt.md`,
  `skills/audit-issue-conflicts/agents/openai.yaml` (Codex host adapter) —
  confirmed none of these reference `SCOPE_EPIC`/positional parsing, so no
  edits expected, but worth a grep pass during implementation to confirm.
- **Additional docs referencing audit-issue-conflicts** beyond `commands/help.md`
  and `docs/reference/COMMANDS.md` (already listed): `docs/reference/API.md`,
  `docs/reference/CLI.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`,
  `docs/guides/LOOPS_REFERENCE.md`, `docs/ARCHITECTURE.md` mention the skill;
  scope of needed edits there is TBD (likely none beyond the two already
  identified, since those five are architecture/guide-level rather than
  per-flag usage docs) — flagged for implementer verification, not a
  confirmed required edit.

_Wiring pass added by `/ll:wire-issue`:_
- **Resolves the TBD above**: `/ll:wire-issue` confirmed via direct read that
  none of `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/ARCHITECTURE.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, or
  `.claude/CLAUDE.md` document per-flag argument syntax for
  `audit-issue-conflicts` — each only mentions the skill/flags in passing
  (directory listing, workflow-sequence example, or loop-state table with no
  positional). No edits needed in any of these.
- `docs/reference/COMMANDS.md`'s `**Arguments:**` bullet for `epic-id`
  (line ~308, in the `## /ll:audit-issue-conflicts` section) is the most
  detailed prose contract in the docs tree and needs its own sibling bullet
  for the comma-list form and abort-message wording — distinct from (in
  addition to) the synopsis-line edit on line 91 already noted.
- The four companion files (`interactive-prompts.md`, `verbatim-output.md`,
  `conflict-detection-prompt.md`, `agents/openai.yaml`) are confirmed via
  direct read to need no edits — none reference `SCOPE_EPIC` or positional
  parsing.

## API/Interface

```
/ll:audit-issue-conflicts [EPIC-NNNN | ID,ID,ID,...] [--auto] [--dry-run] [--cross-theme]
```

Backward compatible: omitting the positional preserves full-backlog behavior;
a single EPIC-shaped token preserves ENH-2634 behavior.

## Program Design

### Types

- `SCOPE_ISSUE_LIST: array[str]` — bash array of resolved absolute paths for
  explicitly-listed issue IDs (Phase 0 output), parallel to existing
  `SCOPE_EPIC`.

### Signatures

- N/A — this is skill-markdown/bash logic, not a Python function; no new
  Python entry point required if `ll-issues show <ID> --json` / `ll-issues
  path <ID>` are reused as-is for per-ID resolution.

### Call Path

Phase 0 positional parse -> (comma detected) -> per-token `ll-issues path
"$ID"` resolution loop -> `SCOPE_ISSUE_LIST` -> Phase 1 `ISSUE_FILES=(
"${SCOPE_ISSUE_LIST[@]}" )`

## Implementation Steps

1. In Phase 0, after the EPIC-token branch, add a comma-detection branch that
   splits the raw positional and resolves each ID via `ll-issues path` (or
   `show --json`), aborting with a per-token error message on first failure.
2. In Phase 1, branch on `SCOPE_ISSUE_LIST` being non-empty before the
   existing `SCOPE_EPIC` branch and the full-backlog glob, setting
   `ISSUE_FILES` directly from the resolved paths.
3. Update the scoped-mode log line to report the explicit-list case
   separately (e.g. `Scoped to N explicit issues`).
4. Update `argument-hint` and the Examples section to document the
   comma-separated form.
5. Add tests mirroring the ENH-2634 test additions in
   `scripts/tests/test_audit_issue_conflicts_skill.py` (Phase 0 comma-parse
   present, Phase 1 explicit-list branch present, abort-on-bad-ID message
   present).

### Wiring Phase (added by `/ll:wire-issue`)

6. Update `docs/reference/COMMANDS.md`'s `**Arguments:**` bullet for
   `epic-id` (line ~308) with a sibling bullet for the comma-list form, in
   addition to the synopsis-line edit already covered by Step 4.
7. Add a `CHANGELOG.md` entry for the comma-separated scope form, modeled
   on ENH-2634's existing bullet, under a concrete version section.

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 0 (comma-list parse +
  per-ID validation), Phase 1 (branch on `SCOPE_ISSUE_LIST`), frontmatter
  `argument-hint`, Examples section.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — invokes
  `/ll:audit-issue-conflicts --auto` with no positional; unaffected.

### Similar Patterns
- ENH-2634's EPIC-scope implementation in the same file is the direct model
  for normalization/validation/abort shape; reuse rather than reinvent.

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — add assertions for
  the new comma-list branch, following the phase-slicing idiom already used
  for the EPIC-scope tests.

### Documentation
- `commands/help.md` and `docs/reference/COMMANDS.md` — update the
  `/ll:audit-issue-conflicts` usage synopsis / Arguments subsection
  (already updated once for ENH-2634's `[EPIC-NNNN]`) to also show the
  comma-separated form.

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add a new entry documenting the comma-separated scope
  form, modeled on ENH-2634's existing bullet ("`audit-issue-conflicts`
  scoped to a positional EPIC argument..."); per project convention, add
  under a concrete version section, not `[Unreleased]`.

## Related Issues

- ENH-2634 — added the `[EPIC-NNNN]` positional scope this issue extends
  with a second, complementary form.
- ENH-1801, ENH-1802 — other audit-issue-conflicts scoping/detection work.

## Session Log
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `d3845334-2f18-413a-a1b0-c5cb779474b0.jsonl`
- `/ll:wire-issue` - 2026-07-28T02:35:16 - `389e3d36-9010-4451-b8f7-22ffba41f7b8.jsonl`
- `/ll:refine-issue` - 2026-07-28T02:26:22 - `390eda17-6836-4908-8103-b710184f7d7e.jsonl`
- `/ll:capture-issue` - 2026-07-28T02:15:38Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea124377-6146-429c-b9b7-5eeb1db61447.jsonl`

---

## Status

- [ ] Not started
