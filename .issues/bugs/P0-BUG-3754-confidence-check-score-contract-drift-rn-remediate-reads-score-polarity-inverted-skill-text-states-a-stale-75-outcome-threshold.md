---
id: 3754
title: 'Confidence-check score contract drift: rn-remediate reads score polarity inverted, skill text states a stale 75 outcome threshold'
type: BUG
priority: P0
status: open
discovered_date: '2026-10-05'
labels:
- confidence-check
- rn-remediate
- scoring
---

## Summary

The confidence-check score contract is read two ways inside little-loops, and its documented outcome threshold is wrong.

**(1) Inverted polarity.** The rubric scores outcome criteria as points toward confidence: higher means better. Criterion A gives 1-2 change sites 12/12 breadth and a simple isolated change 25/25 (`skills/confidence-check/rubric.md`, Criterion A tables and worked examples). Criterion C gives "no ambiguity" 25. `preparation_policy.py` (around line 647) agrees: it treats the lowest of the scores as the worst dimension.

`rn-remediate.yaml` reads high as worse:
- Its band snapshot (line ~180) writes `ABOVE_MINIMAL` for `score_complexity >= diagnose_complexity_threshold` (15), and `gate_implement` then forces a refine+wire pass on those issues.
- Its diagnose step routes `score_ambiguity >= 15` to REFINE ("residual ambiguity") and `score_complexity >= 15` to WIRE/REFINE ("High complexity").
- `docs/guides/LOOPS_REFERENCE.md` (delta table, around line 659) documents `delta_complexity` and `delta_ambiguity` as "lower = improved".

So the complexity- and ambiguity-keyed remediation fires on the simple, well-specified end of the scale. Complex or ambiguous issues reach REFINE only through the separate confidence-floor and outcome-threshold branch.

**(2) Stale threshold text.** `skills/confidence-check/SKILL.md` (around line 424) and `rubric.md` (around line 360) say `outcome_threshold` defaults to 75, so the unproven-mechanism hard cap is documented as 74. The real default is 65 (`config/automation.py` around line 160; `config-schema.json` `outcome_threshold` default 65), so the cap is actually 64. The 65 gate is intended to stay where it is; only the text is stale.

## Prior work this touches

- ENH-2163 (done) introduced the marker-gated refine+wire enforcement on the `ABOVE_MINIMAL` band, and BUG-2306 (done) closed its degenerate pre-implement gate. Both were written on the inverted reading. Fixing the polarity changes which issues that gate catches, so the gate's intent ("hard issues must be refined and wired before implement") should be re-checked against the corrected band, not just flipped mechanically.
- BUG-2007, ENH-2229 and BUG-2230 fixed other rn-remediate routing defects; none addressed polarity.

## Acceptance Criteria

Acceptance: (a) one documented polarity, high = better, stated once in the rubric and followed by rn-remediate's band snapshot, its diagnose routing and the LOOPS_REFERENCE delta table; a test pins it (for example, in test_rn_remediate.py, a score_complexity of 25 issue does not take the ABOVE_MINIMAL path, and a score of 5 does). (b) SKILL.md and rubric.md state default 65 and cap 64, and a test or lint check ties the documented default to config-schema.json. (c) The existing rn-remediate and confidence-check suites pass.

Verified against main 4c6be4c26 on 2026-10-05.
