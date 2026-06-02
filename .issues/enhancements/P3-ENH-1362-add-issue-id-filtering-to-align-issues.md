---
captured_at: '2026-05-04T20:29:24Z'
completed_at: '2026-05-04T22:26:31Z'
discovered_date: '2026-05-04'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 18
missing_artifacts: true
decision_needed: false
status: done
---

# ENH-1362: Add Issue ID Filtering to align-issues Command

## Summary

`/ll:align-issues` always runs against all active issues. There is no way to scope the run to a specific issue ID or a comma-separated list of IDs, making the command impractical when you only want to check one or two issues.

## Current Behavior

Step 4 of `align-issues` uses a broad `find` to collect every active issue file. The only scoping mechanism is the `category` argument, which controls *what to align against*, not *which issues to process*.

## Expected Behavior

An `--issues` flag accepts a comma-separated list of issue IDs and limits processing to only those issues:

```
/ll:align-issues docs/ARCHITECTURE.md --issues ENH-1362
/ll:align-issues architecture --issues BUG-123,FEAT-045
/ll:align-issues --issues ENH-1362
```

Issues not in the list are silently skipped. All other flags (`--verbose`, `--dry-run`, `--all`) compose with `--issues` normally.

## Success Metrics

- Invoking with `--issues ENH-1362` processes only ENH-1362 and skips all other active issues
- Invoking without `--issues` preserves existing behavior (all active issues processed)
- Other flags (`--verbose`, `--dry-run`, `--all`) compose with `--issues` without conflict

## Motivation

When working in a tight review loop (e.g., right after `/ll:capture-issue` or `/ll:refine-issue`), scanning all active issues for alignment is slow and noisy. ID filtering makes the command practical as a per-issue quality gate rather than a bulk batch tool.

## Proposed Solution

Parse `--issues` in the existing Step 1 (Parse Arguments) bash block, splitting on commas into a `FILTER_IDS` array. After `find` collects active issue files in Step 4 (Find Active Issues), post-filter the result array: keep only entries whose basename contains any ID from `FILTER_IDS`. When `--issues` is omitted, `FILTER_IDS` is empty and no filtering occurs.

No new CLI dependencies — the filter operates entirely on the file paths already collected by `find`.

## Integration Map

