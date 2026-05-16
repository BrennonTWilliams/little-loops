---
id: ENH-859
type: ENH
priority: P3
status: active
discovered_date: 2026-03-22
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
---

# ENH-859: go-no-go NO-GO Verdict Lacks Sub-Classification

## Summary

`/ll:go-no-go` produces a binary GO/NO-GO verdict. When the verdict is NO-GO, there is no structured distinction between three meaningfully different situations: the issue should be **closed** (invalid, already covered, wrong direction), the issue is **valid but needs refinement** (under-specified, ambiguous, needs more research), or the issue is **deprioritized** (good idea but wrong timing or lower priority than other active work).

## Current Behavior

The judge agent outputs a single `VERDICT: NO-GO` line. The `RATIONALE` and `DECIDING FACTOR` fields contain free-text reasoning that may imply one of the three situations, but this is not structured or machine-readable. Downstream automation (`--check` mode, FSM routing) cannot act on the distinction. Users receive no actionable guidance on what to do next with a NO-GO issue.

## Expected Behavior

A NO-GO verdict includes a structured sub-classification indicating the recommended next action:

- **`CLOSE`** — Issue is invalid, already covered by existing functionality, or fundamentally misdirected. Recommended action: close or move to completed.
- **`REFINE`** — Issue is valid but under-specified, ambiguous, or needs additional research before it can be implemented. Recommended action: run `/ll:refine-issue` or `/ll:ready-issue`.
- **`SKIP`** — Issue is good but poorly timed: competing priorities, missing prerequisites, or lower value relative to other active work. Recommended action: keep open, deprioritize, or remove from sprint.

## Motivation

The three NO-GO sub-types require completely different follow-up actions. A CLOSE verdict should trigger issue archival; a REFINE verdict should prompt refinement; a SKIP verdict is informational and requires no immediate action. Without sub-classification, users must read free-text rationale to determine next steps, and automation cannot gate or route based on the verdict type. This limits the skill's usefulness as a decision-making tool in both interactive and automated contexts.

## Proposed Solution

Add a `NO-GO REASON` field to the judge agent's output format (between `VERDICT` and `RATIONALE`):

```
VERDICT: NO-GO
NO-GO REASON: [CLOSE | REFINE | SKIP]
```

The judge agent prompt should define the three reasons and instruct the judge to select one when issuing NO-GO. The skill's display step (Step 3e) renders the reason in the verdict block. The `--check` mode can optionally surface the reason in its exit output.

## Success Metrics

- When `VERDICT: NO-GO`, a structured `NO-GO REASON` is always present
- The display block shows the reason prominently alongside the verdict
- In `--check` mode, the reason is included in the per-issue output line: `[ID] no-go (REFINE): [deciding factor]`
- The judge correctly classifies at least 3 representative test cases to the expected reason

## Scope Boundaries

- **In scope**: Adding `NO-GO REASON` to the judge prompt and output format; rendering in display and check-mode output
- **Out of scope**: Automatically acting on the reason (e.g., auto-closing issues on CLOSE, auto-running refine on REFINE) — that is a separate automation concern; changing the GO verdict format; adding sub-classification to GO verdicts

> **Note**: `SKIP` is intentionally distinct from the system concept of "deferring" — deferring moves an issue to `.issues/deferred/` (a status/folder change). SKIP means "valid, keep active, but not the right time to implement now."

## API/Interface

Updated judge output format:

```
VERDICT: [GO | NO-GO]
NO-GO REASON: [CLOSE | REFINE | SKIP]  ← new, only present when VERDICT is NO-GO

RATIONALE:
...
```

Updated check-mode output:

