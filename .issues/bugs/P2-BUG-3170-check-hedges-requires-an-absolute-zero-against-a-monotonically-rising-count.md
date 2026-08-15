---
id: BUG-3170
type: BUG
title: check_hedges requires an absolute zero against a count that refine can only
  raise
priority: P2
status: open
discovered_by: bug-3169-review
discovered_date: '2026-08-14'
captured_at: '2026-08-14T00:00:00Z'
relates_to:
- BUG-3169
- ENH-3031
- ENH-2446
testable: true
confidence_score: 96
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 22
---

# BUG-3170: check_hedges requires an absolute zero against a count that refine can only raise

## Summary

`refine-to-ready-issue`'s `check_hedges` gate
(`scripts/little_loops/loops/refine-to-ready-issue.yaml:298`) passes only when
`ll-issues check-open-questions` exits 0, and that CLI exits 0 only when
`count_open_questions_in_sections(...) == 0`
(`scripts/little_loops/cli/issues/check_open_questions.py:62`). The count is an
additive scan over the very sections `/ll:refine-issue --auto --gap-analysis`
deposits prose into (`_OPEN_QUESTION_SECTIONS`, widened by ENH-3031 to include
`Program Design`, `Codebase Research Findings`, `Integration Map`, `Suggested
Fix Direction`), using hedge vocabulary that has no answer/hedge distinction.

So the loop's own remediation step is the thing that raises the number it is
being graded on. Every `--gap-analysis` pass is additive by construction (it
never removes content), which means an issue can research and *answer* a
question and come out redder than it went in. When that happens the gate is
unclearable: `check_hedges → check_refine_limit → refine_followup` cycles until
the refine budget is spent, then falls through to `breakdown_issue` — with
`confidence_check` never reached, so a correctly-sized issue gets decomposed.

BUG-3169 fixed one instance of this (the `open question` alternative firing on
citations). It was 1 of 15 alternatives. This issue is about the gate shape,
which survives that fix.

## Steps to Reproduce

The remaining hedge vocabulary fires on ordinary *resolution* prose:

```python
>>> from little_loops.issue_parser import count_open_questions_in_sections
>>> count_open_questions_in_sections("""## Program Design

- Verified the transport pin (worth confirming, and now confirmed): `build_server()` takes no params.
- Prior note said TBD; resolved by grep sweep — no ContextVar usage anywhere.
""")
2
```

Neither item is unresolved; both read as answers. `worth confirming`,
`worth checking`, `should be considered`, `needs confirmation`, `TBD`, and
`to be determined` all have this citation/report form, and `_RESOLVED_QUESTION_MARKER_RE`
does not exclude them because refine writes prose findings, not
`✅ RESOLVED`-marked question bullets.

The observed end-to-end failure is recorded in BUG-3169 (FEAT-3168,
`.loops/runs/refine-to-ready-issue-20260814T180315/`): two refine passes and two
verify passes burned (~$2.36, 19m46s), budget exhausted, `breakdown_issue`
entered.

## Current Behavior

`check_hedges` is an absolute-zero gate over a monotonically non-decreasing
signal. There is no notion of *progress*: an issue that goes 7 → 3 across a
refine pass is treated exactly like one that goes 7 → 7, and both route to
`check_refine_limit`.

Chasing this by pruning vocabulary alternative-by-alternative (ENH-2446 added
the phrases, ENH-3031 widened the sections, BUG-3169 narrowed one alternative)
trades false positives for false negatives on each pass and never removes the
underlying ratchet.

## Program Design

### Types

- `baseline: int | None` — parsed contents of the baseline file; `None` means
  no baseline (file absent, empty, or unparseable).

### Signatures

- `add_check_open_questions_parser(subparsers: argparse._SubParsersAction) -> None`
  (`check_open_questions.py:21`) — register `--baseline-file` alongside the
  existing arguments.
- `cmd_check_open_questions(args: argparse.Namespace) -> int`
  (`check_open_questions.py:59-62`) — split the current
  `unresolved_options == 0 and open_questions == 0` conjunction to also accept
  `open_questions < baseline` when `args.baseline_file` is set and a baseline
  was read.