### Files to Modify
- `commands/align-issues.md` — add `--issues` flag parsing in Step 1 (Parse Arguments); filter `find` results in Step 4 (Find Active Issues) to only files whose name contains a specified ID
- `commands/help.md` — add `--issues` to the `Flags:` line of the `/ll:align-issues <category> [flags]` entry in the ISSUE REFINEMENT section [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `skills/audit-issue-conflicts/SKILL.md` — invokes `/ll:align-issues`
- `skills/issue-workflow/SKILL.md` — invokes `/ll:align-issues`

### Similar Patterns
- `commands/tradeoff-review-issues.md` — primary reference: Phase 1 Discovery (lines 32–54) implements `ISSUES_ARG`→`IDS`→`ISSUE_FILES` pattern with `IFS=',' read -ra IDS` split, `id="${id// /}"` whitespace strip, and `ll-issues path "${id}" 2>/dev/null` path resolution (ENH-1363, completed)
- `commands/create-sprint.md` — implements `--issues` argument with comma-separated ID parsing (secondary reference)

### Tests
- `scripts/tests/test_enh1363_doc_wiring.py` — doc-wiring test template from the parallel ENH-1363 feature; follow this pattern to validate frontmatter argument declaration, conditional branch presence, and `ll-issues path` call in `commands/align-issues.md`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1362_doc_wiring.py` — new test file to create (does not yet exist); mirror `test_enh1363_doc_wiring.py` with five classes: `TestAlignIssuesFrontmatter` (assert `name: issues` argument entry, `Bash(ll-issues:*)` in allowed-tools, `argument-hint` updated), `TestAlignIssuesConditionalStep4` (assert `ISSUES_ARG="${issues:-}"`, `ll-issues path` call, `"not found (skipping)"` warning, zero-IDs error guard), `TestAlignIssuesExamples` (single-ID and comma-separated examples), `TestHelpFileUpdated` (assert `--issues` in `Flags:` line of `/ll:align-issues` entry), `TestCommandsRefUpdated` (assert `issues` in `**Arguments:**` block under `### /ll:align-issues`) [confirmed by reading test_enh1363_doc_wiring.py]

### Documentation
- `commands/align-issues.md` — update Arguments section and Examples section; also update frontmatter `argument-hint:` field (currently `"[category]"`) and `arguments:` YAML block to declare `--issues` in the `flags` description (or as a separate named argument entry following `tradeoff-review-issues.md` pattern)
- `docs/reference/COMMANDS.md` — update `/ll:align-issues` entry to document the new `--issues` flag

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — `/ll:align-issues <category> [flags]` entry, `Flags:` line: currently lists `--verbose, --dry-run`; add `--issues` [Agent 1 + Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Add `--issues` flag parsing in the Parse Arguments bash block (Step 1), producing an array of IDs
2. In Step 4 (Find Active Issues), post-filter the `find` results to only files whose basename contains any specified ID
3. Update the Arguments section and Examples with `--issues` usage
4. Verify no interaction issues with `--all`, `--verbose`, `--dry-run`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `commands/align-issues.md` frontmatter — add `name: issues` as a separate named argument (NOT extending `flags`); set `argument-hint` to `"[category] [--issues ID,...]"`; add `Bash(ll-issues:*)` to `allowed-tools` (required for `ll-issues path` calls; see `refine-issue.md`, `ready-issue.md` for pattern)
6. Update `commands/help.md` — add `--issues` to the `Flags:` line of the `/ll:align-issues <category> [flags]` entry in the ISSUE REFINEMENT section
7. Create `scripts/tests/test_enh1362_doc_wiring.py` — new doc-wiring test file asserting `--issues` presence in frontmatter, command body (FILTER_IDS variable), Arguments + Examples sections, help.md Flags line, and COMMANDS.md documentation; mirror class structure of `test_enh1363_doc_wiring.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 insertion point**: `commands/align-issues.md` Step 1 Parse Arguments — add `ISSUES_ARG="${issues:-}"` and `declare -a ISSUE_FILES`; use `ISSUES_ARG`/`IDS` naming (NOT `FILTER_IDS`) to match the reference verbatim
- **Step 4 insertion point**: `commands/align-issues.md` Step 4 Find Active Issues — when `ISSUES_ARG` is non-empty, skip `find` and instead loop over `IDS`, resolving each via `ll-issues path "${id}" 2>/dev/null` into `ISSUE_FILES`; error out if `${#ISSUE_FILES[@]} -eq 0`; when empty, run unconditional `find` as before
- **Bash split pattern** (from `commands/tradeoff-review-issues.md` Phase 1 Discovery): `IFS=',' read -ra IDS <<< "$ISSUES_ARG"` with per-element `"${id// /}"` whitespace strip; `ll-issues path "${id}" 2>/dev/null` for canonical path resolution
- **`allowed-tools` addition** (verified by research): `commands/align-issues.md` frontmatter `allowed-tools` currently lacks `Bash(ll-issues:*)`; must be added alongside existing `Bash(git:*)` — required for `ll-issues path` calls (confirmed: `refine-issue.md` and `ready-issue.md` both use `Bash(git:*, ll-issues:*)`)
- **Naming resolution** (from Confidence Check notes): use `ISSUES_ARG`/`IDS` from the reference — do not use `FILTER_IDS` (present in earlier drafts of this issue)

## Impact

- **Priority**: P3 - Quality-of-life improvement; nothing is blocked without it
- **Effort**: Small - argument parsing + filename filter in a single markdown command file
- **Risk**: Low - purely additive; existing behavior unchanged when `--issues` is omitted
- **Breaking Change**: No

## API/Interface

```markdown
# New optional flag (added to existing flags argument)
--issues ID[,ID,...]   Comma-separated issue IDs to process (e.g. --issues ENH-1362,BUG-123)
                       When omitted, all active issues are processed (current behavior)
```

## Scope Boundaries

- Behavioral change is confined to `commands/align-issues.md` (argument parsing + issue filtering)
- The flag filters which issue files are loaded; alignment logic, document loading, and auto-fix behavior are unchanged
- Additional wiring touchpoints (non-behavioral): `commands/help.md` (Flags line), `docs/reference/COMMANDS.md` (Arguments block), `scripts/tests/test_enh1362_doc_wiring.py` (new test file)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Test file `scripts/tests/test_enh1362_doc_wiring.py` does not exist yet — creating it is step 7 of the wiring phase; without it, doc-wiring regressions go undetected until CI
- Minor variable naming inconsistency: issue body uses `FILTER_IDS` but reference uses `ISSUES_ARG`/`IDS`; resolve by following the reference (tradeoff-review-issues.md) verbatim

## Session Log
- `/ll:manage-issue` - 2026-05-04T22:26:50 - `bb09f315-36be-4088-ab88-df9bd9d8efcd.jsonl`
- `/ll:ready-issue` - 2026-05-04T22:22:58 - `4aa4525b-9d52-4b07-a0e0-8b3e2ab19f5e.jsonl`
- `/ll:refine-issue` - 2026-05-04T22:09:09 - `99bf23d1-7f7c-4d86-815f-b73d3e9f84d7.jsonl`
- `/ll:confidence-check` - 2026-05-04T22:30:00Z - `0bc09efe-4dd1-4f13-94b7-adc41eb07732.jsonl`
- `/ll:wire-issue` - 2026-05-04T22:02:05 - `b7a43605-61dd-447c-93e0-90f02f729ba7.jsonl`
- `/ll:refine-issue` - 2026-05-04T21:58:52 - `bdc712fd-a65a-4aed-9dad-38ccc93799c9.jsonl`
- `/ll:format-issue` - 2026-05-04T21:08:43 - `b2cacbb2-3baa-47a6-8310-3720c7e6ca3e.jsonl`

- `/ll:capture-issue` - 2026-05-04T20:29:24Z - `db5648f7-6175-41b6-9af0-89d734f66fea.jsonl`

---

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-05-04
- **Implementation**:
  - Added `name: issues` argument to `commands/align-issues.md` frontmatter with `Bash(ll-issues:*)` in `allowed-tools`
  - Updated `argument-hint` to `"[category] [--issues ID,...]"`
  - Added `ISSUES_ARG="${issues:-}"` parsing in Step 1
  - Replaced Step 4 `find` with conditional: when `ISSUES_ARG` is set, resolve each ID via `ll-issues path` (using `ISSUES_ARG`/`IDS` naming matching the reference); fall back to `find` when omitted
  - Updated Arguments section and Examples with `--issues` usage
  - Updated `commands/help.md` Flags line and `docs/reference/COMMANDS.md` Arguments block
  - Created `scripts/tests/test_enh1362_doc_wiring.py` (15 tests, all passing)

**Closed** | Completed: 2026-05-04 | Priority: P3
