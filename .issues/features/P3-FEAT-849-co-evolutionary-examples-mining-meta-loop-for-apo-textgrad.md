---
id: FEAT-849
type: FEAT
priority: P3
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# FEAT-849: Co-evolutionary Examples Mining Meta-Loop for apo-textgrad

## Summary

Build a continuous, self-calibrating meta-loop that mines completed issues and session logs to produce an adaptive `examples.json` for `apo-textgrad`. The mining loop and the optimization loop are coupled: each optimization cycle's gradient signal drives adversarial example generation in the next mining cycle, and the example corpus is continuously re-calibrated to the current prompt's capability level.

## Current Behavior

`apo-textgrad` requires a manually created `examples.json`. There is no mechanism to source examples from the project's existing history — 784+ completed issues and hundreds of linked session logs contain real labeled invocations but none of it is harvested. The corpus is static; once created it never updates to reflect evolved conventions or harder edge cases.

## Expected Behavior

A loop (`examples-miner.yaml` or similar) runs as a wrapper around `apo-textgrad` that:

1. **Harvests** skill invocations from all session logs linked in completed issues (`## Session Log` entries)
2. **Judges** each harvested pair using a rubric oracle (a separate calibrated prompt) that scores outputs against structured criteria rather than literal string matching
3. **Calibrates** the active example set to the informative difficulty band (40–80% pass rate against the current prompt) — trivially easy examples are retired, noise-level hard examples are excluded
4. **Synthesizes** new adversarial examples by reading the gradient output (`FAILURE_PATTERN`, `ROOT_CAUSE`) from the most recent `apo-textgrad` run and generating targeted perturbations of passing examples
5. **Diversifies** via a coverage budget: at least N examples per skill type, issue type, priority band, lifecycle stage, and failure cluster
6. **Publishes** a fresh `examples.json` with per-example metadata (provenance, difficulty score, failure cluster, freshness weight)
7. **Maintains** a living corpus: new completions enter the harvest queue automatically; stale examples decay in weight; an archived regression floor prevents backward drift

## Motivation

`apo-textgrad` is only as good as its examples. A static hand-crafted `examples.json` optimizes the prompt for known cases while leaving blind spots untouched. The project already has the labeled dataset — completed issues with accepted outputs are implicit human approvals — it just lacks the mining step. Without adaptive calibration, the corpus goes stale as the prompt improves and new conventions emerge. Without adversarial synthesis, the gradient signal only covers patterns already in the corpus. The co-evolutionary design ensures the example difficulty always leads the prompt's current capability, producing continuous improvement rather than convergence to a local optimum.

## Proposed Solution

A two-loop architecture:

**Outer loop** (`examples-miner.yaml`): harvest → judge → calibrate → synthesize → diversify → publish
**Inner loop** (`apo-textgrad`): test → gradient → apply → iterate

The outer loop reads the gradient output from the inner loop's most recent run as its synthesis signal. The inner loop reads `examples.json` published by the outer loop. They run in sequence per optimization cycle.

Key components:
- **Harvest script** (extend `ll-messages`): `--skill` filter + `--examples-format` flag that extracts (invocation context, accepted output) pairs from `.jsonl` logs
- **Oracle prompt**: a separate prompt optimized for scoring skill outputs against rubric criteria; itself a candidate for apo-textgrad optimization
- **Calibration state**: run current prompt against all candidates, compute pass rates, select 40–80% band
- **Adversarial synthesizer**: LLM-guided perturbation of passing examples using the current gradient
- **Diversity budget**: enforced per-axis coverage constraints

## Integration Map

### Files to Modify
- `scripts/little_loops/messages.py` — add `--skill` filter and `--examples-format` output mode
- `loops/apo-textgrad.yaml` — add optional `examples_miner` pre-step or document pairing pattern

### Dependent Files (Callers/Importers)
- `loops/examples-miner.yaml` (new) — the outer loop definition
- Any `apo-*.yaml` loop that uses an `examples_file` context variable

### Similar Patterns
- `loops/apo-textgrad.yaml` — inner loop being wrapped
- `loops/apo-opro.yaml` — similar prompt optimization pattern
- `scripts/little_loops/messages.py` — source of session log parsing logic

### Tests
- TBD — unit tests for harvest script (`--examples-format` output)
- TBD — integration test: mine a small fixture corpus, verify examples.json schema

### Documentation
- `loops/README.md` — document the miner/optimizer pairing pattern
- `docs/guides/` — add guide for setting up apo-textgrad with a live corpus

### Configuration
- `loops/examples-miner.yaml` — new loop config
- `context.examples_file` in `apo-textgrad.yaml` — path to published examples

## Implementation Steps

1. **Extend `ll-messages`**: add `--skill <name>` filter and `--examples-format` flag; output `[{input, expected, provenance}]` JSON
2. **Build `examples-miner.yaml`**: harvest → judge → calibrate → publish states; no synthesis yet
3. **Validate end-to-end**: run miner on `ready-issue` session logs, feed output to `apo-textgrad`, verify gradient fires
4. **Add adversarial synthesis state**: read gradient from previous apo-textgrad run, generate targeted perturbations
5. **Add diversity enforcement**: coverage budget logic in the calibrate/publish state
6. **Add oracle prompt**: separate calibrated scoring prompt; document how to optimize it
7. **Add corpus maintenance**: freshness decay, regression floor archiving, auto-ingest hook on issue completion

## Impact

- **Priority**: P3 — High leverage for prompt optimization quality, no existing workaround
- **Effort**: Large — multiple components (script extension, two new loops, oracle prompt)
- **Risk**: Medium — core loop logic is well-understood; oracle calibration is the open research question
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `apo`, `prompt-optimization`, `captured`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2dab8d3-f1a2-4974-84ba-68f20250569c.jsonl`
