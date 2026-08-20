---
id: BUG-3271
type: BUG
title: 'general-task: final_verify appends unboundedly to dod.md; count_final awk
  never clears in_section'
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T22:49:08Z'
labels:
- bug
- loops
- general-task
- fsm
- dod
- postmortem
relates_to:
- ENH-2584
- BUG-3269
- BUG-3270
- ENH-3272
---

# BUG-3271: general-task: final_verify appends unboundedly to dod.md; count_final awk never clears in_section

## Summary

`general-task.yaml`'s `final_verify` state instructs the model to **append** a new section
to `dod.md` on every entry. It is on a cycle, so across 45 laps of run
`2026-08-20T121448` it grew `dod.md` to **610 KB / 1973 lines / 932 checkboxes** with ~45
duplicate `## Final Verification` blocks — each re-listing the same 20 criteria.

Bundled here because it is the same state and the same file: `count_final`'s awk never
clears `in_section`, so its FAILED tally covers the last `## Final Verification` block plus
everything after it to EOF.

Postmortem: `postmortems/general-task-final-verify-spin-2026-08-20.md` (§4).

## Current Behavior

### Unbounded append

`general-task.yaml:564` instructs:

> Append a new section to the DoD file in this exact format:
> ```
> ## Final Verification
> - [x] <criterion>: <evidence>
> ```

Final section tally from the run:

```
20  ## Verification Criteria
 3  ## Sample Verification
 4  ## Standing Criteria
81  ## Final Verification
20  ## Final Verification (2026-08-20T20:14 — fresh independent re-run)
20  ## Final Verification (2026-08-20T20:45 — fresh independent re-run)
...  [~40 more]
```

Two secondary effects:

**Hallucinated timestamps.** Section headers include `23:55`, `23:58`, `23:59`,
`2026-08-21`, and `this run`. The prompt asks for a bare `## Final Verification` header —
the model added timestamps unprompted, precisely because each lap it found its own prior
identical section and tried to differentiate. The model has no clock, so the times are
invented. **Do not ask a model to disambiguate repeated writes it cannot distinguish.**

**Superlinear cost growth.** Each lap re-reads the file it just doubled. Later laps ran
113s+. The state carries `timeout: 1800` with `on_error: summarize_partial`
(`general-task.yaml:585`), so a long enough run silently degrades to the `partial` terminal
purely from self-inflicted file growth — a `partial` outcome caused by nothing but the
loop's own accumulated prose.

### `count_final` awk scans past its section

`general-task.yaml:635-639`:

```awk
/^## Final Verification/ { in_section=1; count=0; next }
in_section && /FAILED/ { count++ }
END { print count+0 }
```

`in_section` is never cleared on a subsequent non-matching `## ` header, so the count
covers the last `## Final Verification` block **plus everything after it to EOF**.
Verified:

```
$ printf '## Final Verification\n- FAILED x\n## Other\n- FAILED y\n## Final Verification (2)\n- FAILED z\n' | awk '...'
1        # 'y' was counted into the first section's tally before the reset
```

In the audited run this was harmless-to-helpful — the trailing `## Closing consistency
sweep` blocks contain failures the prompt *wanted* counted. But it is the same
accumulating-prose-poisons-the-gate hazard that `count_done`'s own inline description warns
about at length for `failed_samples`, and the "helpful" behavior is accidental, not
designed.

## Steps to Reproduce

**The awk defect — self-contained, no run needed:**

```
$ printf '## Final Verification\n- FAILED x\n## Other\n- FAILED y\n## Final Verification (2)\n- FAILED z\n' \
  | awk '/^## Final Verification/ { in_section=1; count=0; next } in_section && /FAILED/ { count++ } END { print count+0 }'
1
```

Expected `1` for the last section alone — but `y`, which lives under `## Other`, was counted
into the preceding section's tally before the reset. The scan never terminates at a
non-matching `## ` header.

**The unbounded append:**

1. Run `general-task` on any task that enters `final_verify` more than once — i.e. any run
   where `run_final_tests` fails at least once and `continue_work` then fixes it.
   Reproducing BUG-3269 forces this maximally.
