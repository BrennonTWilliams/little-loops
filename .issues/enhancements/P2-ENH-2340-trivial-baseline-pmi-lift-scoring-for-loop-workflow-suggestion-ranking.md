---
id: ENH-2340
type: ENH
priority: P2
status: open
captured_at: "2026-06-27T04:45:41Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
relates_to: [FEAT-716, FEAT-1546]
labels: [loop-suggester, analytics, ranking]
---

# ENH-2340: Trivial-baseline (PMI/lift) scoring for loop/workflow suggestion ranking

## Summary

`loop-suggester`, `ll-logs sequences`, and `analyze-workflows` rank candidate
workflows/loops by **raw frequency count** (or heuristic confidence bonuses)
with no comparison against a trivial statistical baseline. Add a pointwise
mutual information (PMI) / lift score — `P(a→b) / (P(a)·P(b))` — alongside the
raw count so suggestions earn their confidence by being *non-obvious*
co-occurrences, not just artifacts of how common their head command is.

## Motivation

Sourced from `docs/research/05-26-2026-batch/Automating SKILL.md Generation for
Computer-Using Agents via Interaction Trajectory Mining.md`. The paper is a
negative-result diagnostic study on mining `SKILL.md`-style routines from
interaction trajectories. Its central methodological finding:

> "Mined-skill methods should be evaluated against frequency and transition
> priors before being compared to large language models... the most-common-skill
> baseline is not a strawman; it captures class imbalance and repetitive
> workflow structure that learned systems can easily appear to exploit. Without
> these controls, improvements from mined skill labels may be mistaken for
> improvements from dataset imbalance."

In the paper, a trivial **Frequency** baseline strictly outperformed the
learned MLP and GRPO policies on skill-step accuracy and beat the
auto-generated `SKILL.md` on edit distance at *every* data size.

little-loops mines workflows the same way the paper's pipeline does, and is
exposed to the same trap: a 2-gram like `commit → run-tests` may rank highly
purely because `commit` is a frequent head command, not because the *pair* is a
meaningful automatable unit. Surfacing PMI/lift turns "this is common" into
"this pair co-occurs more than chance would predict," which is the actual signal
for automation worth proposing.

This aligns with the existing project philosophy already encoded in
`.claude/CLAUDE.md` (non-LLM evaluators required, `diagnose-evaluators` variance
gate, `ll-loop run --baseline`): measure externally, distrust the readable
artifact. The gap is that the *suggestion-ranking* path never got a baseline
control.

## Current Behavior

- **`ll-logs sequences`** (`scripts/little_loops/cli/logs.py:411-493`): extracts
  per-session n-grams via sliding window, ranks by `counter.most_common()`
  (raw descending count); per-edge transition frequency is
  `count(a→b) / total_outgoing(a)`. No baseline / lift.
- **`analyze-workflows`** (`scripts/little_loops/workflow_sequence/analysis.py:436-617`):
  segments by time-gap + entity Jaccard, ranks by template-pattern overlap
  confidence `matching_steps / template_steps`. No baseline.
- **`loop-suggester`** (`commands/loop-suggester.md:99-118`, `--from-sequences`
  mode `:299-359`): heuristic confidence = base-by-paradigm + `+0.15` (count≥5)
  + `+0.10` (multi-session) + `+0.05` (identical cmds) − `+0.10` (variance). No
  null-hypothesis / frequency-prior term.

Order is already preserved everywhere (tuple n-grams, ordered message
sequences) — that is *not* the gap and should not regress.

## Expected Behavior

Each candidate sequence/edge carries a PMI (or lift) score next to its raw
count, and ranking/confidence incorporates it:

- `ll-logs sequences --json` emits a `pmi` (or `lift`) field per n-gram/edge.
- A 2-gram whose transition probability merely equals the unigram base rate of
  its successor (PMI ≈ 0 / lift ≈ 1) is flagged as "frequency-prior equivalent"
  and is *not* eligible for a high suggestion confidence in `loop-suggester`.
- `loop-suggester` confidence formula adds a lift-based term (or down-weights
  low-lift candidates) so that suggestions reflect non-obvious co-occurrence.

## Proposed Solution

1. Add a small pure-Python helper (e.g. `analytics/association.py`) computing
   PMI / lift from the already-collected `Counter` of n-grams plus unigram
   counts. PMI(a→b) = log( P(a→b) / (P(a)·P(b)) ); lift = P(b|a) / P(b). Both
   are derivable from data `ll-logs sequences` already has in hand — no new
   corpus pass required.
2. Extend the `sequences` ChainResult / JSON schema with the new field; keep
   raw count for backward compatibility.
3. Thread the score into `loop-suggester`'s `--from-sequences` confidence
   mapping: introduce a lift threshold below which a candidate is labelled
   "frequency-prior equivalent" and capped/excluded.
4. (Optional, follow-on) surface a one-line "vs. frequency prior" note in
   `analyze-workflows` template-match output.

Scope deliberately excludes a full Markov transition-memory model and the
`--baseline` arm work (tracked separately) — this issue is the cheap, highest-
leverage rung: PMI/lift on existing counts.

## Implementation Steps

1. Implement and unit-test the PMI/lift helper against a known toy corpus.
2. Wire `pmi`/`lift` into `logs.py` sequence emission (`--json` + table column).
3. Update `loop-suggester.md` `--from-sequences` scoring doc + confidence rules.
4. Add a "frequency-prior equivalent" guard with a documented default threshold.
5. Update docs (`API.md` for the sequences subcommand; CLAUDE.md tool note if
   the JSON contract changes).

## Impact

- **Files**: `scripts/little_loops/cli/logs.py`,
  `scripts/little_loops/analytics/` (new helper),
  `commands/loop-suggester.md`, tests, docs.
- **Risk**: Low — additive field + opt-in ranking adjustment; existing raw-count
  output preserved.
- **Value**: Stops the suggestion tools from confidently recommending dataset
  imbalance as automation; gives users a defensible "why this loop" signal.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/Automating SKILL.md Generation for Computer-Using Agents via Interaction Trajectory Mining.md` | Source: frequency/transition-prior control requirement |
| `.claude/CLAUDE.md` § Loop Authoring | Existing external-measurement philosophy this extends |

## Session Log
- `/ll:capture-issue` - 2026-06-27T04:45:41Z - conversation mode (research-paper analysis)

---

## Status

- **Created**: 2026-06-27
- **Status**: open
