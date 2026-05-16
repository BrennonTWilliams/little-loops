---
captured_at: "2026-04-21T20:38:05Z"
completed_at: "2026-04-21T21:19:46Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1237: Update /ll:refine-issue --auto to set decision_needed frontmatter flag

## Summary

Update the enrichment output step of `/ll:refine-issue --auto` to detect when it deposits 2+ implementation options into an issue's `Proposed Solution` section and automatically set `decision_needed: true` in frontmatter. Makes the "unresolved options" state machine-readable, enabling automated pipelines (`ll-auto`, `ll-parallel`) to conditionally invoke `/ll:decide-issue` (FEAT-1236) without parsing issue content.

## Current Behavior

`/ll:refine-issue --auto` deposits multiple implementation options from codebase research without setting any signal in the issue frontmatter. Automation cannot detect this state and cannot conditionally invoke a decision step — it must either always run a decision pass (wasteful) or never run it (leaving options unresolved).

## Expected Behavior

When `/ll:refine-issue --auto` adds 2+ implementation options to the `Proposed Solution` section, it sets `decision_needed: true` in the issue frontmatter before writing the file. If it adds only one option (or none), the flag is not set (or is set to false if previously true from a prior pass).

## Motivation

Without a machine-readable signal, `ll-auto` cannot know which issues need a decision pass. The `decision_needed` flag makes the conditional explicit and auditable — you can `grep` for it across all issues to find ones pending a decision. It also ensures the decision skill (FEAT-1236) is only invoked when warranted, keeping pipeline runtime low for issues that already have a clear approach.

## Proposed Solution

In Step 5a (Fill Gaps / Auto Mode) of `commands/refine-issue.md`, add a post-write check after depositing options into `Proposed Solution`:

1. Count the implementation options deposited (detect by numbered list items starting with `1.`/`2.` or option headers like `### Option A`)
2. If count >= 2: add or update `decision_needed: true` in the issue's YAML frontmatter
3. If count == 1: ensure `decision_needed` is absent or `false` in frontmatter (clear a stale flag from a prior pass)

Also update Step 8 (Output Report) to include a `decision_needed` line in the FILE STATUS section.

## Scope Boundaries

- Only the `--auto` mode code path (Step 5a). Interactive mode (Step 5b) already prompts the user for clarification, so no flag is needed there.
- Does not implement the decision-making logic — that is FEAT-1236.
- Does not change how `ll-auto` consumes the flag — that is part of FEAT-1236 implementation.

## Success Metrics

Running `/ll:refine-issue --auto` on an issue where research finds 2+ implementation approaches results in `decision_needed: true` appearing in that issue's YAML frontmatter. Running it on an issue where research finds 1 approach results in no flag (or `false` if previously set).

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — Step 5a: add option-count detection and frontmatter update logic; Step 8: surface `decision_needed` in output report

