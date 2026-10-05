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
blocks:
- ENH-3728
relates_to:
- ENH-3728
- ENH-3700
---

# ENH-3729: Fail-closed failure routing and atomic enrich publish for the sft-corpus loop

## Summary

Make the packaged `sft-corpus` loop fail closed: a failing `ll-messages` or enrich step must reach a terminal failure state, never be masked into an empty corpus that flows on to filter/publish/success. Split from ENH-3700 on 2026-10-04 (Opus review). This is general FSM failure routing testable with the local backend; it has no fixture or remote-guard prerequisite. It must precede ENH-3728, whose remote quality refusal relies on these failure routes.

## Current Behavior

In `scripts/little_loops/loops/sft-corpus.yaml`, `stage` masks failure with `2>/dev/null || touch "$OUTPUT"` and ends in a pathname `echo`, so even an un-masked non-zero status from `ll-messages` would be overwritten by the echo's success and `on_error` never runs. `enrich` has no failure route and writes `enriched.jsonl` in place, so a mid-run failure can leave a partial file that is later consumed.

## Expected Behavior

- Remove stage's `2>/dev/null || touch "$OUTPUT"` masking. Explicitly propagate the `ll-messages` status (`... > "$OUTPUT" || exit $?`) before the final pathname echo. Check other fallible shell commands too, while preserving the optional absent harvest sentinel.
- On success, emit exactly one pathname on stdout, with notices on stderr. A partial run-private raw file may remain on failure but is never consumed.
- Add `on_error: corpus_failed` to `stage` and `enrich`, with a `corpus_failed` state `terminal: true, failure: true`. Unexpected staging/parsing/serialization errors terminate.
- Publish `enriched.jsonl` through a unique temporary sibling and atomic replace only after success; clean failed temps and retain the previous final file.
- Report expected file/JSON/serialization/publish failures at the enrich state boundary with a fixed safe stderr reason and non-zero exit, after temp cleanup; do not print raw records, SQL, tokens or an unhandled traceback. This handler must never turn failure into an echoed success pathname.
- No failure reaches filter/publish or the harvest success sentinel.

The optional absence of `sft-corpus.last_harvested` is normal; an existing sentinel that cannot be read is an error. Check `mkdir`, sentinel reads and the captured-path sidecar write as well as `ll-messages`/Python exits: a succeeding later command must not mask their status. Do not change the successful incremental-harvest semantics.

## Motivation

A masked failure in `sft-corpus` silently yields an empty or partially enriched training corpus that downstream states treat as success; failing closed makes the loop's result trustworthy and keeps the previous good `enriched.jsonl`.

## Proposed Solution

Edit the packaged YAML only; keep `${...}` bash escaped as `$${...}` in FSM shell actions and write per-run artifacts under `${context.run_dir}/`. Remember the FSM interpolates the whole action string before bash. A subprocess failure must exit non-zero in the state's shell so `on_error` routes (do not wrap the host command in `if cmd; then` / `|| true`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml`; `scripts/tests/test_loops_sft_corpus.py` (and the built-in-loop gates it participates in).

### Tests
- Execute the actual packaged YAML states and the FSM failure route (not copied shell snippets): a failing `ll-messages` status cannot be overwritten by its pathname echo; stage/enrich failures reach `terminal: true, failure: true` without filter/publish/success sentinel; failure after one record leaves the previous `enriched.jsonl` intact and no leaked temp file; success stdout contains only the captured pathname.
- Cover absent vs unreadable harvest sentinel, failed run-directory/sidecar writes, malformed second JSONL record and replace failure. These are local deterministic failure injections; ENH-3677's remote fixture is not needed. Leave remote quality-refusal integration tests to ENH-3728 and preserve these routes/temp cleanup in that later edit.
- `ll-loop validate` must stay clean (MR rules).

## Program Design

### Signatures
- `stage(output: Path) -> Path` — `sft-corpus.yaml` state; non-zero `ll-messages` status routes via `on_error: corpus_failed`.
- `enrich(raw: Path) -> Path` — `sft-corpus.yaml` state; publishes `enriched.jsonl` atomically, `on_error: corpus_failed`.
- `corpus_failed() -> None` — new terminal failure state (`terminal: true, failure: true`).

### Call Path
- `stage` -> `ll-messages --sft-format` -> `enrich` -> filter -> publish; any non-zero status -> `corpus_failed`.

### Decision Rules
- A failure never exits with a code or sentinel that a downstream state could read as success; the previous final output is retained on failure.

## Implementation Steps

1. Remove masking; add status propagation for the named fallible shell steps; add `corpus_failed` and `on_error` routes. No ENH-3677 dependency is required.
2. Atomic temp+replace publish for `enriched.jsonl`.
3. Tests per above; `ll-loop validate`; run `python -m pytest scripts/tests/` and update the README loop count only if a loop file is added (none is).

## Impact

- **Priority**: P3 - a masked failure silently yields an empty training corpus.
- **Effort**: Small/Medium - one YAML, targeted FSM tests.
- **Risk**: Low-Medium - changes failure semantics of a shipped loop (previously never failed).
- **Breaking Change**: No (behavior only differs where it previously masked an error).

## Scope Boundaries

- **In scope**: failure routing, status propagation, atomic enrichment publication in `sft-corpus.yaml`, and tests of the packaged YAML states.
- **Out of scope**: the `--reader auto` flag and remote enrich passthrough/quality refusal/notes (ENH-3728 — same states, lands after this); the central guard (ENH-3700). ENH-3685 reuses this wiring if revived.

## Acceptance Criteria

- [ ] A failing `ll-messages` status in `stage` terminates the loop in `corpus_failed`; the pathname echo cannot overwrite it; success stdout contains only the captured pathname.
- [ ] `stage` and `enrich` both route `on_error` to a `terminal: true, failure: true` state; no failure reaches filter/publish or the harvest success sentinel.
- [ ] `enriched.jsonl` is published atomically only after success; a failure after one record retains the previous final file and cleans temps.
- [ ] Absent harvest sentinel remains successful; unreadable sentinel, mkdir/sidecar failure, malformed later JSONL record and atomic-replace failure reach the failure terminal without downstream execution or replacement of the previous good output.
- [ ] Tests execute the packaged YAML states and the FSM route; `ll-loop validate` is clean; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3700 (origin of this scope), ENH-3728 (blocked by this route/atomic publish; edits the same `stage`/`enrich` states), ENH-3685 (deferred; reuses this wiring). ENH-3677 has no functional edge to this backend-independent change.

## Related Key Documentation

- `docs/reference/loops.md` (SFT corpus behavior), `docs/guides/LOOPS_GUIDE.md` (FSM terminal failure semantics).

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Confidence Check Notes

Scope/dependencies amended 2026-10-05; run `/ll:confidence-check` before implementation. This issue can be prepared independently of the remote fixture. Its local FSM tests must pass before ENH-3728 adds the remote fallback/refusal branches.

## Session Log

- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - artificial fixture dependency removed, ENH-3728 failure-route prerequisite wired, shell/atomic failure cases pinned; implementation not performed