- `_read_baseline(path: Path) -> int | None` (new) — read-and-parse; any
  failure (missing, empty, unparseable) returns `None`.
- `_write_baseline(path: Path, value: int) -> None` (new) — write
  `min(existing, value)`; swallow write errors to stderr, never raise.

### Call Path

`refine-to-ready-issue.yaml:check_hedges` (`:298`) → `ll-issues
check-open-questions <ID> --baseline-file <path>` → `cmd_check_open_questions()`
→ `count_open_questions_in_sections()` / `locate_unresolved_options()`
(`issue_parser.py`) for the counts, `_read_baseline()` /
`_write_baseline()` for the ratchet.

## Expected Behavior

The gate should force another refine pass when refine is **not making
progress**, not when a residual count exists. Concretely, for the *open
questions* term only:

- Count 0 → pass (unchanged).
- Count strictly below the best count seen this run → pass; refine did its
  job, let the chain reach `confidence_check`.
- Count unchanged or increased → fail, forcing `refine_followup` as today.
- First measurement in a run with a nonzero count → fail (one refine pass is
  still warranted before conceding).

The *unresolved options* term keeps absolute-zero semantics — see
[Scope of the baseline](#scope-of-the-baseline-open-questions-only) below.

## Proposed Solution

Give `ll-issues check-open-questions` a baseline mode, and have the loop pass a
per-run baseline file:

```
ll-issues check-open-questions <ID> --baseline-file <path>
```

- Reads the previously recorded baseline from `<path>` (absent, empty, or
  unparseable = **no baseline**).
- Writes `min(existing_baseline, current_open_questions)` back to `<path>` on
  every invocation, creating the file when absent — see
  [Ratchet direction](#ratchet-direction-min-seen-not-last-seen).
- Exit 0 when `unresolved_options == 0` **and** (`open_questions == 0` **or**
  a baseline exists and `open_questions < baseline`).
- Exit 1 otherwise, with the existing `OPEN_QUESTIONS_REMAIN` token still
  leading the stderr line and the baseline delta **appended** to the existing
  message so `diagnose` can see the trend.

### Scope of the baseline: open questions only

`cmd_check_open_questions` exits 1 when `unresolved_options != 0` **OR**
`open_questions != 0` (`check_open_questions.py:59-62`). The baseline applies to
`open_questions` **only**. `locate_unresolved_options` counts option blocks
lacking a `> **Selected:**` marker — a discrete, resolvable, *non-additive*
signal with its own remediation path (`check_decision_needed` →
`resolve_decision_pre_breakdown` → `/ll:decide-issue`). It is not part of the
ratchet and must not inherit the tolerance, or an issue with two permanently
undecided option blocks would pass the gate the moment its hedge count drifted
from 5 to 3.

### Ratchet direction: min-seen, not last-seen

Recording the *last* measurement lets the bar move the wrong way: a pass that
goes 5 → 8 raises the floor, and the next pass at 8 → 6 then passes at 6 —
worse than the run started. Persisting `min(existing, current)` keeps the
baseline monotone-decreasing, so the gate measures net progress against the
best state seen this run.

### Do not seed the baseline file in `resolve_issue`

`resolve_issue` (`refine-to-ready-issue.yaml:78-81`) seeds every other run-dir
counter with `printf '0' >`. Mirroring that pattern here is actively broken: a
`0` baseline makes `open_questions < baseline` unsatisfiable, welding the gate
permanently shut. Absence-means-no-baseline is load-bearing.

### Baseline-file I/O must not affect the exit code

`check_hedges` has `on_error: check_ac_automatable`, which fails *open* — past
the gate. So an unhandled `PermissionError` on the baseline write would
silently skip the gate entirely rather than tighten it. Read errors are treated
as "no baseline"; write errors warn on stderr and leave the exit code derived
from the counts alone.

Loop side (`refine-to-ready-issue.yaml`):

```yaml
  check_hedges:
    action: >-
      ll-issues check-open-questions ${captured.issue_id.output}
      --baseline-file ${context.run_dir}/refine-to-ready-open-questions
```

`${context.run_dir}`-scoped counter files are the established pattern here —
`check_refine_limit` (line 456) already uses exactly this shape, and it
satisfies the meta-loop per-run artifact isolation rule. **No `scope:` edit is
needed**: `scope:` (`:33-35`) already lists `${context.run_dir}`, and
`resolve_issue` already `mkdir -p`s it.

Default behavior with no `--baseline-file` is unchanged (absolute zero), so
other callers and any consuming project's loops are unaffected.

The flag reads *and* overwrites `<path>`; its `--help` text must say so (or the
flag is named `--progress-file` instead). The module docstring
(`check_open_questions.py:1-8`) and the subparser `help=` string both currently
assert absolute-zero semantics and need updating alongside `docs/reference/CLI.md`.

### Precondition: `check_hedges` must get two measurements

The baseline is only consultable if `check_hedges` runs at least twice, and the
`check_refine_limit` counter is shared by four gates — `check_verify_verdict`
(`:295`), `check_hedges` (`:306`), `check_ac_automatable` (`:317`), and
`check_readiness` (`:363`) — against `target: 2`, i.e. **one loopback per run,
total**. If another gate spends the loopback first, `check_hedges` measures
once, fails on any nonzero count, and this fix changes nothing for that run.

Verified for the recorded failure: the event log for
`refine-to-ready-issue-20260814T180315` shows `check_hedges → check_refine_limit`
at iterations 12→13 **and** 19→20, with `check_verify_verdict` passing both
times. `check_hedges` spent the whole budget itself, so it got exactly the two
measurements the fix needs. (Whether the count actually fell between those two
passes is not recoverable post-hoc — BUG-3169 changed the parser underneath.)
This fix does not address the shared-budget fragility for runs where a
different gate consumes the loopback; that remains out of scope.

## Alternatives Considered

- **Keep pruning the vocabulary.** Each pass is a guess at authorial intent and
  costs a false negative (BUG-3169's first draft silently stopped counting
  wrapped and imperative numbered questions). Does not address the ratchet.
- **Exclude the refine-deposited sections again.** Reverts ENH-3031, which was
  added because real hedges accumulate in exactly those sections.
- **Have refine emit a structured count of what it resolved.** Larger surface,
  relies on the LLM to self-report, and the deterministic probe exists
  specifically to not do that.

## Impact

- **Priority**: P2 — burns a full refine budget per affected issue and pushes
  correctly-sized issues into `breakdown_issue`. Same severity as BUG-3169; the
  difference is that this one recurs through 14 remaining alternatives.
- **Effort**: Medium — one CLI flag with a split exit-code contract, one
  loop-state edit, docs, and subprocess-level tests covering the decrease,
  ping-pong, no-baseline, zero-baseline, unresolved-options, and I/O-failure
  paths.
- **Risk**: Low — additive flag, default path unchanged. The one non-obvious
  hazard is the fail-open `on_error` on `check_hedges`, which is why
  baseline-file I/O is required not to influence the exit code.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `ll-issues check-open-questions <ID> --baseline-file <p>` exits 0 when the
      open-questions count is strictly below the value recorded in `<p>`.
- [ ] It exits 1 when the open-questions count is unchanged or increased, and the
      stderr message names both the current count and the baseline, with
      `OPEN_QUESTIONS_REMAIN` still the **leading** token and the existing message
      text appended-to rather than restructured (`test_fsm_open_question_stall.py`
      and the `diagnose` prompt key off that token).
- [ ] **Unresolved options keep absolute-zero semantics**: with
      `unresolved_options > 0`, the command exits 1 even when the open-questions
      count decreased relative to `<p>`.
- [ ] It writes `min(existing_baseline, current_open_questions)` to `<p>` on every
      invocation, including the exit-0 paths, and creates the file when absent. A
      test covers the ping-pong case: 5 → 8 → 6 exits 1 at the third invocation
      (6 is not below the recorded best of 5).
- [ ] A first invocation with no existing baseline file and a nonzero count
      exits 1.
- [ ] A baseline file containing `0` (or empty, or unparseable) with a nonzero
      count exits 1 — empty/unparseable is treated as *no baseline*, not as `0`.
- [ ] Baseline-file I/O never changes the exit code: an unreadable `<p>` is
      treated as no baseline, and an unwritable `<p>` warns on stderr while the
      exit code stays derived from the counts alone (covered by a test that
      points `--baseline-file` at an unwritable path).
- [ ] Without `--baseline-file`, exit-code behavior is byte-identical to today
      (existing `test_ll_issues_check_open_questions.py` cases pass unmodified).
- [ ] `check_hedges` in `refine-to-ready-issue.yaml` passes the run-scoped
      baseline file and `ll-loop validate refine-to-ready-issue` exits 0.
- [ ] `resolve_issue` does **not** seed the baseline file (no `printf '0' >`
      alongside the other run-dir counters).
- [ ] A test drives the decrease path end-to-end: nonzero count → refine
      simulated by editing the issue down → second invocation exits 0.
- [ ] `docs/reference/CLI.md`, the `check_open_questions.py` module docstring, and
      the subparser `help=` string all describe the baseline mode; the `--help`
      text states that the file is read *and* overwritten.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Out of Scope

- The false positives themselves. Reducing them further (the unnumbered "see
  Open Questions" pointer shape noted in BUG-3169's Out of Scope, the
  `worth confirming`-in-answer-prose shape shown above) remains worthwhile but
  is a separate axis; this issue makes the gate tolerant of them rather than
  attempting to eliminate them.
- `check_ac_automatable` and `check_verify_verdict`, which sit in the same
  chain but are not additive-scan gates.
- The shared `check_refine_limit` budget. Four gates increment one counter
  against `target: 2`, so a run where a gate other than `check_hedges` spends
  the loopback still gets a single hedge measurement and cannot benefit from the
  baseline. Re-examining `target: 2` or giving each gate its own budget is a
  separate change.
- `unresolved_options` semantics. The baseline deliberately does not cover that
  term; decision resolution stays owned by `check_decision_needed` /
  `/ll:decide-issue`.

## Integration Map

- `scripts/little_loops/cli/issues/check_open_questions.py:59-62` — the
  `unresolved_options == 0 and open_questions == 0` conjunction that the
  baseline must split (the fix site); `:1-8` and `:27-33` — the module docstring
  and subparser `help=` asserting absolute-zero semantics.
- `scripts/little_loops/cli/issues/check_open_questions.py:21-37` —
  `add_check_open_questions_parser`, where `--baseline-file` is registered.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:298` — `check_hedges`
  (the consumer); `:456` — `check_refine_limit`, the existing
  `${context.run_dir}` counter-file precedent to mirror; `:78-81` —
  `resolve_issue`'s counter seeding, the pattern that must **not** be extended
  to the baseline file; `:33-35` — `scope:`, already covering
  `${context.run_dir}` (no edit needed).
- `scripts/little_loops/issue_parser.py:1439` — `_OPEN_QUESTION_SIGNAL_RE` and
  `_OPEN_QUESTION_SECTIONS`; unchanged by this issue, cited as the source of the
  ratchet.
- `scripts/tests/test_ll_issues_check_open_questions.py` — subprocess-level
  exit-code contract (add baseline cases).
- `scripts/tests/test_fsm_open_question_stall.py` — existing stall coverage.
- `docs/reference/CLI.md` — `ll-issues check-open-questions` entry.

## Status

**Open** | Created: 2026-08-14 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-15T00:02:16 - `f2a7b3a1-13a3-4789-a189-b1a33c413ed6.jsonl`
- `/ll:format-issue` - 2026-08-15T00:00:21 - `89d8e25e-eb7d-4616-8513-9b90d6e3e96f.jsonl`
