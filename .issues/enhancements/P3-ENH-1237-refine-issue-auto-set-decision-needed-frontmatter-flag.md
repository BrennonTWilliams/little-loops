---
captured_at: "2026-04-21T20:38:05Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
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

### Similar Patterns
- `commands/capture-issue.md` — `testable: false` inference pattern: detect signal, conditionally write frontmatter field

### Tests
- TBD — add test fixture: issue with 2+ options in Proposed Solution; assert `decision_needed: true` in output

### Documentation
- `commands/refine-issue.md` — Step 8 output report section

### Configuration
- N/A

## Implementation Steps

1. Add option-count detection logic to Step 5a of `commands/refine-issue.md` (count numbered/headed option blocks deposited)
2. Add frontmatter update logic: set `decision_needed: true` if count >= 2, clear if count < 2
3. Update Step 8 output report to include `decision_needed` status line
4. Add example showing flag behavior to the Examples section of the command

## Impact

- **Priority**: P3 - prerequisite for FEAT-1236 to work correctly in automated pipelines; small standalone change
- **Effort**: Small - localized change to `commands/refine-issue.md`; additive only
- **Risk**: Low - additive frontmatter write; no behavior change to existing enrichment output
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `pipeline`, `refine-issue`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-21T20:38:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c8873df-f234-41f4-a242-d1cae3dc0002.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
