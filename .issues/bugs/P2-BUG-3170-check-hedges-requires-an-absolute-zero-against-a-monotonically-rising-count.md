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
relates_to: [BUG-3169, ENH-3031, ENH-2446]
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

## Reproduction

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

## Expected Behavior

The gate should force another refine pass when refine is **not making
progress**, not when a residual count exists. Concretely:

- Count 0 → pass (unchanged).
- Count decreased since the last measurement this run → pass; refine did its
  job, let the chain reach `confidence_check`.
- Count unchanged or increased since the last measurement → fail, forcing
  `refine_followup` as today.
- First measurement in a run with a nonzero count → fail (one refine pass is
  still warranted before conceding).

## Proposed Solution

Give `ll-issues check-open-questions` a baseline mode, and have the loop pass a
per-run baseline file:

```
ll-issues check-open-questions <ID> --baseline-file <path>
```

- Reads the previously recorded count from `<path>` (absent = no baseline).
- Writes the current count back to `<path>` on every invocation.
- Exit 0 when `count == 0` **or** (`baseline` exists and `count < baseline`).
- Exit 1 otherwise, with the existing `OPEN_QUESTIONS_REMAIN` token plus the
  baseline delta in the message so `diagnose` can see the trend.

Loop side (`refine-to-ready-issue.yaml`):

```yaml
  check_hedges:
    action: >-
      ll-issues check-open-questions ${captured.issue_id.output}
      --baseline-file ${context.run_dir}/refine-to-ready-open-questions
```

`${context.run_dir}`-scoped counter files are the established pattern here —
`check_refine_limit` (line 456) already uses exactly this shape, and it
satisfies the meta-loop per-run artifact isolation rule.

Default behavior with no `--baseline-file` is unchanged (absolute zero), so
other callers and any consuming project's loops are unaffected.

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
- **Effort**: Small–Medium — one CLI flag, one loop-state edit, tests at both
  the unit and subprocess levels.
- **Risk**: Low — additive flag, default path unchanged.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `ll-issues check-open-questions <ID> --baseline-file <p>` exits 0 when the
      count decreased relative to the value recorded in `<p>`.
- [ ] It exits 1 when the count is unchanged or increased, and the stderr message
      names both the current count and the baseline.
- [ ] It writes the current count to `<p>` on every invocation, including the
      exit-0 paths, and creates the file when absent.
- [ ] A first invocation with no existing baseline file and a nonzero count
      exits 1.
- [ ] Without `--baseline-file`, exit-code behavior is byte-identical to today
      (existing `test_ll_issues_check_open_questions.py` cases pass unmodified).
- [ ] `check_hedges` in `refine-to-ready-issue.yaml` passes the run-scoped
      baseline file and `ll-loop validate refine-to-ready-issue` exits 0.
- [ ] A test drives the decrease path end-to-end: nonzero count → refine
      simulated by editing the issue down → second invocation exits 0.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Out of Scope

- The false positives themselves. Reducing them further (the unnumbered "see
  Open Questions" pointer shape noted in BUG-3169's Out of Scope, the
  `worth confirming`-in-answer-prose shape shown above) remains worthwhile but
  is a separate axis; this issue makes the gate tolerant of them rather than
  attempting to eliminate them.
- `check_ac_automatable` and `check_verify_verdict`, which sit in the same
  chain but are not additive-scan gates.

## Integration Map

- `scripts/little_loops/cli/issues/check_open_questions.py:40-80` —
  `cmd_check_open_questions`, the exit-code contract (the fix site).
- `scripts/little_loops/cli/issues/__init__.py` — argparse wiring for the new
  `--baseline-file` flag.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:298` — `check_hedges`
  (the consumer); `:456` — `check_refine_limit`, the existing
  `${context.run_dir}` counter-file precedent to mirror.
- `scripts/little_loops/issue_parser.py:1439` — `_OPEN_QUESTION_SIGNAL_RE` and
  `_OPEN_QUESTION_SECTIONS`; unchanged by this issue, cited as the source of the
  ratchet.
- `scripts/tests/test_ll_issues_check_open_questions.py` — subprocess-level
  exit-code contract (add baseline cases).
- `scripts/tests/test_fsm_open_question_stall.py` — existing stall coverage.
- `docs/reference/CLI.md` — `ll-issues check-open-questions` entry.

## Status

**Open** | Created: 2026-08-14 | Priority: P2
