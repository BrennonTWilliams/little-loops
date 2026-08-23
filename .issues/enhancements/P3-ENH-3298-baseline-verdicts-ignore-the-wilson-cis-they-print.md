---
id: ENH-3298
type: ENH
title: Baseline verdicts ignore the Wilson CIs they print
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T06:03:35Z'
parent: EPIC-2087
labels:
- loops
- evaluation
- stats
---

# ENH-3298: Baseline verdicts ignore the Wilson CIs they print

## Summary

`ll-loop run --baseline` prints Wilson 95% confidence intervals (ENH-2084) but
every *conclusion* it draws ignores them. Both the A/B "Verdict" line and the
cross-host "ordering reversal" warning branch on the raw sign of the point
estimate, so a one-item difference at small `n` is reported with the same
confidence as a decisive result. The epic's goal is loops that are *measurably*
correct rather than subjectively reviewed; today the measurement is displayed
and then discarded.

## Current Behavior

`scripts/little_loops/cli/loop/_helpers.py:2031` computes the two intervals and
prints them:

<!-- ll-evidence-ok: illustrative sample output the format code would produce, not a literal quote from _helpers.py's source text -->
```
A/B Summary (n=5)
  Harness pass-rate:  60%  [0.23, 0.88]
  Baseline pass-rate: 40%  [0.12, 0.77]
  Delta:              +20%
```

Then `_helpers.py:2074` picks the verdict from the sign of `results.delta`
alone:

```python
quality_verdict = (
    "harness wins on quality"
    if results.delta > 0
    else "baseline wins on quality"
    if results.delta < 0
    else "no quality difference"
)
```

The run above prints `Verdict: harness wins on quality` off a single flipped
item, with two intervals that overlap across almost their whole range.

`_print_cross_host_table` (`_helpers.py:2186`) has the same defect at
`_helpers.py:2213`:

```python
host1_harness_wins = results1.delta > 0
host2_harness_wins = results2.delta > 0
if host1_harness_wins != host2_harness_wins:
    ...  # "⚠ Ordering reversal: ... Improvement may be host-specific."
```

Two deltas of `+1 item` and `-1 item` — indistinguishable from noise — emit the
reversal warning, and a genuine host-specific regression prints identically to
that false alarm.

`grep -rnE 'overlap|significan|inconclusive'` over `cli/loop/`, `stats.py`, and
`ab_writer.py` returns nothing: no code path anywhere converts an interval into
a claim.

## Expected Behavior

Both surfaces gain a third, explicitly inconclusive outcome, and only assert a
winner when the data separates one.

A/B summary at the same `n=5`:

```
  Verdict:            inconclusive at n=5 (2 discordant pairs), same token cost
```

and when it does separate:

```
  Verdict:            harness wins on quality (9/10 discordant pairs favor
                      harness), costs ~12% more tokens
```

Cross-host: the reversal warning fires only when *both* runs independently
establish a direction. When either is inconclusive, say so instead:

```
  Note: ordering differs between hosts, but neither run separates from
        chance (n=5, n=5) — not evidence of a host-specific effect.
```

The cost half of the verdict (`cost_verdict`) is a ratio of medians, not a
Bernoulli rate, and is out of scope here — it keeps its current wording.

## Motivation

ENH-2084's acceptance criteria only asked for the CI to be *shown* alongside
the point estimate, and that is exactly what shipped. Nothing in that issue
covered the verdict line, so the display and the conclusion were allowed to
disagree. The practical failure mode is that a loop author runs `--baseline`
once at small `n`, reads "harness wins on quality," and promotes a change that
the same command's own intervals do not support.

## Proposed Solution

The A/B arms are **paired** — `ABResults.per_item`
(`scripts/little_loops/ab_writer.py:153`) holds one record per item carrying
both `harness_pass` and `baseline_pass`, so the same item runs through both
arms. That matters for the choice of test: comparing the two independent Wilson
intervals for overlap is the *wrong* test for paired data (it is needlessly
conservative and throws away the pairing).

The correct small-`n`, stdlib-only test is a sign test on the discordant pairs:

- `b` = items where harness passed and baseline failed
- `c` = items where harness failed and baseline passed
- Concordant items carry no information about direction and drop out.

Reuse the existing `wilson_ci(k, n)` on `b / (b + c)`. If that interval
contains `0.5`, the direction is not established → `inconclusive`. No new
dependency, no scipy, and it reuses the helper ENH-2084 already landed.

