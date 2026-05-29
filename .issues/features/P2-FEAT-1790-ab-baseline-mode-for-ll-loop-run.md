---
id: FEAT-1790
type: FEAT
priority: P2
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: open
parent: EPIC-1663
labels: [feature, loops, harness, evaluation, ab-testing, meta-loop]
---

# FEAT-1790: A/B Baseline Mode for `ll-loop run`

## Summary

Add an opt-in baseline-comparison mode to `ll-loop run` that executes the harness's `execute` action twice in parallel — once with the harness's evaluation gates active, once as an ungated bare-skill invocation — and logs the delta in pass-rate, tokens, and duration to `.loops/runs/<id>/ab.json`. Produces measurable evidence that the harness improves on the bare skill, rather than relying on LLM self-grades.

## Motivation

EPIC-1663's MR-1 rule (CLAUDE.md § Loop Authoring) requires meta-loops to pair LLM judges with non-LLM external evidence because LLM self-grades on harness updates are ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%). The rule catches *missing* non-LLM evidence but doesn't *produce* the evidence — authors still have no native way to demonstrate that a harness beats the underlying skill.

`revfactory/harness` (reviewed 2026-05-29) addresses this by spawning two subagents per test prompt — `with_skill/` and `without_skill/` — into a per-iteration workspace, capturing `total_tokens`, `duration_ms`, and assertion grading for both. Their A/B (n=15) shows +60% quality with the harness; whether that holds for *our* harnesses is currently untestable. Without baseline comparison the harness's value is asserted, not measured.

This is also the empirical foundation for downstream issues in this batch (non-discriminating evaluator detection, blind comparator) — both depend on having paired with/without runs to analyze.

## Use Case

A user has built a `harness-refine-issue` loop and wonders whether the eval chain (`check_concrete` + `check_semantic` + `check_invariants`) actually improves output quality over just running `/ll:refine-issue` once. They run:

```bash
ll-loop run harness-refine-issue --baseline --items 10
```

The loop processes 10 issues. For each, it executes `/ll:refine-issue` twice: once inside the gated harness (retrying on failed evals), once as a one-shot bare invocation. Both outputs are passed to `check_semantic` blind (anonymized) for scoring. The output:

```
A/B Summary (n=10)
  Harness pass-rate:  9/10  (90%)
  Baseline pass-rate: 6/10  (60%)
  Delta:              +30%

  Median tokens:      harness=84k  baseline=42k  (+100%)
  Median duration:    harness=3m   baseline=1m   (+200%)
  Verdict:            harness wins on quality, costs ~2× tokens

Per-item: .loops/runs/<id>/ab.json
```

This converts MR-1's qualitative warning into a quantitative artifact authors can cite when defending or refining a harness.

## API/Interface

```bash
ll-loop run <loop> --baseline [--baseline-skill <skill>] [--items N]
```

- `--baseline` — enables A/B mode. Both arms run; verdicts go to a blind comparator.
- `--baseline-skill` (optional) — override what the baseline arm runs. Default: extract the slash command from `execute.action` and invoke it once with no retries.
- `--items N` (optional, multi-item only) — limit the sample size for the A/B run (full backlog can be expensive).

Output:
- `.loops/runs/<id>/ab.json` — per-item record:
  ```json
  {
    "items": [
      {
        "id": "BUG-1759",
        "harness": {"verdict": "yes", "tokens": 84852, "duration_ms": 23332},
        "baseline": {"verdict": "no",  "tokens": 41200, "duration_ms": 9870},
        "blind_compare": {"winner": "A", "rationale": "..."}
      }
    ],
    "summary": {"harness_pass_rate": 0.9, "baseline_pass_rate": 0.6, "delta": 0.3}
  }
  ```
- Summary printed at end of run (as shown in Use Case).

## Implementation Steps

1. **Wire `--baseline` flag** into `ll-loop run`'s argparse and pass through to the runner.
2. **Parallel execute** — when baseline mode is active, after `discover` resolves an item, spawn the harness arm (normal flow) and the baseline arm (single-shot skill invocation, no eval gates, no retries) concurrently. Reuse host-runner abstraction for the baseline invocation.
3. **Blind evaluation** — feed both outputs into `check_semantic` *anonymized as A and B* (random shuffle per item) and capture which got `yes`. Avoids judge bias toward longer/more-formatted output.
4. **Capture timing/tokens** — record `total_tokens` and `duration_ms` for both arms at completion. (Per `references/skill-testing-guide.md` §3-3, this data is only available at completion notification — store immediately.)
5. **Aggregate and report** — compute pass-rate delta, median token/duration ratios, write `ab.json`, print summary on terminal.
6. **Tests** — pytest fixtures simulating both-pass, harness-only-pass, baseline-only-pass, both-fail cases. Validate ab.json schema. Mock host runner.
7. **Docs** — update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` with a "Validating Your Harness" section pointing at `--baseline`. Cross-reference from EPIC-1663 and ENH-1665.

## Acceptance Criteria

- [ ] `ll-loop run <loop> --baseline` runs both arms in parallel without serializing
- [ ] Blind anonymization verified (judge prompt does not reveal which arm is the harness)
- [ ] `ab.json` written with per-item records and summary block
- [ ] Terminal summary prints delta, token/duration ratios
- [ ] Tests cover all four pass/fail combinations
- [ ] Documentation updated with usage example

## Out of Scope

- Multi-iteration improvement tracking (covered by ENH "Cross-iteration comparator").
- Non-discriminating evaluator detection (covered by ENH "Detect non-discriminating evaluators").
- Auto-tuning the harness based on A/B results (a future meta-loop on top of this primitive).

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | The harness pattern being measured; this gates whether harnessing pays off |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 rule that this issue operationalizes |
| `.issues/enhancements/P2-ENH-1665-ll-loop-validate-meta-loop-lint-rules.md` | Sibling rule-enforcement work under EPIC-1663 |

## Session Log
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open
