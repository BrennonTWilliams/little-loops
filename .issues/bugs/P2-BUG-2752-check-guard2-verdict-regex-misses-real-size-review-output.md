---
id: BUG-2752
title: 'autodev: check_guard2_verdict regex misses real issue-size-review skip line'
type: BUG
priority: P2
status: open
captured_at: '2026-07-23T21:42:00Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
decision_needed: false
confidence_score: 98
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 24
---

# BUG-2752: autodev: check_guard2_verdict regex misses real issue-size-review skip line

## Summary

Split out of FEAT-2751 (the regex-fix half only; the stagnation-detector half
stays in FEAT-2751). `check_guard2_verdict`'s regex
`skipped: score (8|9|10|11) ` (`scripts/little_loops/loops/autodev.yaml:1132`)
did not match the real `/ll:issue-size-review --auto` output captured for
`FEAT-021` during the `2026-07-23T16:08 autodev` run on `sketch-storyboards`
(run_dir `.loops/runs/autodev-20260723T160811/`). The state's own comment
block documents the real observed wording — `"skipped: score 11 (Very
Large) — strictly sequential, ..."` — but the pattern requires an exact
`"skipped: score N "` prefix with nothing in between, so it never matches
that documented shape. This silently defeats the BUG-2734 atomic-remediation
path (`check_readiness_for_atomic_remediation` → `remediate_oversized_atomic`),
the only route that can rescue a `Very Large`, deliberately-atomic, ready
issue from a `low_readiness` deferral.

## Current Behavior

`scripts/little_loops/loops/autodev.yaml:1131-1134`:

```yaml
evaluate:
  type: output_contains
  source: "${captured.size_review_output.output}"
  pattern: "skipped: score (8|9|10|11) "
on_yes: check_readiness_for_atomic_remediation
on_no: recheck_after_size_review
```

Real captured output for `FEAT-021` did not satisfy this pattern, so
`on_no` fired and the loop went straight to `recheck_after_size_review`,
which deferred with `low_readiness` after 28m 3s / 25 iterations — never
attempting the earn-the-pass remediation this run's profile (Very Large,
confidence 85, deliberately atomic) exists specifically to rescue.

## Expected Behavior

1. Loosen the pattern to allow arbitrary text between `skipped:` and
   `score N`: `pattern: "skipped:.* score (8|9|10|11)\\b"`.
2. Add a fallback: on `on_no`, route to a new `check_guard2_score_fallback`
   state that re-parses `${captured.size_review_output.output}` with the
   same inline-Python idiom already used in
   `check_readiness_for_atomic_remediation` (line ~1146) — re-entrant,
   text-scoped, no shell interpolation of untrusted captured text (per
   BUG-2594) — to catch any `score (8|9|10|11)` substring the regex still
   misses. On match → `check_readiness_for_atomic_remediation`; on no
   match → `recheck_after_size_review` (unchanged fall-through).

## Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — loosen
  `check_guard2_verdict.pattern`; add `check_guard2_score_fallback` state
  on the `on_no` branch.
- `scripts/tests/test_autodev_loop.py` (create) —
  `test_guard2_pattern_matches_status_line` (exact FEAT-021-shaped line),
  `test_guard2_fallback_probe_detects_score_9` (score present, no
  `skipped:` prefix at all).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Exact state boundaries in `scripts/little_loops/loops/autodev.yaml`:
  `check_guard2_verdict` spans lines 1110-1137 (regex at line 1134,
  `on_no: recheck_after_size_review` at line 1136); the sibling state
  `check_readiness_for_atomic_remediation` (whose `on_yes` the fix must
  keep reachable) spans 1139-1154; `recheck_after_size_review` (the
  unchanged fallback target) starts at line 1253.
- `scripts/little_loops/fsm/evaluators.py:396-431`
  (`evaluate_output_contains`) confirms `output_contains` tries
  `re.search(pattern, output)` first and only falls back to plain
  substring match `pattern in output` if the pattern fails to compile as
  regex — so the loosened pattern
  `"skipped:.* score (8|9|10|11)\\b"` from Expected Behavior #1 is a
  valid Python regex (it compiles), meaning it will be evaluated as
  regex, not silently degrade to substring matching.
- `skills/issue-size-review/SKILL.md:242` documents a **different**
  skip line than the one this bug targets: the fixed template there is
  for guard-1's ambiguous *Large* (5-7) case,
  `"[ID] skipped: score X (ambiguous)"`. The guard-2 *Very Large* (8-11)
  decline wording quoted in this issue and in the `autodev.yaml:1120`
  comment (`"skipped: score 11 (Very Large) — strictly sequential,
  ..."`) has **no fixed template anywhere in SKILL.md** — it's
  freeform agent-generated prose following the general
  `"[ID] [action]: [summary]"` convention (SKILL.md:72). This means the
  wording is not guaranteed stable even after this fix's regex is
  loosened, which raises the priority of Expected Behavior #2's
  `check_guard2_score_fallback` probe from a defensive nicety to the
  actual long-term safety net — the regex fix alone can drift out of
  sync again if the skill's prose wording changes further.
- `scripts/tests/test_autodev_loop.py` does not exist yet — confirmed via
  filesystem check, so this is a new test file, not an addition to an
  existing suite.

## Acceptance Criteria

- [ ] `check_guard2_verdict.pattern` matches `"skipped: score 11 (Very
      Large) — strictly sequential, …"` on `on_yes`
- [ ] `check_guard2_score_fallback` routes to
      `check_readiness_for_atomic_remediation` when the captured output
      contains `score (8|9|10|11)` without the `skipped:` prefix, and to
      `recheck_after_size_review` otherwise
- [ ] `ll-loop validate autodev` passes with no MR-1 / MR-3 violations
- [ ] `pytest scripts/tests/test_autodev_loop.py -q` passes
- [ ] `pytest scripts/tests/ -q` (full suite) passes

## Related

- FEAT-2751 (stagnation detector — split from this issue; same run/finding)
- BUG-2734 (introduced the atomic-remediation path and this regex)
- BUG-2594 (why the fallback probe uses `evaluate.source` instead of shell
  interpolation of captured text)

## Session Log
- `/ll:refine-issue` - 2026-07-23T21:57:11 - `411e7b05-6695-47c9-8ae7-ebcadbdf2ef1.jsonl`

- split from FEAT-2751 on 2026-07-23 — regex-fix half only, kept as a
  standalone low-risk BUG so it can ship without waiting on the larger
  stagnation-detector design in FEAT-2751.
