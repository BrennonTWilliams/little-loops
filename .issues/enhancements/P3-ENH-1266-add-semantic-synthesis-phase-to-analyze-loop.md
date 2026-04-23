---
captured_at: "2026-04-23T01:19:11Z"
discovered_date: 2026-04-23
discovered_by: capture-issue
---

# ENH-1266: Add Semantic Synthesis Phase to analyze-loop

## Summary

`/ll:analyze-loop` classifies execution history into discrete issue signals using mechanical threshold rules (exit codes, retry counts, duration averages) but never reasons about what those signals *mean together* or whether the observed execution behavior reflects a design problem vs. a runtime environment problem. Adding a post-classification semantic synthesis phase would surface higher-level insights that no individual signal rule can detect.

## Motivation

The current signal rules are appropriate for what they do — detecting quantitative anomalies. But users are left to draw their own conclusions from a list of independent signals. The tool misses:

- **Cross-signal patterns**: retry flood + evaluate failures + SIGKILL in adjacent states together suggest a state doing too much — individually they look unrelated
- **Execution vs. intent gaps**: if a loop's observed path diverges from what its `description:` implies it should do, that's actionable but invisible to per-signal rules
- **Sub-threshold behavioral fingerprints**: a loop consistently spending 80% of iterations cycling one state before reaching `done` has a design issue that no single rule catches (each visit is below slow-state threshold)

This is the dynamic-analysis analogue of ENH-1265, which adds semantic review to `/ll:review-loop`'s static config analysis.

## Current Behavior

Step 3 of `skills/analyze-loop/SKILL.md` classifies signals independently:

- Each signal is evaluated in isolation against a fixed threshold
- Signals from different states are never compared or synthesized
- The loop's `description:` field is loaded in Step 2 (via `ll-loop show`) but never used in analysis
- `loop_complete` with `terminated_by == "completed"` is not analyzed — success is assumed without checking goal alignment

After classification, Steps 4–6 proceed directly to deduplication and issue creation with no holistic reasoning.

## Expected Behavior

After existing signal classification (Step 3), a new **Step 3b: Semantic Synthesis** phase:

1. **Reads the loop's declared goal** from the `description:` field (already loaded in Step 2)
2. **Reconstructs the observed execution path** from `state_enter` and `route` events — the actual sequence of states visited
3. **Compares path to goal** — does the execution pattern suggest the loop achieved its declared purpose? Note anomalies (e.g., heavy cycling before terminal, goal-unrelated states dominating runtime)
4. **Cross-signal reasoning** — do multiple signals on adjacent states suggest a shared root cause (e.g., one state doing too much, upstream dependency failure)?
5. **Detects sub-threshold patterns** — execution distributions that are individually unremarkable but collectively indicate a design smell (e.g., one state accounts for >70% of total iterations despite not being a cycling state)
6. **Produces a synthesis summary** as a preamble to the signal list:

```
### Execution Summary

**Loop goal**: "Refine open issues with codebase context until all sections are populated"
**Observed path**: start → analyze_issue (×12) → check_completeness (×11) → finalize → done
**Goal alignment**: Partial — loop completed but `analyze_issue` re-entered 12× suggests the
  completeness criterion in `check_completeness` is ambiguous or too strict.

**Cross-signal note**: `analyze_issue` action failures (BUG signal) and `check_completeness`
  evaluate failures (BUG signal) likely share a root cause — investigate whether analysis
  output format matches what the evaluator expects.
```

## Proposed Solution

Add **Step 3b: Semantic Synthesis** to `skills/analyze-loop/SKILL.md`, positioned after the per-signal classification loop and before Step 4 (deduplication):

1. Extract `description:` from the `ll-loop show` JSON (already loaded)
2. Build the observed state sequence from ordered `state_enter` events
3. Compute per-state visit counts and identify the dominant state (most re-entries)
4. Check if the dominant state is the declared work state implied by the `description:` or an unexpected cycling state
5. Group signals by proximity (adjacent states sharing a dependency) and note shared root cause candidates
6. Emit a **Synthesis Summary** block at the top of the findings output (before signal list)
7. If synthesis identifies a cross-signal root cause, add a `NOTE` entry to the signal list referencing the relevant signals

The synthesis phase is advisory — it does not add/remove signals, only annotates and contextualizes them.

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md` — add Step 3b Semantic Synthesis phase

### Dependent Files (Callers/Importers)
- No callers — skill is invoked directly by users

### Similar Patterns
- ENH-1265 (`skills/review-loop/SKILL.md`) — parallel semantic review addition for static config analysis
- Step 3 signal rules in `analyze-loop/SKILL.md` — classification logic to build alongside

### Tests
- Check `scripts/tests/` for analyze-loop fixtures; add a multi-signal scenario that exercises cross-signal synthesis

### Documentation
- N/A — no existing docs for this skill

### Configuration
- N/A

## Implementation Steps

1. Read full `skills/analyze-loop/SKILL.md` to understand Step 2 data structures and Step 3 signal output format
2. Design the state-sequence reconstruction algorithm from `state_enter`/`route` events
3. Define cross-signal proximity rules (what counts as "adjacent" states)
4. Add Step 3b to SKILL.md with the synthesis algorithm and output block format
5. Test against 2-3 real loop history outputs covering: single-signal runs, multi-signal runs, completed-but-misaligned runs

## Impact

- **Priority**: P3 - Improves diagnostic quality of an existing tool; not blocking
- **Effort**: Medium - Prompt engineering in SKILL.md; no Python changes required
- **Risk**: Low - Additive only; synthesis phase does not modify per-signal classification
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Status

**Open** | Created: 2026-04-23 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-04-23T01:19:11Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