2. After each lap, count sections: `grep -c '^## Final Verification' ${run_dir}/dod.md`.
   It rises by one per lap and never falls.
3. Watch `dod.md` size and `final_verify` state duration climb together — each entry
   re-reads the file the previous entry grew.
4. Inspect the section headers. Beyond ~2 laps the model begins appending invented
   timestamps and run labels (`(2026-08-20T20:14 — fresh independent re-run)`) that the
   prompt never asked for.

**Frequency**: every multi-entry `final_verify`. Not conditional on any config.

**Observed in**: `general-task` v1.156.0, run `2026-08-20T121448` — 45 entries produced
`dod.md` at 610 KB / 1973 lines / 932 checkboxes.

## Expected Behavior

**Idempotent `final_verify`.** Re-entering the state N times produces the same `dod.md`
size and structure as entering it once. Either:

- **replace** the existing `## Final Verification` section rather than appending, or
- write to a separate `final-verify-<n>.md` capped at the last K runs.

Replacement is preferred: it keeps `count_final`'s single-file contract intact and removes
the model's incentive to invent disambiguating timestamps, since there is never a prior
section to collide with.

**Bounded `count_final` scan.** The FAILED tally covers exactly the `## Final Verification`
section, not everything after it:

```awk
/^## / && !/^## Final Verification/ { in_section=0 }
```

If the trailing `## Closing consistency sweep` failures are genuinely wanted in the tally,
that must be stated explicitly — matched by name, not captured by an unterminated scan.
Decide which, and encode the decision; do not preserve the current accident.

## Motivation

Independent of BUG-3269 and BUG-3270: even a *correctly terminating* run enters `final_verify`
more than once whenever `run_final_tests` legitimately fails and `continue_work` fixes it.
The append is unbounded on any cycle, not just the pathological one.

