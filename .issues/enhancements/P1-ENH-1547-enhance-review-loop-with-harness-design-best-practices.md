---
title: "Enhance /ll:review-loop with harness-design best practices"
type: ENH
priority: P1
effort: High
impact: High
risk: Medium
status: open
captured_at: "2026-05-17T07:41:00Z"
discovered_date: 2026-05-17
discovered_by: capture-issue
labels:
  - loops
  - review-loop
  - harness
  - testing
---

# ENH-1547: Enhance /ll:review-loop with harness-design best practices

## Summary

The current `/ll:review-loop` skill is a single-pass static analyzer. It parses a loop YAML, runs `ll-loop validate`, applies a check suite, and prints findings — but never executes the loop, never persists results, and never iterates after applying fixes. Anthropic's harness-design principles (evaluators interact with running apps, communication via artifacts, generator-evaluator iteration, gradable criteria, avoiding self-evaluation bias, calibration examples, planner expands underspecified intent) are all applicable and all currently missing. This enhancement adopts all seven principles in one substantial change.

## Current Behavior

- Single-pass: parse → validate → checks → findings → one narrow auto-fix (QC-6) → done
- Findings exist only in conversation context; no persistence
- No execution: loop is never simulated or run
- Subjective SR-* checks have no rubric anchors or calibration exemplars
- Same LLM that found semantic issues also judges whether they're resolved (self-evaluation bias)
- If `description:` is absent, SR-1/SR-4 silently skip

## Expected Behavior

- **Step 1.5**: Description completeness gate — draft description from FSM structure if absent/too short; unblocks SR-1/SR-4
- **Step 2.5**: Behavioral verification via `ll-loop simulate` (default) or `ll-loop run --max-iterations 1` (`--exercise`); new check IDs SIM-1/SIM-2/SIM-3
- **Step 3**: 6-dimension rubric scorecard (1–5 per dim, composite /30) with trend arrows when a prior artifact exists
- **Step 4.5**: Post-fix iteration — re-run checks after applying fixes; surface RT-1 for regressions; max 3 rounds
- **Step 6.5**: Persist review artifact to `.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md`
- New flags: `--exercise`, `--no-simulate`, `--rubric-only`, `--strict-semantic`

## Motivation

The review skill is the primary quality gate for FSM loops. A static-only analyzer misses behavioral problems (stalls, premature termination), cannot track quality trends over time, and gives LLM-judges no calibration to prevent score drift. This gap means the review provides a false sense of confidence without verifying the loop actually runs correctly.

## Proposed Solution

Full adoption of all seven harness-design enhancements in one PR:

### New Workflow Phases

```
Step 1.5  Description completeness gate
          If description: absent or <5 words → draft from FSM structure
          Propose as first fix; unblocks SR-1/SR-4 from silent skip

Step 2.5  Behavioral verification
          Default: ll-loop simulate <name> → parse for SIM-1 (stall),
            SIM-2 (premature terminal in < 2 iters on max_iterations > 5),
            SIM-3 (exceeds max_iterations)
          --exercise: also run ll-loop run --max-iterations 1
          --no-simulate: skip entirely

Step 3    (extended) Rubric scorecard after findings table
          6 dimensions: Clarity, Decomposition, Resilience, Observability,
            Idempotence, Cost-efficiency (each 1–5, composite /30)
          Trend arrows vs prior artifact if .loops/reviews/<name>-*.md exists

Step 4.5  Post-fix iteration
          Re-run Steps 2a+2b (cheap checks only; skip 2c to control cost)
          Surface RT-1 for any new issues; loop max 3 rounds

Step 6.5  Persist review artifact
          .loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md
          Frontmatter: loop, reviewed_at, scorecard, findings counts,
            simulation result, fixes_applied
          Body: findings table, rubric justifications, simulation summary,
            before/after diffs
```

### New Check IDs

| ID    | Phase | Severity | Trigger |
|-------|-------|----------|---------|
| SIM-1 | 2.5   | Warning  | Simulation stalls before any terminal state |
| SIM-2 | 2.5   | Warning  | Terminal reached in <2 iters on max_iterations>5 (no-op happy path) |
| SIM-3 | 2.5   | Error    | Simulation exceeds max_iterations without terminating |
| RT-1  | 4.5   | Warning  | Post-fix pass surfaces new finding not present pre-fix |

