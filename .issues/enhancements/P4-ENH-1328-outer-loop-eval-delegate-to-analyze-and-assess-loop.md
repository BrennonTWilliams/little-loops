---
id: ENH-1328
type: ENH
priority: P4
captured_at: "2026-05-02T19:05:00Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# ENH-1328: `outer-loop-eval` Should Delegate to `/ll:analyze-loop` and `/ll:assess-loop`

## Summary

`outer-loop-eval.yaml` currently has three inline prompt-based states — `analyze_definition`, `analyze_execution`, `generate_report` — that each ask the model to inspect the target loop's YAML and execution trace and produce structured analysis. With FEAT-1325 (`/ll:assess-loop`) and the existing `/ll:analyze-loop` skill, that logic is duplicated. Replace the inline prompts with skill invocations so we ship a single canonical analyzer.

## Motivation

- **Two diverging analyzers** — every improvement to `/ll:analyze-loop` (e.g., the new effectiveness signals in ENH-1327) has to be either re-implemented in `outer-loop-eval`'s prompts or remain unavailable to it. That guarantees drift.
- **Inline prompts can't access the resolved state map** — once ENH-1326 lands, `/ll:analyze-loop` will see merged `from:`/`fragment:`/sub-loop graphs. The inline prompts in `outer-loop-eval` will continue to call `ll-loop show <name>` and miss that resolution.
- **Inline prompts produce free-text** — `analyze_definition.capture: definition_analysis` is unstructured. `/ll:analyze-loop --json` and `/ll:assess-loop --json` produce structured output that `generate_report` can route on programmatically.

## Current Behavior

`scripts/little_loops/loops/outer-loop-eval.yaml` states:

- `analyze_definition` (lines 28-49) — prompt that asks the model to read `ll-loop show ${context.loop_name}` and emit a structured analysis covering state coverage, missing routes, evaluator types, context hygiene, and cycle risks.
- `analyze_execution` (lines 59-81) — prompt that parses sub-loop output for transition sequence, retry counts, verdicts, terminal state, anomalies.
- `generate_report` (lines 83-135) — prompt that combines the two analyses into a 5-section improvement report.
- `refine_analysis` (lines 137-164) — fallback when `generate_report` produced no concrete findings.

## Expected Behavior

After ENH-1326 and FEAT-1325 land:

- `analyze_definition` becomes a `shell` action: `/ll:analyze-loop ${context.loop_name} --static-only --json` (or equivalent) capturing the resolved-graph + static-signal output.
- `analyze_execution` becomes a `shell` action: `/ll:analyze-loop ${context.loop_name} --json` capturing the full fault + effectiveness signals from the just-completed sub-loop run.
- `generate_report` calls `/ll:assess-loop ${context.loop_name} --json` and uses its structured scorecard + proposals as the report basis.
- `refine_analysis` either disappears (the assessor's "always emit ≥1 proposal" guarantee replaces it) or is repurposed as a higher-temperature fallback that runs only when `assess-loop` returns zero proposals.

## Implementation Steps

1. Wait for FEAT-1325 (`/ll:assess-loop`) and ENH-1326 (resolver) to ship, plus ideally ENH-1327 (effectiveness signals) so the assessor has rich input.
2. Add `--json` and `--static-only` flags to `/ll:analyze-loop` if not present (likely already there or trivial to add).
3. Rewrite `outer-loop-eval.yaml` states to be `action_type: shell` with skill invocations, capturing `--json` output.
4. Update the `evaluate` block on the new `generate_report` to read structured fields rather than free text (e.g., check that the `proposals` array is non-empty rather than parsing prose for "None identified.").
5. Update tests for `outer-loop-eval` to mock the skill outputs rather than the inline prompts.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — rewrite `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` states to `action_type: shell` skill invocations

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "outer-loop-eval" scripts/`

### Similar Patterns
- Other loop YAML files using `action_type: shell` with skill invocations

### Tests
- TBD — identify test files: `grep -r "outer.loop.eval\|outer_loop_eval" scripts/tests/`

### Documentation
- TBD — any docs describing `outer-loop-eval` behavior

### Configuration
- N/A

## API/Interface

No new CLI surface — this is a pure refactor of one loop YAML to consume existing skills.

## Scope Boundaries

- **In scope**: Rewriting the four analysis states in `outer-loop-eval.yaml` to `action_type: shell` skill invocations; updating associated tests to mock skill output instead of inline prompts.
- **Out of scope**: Changes to `/ll:analyze-loop` or `/ll:assess-loop` skill implementations; new CLI flags or public interface changes; altering `outer-loop-eval`'s invocation contract with callers.

## Acceptance Criteria

- [ ] `outer-loop-eval.yaml` no longer contains inline analysis prompts; states delegate to `/ll:analyze-loop` and `/ll:assess-loop`.
- [ ] `outer-loop-eval` produces an improvement report identical in structure (or richer) to the prior version.
- [ ] When the underlying skills change (e.g., new signal added), `outer-loop-eval` benefits without YAML edits.
- [ ] Existing tests for `outer-loop-eval` updated and passing.

## Depends On

- FEAT-1325 — `/ll:assess-loop` must exist.
- ENH-1326 — resolved-graph view should be available.
- ENH-1327 — effectiveness signals enrich the assessor's input (nice-to-have, not strict blocker).

## Impact

- **Priority**: P4 — blocked by FEAT-1325 and ENH-1326; low urgency until dependencies land
- **Effort**: Medium — rewriting 3-4 YAML states + test mock updates; no new logic required
- **Risk**: Low — pure refactor with identical external behavior; existing tests provide regression coverage
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `refactor`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T13:08:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66b7ef9c-3106-4ab5-9130-c852d0e94984.jsonl`
