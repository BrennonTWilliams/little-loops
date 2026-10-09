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

Validate a present readable sentinel before invoking `ll-messages`: after removing an optional trailing line ending, accept exactly one real UTC timestamp in the writer's `YYYY-MM-DDTHH:MM:SSZ` format. Empty, multiline, invalid-date or extra-argument content fails with a fixed safe reason naming `sft-corpus.last_harvested` and telling the user to remove it before rerunning; never echo its contents. Preserve the bad file for inspection and do not silently restart a full harvest. Build optional `--since` arguments with a bash array and quoted expansion, not `SINCE_ARG` word splitting. A valid sentinel yields exactly one value for `--since`. Only genuine path absence is optional; a dangling link is an existing unusable sentinel, not absence. The existing success writer remains outside this slice.

## Motivation

A masked failure in `sft-corpus` silently yields an empty or partially enriched training corpus that downstream states treat as success; failing closed makes the loop's result trustworthy and keeps the previous good `enriched.jsonl`.

## Proposed Solution

Edit the packaged YAML only; keep `${...}` bash escaped as `$${...}` in FSM shell actions and write per-run artifacts under `${context.run_dir}/`. Remember the FSM interpolates the whole action string before bash. A subprocess failure must exit non-zero in the state's shell so `on_error` routes. A checked conditional is allowed if it captures/propagates the failing status; an unchecked conditional, `|| true`, or succeeding final echo must not mask it.

Within these two touched actions, pass `context.run_dir` through the existing quoted `:shell` environment pattern and read it from `os.environ` in Python, rather than injecting it into Python string literals. Use the selected shell variable for mkdir/redirection/sidecar paths. Spaces, quotes and shell metacharacters in a valid run-directory name must remain pathname data. ENH-3728 preserves this plumbing while adding its four quality flags; no sweep of later filter/publish actions is included.

Validate the enrich input record shape before `.get`/`Path(source)`: a syntactically valid JSON array/scalar or non-string non-null source is malformed input, not a traceback-producing `AttributeError`/`TypeError`. Null/missing source retains its existing empty-session behavior. Use the same fixed safe boundary reason and atomic cleanup as syntax/I/O failures, without printing a record or exception text. This is validation for the existing accepted object records, not a change to SFT formats or downstream filters.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml`; `scripts/tests/test_loops_sft_corpus.py` (and the built-in-loop gates it participates in).

### Tests
- Execute the actual packaged YAML states and the FSM failure route (not copied shell snippets): a failing `ll-messages` status cannot be overwritten by its pathname echo; stage/enrich failures reach `terminal: true, failure: true` without filter/publish/success sentinel; failure after one record leaves the previous `enriched.jsonl` intact and no leaked temp file; success stdout contains only the captured pathname.
- Cover absent vs unreadable harvest sentinel, failed run-directory/sidecar writes, malformed second JSONL record and replace failure. These are local deterministic failure injections; ENH-3677's remote fixture is not needed. Leave remote quality-refusal integration tests to ENH-3728 and preserve these routes/temp cleanup in that later edit.
- Include valid JSON with the wrong top-level shape and invalid source type after a good first record: safe non-zero failure, no traceback/raw-record canaries, previous final retained and no temp leak. An existing non-regular harvest sentinel is an error; only genuine absence takes the optional-sentinel path.
- Present empty/garbage/multiline/invalid-date/extra-argument sentinels and a dangling link fail before `ll-messages`, expose no content canary, retain the sentinel and final output, and name the recovery action safely. An actual writer-format timestamp reaches the command as one `--since` value. Stage/enrich also succeed under run-directory names containing spaces, an apostrophe and shell metacharacters through the packaged FSM interpolation path.
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

1. Remove masking; add status propagation for the named fallible shell steps, sentinel validation/quoted argument arrays and run-directory environment transport; add `corpus_failed` and `on_error` routes. No ENH-3677 dependency is required.
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
- [ ] Syntactically valid wrong-shape records and invalid source types fail through the safe enrich boundary without traceback/raw-record output or temp leaks; null/missing source retains its existing behavior. Existing non-regular sentinel paths fail rather than masquerading as absence; checked shell conditionals preserve non-zero status.
- [ ] Readable malformed or dangling-link sentinels fail before command invocation with a safe recovery reason, no content leak or automatic deletion; a valid UTC writer-format timestamp is one quoted `--since` argument. Touched stage/enrich paths survive spaces/quotes/shell metacharacters through environment transport and actual FSM interpolation.
- [ ] Tests execute the packaged YAML states and the FSM route; `ll-loop validate` is clean; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3700 (origin of this scope), ENH-3728 (blocked by this route/atomic publish; edits the same `stage`/`enrich` states), ENH-3685 (deferred; reuses this wiring). ENH-3677 has no functional edge to this backend-independent change.

## Related Key Documentation

- `docs/reference/loops.md` (SFT corpus behavior), `docs/guides/LOOPS_GUIDE.md` (FSM terminal failure semantics).

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Confidence Check Notes

Scope amended 2026-10-06 for sentinel-content validation and safe transport in the two touched actions. The prior 100/82 scores and component scores are cleared; run `/ll:confidence-check` on this revised plan before implementation. This issue can be prepared independently of the remote fixture. Its local FSM tests must pass before ENH-3728 adds the remote fallback/refusal branches.

## Session Log

- EPIC-3693 review #6 + `/ll:advise` (opus, user_requested, confidence 0.62) - 2026-10-06 - validated the sentinel writer format against code; added safe malformed-sentinel recovery and quoted optional arguments, plus run_dir environment transport for touched stage/enrich actions. Prior 100/82 scores cleared for the changed plan; implementation not performed.
- `/ll:confidence-check` - 2026-10-05T18:33:45 - `af0cc2df-1eb5-430f-a8c4-2e0bd187887f.jsonl`
- EPIC-3693 review #4 - 2026-10-05 - malformed object/source cases and non-regular sentinel added to safe atomic failure tests; misleading ban on correctly checked shell conditionals replaced with status-propagation requirement. Fresh Opus consult skipped: existing per-chat budget exhausted; implementation not performed.
- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - artificial fixture dependency removed, ENH-3728 failure-route prerequisite wired, shell/atomic failure cases pinned; implementation not performed