Cross-host is the genuinely independent case (two separate runs), so its
guard is different: require each run's own paired test to establish a
direction before calling the disagreement a reversal.

## Integration Map

- `scripts/little_loops/stats.py` — new `paired_direction`.
- `scripts/little_loops/cli/loop/_helpers.py` — `_print_ab_summary:2074`,
  `_print_cross_host_table:2213`.
- `docs/reference/CLI.md:638-641` — `--baseline` / `--cross-host` rows.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:368` — the section describing
  Wilson intervals and trial counts.
- No change to `ab_writer.py`, `ab.json`'s schema, or the executor.

## Program Design

### Types

No new dataclass. `ABResults` (`ab_writer.py:132-153`) is unchanged — the new
computation is derived from `per_item` at print time, alongside the existing
`k_harness` / `k_baseline` counts at `_helpers.py:2029-2032`.

### Signatures

- **New — in `scripts/little_loops/stats.py`, beside `wilson_ci`:**

  ```python
  def paired_direction(
      per_item: list[dict[str, Any]],
      *,
      harness_key: str = "harness_pass",
      baseline_key: str = "baseline_pass",
  ) -> tuple[str, int, int]:
  ```

  Returns `(direction, b, c)` where `direction` is one of `"harness"`,
  `"baseline"`, or `"inconclusive"`, and `b`/`c` are the discordant counts
  defined above. `"inconclusive"` is returned whenever `b + c == 0` (no
  discordant pairs at all) or `wilson_ci(b, b + c)` brackets `0.5`.

  It lives in `stats.py` rather than `_helpers.py` because `_print_ab_summary`
  and `_print_cross_host_table` both need it, and because it is the unit the
  tests should target directly rather than through captured stdout.

- `wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]`
  (`stats.py:13`) — existing, unchanged; `paired_direction` is its only new
  caller.

### Call Path

`read_ab_json()` → `ABResults.per_item` → **`paired_direction()`** →
verdict string, in both `_print_ab_summary` (`_helpers.py:2011`) and
`_print_cross_host_table` (`_helpers.py:2186`).

### Decision Rules

- A/B verdict: `direction == "inconclusive"` → print `inconclusive at n=<n>
  (<b+c> discordant pairs)`; otherwise name the winner and cite `b`/`c`.
- Cross-host reversal warning: fires only when both runs return a non-
  `inconclusive` direction *and* those directions differ. When the directions
  differ but either is inconclusive, print the softened note instead of the
  `⚠` warning.
- `cost_verdict` is untouched.

## Implementation Steps

1. Add `paired_direction` to `scripts/little_loops/stats.py`.
2. Rewrite the `quality_verdict` expression at `_helpers.py:2074` to call it.
3. Gate the reversal branch at `_helpers.py:2213-2222` on both directions
   being established.
4. Update the `--baseline` and `--cross-host` rows in
   `docs/reference/CLI.md:638-640` to describe the three-way verdict.
5. Tests in `scripts/tests/` covering: no discordant pairs; all-discordant
   one-way; the `n=5`, `b=2`, `c=0` case that must read inconclusive; a
   decisive case; and both cross-host branches (true reversal vs. noisy
   disagreement).

## Impact

Terminal output only; `ab.json` is unchanged, so nothing that consumes the
artifact breaks. Existing runs that reported a winner off a thin delta will
start reporting `inconclusive` — that is the point of the change, but it will
read as a regression to anyone who trusted the old verdict, so the CHANGELOG
entry should say so plainly.

Low risk, warning-level semantics, no behavior change to loop execution.

## Success Metrics

- `--baseline` never names a winner when the paired sign test brackets `0.5`.
- The cross-host `⚠` warning fires only on reversals where both runs
  independently establish a direction.

## Scope Boundaries

- **In scope**: the two verdict/warning code paths and their tests and docs.
- **Out of scope**: changing `--items` defaults or adding sample-size planning;
  the `cost_verdict` median-ratio wording; `ll-loop diagnose-evaluators` and
  `calibrate-budget`, which already report CIs without drawing a
  winner/loser conclusion from them; any change to `ab.json`.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-loop run` options table
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — harness measurement
- `docs/guides/EVALUATION_GUIDE.md:56,95` — the other Wilson-CI surface
- `docs/reference/API.md:10914` — `little_loops.stats`

## Status

**Open** | Created: 2026-08-23 | Priority: P3
