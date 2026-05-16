---
id: ENH-1087
priority: P3
status: open
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
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

## Success Metrics

- Interactive mode no longer prompts the user when `HAS_FINDINGS` is true: `/ll:confidence-check` with concerns found writes `## Confidence Check Notes` automatically, no `AskUserQuestion` shown
- Zero confirmation steps required in interactive write-back path (down from 1 prompt)
- Issue files consistently contain confidence check findings after every run with concerns (no findings lost from dismissed prompts)

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
- `skills/manage-issue/SKILL.md:117–129` — Phase 2 calls `/ll:confidence-check [ISSUE-ID]` without `--auto`; currently hits the interactive gate when findings exist; after this fix, write-back becomes unconditional
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:110–113` — the actual loop invocation site: `action: "/ll:confidence-check ${captured.issue_id.output}"` with no `--auto` flag; currently hits the interactive gate in every loop-driven run; after this fix, write-back becomes unconditional
- `scripts/little_loops/loops/issue-refinement.yaml` — delegates to `refine-to-ready-issue` sub-loop; does not invoke confidence-check directly
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — delegates via `recursive-refine` → `refine-to-ready-issue`; does not invoke confidence-check directly
- `skills/wire-issue/SKILL.md` — references `/ll:confidence-check` in post-wiring workflow guidance only; no invocation; no change needed

### Similar Patterns
- `skills/capture-issue/SKILL.md:253–264` — always stages and writes without user confirmation after creation; exact unconditional-write-then-`git add` pattern to follow
- `skills/format-issue/SKILL.md` — uses `AskUserQuestion` for its main action, but that's a higher-stakes rewrite; confidence-check write-back is append-only
- `skills/go-no-go/SKILL.md:319–361` — **identical write-back structure**: same `HAS_FINDINGS` gate, same interactive `AskUserQuestion` / auto-bypass / no-findings-skip pattern; useful parallel reference showing how the refactored Phase 4.5 should read

### Tests
- `scripts/tests/test_builtin_loops.py:501–661` — 6 test methods for confidence-check state routing in `refine-to-ready-issue` loop (e.g. `test_confidence_check_routes_to_check_readiness`); tests state transitions, not write-back behavior
- `scripts/tests/test_refine_status.py:267,816` — 2 fixtures reference `/ll:confidence-check` as a `session_commands` entry; no write-back assertions
- `scripts/tests/test_issue_workflow_integration.py` — exists but has no confidence-check references; not relevant to this change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — new test file needed; no write-back tests exist anywhere in the test suite; assert: (1) `AskUserQuestion` does not appear in Phase 4.5 write-back path, (2) `CHECK_MODE` skip guard is preserved, (3) `HAS_FINDINGS` gate is preserved, (4) `Confidence Check Notes` section name is preserved; follow pattern in `scripts/tests/test_audit_issue_conflicts_skill.py`

### Documentation
- N/A

### Configuration
- N/A

## API/Interface

N/A - No public API changes. This removes an interactive prompt from a skill's write-back path; no function signatures, CLI arguments, or data schemas are modified.

## Implementation Steps

1. Open `skills/confidence-check/SKILL.md` — locate **Phase 4.5** at line 434
2. Delete the interactive-mode block (lines 443–448): the "`AUTO_MODE` is false" header, `AskUserQuestion` instruction, and Yes/No options
3. Replace the auto-mode bypass prose (lines 450–451) with a single unconditional block: "If `HAS_FINDINGS` is true (and `CHECK_MODE` is false): append `## Confidence Check Notes` and run `git add`"
4. Remove the "auto mode with no findings" branching prose (line 452) and the "If the user confirms (interactive) or" qualifier on line 454 — replace with simply "If `HAS_FINDINGS` is true:"
5. Keep the `CHECK_MODE` skip guard (line 436) and the `HAS_FINDINGS=false` → skip path (currently only in auto branch; make it universal)
6. Scan for "user confirms" or "interactive" in Phase 4.5 prose and remove any remaining references
7. Verify by running: `python -m pytest scripts/tests/test_builtin_loops.py -v -k "confidence_check"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Create `scripts/tests/test_confidence_check_skill.py` — structural test (reading `skills/confidence-check/SKILL.md` from disk) asserting: (a) `AskUserQuestion` is absent from Phase 4.5 write-back, (b) `CHECK_MODE` skip guard remains present, (c) `HAS_FINDINGS` gate remains present, (d) `Confidence Check Notes` section name remains present; follow the pattern in `scripts/tests/test_audit_issue_conflicts_skill.py`

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

## Resolution

**Status**: Completed
**Resolved**: 2026-04-12
**Solution**: Removed `AskUserQuestion` interactive block from Phase 4.5 of `skills/confidence-check/SKILL.md`. Write-back is now unconditional when `HAS_FINDINGS` is true and `CHECK_MODE` is false. Added structural test in `scripts/tests/test_confidence_check_skill.py` to enforce this invariant.

## Session Log
- `/ll:manage-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-04-13T01:00:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90984138-30d2-411d-a35b-e7b980602eb0.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0b40f01-0f45-4840-a5cb-6aa6c3c11276.jsonl`
- `/ll:wire-issue` - 2026-04-13T00:51:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1bcc4d81-5ad2-4708-a587-c3bd0b7e8834.jsonl`
- `/ll:refine-issue` - 2026-04-13T00:46:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/640676ed-f4a8-4ca1-89b3-8d7f9a65d2ce.jsonl`
- `/ll:format-issue` - 2026-04-13T00:42:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/511e9704-cc49-4046-a1d4-8f1bd694450b.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdeb08e4-632d-4ce8-a9b9-858290db380b.jsonl`

---

## Status

**Completed** | Created: 2026-04-12 | Resolved: 2026-04-12 | Priority: P3
