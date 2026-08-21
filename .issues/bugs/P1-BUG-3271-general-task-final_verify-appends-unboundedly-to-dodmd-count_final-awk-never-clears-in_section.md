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
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 22
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

**The awk half is the load-bearing one.** An earlier pass framed it as a cheap P3 rider on
the append fix. It is not: `check_done` writes a `## Sample Verification` section from
inside the same cycle, so that section lands *after* the last `## Final Verification`
section and its historical `FAILED` lines are swept into `count_final`'s gate — the exact
poisoning `count_done` explicitly refuses for its own gate. That can pin `failed_finals`
above 0 permanently and hang the run. See
[§`count_final` awk scans past its section](#count_final-awk-scans-past-its-section).
Sequence the awk fix first and independently.

Postmortem: `postmortems/general-task-final-verify-spin-2026-08-20.md` (§4).

## Current Behavior

### Unbounded append

`general-task.yaml:595` instructs:

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
(`general-task.yaml:625`), so a long enough run silently degrades to the `partial` terminal
purely from self-inflicted file growth — a `partial` outcome caused by nothing but the
loop's own accumulated prose.

### `count_final` awk scans past its section

`general-task.yaml:676-680`:

```awk
/^## Final Verification/ { in_section=1; count=0; next }
in_section && /FAILED/ { count++ }
END { print count+0 }
```

`in_section` is never cleared on a subsequent non-matching `## ` header, so the count
covers the last `## Final Verification` block **plus everything after it to EOF**.
Verified:

```
$ printf '## Final Verification\n- FAILED x\n## Closing consistency sweep\n- FAILED y\n' \
  | awk '/^## Final Verification/ { in_section=1; count=0; next }
         in_section && /FAILED/ { count++ }
         END { print count+0 }'
2        # 'y' lives under ## Closing consistency sweep, outside the section
```

#### This is a run-hanging defect, not a cosmetic one

An earlier pass called the over-scan "harmless-to-helpful" on the grounds that the trailing
`## Closing consistency sweep` blocks contain failures the prompt wanted counted. That
reading is wrong, because the sweep is not the only thing that lands after the section.

`check_done` (`general-task.yaml:483-495`) writes a `## Sample Verification` section, and it
sits on the same cycle as `final_verify`:

```
continue_work → select_step → … → check_done → count_done → final_verify
```

So on any lap that routes through `select_step`, `check_done` writes `## Sample
Verification` **after** the last `## Final Verification` section, and `count_final`'s
scan-to-EOF sweeps its `FAILED` lines into the gate.

That is precisely the poisoning `count_done` refuses for itself. Its inline comment
(`general-task.yaml:562-569`) states that Sample Verification sections "accumulate across
iterations and are free-form LLM prose that re-emits historical FAILEDs, which permanently
poisons the count," and deliberately drops `failed_samples` from its own gate
(`evaluate.path: ".total"`). `count_final` has no such exclusion — `.failed_finals` **is**
the gate, with `on_no: continue_work` (`:690`). A single historical sample FAILED can
therefore hold `failed_finals` above 0 for the rest of the run, and the loop can never
reach `check_provisional_markers`.

This makes the over-scan a plausible direct mechanism for the observed 45-lap spin, and it
settles the (a)/(b) decision in Program Design decisively in favor of **(b), a bounded
scan**. It also rules out the tempting third option — "keep scan-to-EOF and rely on the
deterministic strip for boundedness" — because the strip removes stale *Final Verification*
sections, not Sample Verification ones.

## Steps to Reproduce

**The awk defect — self-contained, no run needed:**

```
$ printf '## Final Verification\n- FAILED x\n## Closing consistency sweep\n- FAILED y\n' \
  | awk '/^## Final Verification/ { in_section=1; count=0; next } in_section && /FAILED/ { count++ } END { print count+0 }'
2
```

Expected `1` — the section holds one FAILED. `y` lives under `## Closing consistency
sweep`, outside the section, but the scan never terminates at a non-matching `## ` header
and runs to EOF.

**The fixture must place the foreign heading after the LAST `## Final Verification`
section.** A fixture that interleaves them —
`## Final Verification / FAILED x / ## Other / FAILED y / ## Final Verification (2) /
FAILED z` — returns `1` under both the current and the fixed awk, because the `count=0`
reset on the second `## Final Verification` match discards the mis-counted `y`. Verified
both ways. A pinning test built on that shape asserts a value the fix does not change, so
it proves nothing. The two-section shape above is the discriminating one: `2` today, `1`
after the fix.

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
section, not everything after it. Add a section-terminating rule after the existing
section-entry rule:

```awk
/^## Final Verification/ { in_section=1; count=0; next }
/^## / { in_section=0 }
in_section && /FAILED/ { count++ }
END { print count+0 }
```

The entry rule ends in `next`, so the terminator does not need the
`&& !/^## Final Verification/` guard an earlier pass proposed — a bare `/^## /` placed
after it is sufficient and is the exact form already used by `write_partial_summary`
(`:911+`) and `summarize_success` (`:718+`). Verified: `2` → `1` on the fixture above.

Trailing `## Closing consistency sweep` failures are **not** admitted to the tally by the
scan. They belong inside the `## Final Verification` section, which is what the
`final_verify` prompt already instructs at `:614`; strengthen that instruction rather than
widening the scan. See the resolved (a)/(b) decision in Program Design.

## Motivation

Independent of BUG-3269 and BUG-3270: even a *correctly terminating* run enters `final_verify`
more than once whenever `run_final_tests` legitimately fails and `continue_work` fixes it.
The append is unbounded on any cycle, not just the pathological one.

This is a cheaper subset of deferred **ENH-2584** ("decompose `final_verify` into bounded
per-batch verification", P2, status `deferred`). The unbounded-append problem is the part
that actually bites, and it is landable without the decomposition. Land it independently;
ENH-2584 stays deferred.

The awk fix stays bundled here (the postmortem proposed it as its own P3) because it
touches the same file and the same cycle — but it is **not** a rider. It is the half that
can hang a run outright, via the `## Sample Verification` poisoning path documented under
Current Behavior, and it is independently landable with its own test. Land it first, on its
own commit, before the prompt rewrite and the strip.

## Proposed Solution

1. Add the `in_section` reset line to the `count_final` awk (`:676-680`) — first, standalone,
   with the discriminating 2-section fixture test. This is the run-hanging half.
2. Rewrite the `final_verify` prompt (`general-task.yaml:595`) to instruct
   **replacement** of the `## Final Verification` section — including explicit
   instruction to remove any pre-existing section of that name first, and to use the bare
   header with no timestamp or run identifier.
3. Because prompt instructions are advisory, add a deterministic shell strip that keeps only
   the last `## Final Verification` section, so the invariant holds even when the model
   appends anyway. **Place it at the head of `run_final_tests` (`:627`), not `count_final`** —
   see Program Design §Invariant for why `count_final` is the wrong edge.
4. Test: execute the strip twice against a fixture `dod.md`, assert byte-identical output
   and exactly one `## Final Verification` section; assert the awk tally against the
   2-section fixture above; assert statically that the `final_verify` prompt carries the
   replace + no-timestamp language.

## Integration Map

### Files to Modify

All line numbers below re-anchored against `general-task.yaml` as of 2026-08-20 (an earlier
pass's `:564` / `:635-639` / `:580` citations were stale).

- `scripts/little_loops/loops/general-task.yaml:676-680` — the `count_final` awk (change 1)
- `scripts/little_loops/loops/general-task.yaml:595` — the `final_verify` prompt body
  (append → replace, and drop the model's timestamp latitude)
- `scripts/little_loops/loops/general-task.yaml:614` — the sweep-append instruction;
  strengthen so sweep failures land *inside* the section (decision (a), below)
- `scripts/little_loops/loops/general-task.yaml:627` — head of `run_final_tests`, where the
  new deterministic section-strip step goes (see Program Design)
- `scripts/little_loops/loops/general-task.yaml:545-549` — `count_done`'s `FAILED_SAMPLES`
  awk carries the identical unreset-`in_section` defect. It is observability-only there
  (excluded from the gate, `:562-569`), but fixing only one of the instances invites
  reintroduction. `write_partial_summary` (`:911+`) and `summarize_success` (`:718+`)
  already carry the correct reset — this one line makes it 4-for-4.

### Dependent Files (Callers/Importers)
- Nothing imports `dod.md` outside this loop, but four states read or write it and all
  four must agree on the invariant:
  - `check_done` (`:483-495`) — writes/replaces `## Sample Verification`; the section whose
    trailing placement poisons `count_final`'s unbounded scan
  - `count_done` (`:501-582`) — counts unchecked DoD criteria
  - `final_verify` (`:584-625`) — writes
  - `count_final` (`:669-691`) — counts FAILEDs
- `summarize_success` / `summarize_partial` — surface DoD state in the run summary

### Similar Patterns
- `count_done`'s own inline description already warns at length about accumulating prose
  poisoning the `failed_samples` gate — the same hazard, already articulated, one state over
- `select_step:273-275` and `mark_done:421,423` — the in-place
  `awk ... > "$PLAN.tmp" && mv` rewrite pattern to model the deterministic strip on

### Tests
- `scripts/tests/test_general_task_loop.py` — `TestCountFinalShellScript` (~`:1354`), where
  the existing `count_final` shell coverage lives. **Not** `test_builtin_loops.py`, which
  only carries static routing assertions for this state (`:14777`).
- New: the awk tally against the discriminating 2-section fixture in Steps to Reproduce
  (`2` before the fix, `1` after) — the existing `_TWO_SECTIONS_FINAL_DOD` fixture
  (`:1339-1350`) does not exercise this gap, since it stacks two Final Verification sections
  back-to-back with no foreign heading between them.
- New: strip idempotence — execute the strip twice against a fixture `dod.md`, assert
  byte-identical output and exactly one `## Final Verification` section.
- New: static assertion that the `final_verify` prompt carries replace-not-append and
  no-timestamp language.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — state the invariant that a state on a cycle
  must be idempotent in its file writes
- ENH-2584 remains `deferred`; note there that this issue landed the append fix separately

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Test file location corrected**: existing `count_final` awk coverage lives in `scripts/tests/test_general_task_loop.py` (class `TestCountFinalShellScript`, around line 1353; helper `_load_count_final_script()` at line 1251), **not** `test_builtin_loops.py` as cited above and in Program Design's Call Path. Fixture `_TWO_SECTIONS_FINAL_DOD` (lines 1339-1350) stacks two `## Final Verification` sections back-to-back with no other heading between them; `test_two_sections_only_counts_most_recent` (lines 1380-1393) asserts `failed_finals == 0` — but this passes today because `count=0` resets on every `/^## Final Verification/` match itself, not because of a generic `## ` reset, so it does **not** exercise the specific gap this issue reports (a *different* `## ` heading following the last Final Verification section). New idempotence/awk-boundary tests belong alongside `TestCountFinalShellScript` in `test_general_task_loop.py`.
- **Test-writing shape to follow**: `test_general_task_loop.py`/`test_builtin_loops.py` share a family of helpers that load a state's real `action:` shell text from the YAML, substitute `${context.*}`/`${captured.*.output}` tokens with concrete literals, then execute it via `subprocess.run(["bash", "-c", script], ...)` against a staged fixture directory — e.g. `_run_record` (`test_builtin_loops.py:3204-3208`), `_run_check_hedge_attempts` (`test_builtin_loops.py:1592-1600`, includes an `assert "${" not in script` guard), and `_run_test_and_aggregate` (`test_builtin_loops.py:12333-12359`, chains two states against one `run_dir`). The new idempotence test (apply the file contract twice, assert byte-identical output) fits this family, not the separate static-YAML-assertion family also present in `TestGeneralTaskLoop` (e.g. `test_check_baseline_tests_writes_baseline_exit_to_run_dir`).
- **Additional section-scoping precedent** (beyond `count_done`'s `HARD_UNCHECKED_DOD`/`SOFT_UNCHECKED_DOD`/`TOTAL_DOD` awks already cited): `write_partial_summary` (`general-task.yaml:882-903`) and `summarize_success` (`general-task.yaml:693-704`) both run the same `TOTAL`/`UNCHECKED` awk pair with a correct `/^## / { in_section=0 }` reset immediately after the section-entry rule — two more instances of the pattern `count_final`'s awk should match.
- **Existing prompt-only "replace" precedent, no deterministic backstop**: `check_done`'s prompt (`general-task.yaml:452-460`) already instructs the model to *"Replace the `## Sample Verification` section in the DoD file: if one already exists, remove it entirely before writing the new one; if none exists, create it."* This is the only existing "replace a whole section" instruction in the file — like the `final_verify` fix this issue proposes, it is advisory only (no shell-level backstop exists for it either), so it is evidence the phrasing pattern is already in use here, not evidence that advisory-only replacement is reliable.
- **No cross-loop idempotent-write idiom found**: a search of `scripts/little_loops/loops/*.yaml` found no "strip stale section, keep the last" shell idiom anywhere outside the single-line `plan.md` awk-tmp-mv mark idiom already cited. `resolve-decision.yaml` (`:120-134`) handles a structurally similar accumulating-file concern via a Python helper (`count_open_questions_in_sections`/`count_unresolved_options` from `little_loops.issue_parser`, invoked via `python3 -c`) — but it only counts, it does not strip/replace a section, so it is not a counter-example to model the new strip step on.

## Program Design

### Signatures

- `final_verify` — an `action_type: prompt` state, **not** a callable with a file-mutation
  signature. An earlier pass listed `final_verify(dod_path: str) -> None` here; that is
  fiction, and it is what produced the untestable "apply the file contract twice" step. The
  only thing testable about `final_verify` is its prompt *text* (static YAML assertions).
  Behaviorally: it currently appends, and must be reworded to replace.
- `strip_stale_final_sections(dod_path: str) -> None` — new deterministic shell step at the
  **head of `run_final_tests`**; leaves at most one `## Final Verification` section. This is
  the only part of the idempotence story that is executable, and therefore the only part the
  idempotence test can target.
- `count_final(dod_path: str) -> dict` — unchanged signature, emitting
  `{"failed_finals": int}`; the awk gains a section-terminating rule so the tally is bounded.

### Call Path

- `count_done` → `final_verify` — one entry edge; reached whenever `done_counts.total == 0`.
- `continue_work` → `final_verify` — the *other* entry edge (`on_yes`, `:816+`), which
  bypasses `count_done` entirely. This is the edge that makes the spin tight.
- `final_verify` → writes `${context.run_dir}/dod.md` — the unbounded append at
  `general-task.yaml:595`, plus a second append into the same section at `:614`.
- `final_verify` → `run_final_tests` — an unconditional `next:`. Every `final_verify` entry
  passes through `run_final_tests` on the very next step, on both of its outcome branches.
  **This is why the strip belongs here.**
- `final_verify` → `run_final_tests` → (`on_no`) `continue_work` → (`on_yes`)
  `final_verify` — the spin cycle. Note it never touches `count_final`.
- `final_verify` → `summarize_partial` — the `on_error` edge at `general-task.yaml:625`;
  the silent degradation path once file growth pushes the state past `timeout: 1800`.
- `run_final_tests` → (`on_yes`) `count_final` → bounded awk tally → (`on_no`)
  `continue_work` — the gate that historical `## Sample Verification` FAILEDs can pin.
- `count_final` → `check_provisional_markers` → `summarize_success` — the terminal path
  gated by the tally.
- Test placement: alongside `TestCountFinalShellScript` in
  `scripts/tests/test_general_task_loop.py`, following the load-the-real-`action:`-text,
  substitute-`${...}`-tokens, `subprocess.run(["bash", "-c", script])` family used by
  `_run_record` (`test_builtin_loops.py:3204-3208`) and `_run_check_hedge_attempts`
  (`:1592-1600`, which includes an `assert "${" not in script` guard worth copying).

### Invariant

**Invariant**: `dod.md` contains **at most one** `## Final Verification` section, and
entering `final_verify` N times produces the same file as entering it once.

Enforced at two levels, because a prompt instruction alone is advisory:

1. **Prompt (`:595`)** — instruct replacement, not append: remove any pre-existing
   `## Final Verification` section, then write exactly one, using the bare header with **no**
   timestamp, date, or run identifier. State the "no timestamp" rule explicitly — the model
   invented them precisely because it kept colliding with its own prior section, and it has
   no clock to invent them correctly.
2. **Deterministic strip** — a shell step that keeps only the **last**
   `## Final Verification` section, so the invariant holds even when the model appends
   anyway. Use the `awk ... > tmp && mv` pattern from `select_step:273-275`.

**Strip placement — head of `run_final_tests` (`:627`), NOT `count_final`.** An earlier pass
folded it into `count_final`'s head on the reasoning that `count_final` is the section's only
consumer and already reads the file. That placement does not work: `count_final` is reached
only via `run_final_tests.on_yes`, so on the spin cycle
(`final_verify → run_final_tests → on_no → continue_work → on_yes → final_verify`) it is
never entered. In the audited 45-lap run — where `run_final_tests` was failing — the strip
would never have executed and `dod.md` would have reached 610 KB regardless. A backstop that
skips the failure mode it was written for is not a backstop.

`run_final_tests` is the correct edge: it is `final_verify`'s unconditional `next:`, so it
runs after **every** entry, before either branch. Constraints on the implementation there:

- It is `action_type: shell` via `fragment: shell_exit`, so the state's exit code is the
  gate. Put the strip at the head; the trailing `if` still determines the exit status.
- Shell actions run as `bash -c` with no `set -e`
  (`scripts/little_loops/fsm/runners.py:297`), so a failed `awk … > tmp && mv` will not abort
  the state — but guard it anyway so a strip failure can never mask the test result.
- The strip must treat timestamped headers as sections: `/^## Final Verification/` prefix-
  matches `## Final Verification (2026-08-20T20:14 — fresh independent re-run)`, which is
  exactly the shape the model produces. "Keep the last" must count those.

**`count_final` awk — bounded scan.** Add the terminating rule after the entry rule; the
entry rule's `next` makes a bare `/^## /` sufficient (no `&& !/^## Final Verification/`
guard needed):

```awk
/^## Final Verification/ { in_section=1; count=0; next }
/^## / { in_section=0 }
in_section && /FAILED/ { count++ }
END { print count+0 }
```

**Decision — RESOLVED as (a) + (b) together.** The question an earlier pass left open was
whether the trailing `## Closing consistency sweep` failures that the unterminated scan
currently sweeps up belong in the tally.

- **(a)** Sweep failures belong in the tally → have `final_verify` put them *into* the
  `## Final Verification` section (as its prompt already instructs at `:614`), and let the
  bounded scan pick them up there. **Adopt this**, and strengthen the `:614` wording, since
  the model was evidently not following it reliably.
- **(b)** The scan itself must be bounded regardless. **Adopt this too** — and it is not
  optional, contrary to the earlier framing that treated the pair as alternatives. Per
  Current Behavior, an unbounded scan also swallows `## Sample Verification` FAILEDs written
  by `check_done` from inside the same cycle, which can pin `failed_finals` above 0 for the
  rest of the run.
- **Rejected: (c)** "keep scan-to-EOF, rely on the strip for boundedness." Superficially
  attractive — once the strip guarantees a single Final Verification section, scan-to-EOF
  would mean "the section plus any trailing sweep output," which is robust to the model
  filing sweep failures under their own heading. But the strip removes stale *Final
  Verification* sections only; a `## Sample Verification` section written after it survives
  and poisons the gate. (b) is required.

Under (a)+(b) the bounded scan loses nothing real: sweep failures are supposed to be inside
the section already, and the residue the current scan picks up is historical LLM prose that
`count_done` deliberately refuses to count.

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

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **`continue_work` confirmed not a source of additional `dod.md` headings**: its prompt at `general-task.yaml:863` explicitly instructs "Do not touch the DoD file" — it only appends remediation steps to `plan.md`. This closes the data-flow question of whether any state besides `final_verify` could introduce a differing `## ` heading between Final Verification sections.
- **No FSM validation rule enforces this invariant today**: `scripts/little_loops/fsm/validation/structural_rules.py` has no rule inspecting awk section-scoping correctness or append-vs-replace semantics for prompt-authored file edits (`_validate_zero_retry_counter` at line 1132 is the nearest awk-related check, but it only flags zero-retry-budget counter/threshold combinations, unrelated to section boundaries). `reachability.py`'s `_validate_progress_paths_isolation` (line 189) is the only rule touching "a window resets on repeated failure," but it governs `circuit.repeated_failure.progress_paths`/`exclude_paths`, not markdown section idempotence.
- **`dod.md` is already exempt from the repeated-failure circuit breaker**: `general-task.yaml:26-32` lists both `dod.md` and `plan.md` under `circuit.repeated_failure.exclude_paths` — so the unbounded growth this issue describes does not (and structurally cannot) trip that circuit breaker; the `timeout: 1800` / `on_error: summarize_partial` degradation path (`:594`) is the only existing backstop, which is exactly the silent-degradation failure mode the issue's Motivation section already calls out.
- **`action_type` constraint on the fix's shape**: `final_verify` is an `action_type: prompt` state, not `action_type: shell` — unlike `select_step`/`mark_done`, which run their awk-tmp-mv idiom inside `action_type: shell` states. Any file-level rewrite of `final_verify`'s output must therefore either be instructed to the model in the prompt text itself (the replace-in-place instruction this issue proposes), or deferred to a following shell state that post-processes the model's output (the `strip_stale_final_sections` step already proposed, folded into `count_final`'s head) — the model cannot itself run a deterministic awk-tmp-mv step from within a `prompt` action.

_Added by pre-implementation review — 2026-08-20 — all claims executed or read, not inferred:_

- **`count_final` is not on the spin cycle** — verified by dumping every transition:
  `final_verify.next = run_final_tests`; `run_final_tests.on_no = continue_work`;
  `continue_work.on_yes = final_verify`. `count_final` is reachable only via
  `run_final_tests.on_yes`. The previously-proposed strip placement would not have run in
  the failure mode that motivated this issue. Strip moved to `run_final_tests`'s head.
- **The old repro fixture is non-discriminating** — both the current and the fixed awk
  return `1` on `## Final Verification / FAILED x / ## Other / FAILED y /
  ## Final Verification (2) / FAILED z`. Executed both. Replaced with the 2-section shape,
  which returns `2` today and `1` after the fix.
- **`## Sample Verification` reaches the tail of `dod.md`** — `check_done` (`:430-500`,
  `action_type: prompt`, `next: count_done`) replaces that section on every lap that routes
  through `select_step`, so it lands after the last `## Final Verification` section and its
  FAILEDs enter `count_final`'s gate. This is the poisoning `count_done` excludes from its
  own gate at `:562-569`. Upgrades the awk fix from rider to primary and settles (a)/(b).
- **No `set -e` in FSM shell actions** — `scripts/little_loops/fsm/runners.py:297` runs
  `["bash", "-c", action]` with no `-e`, so a mid-action failure does not abort the state and
  the state's exit code is the last command's. Relevant to putting the strip ahead of
  `run_final_tests`' exit-code gate.
- **Line anchors re-verified** against the current file; the previous `:564` / `:580` /
  `:635-639` citations were stale and have been updated throughout.

## Implementation Steps

Two independently landable commits. Commit 1 is the run-hanging fix and should go first.

**Commit 1 — bounded scan (`count_final`):**

1. **Pin the current behavior in a test** — the *discriminating* 2-section fixture
   (`## Final Verification` / FAILED / `## Closing consistency sweep` / FAILED), asserting
   today's wrong answer of `2`, so the change is visible as an intentional flip. Do not use
   the interleaved 3-section shape: it returns `1` both before and after.
2. **Fix the awk** (`:676-680`). Add the `/^## / { in_section=0 }` reset; flip the fixture
   assertion to `1`.
3. **Apply the same reset to `count_done`'s `FAILED_SAMPLES` awk** (`:545-549`) for
   consistency, noting in the comment that it remains observability-only and outside the
   gate. This brings all four section-scoped awks in the file into agreement.

**Commit 2 — idempotent `final_verify`:**

4. **Strengthen the sweep-append instruction** (`:614`) so sweep failures land inside the
   `## Final Verification` section — decision (a).
5. **Rewrite the `final_verify` prompt** (`:595`) for replacement semantics with an explicit
   no-timestamp rule.
6. **Add the deterministic strip** at the head of `run_final_tests` (`:627`), guarded so a
   strip failure cannot affect the state's exit code.
7. **Test the strip.** Two applications → byte-identical `dod.md`, exactly one
   `## Final Verification` section, including when the input carries timestamped headers.
   Add a static assertion that the prompt text carries the replace + no-timestamp language.
   Do **not** attempt to execute `final_verify`'s "file contract" — it is a `prompt` state.

**Both:**

8. **Validate and verify.** `ll-loop validate general-task` clean;
   `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P1, and the awk half arguably reads P0-adjacent: it can pin `failed_finals`
  above 0 permanently, making the loop unable to reach a terminal at all. The append half
  degrades any multi-lap run and can silently convert a `success` into a `partial` via
  timeout.
- **Scope**: one prompt body, one shell guard, two awk lines — all in `general-task.yaml`.
- **Risk**: low. The replacement semantics discard prior `final_verify` sections, which are
  by construction supposed to be re-derived from evidence on every entry.
- **Note**: the awk change alters the FAILED tally for any run whose `dod.md` carries
  content after the last `## Final Verification` section. That is the point — the excluded
  content is historical LLM prose, not live failures — but it is a behavior change, so state
  the intended scope explicitly in the state's comment.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §4
- ENH-2584 — deferred bounded-`final_verify` decomposition; this is a landable subset
- ENH-2575 — `final_verify` `on_error: summarize_partial` routing, the degradation path

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-08-21T03:39:27 - `e2bbe140-81de-4ea2-9df1-3998acd52ab8.jsonl`
- `/ll:refine-issue` - 2026-08-21T02:42:50 - `9531ff26-6896-4f25-b550-1bb125e45484.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T02:37:32 - `c4d0cb49-2d47-43ee-bd0a-5286b5885739.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