### Rubric Dimensions (reference.md)

1. **Clarity of intent** — `description:` specific and testable; happy path matches description
2. **Decomposition** — states are focused single-purpose units (FA-4 inverse)
3. **Resilience** — `on_error`, `on_partial`, failure terminals, handoff all explicit
4. **Observability** — captures, evaluators, and state names enable debug from logs
5. **Idempotence** — shared state reset (FA-3), tolerates restart mid-run
6. **Cost-efficiency** — deterministic ops are programmatic not prompts (PR-1); `max_iterations` proportionate

### Calibration Examples (reference.md)

For each SR-* check: one good and one bad example pair from real ll built-in loops. Anchors the LLM's judgment to concrete references rather than free-form invention.

### Anti-Self-Evaluation Bias

`--strict-semantic` flag: in Step 2c, prompts the SR-* evaluator as a fresh session with calibration examples as the only context — prevents static-check findings from biasing semantic judgment.

## Integration Map

| File | Change |
|------|--------|
| `skills/review-loop/SKILL.md` | Add Steps 1.5, 2.5, 4.5, 6.5; new flags; rubric scorecard in Step 3 |
| `skills/review-loop/reference.md` | Rubric Dimensions section (6 dims with 1–5 rubrics), Calibration Examples (good/bad SR-* pairs), new check IDs SIM-1..3 + RT-1, Review Artifact Schema, Description Draft Template |
| `scripts/tests/test_review_loop.py` | New test classes: `TestReviewLoopSimulation`, `TestReviewLoopPostFixIteration`, `TestReviewLoopArtifact`, `TestReviewLoopRubric`, `TestReviewLoopDescriptionDraft` |
| `scripts/tests/fixtures/fsm/` | Two new fixtures: `simulation-stalls.yaml` (SIM-1 trigger), `no-description.yaml` (description-draft path) |
| `docs/reference/COMMANDS.md` | Update `/ll:review-loop` entry: new flags, artifact location, rubric reference link |
| `.gitignore` | Add `.loops/reviews/` below `.loops/diagnostics/` (line 80 precedent) |

No changes to: `scripts/little_loops/cli/loop/testing.py`, `scripts/little_loops/fsm/schema.py`, or the loop-specialist agent (reads artifact read-only).

## Implementation Steps

1. **`.gitignore`**: Add `.loops/reviews/` entry (1-line change, done first to avoid committing review artifacts)
2. **`reference.md`**: Add Rubric Dimensions, Calibration Examples, new check IDs, Artifact Schema, Description Draft Template
3. **`SKILL.md`**: Add Steps 1.5, 2.5, 4.5, 6.5 and new flags; extend Step 3 with scorecard rendering
4. **Test fixtures**: `simulation-stalls.yaml` and `no-description.yaml`
5. **`test_review_loop.py`**: Add 5 new test classes using existing `TestReviewLoopAutoFix` mock pattern
6. **`COMMANDS.md`**: Update `/ll:review-loop` entry
7. **Smoke test**: `/ll:review-loop loop-specialist-eval --dry-run` — verify scorecard, simulation transcript, artifact written

## Impact

- **Affected**: `skills/review-loop/SKILL.md`, `skills/review-loop/reference.md`, `scripts/tests/test_review_loop.py`, `docs/reference/COMMANDS.md`, `.gitignore`
- **Backwards compatible**: All new steps and flags are additive; existing V-*/QC-*/FA-*/SR-* behavior unchanged
- **New capability**: Trend tracking across reviews, behavioral verification, quality scorecard

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/review-loop/SKILL.md` | The skill being enhanced |
| `skills/review-loop/reference.md` | Check ID definitions; rubric goes here |
| `scripts/little_loops/cli/loop/testing.py:175` | `ll-loop simulate` implementation to parse |
| `agents/loop-specialist.md` | Artifact frontmatter style to mirror |
| `.gitignore:80` | `.loops/diagnostics/` precedent for new gitignore entry |

## Labels

- loops
- review-loop
- harness
- testing

## Status

Open — sourced from `~/.claude/plans/use-the-best-practices-glowing-sparkle.md`

---

## Session Log
- `/ll:capture-issue` - 2026-05-17T07:41:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/faeb9229-ba0c-487a-b4e2-34a81c432ad9.jsonl`