This is a cheaper subset of deferred **ENH-2584** ("decompose `final_verify` into bounded
per-batch verification", P2, status `deferred`). The unbounded-append problem is the part
that actually bites, and it is landable without the decomposition. Land it independently;
ENH-2584 stays deferred.

The awk fix is bundled rather than filed separately (the postmortem proposed it as its own
P3) because it is a one-line change to the state immediately downstream of `final_verify`,
touching the same file and covered by the same test. Filing it alone would cost more
process overhead than the fix.

## Proposed Solution

1. Rewrite the `final_verify` prompt (`general-task.yaml:564`) to instruct
   **replacement** of the `## Final Verification` section — including explicit
   instruction to remove any pre-existing section of that name first, and to use the bare
   header with no timestamp or run identifier.
2. Because prompt instructions are advisory, add a deterministic shell pre-step (or a
   post-step in `count_final`) that strips all but the last `## Final Verification`
   section, so the invariant holds even when the model appends anyway.
3. Add the `in_section` reset line to the `count_final` awk.
4. Test: run `final_verify`'s file-mutation contract twice against a fixture `dod.md`,
   assert byte-identical output and exactly one `## Final Verification` section. Separately
   assert the awk tally against the 3-section fixture above.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml:564` — the `final_verify` prompt body
  (append → replace, and drop the model's timestamp latitude)
- `scripts/little_loops/loops/general-task.yaml:635-639` — the `count_final` awk
- `scripts/little_loops/loops/general-task.yaml` — new deterministic section-strip step
  (see Program Design)

### Dependent Files (Callers/Importers)
- Nothing imports `dod.md` outside this loop, but three states read or count it and all
  three must agree on the invariant:
  - `count_done` (`:~530`) — counts unchecked DoD criteria
  - `final_verify` (`:552`) — writes
  - `count_final` (`:632`) — counts FAILEDs
- `summarize_success` / `summarize_partial` — surface DoD state in the run summary

### Similar Patterns
- `count_done`'s own inline description already warns at length about accumulating prose
  poisoning the `failed_samples` gate — the same hazard, already articulated, one state over
- `select_step:245` — the in-place `awk ... > "$PLAN.tmp" && mv` rewrite pattern to model the
  deterministic strip on

### Tests
- `scripts/tests/test_builtin_loops.py`
- New: idempotence — apply `final_verify`'s file contract twice to a fixture `dod.md`,
  assert byte-identical output and exactly one `## Final Verification` section
- New: the awk tally against the 3-section fixture in Steps to Reproduce

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — state the invariant that a state on a cycle
  must be idempotent in its file writes
- ENH-2584 remains `deferred`; note there that this issue landed the append fix separately

### Configuration
- N/A

## Program Design

### Signatures

- `final_verify(dod_path: str) -> None` — writes `dod.md`; currently append-only, becomes
  replace-in-place so N entries produce the file of one entry.
- `strip_stale_final_sections(dod_path: str) -> None` — new deterministic shell step folded
  into the head of `count_final`; leaves at most one `## Final Verification` section.
- `count_final(dod_path: str) -> dict` — unchanged signature, emitting
  `{"failed_finals": int}`; the awk gains a section-terminating rule so the tally is bounded.

### Call Path

- `count_done` → `final_verify` — the entry edge; reached whenever `done_counts.total == 0`.
- `final_verify` → writes `${context.run_dir}/dod.md` — the unbounded append at
  `general-task.yaml:564`.
- `final_verify` → `run_final_tests` → `continue_work` → `final_verify` — the cycle that
  makes the append unbounded; each lap re-reads the file the previous lap grew.
- `final_verify` → `summarize_partial` — the `on_error` edge at `general-task.yaml:585`;
  the silent degradation path once file growth pushes the state past `timeout: 1800`.
- `run_final_tests` → `count_final` → `strip_stale_final_sections` → awk tally — the new
  bounded read path.
- `count_final` → `check_provisional_markers` → `summarize_success` — the terminal path
  gated by the tally.
- `load_and_validate` (`scripts/little_loops/fsm/validation/structural_rules.py:1659`) —
  the validator `general-task.yaml` is checked against; the new idempotence and
  awk-tally tests belong alongside its existing `test_builtin_loops.py` coverage
  rather than as a new standalone harness.

### Invariant

**Invariant**: `dod.md` contains **at most one** `## Final Verification` section, and
entering `final_verify` N times produces the same file as entering it once.

Enforced at two levels, because a prompt instruction alone is advisory:

1. **Prompt (`:564`)** — instruct replacement, not append: remove any pre-existing
   `## Final Verification` section, then write exactly one, using the bare header with **no**
   timestamp, date, or run identifier. State the "no timestamp" rule explicitly — the model
   invented them precisely because it kept colliding with its own prior section, and it has
   no clock to invent them correctly.
2. **Deterministic strip** — a shell step that keeps only the **last**
   `## Final Verification` section, so the invariant holds even when the model appends
   anyway. Place it at the head of `count_final` rather than as a new state: `count_final`
   is the only consumer of the section, it already reads the file, and folding it in avoids
   an extra state on the cycle. Use the `awk ... > tmp && mv` pattern from `select_step:245`.

**`count_final` awk — bounded scan.** Add the terminating rule:

```awk
/^## / && !/^## Final Verification/ { in_section=0 }
```

**Open decision this issue must resolve, not inherit.** The current unterminated scan also
sweeps up `## Closing consistency sweep` failures, which the `final_verify` prompt does ask
the model to produce. Today that inclusion is an accident of a missing reset, not a design.
Pick one and encode it:

- **(a)** Sweep failures belong in the tally → have `final_verify` append them *into* the
  `## Final Verification` section (as its prompt already instructs at `:580`), and let the
  bounded scan pick them up there.
- **(b)** They do not → the bounded scan alone is correct.

**(a) is the better fit**: the prompt at `:580` already says "Append any failure found by
this sweep to the `## Final Verification` section above", so the sweep failures are
*supposed* to be inside the section already. The bounded scan then loses nothing, and the
current behavior was compensating for a prompt the model was not reliably following.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Confirmed current anchors** (`scripts/little_loops/loops/general-task.yaml`, line numbers as of this pass):
  - `final_verify` state: `:553-594` (`timeout: 1800` at `:554`). Prompt confirms **two independent append instructions**, no timestamp anywhere in the prompt text:
    - `:564` — "Append a new section to the DoD file..." (the primary unbounded append).
    - `:583` — "Append any failure found by this sweep to the `## Final Verification` section above..." — a second append targeting the *same* section, on every cycle. (The issue's `:580` citation for this instruction is stale; it is now at `:583`, with the sweep description spanning `:576-582`.)
    - `on_error: summarize_partial` at `:594`, with an inline `ENH-2575` comment explaining the routing (a timeout re-verifying a large DoD must not collapse to `failed`).
  - `count_final` state: `:629-651`. Exact current awk (`:636-640`):
    ```
    /^## Final Verification/ { in_section=1; count=0; next }
    in_section && /FAILED/ { count++ }
    END { print count+0 }
    ```
    Confirmed: no rule clears `in_section` on a subsequent non-matching `^## ` header — the scan runs to EOF. `capture: final_counts`; `evaluate: {type: output_json, path: ".failed_finals", operator: eq, target: 0}` (`:644-648`); `on_no: continue_work` (`:650`) — this awk output directly drives the gate, unlike the analogous case in `count_done` below.
  - `select_step` awk-tmp-mv in-place rewrite pattern (the model to follow): `:242-244` (abandonment mark), plus two further instances of the identical idiom at `:390` and `:392` (step-completion marks) — all three target `plan.md`. Shape: `awk '<condition> { <sub()>; found=1 } 1' "$FILE" > "$FILE.tmp" && mv "$FILE.tmp" "$FILE"`. No equivalent strip-to-last-section rewrite currently exists for `dod.md`.
  - `count_done`'s inline warning about accumulating prose poisoning a gate: state-level `description:` block at `:470-480` and a restated inline comment in the action body at `:531-538` (two separate places, same warning) — explicitly instructs "Do NOT re-add `failed_samples` to the gate" because Sample Verification sections accumulate free-form LLM prose that re-emits historical FAILEDs.
  - **Important asymmetry**: `count_done`'s own `FAILED_SAMPLES` awk (`:514-518`) has the *same* unreset-`in_section` defect as `count_final`'s, but it is explicitly excluded from `count_done`'s gate (`evaluate.path: ".total"` does not include it — see `:531` "reported for observability but is NOT part of the gate"). `count_final`'s awk has no such exclusion — its `FAILED` count is the direct gate input, which is why its identical defect is load-bearing (drives `on_no: continue_work`) where `count_done`'s is merely cosmetic.

## Implementation Steps

1. **Pin the current behavior in a test** — the 3-section awk fixture, asserting today's
   wrong answer, so the change is visible as an intentional flip.
2. **Fix the awk.** Add the `in_section=0` reset; update the fixture assertion.
3. **Resolve the (a)/(b) decision** above and, if (a), strengthen the `:580` prompt language
   so sweep failures land inside the section.
4. **Rewrite the `final_verify` prompt** for replacement semantics with an explicit
   no-timestamp rule.
5. **Add the deterministic strip** at the head of `count_final`.
6. **Test idempotence.** Two applications of the file contract → byte-identical `dod.md`,
   exactly one `## Final Verification`.
7. **Validate and verify.** `ll-loop validate general-task` clean;
   `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P1. Degrades any multi-lap run, and can silently convert a `success` into
  a `partial` via timeout.
- **Scope**: one prompt body, one shell guard, one awk line — all in `general-task.yaml`.
- **Risk**: low. The replacement semantics discard prior `final_verify` sections, which are
  by construction supposed to be re-derived from evidence on every entry.
- **Note**: the awk change may alter the FAILED tally for runs that relied on the
  scan-to-EOF behavior. That is the point, but it is a behavior change, so make the
  intended scope explicit in the state's comment.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §4
- ENH-2584 — deferred bounded-`final_verify` decomposition; this is a landable subset
- ENH-2575 — `final_verify` `on_error: summarize_partial` routing, the degradation path

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
