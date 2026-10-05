---
id: ENH-3729
type: ENH
title: Fail-closed failure routing and atomic enrich publish for the sft-corpus loop
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T01:33:28Z'
parent: EPIC-3693
---

# ENH-3729: Fail-closed failure routing and atomic enrich publish for the sft-corpus loop

## Summary

Make the packaged `sft-corpus` loop fail closed: a failing `ll-messages` or enrich step must reach a terminal failure state, never be masked into an empty corpus that flows on to filter/publish/success. Split from ENH-3700 on 2026-10-04 (Opus review). This is general FSM failure routing that is testable with the local backend; it is independent of the remote guard and of the degrade verdicts.

## Current Behavior

In `scripts/little_loops/loops/sft-corpus.yaml`, `stage` masks failure with `2>/dev/null || touch "$OUTPUT"` and ends in a pathname `echo`, so even an un-masked non-zero status from `ll-messages` would be overwritten by the echo's success and `on_error` never runs. `enrich` has no failure route and writes `enriched.jsonl` in place, so a mid-run failure can leave a partial file that is later consumed.

## Expected Behavior

- Remove stage's `2>/dev/null || touch "$OUTPUT"` masking. Explicitly propagate the `ll-messages` status (`... > "$OUTPUT" || exit $?`) before the final pathname echo. Check other fallible shell commands too, while preserving the optional absent harvest sentinel.
- On success, emit exactly one pathname on stdout, with notices on stderr. A partial run-private raw file may remain on failure but is never consumed.
- Add `on_error: corpus_failed` to `stage` and `enrich`, with a `corpus_failed` state `terminal: true, failure: true`. Unexpected staging/parsing/serialization errors terminate.
- Publish `enriched.jsonl` through a unique temporary sibling and atomic replace only after success; clean failed temps and retain the previous final file.
- No failure reaches filter/publish or the harvest success sentinel.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Edit the packaged YAML only; keep `${...}` bash escaped as `$${...}` in FSM shell actions and write per-run artifacts under `${context.run_dir}/`. Remember the FSM interpolates the whole action string before bash. A subprocess failure must exit non-zero in the state's shell so `on_error` routes (do not wrap the host command in `if cmd; then` / `|| true`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml`; `scripts/tests/test_loops_sft_corpus.py` (and the built-in-loop gates it participates in).

### Tests
- Execute the actual packaged YAML states and the FSM failure route (not copied shell snippets): a failing `ll-messages` status cannot be overwritten by its pathname echo; stage/enrich failures reach `terminal: true, failure: true` without filter/publish/success sentinel; failure after one record leaves the previous `enriched.jsonl` intact and no leaked temp file; success stdout contains only the captured pathname.
- `ll-loop validate` must stay clean (MR rules).

## Program Design

### Signatures
- `stage` / `enrich` states in `sft-corpus.yaml` gain `on_error: corpus_failed`; new `corpus_failed` terminal failure state.

### Call Path
- `stage` -> `ll-messages --sft-format` -> `enrich` -> filter -> publish; any non-zero status -> `corpus_failed`.

### Decision Rules
- A failure never exits with a code or sentinel that a downstream state could read as success; the previous final output is retained on failure.

## Implementation Steps

1. Remove masking; add `|| exit $?` propagation; add `corpus_failed` and `on_error` routes.
2. Atomic temp+replace publish for `enriched.jsonl`.
3. Tests per above; `ll-loop validate`; run `python -m pytest scripts/tests/` and update the README loop count only if a loop file is added (none is).

## Impact

- **Priority**: P3 - a masked failure silently yields an empty training corpus.
- **Effort**: Small/Medium - one YAML, targeted FSM tests.
- **Risk**: Low-Medium - changes failure semantics of a shipped loop (previously never failed).
- **Breaking Change**: No (behavior only differs where it previously masked an error).

## Scope Boundaries

- **In scope**: failure routing, status propagation, atomic enrichment publication in `sft-corpus.yaml`, and tests of the packaged YAML states.
- **Out of scope**: the `--reader auto` flag and the remote `enrich` passthrough/notes (degrade-sites issue — same states, coordinate when integrating); the central guard (ENH-3700). ENH-3685 reuses this wiring if revived.

## Acceptance Criteria

- [ ] A failing `ll-messages` status in `stage` terminates the loop in `corpus_failed`; the pathname echo cannot overwrite it; success stdout contains only the captured pathname.
- [ ] `stage` and `enrich` both route `on_error` to a `terminal: true, failure: true` state; no failure reaches filter/publish or the harvest success sentinel.
- [ ] `enriched.jsonl` is published atomically only after success; a failure after one record retains the previous final file and cleans temps.
- [ ] Tests execute the packaged YAML states and the FSM route; `ll-loop validate` is clean; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3700 (origin of this scope), the degrade-sites issue (edits the same `stage`/`enrich` states: `--reader auto`, enrich passthrough), ENH-3685 (deferred; reuses this wiring), ENH-3677 (shared fixture).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-05 | Priority: P3
