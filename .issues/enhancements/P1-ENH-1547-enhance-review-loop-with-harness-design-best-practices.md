---
title: Enhance /ll:review-loop with harness-design best practices
type: ENH
priority: P1
effort: High
impact: High
risk: Medium
status: done
captured_at: '2026-05-17T07:41:00Z'
completed_at: '2026-05-17T15:20:18Z'
discovered_date: 2026-05-17
discovered_by: capture-issue
labels:
- loops
- review-loop
- harness
- testing
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/SKILL.md` — two "Tip:" lines recommend `Run /ll:review-loop <name>` post-creation; no update needed (base invocation, no flags) [Agent 1 finding]
- `commands/loop-suggester.md` — `loops-automation` theme catalog entry lists `review-loop` as a representative example; no update needed (label only, not flag-aware) [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — prose mentions in "Validation" and "Further Reading" sections; no flags described, no update required; optional: could note `.loops/reviews/` artifact persistence in Further Reading [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/agents/openai.yaml` — Codex adapter `short_description` field is currently truncated (`"Use when asked to review loop config quality, validate loop YAML, or audit a loo"`); `disable-model-invocation: true` in SKILL.md frontmatter causes `ll-generate-skill-descriptions` to skip this file — manual update required to reflect behavioral verification, rubric scorecard, and new flags [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`.gitignore` line placement (confirmed)**: `.loops/reviews/` is NOT yet in `.gitignore`. Insert after `.loops/diagnostics/` at line 80:
```
.loops/diagnostics/
.loops/reviews/
```

**`ll-loop simulate` parseable output** (`scripts/little_loops/cli/loop/testing.py:cmd_simulate()` at line 175):

The `=== Summary ===` block always appears at end of stdout. Parse these lines for behavioral check signals:

| SIM check | Signal to parse | Exact pattern |
|-----------|----------------|---------------|
| SIM-1 (stall) | `States visited:` contains repeated state names AND `Terminated by: max_iterations` | `grep "States visited:"` — check for cycle in the `→`-separated list |
| SIM-2 (premature terminal) | `Iterations: 1` (or <2) AND `Terminated by: terminal` | `grep "Iterations:"` + `grep "Terminated by: terminal"` |
| SIM-3 (exceeds max_iterations) | `Terminated by: max_iterations` (regardless of states visited) | `grep "Terminated by: max_iterations"` |

Exit codes from `scripts/little_loops/cli/loop/_helpers.py:EXIT_CODES` (line 24): `terminal → 0`, `max_iterations → 1`, `timeout → 1`, `cycle_detected → 1`. So exit code 1 from simulate does NOT uniquely distinguish SIM-3 — must parse stdout.

**Artifact filename timestamp format**: Use `%Y%m%d-%H%M%S` (dash-separated, matching `scripts/little_loops/cli/loop/run.py:301` and `parallel/worker_pool.py:243`), producing filenames like `loop-name-20260517-143207.md`. Note: `_make_instance_id()` in `_helpers.py:242` uses `%Y%m%dT%H%M%S` (T separator) — do not use that variant.

**Artifact frontmatter style**: The issue says "mirror `agents/loop-specialist.md`" but the loop-specialist's `.loops/diagnostics/` artifacts use **plain markdown bullet lists, not YAML frontmatter**. The review artifact spec (Step 6.5) calls for YAML frontmatter — this is a new pattern. Follow issue spec (YAML frontmatter with `loop:`, `reviewed_at:`, `scorecard:`, `findings_count:`, `simulation_result:`, `fixes_applied:`), not the plain-bullet loop-specialist style.

**Calibration example sources** for SR-* good/bad pairs in `reference.md`: good examples from `scripts/little_loops/loops/` — `harness-optimize.yaml`, `loop-specialist-eval.yaml`, `outer-loop-eval.yaml` (well-described, clear happy paths); bad examples from `scripts/tests/fixtures/fsm/` — `broken-verify-loop.yaml` (self-loop stall, ambiguous-output), `semantic-goal-mismatch.yaml`, `semantic-incoherent-state.yaml`.

**Test class patterns**: Existing classes in `test_review_loop.py` use **no mocks** — pure Python dict/FSMLoop construction. New `TestReviewLoopSimulation` tests that invoke `ll-loop simulate` should follow the subprocess pattern from `scripts/tests/test_ll_loop_execution.py:1386–1540` (which asserts on stdout strings like `"SIMULATION:"`, `"Summary"`, `"terminal"`). The remaining new classes (`TestReviewLoopArtifact`, `TestReviewLoopRubric`, `TestReviewLoopDescriptionDraft`, `TestReviewLoopPostFixIteration`) should follow the existing no-mock dict-assertion pattern.

**SR-* silent-skip confirmed**: `reference.md` SR-1 and SR-4 are explicitly defined to skip "when description is absent or fewer than 5 words". Step 1.5 (description draft) unblocks both by proposing a draft before Step 2c runs.

**Fixture templates** for the two new files:

`simulation-stalls.yaml` — modeled on `broken-verify-loop.yaml` (self-loop on `on_no`):
```yaml
name: simulation-stalls
description: "Loop that stalls: verify self-loops indefinitely on no-pass"
initial: verify
states:
  verify:
    action: echo "checking..."
    action_type: shell
    evaluate:
      type: llm_judge
      prompt: "Did the check pass? Answer YES only for clear success."
    on_yes: done
    on_no: verify
  done:
    terminal: true
```

`no-description.yaml` — modeled on `valid-loop.yaml` minus `description:`:
```yaml
name: no-description
initial: check
states:
  check:
    action: pytest
    on_yes: done
    on_no: done
  done:
    terminal: true
```

## Implementation Steps

1. **`.gitignore`**: Insert `.loops/reviews/` at line 81 (after `.loops/diagnostics/` at line 80) — 1-line change, done first to avoid committing review artifacts
2. **`reference.md`**: Add Rubric Dimensions (6 dims × 1–5 scale), Calibration Examples (good: `harness-optimize.yaml`/`loop-specialist-eval.yaml`; bad: `broken-verify-loop.yaml`/`semantic-goal-mismatch.yaml`), new check IDs SIM-1..3 + RT-1, Review Artifact YAML frontmatter schema, Description Draft Template
3. **`SKILL.md`**: Add Steps 1.5, 2.5, 4.5, 6.5 and new flags (`--exercise`, `--no-simulate`, `--rubric-only`, `--strict-semantic`); extend Step 3 with scorecard rendering; Step 2.5 parses `ll-loop simulate` stdout for `"Terminated by:"` and `"States visited:"` lines (see Integration Map > Codebase Research Findings for exact patterns)
4. **Test fixtures**: Create `scripts/tests/fixtures/fsm/simulation-stalls.yaml` (self-loop on `on_no: verify`) and `scripts/tests/fixtures/fsm/no-description.yaml` (valid loop, `description:` absent) — templates in Integration Map > Codebase Research Findings
5. **`test_review_loop.py`**: Add 5 new test classes:
   - `TestReviewLoopSimulation` — subprocess pattern (from `test_ll_loop_execution.py:1386–1540`); asserts on `"Terminated by:"` in stdout
   - `TestReviewLoopArtifact`, `TestReviewLoopRubric`, `TestReviewLoopDescriptionDraft`, `TestReviewLoopPostFixIteration` — no-mock pure-Python dict pattern (from `TestReviewLoopAutoFix`)
6. **`COMMANDS.md`**: Update `/ll:review-loop` entry with new flags, artifact location (`.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md`), rubric reference link
7. **Smoke test**: `ll-loop simulate loop-specialist-eval` to verify simulate output is parseable, then `/ll:review-loop loop-specialist-eval --dry-run` to verify scorecard renders and artifact path resolves

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **`skills/review-loop/agents/openai.yaml`**: Manually update `short_description` to reflect behavioral verification, rubric scorecard, artifact persistence, and new flags — `ll-generate-skill-descriptions` skips this file due to `disable-model-invocation: true` in SKILL.md frontmatter

## Impact

- **Priority**: P1 — Review skill is the primary quality gate for FSM loops; static-only analysis provides false confidence by missing behavioral failures (stalls, premature termination)
- **Effort**: High — 6 files modified, 5 new test classes, 4 new step phases (1.5, 2.5, 4.5, 6.5) added to SKILL.md, new reference.md sections (rubric, calibration examples, artifact schema)
- **Risk**: Medium — All new phases are additive; existing V-*/QC-*/FA-*/SR-* check behavior unchanged; primary risk is behavioral verification depending on `ll-loop simulate` CLI
- **Breaking Change**: No
- **Affected**: `skills/review-loop/SKILL.md`, `skills/review-loop/reference.md`, `scripts/tests/test_review_loop.py`, `docs/reference/COMMANDS.md`, `.gitignore`
- **Backwards compatible**: All new steps and flags are additive; existing V-*/QC-*/FA-*/SR-* behavior unchanged
- **New capability**: Trend tracking across reviews, behavioral verification, quality scorecard

## Scope Boundaries

**In scope:**
- Steps 1.5, 2.5, 4.5, 6.5 added to `skills/review-loop/SKILL.md`
- New check IDs: SIM-1, SIM-2, SIM-3 (simulation checks), RT-1 (post-fix regression)
- 6-dimension rubric scorecard with trend tracking in `reference.md`
- Review artifact persistence to `.loops/reviews/<name>-<timestamp>.md`
- New flags: `--exercise`, `--no-simulate`, `--rubric-only`, `--strict-semantic`
- Calibration examples (good/bad pairs) for all SR-* checks in `reference.md`

**Out of scope:**
- Changes to `scripts/little_loops/cli/loop/testing.py` (loop simulation engine)
- Changes to `scripts/little_loops/fsm/schema.py` (FSM schema)
- Modifications to loop-specialist agent (reads review artifacts read-only)
- New `ll-loop` CLI subcommands
- Changes to existing check IDs (V-*, QC-*, FA-*, SR-*)
- Loop YAML schema changes

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/review-loop/SKILL.md` | The skill being enhanced |
| `skills/review-loop/reference.md` | Check ID definitions; rubric goes here |
| `scripts/little_loops/cli/loop/testing.py:175` | `ll-loop simulate` / `cmd_simulate()` — parseable stdout format (see Integration Map for exact patterns) |
| `scripts/little_loops/cli/loop/_helpers.py:24` | `EXIT_CODES` dict — exit code 1 for `max_iterations`/`timeout`/`cycle_detected`; not unique for SIM-3, must parse stdout |
| `scripts/little_loops/fsm/types.py:32` | `ExecutionResult.terminated_by` string values: `"terminal"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"error"`, `"handoff"`, `"cycle_detected"` |
| `agents/loop-specialist.md` | Diagnostic artifact format (plain markdown bullets, NOT YAML frontmatter — review artifacts use a new YAML frontmatter pattern instead) |
| `.gitignore:80` | `.loops/diagnostics/` at line 80; add `.loops/reviews/` at line 81 |
| `scripts/tests/test_ll_loop_execution.py:1386` | Subprocess test pattern for simulate output assertions (`"SIMULATION:"`, `"Summary"`, `"terminal"`, `"States visited:"`) |
| `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` | Template for `simulation-stalls.yaml` (self-loop on `on_no`) |
| `scripts/little_loops/loops/harness-optimize.yaml` | Good calibration example for SR-* checks in `reference.md` |

## Labels

- loops
- review-loop
- harness
- testing

## Status

Open — sourced from `~/.claude/plans/use-the-best-practices-glowing-sparkle.md`

---

## Session Log
- `/ll:ready-issue` - 2026-05-17T15:11:38 - `78462d3d-d767-435e-b986-6bb5e5a070d9.jsonl`
- `/ll:confidence-check` - 2026-05-17T16:00:00Z - `3cca01b4-c345-44fc-ad43-ed4c1462fdd7.jsonl`
- `/ll:wire-issue` - 2026-05-17T15:07:04 - `715ddee7-22a8-42d6-98d5-3cd589ead119.jsonl`
- `/ll:refine-issue` - 2026-05-17T15:01:20 - `040a90be-219b-4227-b171-38b8a2382be5.jsonl`
- `/ll:format-issue` - 2026-05-17T07:46:06 - `aac60a3c-4bb3-4d31-b1a0-08e1bc0000bc.jsonl`
- `/ll:capture-issue` - 2026-05-17T07:41:00Z - `faeb9229-ba0c-487a-b4e2-34a81c432ad9.jsonl`
