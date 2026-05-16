---
captured_at: "2026-04-23T01:19:11Z"
discovered_date: 2026-04-23
discovered_by: capture-issue
confidence_score: 85
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
size: Very Large
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
- `skills/analyze-loop/SKILL.md` — add Step 3b Semantic Synthesis phase between Step 3 (line 182) and Step 4 (line 186); update Step 5 display to emit the Execution Summary preamble before the numbered signal list

### Dependent Files (Callers/Importers)
- No callers — skill is invoked directly by users

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1146_doc_wiring.py:18` — reads `skills/analyze-loop/SKILL.md` at load time via `Path.read_text()`; won't break from Step 3b content, but should have a new assertion for the `"Semantic Synthesis"` or `"Step 3b"` heading presence [Agent 1 finding]

### Similar Patterns
- `skills/review-loop/SKILL.md:215–290` — Step 2c (SR-1 through SR-4 semantic checks); primary pattern to follow for sub-step structure and output block format
- `skills/review-loop/reference.md:435–564` — SR-* check schema (`{ check_id, severity, location, message }`); finding format conventions
- `scripts/tests/test_review_loop.py:748–965` — `TestReviewLoopSemanticChecks` class; fixture-backed test pattern for semantic check conditions

### Data Sources (All Already Loaded in Step 2)
- `ll-loop show <name> --json` → top-level `"description"` field (`scripts/little_loops/fsm/schema.py:569` — present when not None)
- `ll-loop history <name> --json` → `state_enter` events (fields: `state`, `iteration`), `route` events (fields: `from`, `to`), `loop_complete` event (field: `terminated_by`)
- Step 3 classified signals — state names and signal types available for cross-signal adjacency check

### Tests
- No existing `test_analyze_loop.py` test file — `scripts/tests/` has `test_review_loop.py` as the pattern
- Add FSM event sequence fixtures in `scripts/tests/fixtures/fsm/` covering: multi-signal adjacent states, dominant-cycling state (≥70% iterations), completed loop with goal misalignment
- Model test class after `TestReviewLoopSemanticChecks` (line 748): fixture-backed structural condition tests (no LLM execution needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — new fixture: adjacent states each with action failure + evaluate failure (exercises 3b-4 cross-signal note); follow `semantic-goal-mismatch.yaml` structure [Agent 3 finding]
- `scripts/tests/fixtures/fsm/analysis-dominant-cycling.yaml` — new fixture: one state accounts for ≥70% of total iterations (exercises 3b-5 sub-threshold detection) [Agent 3 finding]
- `scripts/tests/fixtures/fsm/analysis-completed-misaligned.yaml` — new fixture: `terminated_by == "terminal"` with heavy cycling and `description` unrelated to dominant state (exercises 3b-3 goal alignment) [Agent 3 finding]
- `scripts/tests/test_analyze_loop_synthesis.py` — new test file; class `TestAnalyzeLoopSynthesis` modeled after `TestReviewLoopSemanticChecks`; use `_load_fixture()` from `conftest.py` and inline event sequence dicts (not `.jsonl` files); group by sub-steps 3b-2 through 3b-5 [Agent 3 finding]

### Documentation
- `docs/reference/COMMANDS.md` — `/ll:analyze-loop` entry; may need a note about the new Execution Summary output block
- `docs/guides/LOOPS_GUIDE.md` — mentions analyze-loop; no change needed for this enhancement

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:514–544` — `/ll:analyze-loop` entry; add mention of Execution Summary block emitted before the signal list [Agent 2 finding]
- `docs/reference/COMMANDS.md:664` — quick-reference table row (`| analyze-loop^ | … |`); optionally update description to note semantic synthesis capability [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Done** — Step 3b added to `skills/analyze-loop/SKILL.md` between Step 3 (was line 182) and Step 4; Step 5 updated to always emit the Execution Summary preamble before the signal list
2. Optionally add FSM event sequence fixture files to `scripts/tests/fixtures/fsm/` for:
   - A multi-signal loop run (adjacent states with action failure + evaluate failure) — exercises 3b-4 cross-signal note
   - A dominant-cycling run (one state ≥70% of iterations) — exercises 3b-5 sub-threshold detection
   - A completed-but-misaligned run (loop finished, heavy cycling, description unrelated to dominant state) — exercises 3b-3 goal alignment
3. Optionally add `scripts/tests/test_analyze_loop_synthesis.py` modelled after `TestReviewLoopSemanticChecks` (`test_review_loop.py:748`) to validate the structural conditions each synthesis sub-step relies on
4. Run `/ll:analyze-loop` against 2-3 real archived runs in `.loops/.history/` to validate synthesis output (real event data confirmed at `.loops/.history/2026-04-13T004120-refine-to-ready-issue/events.jsonl` and `.loops/.history/2026-04-13T175936-svg-image-generator/events.jsonl`)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/COMMANDS.md:514–544` — add note about the Execution Summary output block emitted before the signal list in the `/ll:analyze-loop` entry
6. Update `docs/reference/COMMANDS.md:664` — optionally update quick-reference table description to note semantic synthesis capability
7. Optionally enhance `scripts/tests/test_enh1146_doc_wiring.py` — add assertion for `"Semantic Synthesis"` or `"Step 3b"` heading presence in `SKILL.md` (follows existing pattern at line 38)

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-22_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- **Core feature already implemented**: Step 3b is live in `skills/analyze-loop/SKILL.md` — remaining open work is tests (fixtures + test file), docs update, and real-run validation only
- **"Optionally" vs. "must be included" conflict**: Implementation steps 2, 3, 7 say "optionally" but the wiring phase notes those same items "must be included in the implementation" — clarify which governs before starting
- **Test coverage gap**: `test_analyze_loop_synthesis.py` doesn't exist and Step 3b has no automated validation; `test_enh1146_doc_wiring.py` only checks `rate_limit_waiting`, not Step 3b content

## Session Log
- `/ll:confidence-check` - 2026-04-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:wire-issue` - 2026-04-23T02:55:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34b2a3db-64aa-4f52-bbd4-f3e57c5951b3.jsonl`
- `/ll:refine-issue` - 2026-04-23T02:50:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01fb4149-472d-477c-8d93-22e5e1d76b00.jsonl`
- `/ll:capture-issue` - 2026-04-23T01:19:11Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac265e54-5386-49fe-bf5b-6e6f9305772d.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-22
- **Reason**: Issue too large for single session (score: 11/11); core SKILL.md implementation already shipped

### Decomposed Into
- ENH-1267: Test Coverage for analyze-loop Step 3b Semantic Synthesis
- ENH-1268: Docs and Real-Run Validation for analyze-loop Semantic Synthesis