```
[ID] no-go (CLOSE): [deciding factor]
[ID] no-go (REFINE): [deciding factor]
[ID] no-go (SKIP): [deciding factor]
```

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md` — judge prompt (Step 3d), display format (Step 3e), check-mode output (Phase 5)

### Dependent Files (Callers/Importers)
- N/A — skill is invoked by Claude directly; no Python callers

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `commands/ready-issue.md` — `CLOSE_REASON` is a companion field to `VERDICT: CLOSE`; uses `[Only include this section if verdict is CLOSE]` guard — the closest analog to `NO-GO REASON` gated on `VERDICT: NO-GO`
- `skills/confidence-check/SKILL.md:550–555` — batch summary table with six columns including a `Recommendation` column; model for adding a `Reason` column to the go-no-go Phase 4 table
- `skills/issue-size-review/SKILL.md:132–135`, `skills/map-dependencies/SKILL.md:148–151` — check-mode per-issue line format `[ID] <topic>: <detail>`; model for the `[ID] no-go (REASON): [factor]` format

### Tests
- N/A — skill is a prompt document, not testable Python code

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `skills/go-no-go/SKILL.md:268–286` (judge prompt): Add `NO-GO REASON: [CLOSE | REFINE | SKIP]` as the second line of the output format, immediately after `VERDICT: NO-GO`; add a definitions block to the prompt explaining when to choose each reason
2. In `skills/go-no-go/SKILL.md:291–313` (Step 3e parsing): After extracting the `VERDICT` line, also extract the `NO-GO REASON` line (present only when verdict is NO-GO); store the reason alongside the verdict for use in Phase 4 and Phase 5
3. In `skills/go-no-go/SKILL.md:304` (Step 3e display): Update the verdict header from `NO-GO ✗` to `NO-GO ✗ (REASON)` where REASON is the extracted value
4. In `skills/go-no-go/SKILL.md:343` (Phase 5 check-mode): Update the per-issue NO-GO line from `[ID] no-go: [deciding factor]` to `[ID] no-go (REASON): [deciding factor]`
5. In `skills/go-no-go/SKILL.md:326–332` (Phase 4 batch table): Add the reason inline in the Verdict cell as `NO-GO ✗ (REASON)` or add a new `Reason` column

## Impact

- **Priority**: P3 — Improves decision quality and automation utility; not blocking any current workflow
- **Effort**: Small — Changes are confined to one skill file; judge prompt addition + display format update
- **Risk**: Low — Additive change to output format; existing GO verdict and check-mode behavior unchanged
- **Breaking Change**: No — adds a new output field; does not remove or reformat existing fields

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/go-no-go/SKILL.md` | Primary implementation target |

## Labels

`enhancement`, `skills`, `go-no-go`, `captured`

## Resolution

**Status**: Completed — 2026-03-23

Added `NO-GO REASON` sub-classification to `skills/go-no-go/SKILL.md`:

1. **Judge prompt** (Step 3d): Added `NO-GO REASON: [CLOSE | REFINE | SKIP]` as the second line of the output format, immediately after `VERDICT: NO-GO`, with a definitions block explaining when to choose each reason. Line is omitted entirely when verdict is GO.
2. **Step 3e parsing/display**: Updated to parse the `NO-GO REASON` line and render the verdict header as `NO-GO ✗ (REASON)` (e.g. `NO-GO ✗ (REFINE)`).
3. **Phase 4 batch table**: Updated example row to show `NO-GO ✗ (CLOSE)` format in the Verdict column.
4. **Phase 5 check mode**: Updated per-issue NO-GO line from `[ID] no-go: [factor]` to `[ID] no-go ([REASON]): [factor]`.

All changes are additive — GO verdict format and existing check-mode exit codes are unchanged.

## Session Log
- `/ll:ready-issue` - 2026-03-23T02:26:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2f86a73-ed97-4e5e-af24-578ebd4142da.jsonl`
- `/ll:confidence-check` - 2026-03-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68210813-d5d3-4e1b-8275-68e36e51933a.jsonl`
- `/ll:refine-issue` - 2026-03-23T01:58:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9359449-731d-43e3-ba00-6082cc3bba84.jsonl`
- `/ll:capture-issue` - 2026-03-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4128213-770f-4cd5-ac30-edbbda895fb4.jsonl`
- `/ll:manage-issue` - 2026-03-23T02:30:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4654b148-423e-4a16-b229-d5d8d8c1a1ef.jsonl`

---

## Status

**Completed** | Created: 2026-03-22 | Completed: 2026-03-23 | Priority: P3