### Dependent Files (Callers/Importers)
- `scripts/little_loops/auto.py` — will read `decision_needed` flag (in FEAT-1236)
- `scripts/little_loops/parallel_runner.py` — will read `decision_needed` flag (in FEAT-1236)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/auto.py` — correct path for ll-auto entry point (issue path above is `auto.py` without `cli/` prefix); currently reads `IssueInfo` via `IssueParser.parse_file()` but does not yet branch on `decision_needed`
- `scripts/little_loops/cli/parallel.py` — correct path for ll-parallel entry point (issue has `parallel_runner.py`); see also `scripts/little_loops/parallel/orchestrator.py:1184` for frontmatter write-back context
- `scripts/little_loops/issue_parser.py:201-250` — `IssueInfo` dataclass; does not yet have a `decision_needed` field; FEAT-1236 will need to add `decision_needed: bool | None` here and parse it in `parse_file()` at line 359 (out of scope for ENH-1237 per Scope Boundaries, flagged for FEAT-1236)
- `docs/reference/ISSUE_TEMPLATE.md:869-895` — frontmatter fields reference table; `decision_needed` is already documented as `bool`

### Similar Patterns
- `skills/capture-issue/SKILL.md:236-241` — `testable: false` inference block: detect signal keyword count ≥ 2, conditionally write frontmatter field (note: issue originally cited `commands/capture-issue.md`; actual implementation is in the skill file)
- `skills/format-issue/SKILL.md:163-175` — same `testable: false` pattern as a post-loop step with idempotency guard (skip write if field already present with any value)
- `commands/ready-issue.md:230` — same pattern in auto-correction; produces `[content_fix]` CORRECTIONS_MADE entry when flag is written
- `skills/confidence-check/SKILL.md:398-446` — Phase 4 write-back: replaces entire `---` block after computing scores; handles both existing-frontmatter and no-frontmatter cases — follow for the Edit-tool inline approach
- `scripts/little_loops/frontmatter.py:106-129` — `update_frontmatter(content, updates)` Python utility: merges `updates` dict into existing `---` block or creates one; not directly callable from command markdown, but the Edit-tool approach mirrors its merge behavior

### Tests
- `scripts/tests/test_refine_issue_command.py` — new file to create; assert `decision_needed: true` in frontmatter when Proposed Solution has 2+ options; assert flag absent (or `false`) for single-option case
- Model after: `scripts/tests/test_issue_size_review_skill.py:1-67` — structural `commands/refine-issue.md` text assertions (section-scoped, field-key checks, CHECK_MODE guard analog)
- Model after: `scripts/tests/test_confidence_check_skill.py:1-54` — no-`AskUserQuestion` guard pattern for auto-mode paths
- Related: `scripts/tests/test_frontmatter.py:180-282` — `TestUpdateFrontmatter` unit tests covering `update_frontmatter()` for the inline `---` block edit approach

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — also include a doc-wiring assertion that `decision_needed` appears in `docs/reference/ISSUE_TEMPLATE.md`; follow `test_feat1172_doc_wiring.py:20-38` pattern (backtick-wrapped field name search: `assert "\`decision_needed\`" in content`)

### Documentation
- `commands/refine-issue.md` — Step 8 output report section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:869-886` — frontmatter fields table; `decision_needed` field must be ADDED here (currently absent from the table — verified by wiring pass; the Dependent Files entry above incorrectly states it's "already documented as `bool`")
- `docs/reference/COMMANDS.md:178-183` — `/ll:refine-issue` command entry; add "Frontmatter write-back" note for `--auto` mode documenting `decision_needed` side effect (follow the `issue-size-review` pattern at line 249 which reads: "Frontmatter write-back: After assessing each issue, the skill writes `size: <label>`")

### Configuration
- N/A

## Implementation Steps

1. Add option-count detection logic to Step 5a of `commands/refine-issue.md` (count numbered/headed option blocks deposited)
2. Add frontmatter update logic: set `decision_needed: true` if count >= 2, clear if count < 2
3. Update Step 8 output report to include `decision_needed` status line
4. Add example showing flag behavior to the Examples section of the command

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `decision_needed` row to `docs/reference/ISSUE_TEMPLATE.md` frontmatter fields table — field is currently absent (correct the existing integration map note that incorrectly claims it's "already documented as `bool`")
6. Update `docs/reference/COMMANDS.md:178-183` — add "Frontmatter write-back" note for `--auto` mode: "After detecting 2+ options deposited into Proposed Solution, sets `decision_needed: true` in issue frontmatter" (follow `issue-size-review` pattern at line 249)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Insert option-count detection logic directly after the Proposed Solution enrichment block at `commands/refine-issue.md:262-265`
- Option patterns to detect in deposited Proposed Solution content: `### Option A/B/C` (section headers), `**Option A`/`**Option B` (bold inline — most common in real issues; see `.issues/completed/P2-BUG-546-typeerror-mixed-naive-aware-timestamps-crashes-compute-boundaries.md:60-91`), numbered list `1.`/`2.` (as specified in the issue's own Proposed Solution)
- The FILE STATUS block in Step 8 to extend is at `commands/refine-issue.md:428-430` — currently two lines (`## FILE STATUS` + one bullet)
- For the frontmatter write: follow the `skills/confidence-check/SKILL.md:398-446` approach — use the Edit tool to replace the `---` block inline; handle both existing-frontmatter and no-frontmatter cases
- Idempotency: follow `skills/format-issue/SKILL.md:163-175` — skip write if field already set to the same value; always explicitly clear to `false` (or remove) when count < 2 to prevent stale `true` from a prior pass

## Impact

- **Priority**: P3 - prerequisite for FEAT-1236 to work correctly in automated pipelines; small standalone change
- **Effort**: Small - localized change to `commands/refine-issue.md`; additive only
- **Risk**: Low - additive frontmatter write; no behavior change to existing enrichment output
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `pipeline`, `refine-issue`, `captured`

## Resolution

- **Status**: Completed
- **Completed**: 2026-04-21T21:19:46Z
- **Changes**:
  - `commands/refine-issue.md` — added Option-Count Detection block to Step 5a; added `decision_needed` line to Step 8 FILE STATUS
  - `docs/reference/ISSUE_TEMPLATE.md` — added `decision_needed` row to Frontmatter Fields table
  - `docs/reference/COMMANDS.md` — added Frontmatter write-back note to `/ll:refine-issue` entry
  - `scripts/tests/test_refine_issue_command.py` — created with 12 structural assertions (all passing)

## Session Log
- `/ll:manage-issue` - 2026-04-21T21:19:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-21T21:13:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57753c10-b893-4d28-9f7d-e3c6a427d797.jsonl`
- `/ll:confidence-check` - 2026-04-21T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adcfed5f-e3a2-4e93-8315-ec9f052d880a.jsonl`
- `/ll:wire-issue` - 2026-04-21T21:06:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f6ce20b-9702-4231-a275-2b8d62b7bb5b.jsonl`
- `/ll:refine-issue` - 2026-04-21T21:00:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/284a2edd-5323-45eb-a303-182bf4de36f8.jsonl`

- `/ll:capture-issue` - 2026-04-21T20:38:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c8873df-f234-41f4-a242-d1cae3dc0002.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
