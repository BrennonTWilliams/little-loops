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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical implementation detail — unigram collection:** The issue states PMI/lift are "derivable from data `ll-logs sequences` already has in hand." This is accurate but requires a small extension: `_count_ngrams()` (logs.py:411) starts its sliding window at `min_len` (default 2), so length-1 unigrams are **not** currently in the Counter. The existing `out_degree[node]` counter in `_build_chain_results()` (logs.py:436) is NOT a clean marginal P(a) — it accumulates weighted out-transition mass and overcounts nodes appearing in multiple positions of long chains.

**Correct approach (no new JSONL pass):** Extend `_count_ngrams()` to collect a parallel `unigram_counter: Counter[str]` during the same single iteration over session events, then pass it alongside the n-gram counter to `_build_chain_results()`. PMI formula on integer counts: `pmi = math.log(count(a,b) * total_unigrams / (count_a * count_b))` (defers float division until the final log).

**Backward-compatible field emission:** Follow the `if self.ci is not None: result["ci_lower"] = ...` conditional pattern from `EvaluatorVariance.to_dict()` in `analytics/variance.py`. The policy in `test_json_output_contracts.py` (line 12) confirms additive optional fields are non-breaking; existing `TestSequences` JSON schema tests will continue to pass unchanged.

## Implementation Steps

1. Implement and unit-test the PMI/lift helper against a known toy corpus.
2. Wire `pmi`/`lift` into `logs.py` sequence emission (`--json` + table column).
3. Update `loop-suggester.md` `--from-sequences` scoring doc + confidence rules.
4. Add a "frequency-prior equivalent" guard with a documented default threshold.
5. Update docs (`API.md` for the sequences subcommand; CLAUDE.md tool note if
   the JSON contract changes).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete anchor references per step:

1. **PMI/lift helper** — create `scripts/little_loops/analytics/association.py` with `compute_pmi(ngram_count, count_a, count_b, total_unigrams)` and `compute_lift(p_b_given_a, p_b)` functions; add `AssociationScores` dataclass following `EvaluatorVariance` in `analytics/variance.py`; update `analytics/__init__.py` to re-export. Test in new `scripts/tests/test_analytics_association.py` following `TestWilsonCI` structure in `scripts/tests/test_stats.py`.

2. **Wire into `logs.py`** — (a) modify `_count_ngrams()` (logs.py:411) to return `tuple[Counter, Counter[str]]` (ngrams, unigrams); (b) add `pmi: float | None = None` and `lift: float | None = None` to `ChainResult` (logs.py:396) and `Edge` (logs.py:386); (c) update `_build_chain_results()` (logs.py:436) to accept `unigram_counter` and call the new helper; (d) update `_compute_edges()` (logs.py:472) to attach per-edge PMI/lift; (e) update `to_dict()` methods with conditional emission. Existing `TestSequences` tests in `test_ll_logs.py` pass unchanged; add `TestChainResultPMI` class.

3. **`loop-suggester.md` update** — in `--from-sequences` Step FS-3 (approximately lines 299–359), add: if `pmi` field is present in chain JSON and `lift < 1.0`, mark as `"frequency_prior_equivalent": true` and cap `confidence` at `base_confidence` (no bonuses). Extend `TestConfidenceScoreCalculations` in `test_loop_suggester.py` with lift-threshold cases.

4. **Frequency-prior guard threshold** — default `LIFT_THRESHOLD = 1.0` (lift exactly 1.0 means the pair co-occurs at exactly what random chance predicts); document in the command prose as a named constant, not a magic number.

5. **Docs** — update `docs/reference/API.md` for the `sequences` subcommand; update `docs/reference/CLI.md` examples (approximately lines 2086-2089) to show `"pmi": 1.234, "lift": 2.5` in JSON output example.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `commands/loop-suggester.md` Step FS-1 "Parsed schema" inline JSON example (~line 313) — the hardcoded `ChainResult.to_dict()` schema block does not include optional `pmi`/`lift` fields; update to show them (e.g., `"pmi": 1.23, "lift": 2.1`) in the same pass as the Step FS-3 confidence formula change

## Scope Boundaries

**In scope:**
- A pure-Python PMI/lift helper computed from the n-gram + unigram counts
  `ll-logs sequences` already collects (no new corpus pass).
- An additive `pmi`/`lift` field on the `sequences` ChainResult / `--json`
  schema, with raw count preserved.
- A lift-threshold "frequency-prior equivalent" guard wired into
  `loop-suggester`'s `--from-sequences` confidence mapping.

**Out of scope:**
- A full Markov transition-memory model.
- The `ll-loop run --baseline` arm work (tracked separately).
- The optional `analyze-workflows` "vs. frequency prior" note — a follow-on
  (step 4 of Proposed Solution), not required for this issue.

Ordering of sequences/messages is already preserved everywhere and is not in
scope to change; it must not regress.

## Impact

- **Priority**: P2 — raises suggestion quality and gives a defensible "why this
  loop" signal, but no user is currently blocked and existing ranking still
  functions.
- **Effort**: Small — a pure-Python helper over counts already in hand, one
  additive field, and one confidence-rule change; no new corpus pass or schema
  migration.
