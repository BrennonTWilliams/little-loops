---
id: ENH-1087
priority: P3
status: open
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1087: confidence-check always writes concerns to issue without prompting

## Summary

When `/ll:confidence-check` finds concerns, it should write them to the issue file unconditionally before completing — without asking the user for confirmation in interactive mode.

## Current Behavior

Phase 4.5 (Findings Write-Back) in `skills/confidence-check/SKILL.md` gates the write on user confirmation in interactive mode:

> If `HAS_FINDINGS` is true, use `AskUserQuestion` to ask: "Should I update the issue file to include these findings?"

The user must explicitly confirm before concerns are persisted to the issue. In auto mode the write is unconditional, but interactive mode still requires confirmation.

## Expected Behavior

When `HAS_FINDINGS` is true, the findings are always written to the issue file before the skill completes — regardless of whether `AUTO_MODE` is true or false. No `AskUserQuestion` prompt is shown. The `## Confidence Check Notes` section is appended and staged with `git add` automatically.

`CHECK_MODE` remains the only guard that skips the write (no writes in check mode).

## Motivation

Concerns found during a confidence check are actionable information. Requiring user confirmation introduces friction and means findings are routinely lost when users dismiss the prompt or forget to confirm. Since the write is append-only and non-destructive, there is no reason to gate it on confirmation — if concerns were surfaced, they should be on record in the issue.

## Proposed Solution

In `skills/confidence-check/SKILL.md`, Phase 4.5:

1. Remove the `AskUserQuestion` block for interactive mode
2. Replace the combined interactive/auto branch with a single unconditional block: "If `HAS_FINDINGS` is true (and `CHECK_MODE` is false): append `## Confidence Check Notes` to the issue file and run `git add`"
3. Keep the auto-mode no-findings short-circuit (`HAS_FINDINGS` is false → skip) for the clean-bill-of-health case
4. Update the surrounding prose to remove interactive/auto distinction in the write-back path

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 4.5: remove `AskUserQuestion` branch, make write unconditional when `HAS_FINDINGS` is true

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — calls `/ll:confidence-check` in Phase 2.5; behavior unchanged (write-back is side-effect only)
- `loops/issue-refinement.yaml` — invokes confidence-check with `--auto`; already unconditional in auto mode, no change
- `loops/sprint-build-and-validate.yaml` — same as above

### Similar Patterns
- `skills/capture-issue/SKILL.md` — always stages and writes without user confirmation after creation
- `skills/format-issue/SKILL.md` — uses `AskUserQuestion` for its main action, but that's a higher-stakes rewrite; confidence-check write-back is append-only

### Tests
- `scripts/tests/test_issue_workflow_integration.py` — integration tests for issue workflow pipeline

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `skills/confidence-check/SKILL.md` and locate Phase 4.5
2. Delete the `AskUserQuestion` block (interactive-mode ask)
3. Collapse interactive and auto branches into a single: "If `HAS_FINDINGS` is true: write `## Confidence Check Notes` and `git add`"
4. Preserve the `HAS_FINDINGS` is false / `CHECK_MODE` is true short-circuits unchanged
5. Verify prose consistency — remove any references to "user confirms" in the write-back description

## Impact

- **Priority**: P3 - Quality-of-life; reduces friction in a common workflow
- **Effort**: Small - Single skill file, removes ~10 lines, simplifies a branch
- **Risk**: Low - Append-only change; no scoring logic touched; worst case is an extra section written to an issue file
- **Breaking Change**: No

## Scope Boundaries

- Does not change scoring logic, thresholds, or output format
- Does not affect `--check` mode (no writes in check mode remains)
- Does not change auto mode (already unconditional)
- Does not modify callers (`manage-issue`, loops)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `skill`, `confidence-check`, `ux`

## Related Issues

- ENH-779 (completed): Added Phase 4.5 with interactive ask + auto mode; this issue removes the ask from interactive mode

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdeb08e4-632d-4ce8-a9b9-858290db380b.jsonl`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3