- **Files**: `scripts/little_loops/cli/logs.py`,
  `scripts/little_loops/analytics/` (new helper),
  `commands/loop-suggester.md`, tests, docs.
- **Risk**: Low — additive field + opt-in ranking adjustment; existing raw-count
  output preserved.
- **Breaking Change**: No — new field is additive; raw-count output and ordering
  are unchanged.
- **Value**: Stops the suggestion tools from confidently recommending dataset
  imbalance as automation; gives users a defensible "why this loop" signal.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/Automating SKILL.md Generation for Computer-Using Agents via Interaction Trajectory Mining.md` | Source: frequency/transition-prior control requirement |
| `.claude/CLAUDE.md` § Loop Authoring | Existing external-measurement philosophy this extends |

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — extend `_count_ngrams()` to collect a parallel unigram Counter; add `pmi: float | None` and `lift: float | None` to `ChainResult` (line 396) and `Edge` (line 386) dataclasses; update `_build_chain_results()` to call the new association helper; update `_compute_edges()` to compute per-edge PMI/lift; update `to_dict()` methods with conditional field emission
- `scripts/little_loops/analytics/association.py` — NEW: pure-Python PMI/lift helper; expose `compute_pmi()` and `compute_lift()` standalone functions; `AssociationScores` dataclass following `EvaluatorVariance` in `analytics/variance.py`
- `scripts/little_loops/analytics/__init__.py` — re-export new public symbols from `association.py` following the existing `variance.py` export pattern
- `commands/loop-suggester.md` — update `--from-sequences` Step FS-3 confidence formula to add lift-threshold guard; document `LIFT_THRESHOLD = 1.0`

### Dependent Files (Callers / Consumers)
- `scripts/tests/test_ll_logs.py` — `TestSequences` already asserts `chain`, `count`, `edges`, `from`, `to`, `freq` in JSON schema; additive `pmi`/`lift` fields require no changes to existing tests; add new `TestChainResultPMI` class
- `scripts/tests/test_loop_suggester.py` — `TestConfidenceScoreCalculations` covers the existing formula; extend with lift-threshold guard test cases
- `scripts/little_loops/cli/logs.py:_cmd_sequences()` — the `print_json([r.to_dict() for r in results])` output path picks up new fields automatically once `ChainResult.to_dict()` is updated

_Wiring pass added by `/ll:wire-issue`:_
- `skills/ll-loop-suggester/SKILL.md` — bridges `commands/loop-suggester.md`; references `--from-sequences` mode description; verify skill description remains accurate after FS-3 confidence formula and FS-1 schema example updates [Agent 1 finding]

### Similar Patterns (to follow)
- `scripts/little_loops/analytics/variance.py` — `EvaluatorVariance` + `VarianceReport` dataclass structure with conditional `to_dict()` field emission; canonical model for `association.py`
- `scripts/little_loops/stats.py:wilson_ci()` — model for pure-math helper: `import math`, guard clauses with `ValueError`, formula docstring
- `scripts/little_loops/issue_history/coupling.py:analyze_coupling()` — min co-occurrence guard (`< 2`) before computing the score; significance threshold applied before appending results

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loop_run_analytics.py` — existing analytics test file; imports `little_loops.analytics.variance` directly; use as import-pattern reference for `test_analytics_association.py` [Agent 1/2 finding]

### Tests
- `scripts/tests/test_analytics_association.py` — NEW: unit tests for PMI/lift helper following `TestWilsonCI` in `scripts/tests/test_stats.py`; include a hand-derivable toy corpus, edge cases (zero counts), and `ValueError` guards
- `scripts/tests/test_ll_logs.py` — extend with `TestChainResultPMI` class for PMI/lift presence/absence in `to_dict()` output
- `scripts/tests/test_loop_suggester.py` — extend `TestConfidenceScoreCalculations` with lift-threshold guard cases

### Documentation
- `docs/reference/API.md` — update `ll-logs sequences` subcommand schema to document optional `pmi` and `lift` fields
- `docs/reference/CLI.md` — update examples at approximately lines 2086-2089 to show `pmi` and `lift` in JSON output

_Wiring pass added by `/ll:wire-issue`:_
- `commands/loop-suggester.md` Step FS-1 "Parsed schema" inline JSON example (~line 313) — hardcodes `ChainResult.to_dict()` output without optional fields; must be updated alongside Step FS-3 to show `"pmi": 1.23, "lift": 2.1` as optional entries [Agent 2 finding]
- `docs/reference/COMMANDS.md` (lines 644-675) — `/ll:loop-suggester` section's `--from-sequences` feature bullets; advisory: consider adding a bullet noting the lift-based frequency-prior guard [Agent 2 finding]

## Session Log
- `/ll:wire-issue` - 2026-06-28T05:16:23 - `21071d73-56f5-470a-b6f2-dd07673d1d0e.jsonl`
- `/ll:refine-issue` - 2026-06-28T05:04:01 - `ae64e4fc-164f-4fac-8eee-6ac3901e584e.jsonl`
- `/ll:format-issue` - 2026-06-27T04:49:22 - `8fc23559-5acb-4deb-a2be-144622a379a8.jsonl`
- `/ll:capture-issue` - 2026-06-27T04:45:41Z - conversation mode (research-paper analysis)

---

## Status

- **Created**: 2026-06-27
- **Status**: open
