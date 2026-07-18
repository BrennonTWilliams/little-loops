---
id: FEAT-2676
title: "F4b \u2014 LLMLingua benchmark comparator + heuristic_underperforms gate flip"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T00:00:00Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2456
relates_to:
- FEAT-2675
- FEAT-2599
labels:
- token-cost
- fsm
- compression
- tier-3
decision_needed: false
blocked_by:
- FEAT-2675
learning_tests_required:
- llmlingua
- transformers
---

# FEAT-2676: F4b — LLMLingua benchmark comparator + heuristic_underperforms gate flip

## Summary

Run a one-time, offline LLMLingua comparator over the locked 10-trace
`general-task` set (created by FEAT-2675) to measure the heuristic
compressor's ratio against LLMLingua's, and wire the logic that flips
`compression.heuristic_underperforms` if the heuristic falls below 0.5× of
LLMLingua's measured ratio. Shipping the real LLMLingua integration as a
runtime dependency stays out of scope — only the benchmark run and the gate
wiring are in scope, matching FEAT-2599's original boundary.

## Parent Issue

Decomposed from FEAT-2599: F4-gated — Heuristic prompt compressor
(LLMLingua-gated fallback). FEAT-2599 was split because it bundled two
concerns with different dependency profiles: the zero-dependency heuristic
compressor + config wiring (FEAT-2675, ready to implement) and this
LLMLingua-dependent benchmark comparator, which is blocked on an unproven
`llmlingua`/`transformers` Learning Test Registry record —
`/ll:confidence-check` on FEAT-2599 flagged exactly this gap: "No Learning
Test Registry record exists for `llmlingua` or `transformers`, both
required for the one-time offline benchmark comparator run in the
acceptance criteria... Run `/ll:explore-api llmlingua` (and `transformers`
if its usage surface isn't trivial/pinned by llmlingua's own API) to prove
the comparator invocation actually works before implementing the
benchmark/gate acceptance criterion; record proof in the Learning Test
Registry." This issue exists to carry that unresolved gap without blocking
the ready half of the work.

## Dependency

**Blocked by FEAT-2675.** This issue reuses FEAT-2675's committed 10-trace
`general-task` set (data files, no code coupling) and calls its
`compression/heuristic.py:compress()` to produce the heuristic side of the
comparison. Do not re-curate a trace set here — reuse the one FEAT-2675
locks and commits.

## Expected Behavior

- `llmlingua` (and `transformers` if its usage surface isn't already
  pinned/trivial via llmlingua's own API) is proven via `/ll:explore-api`
  and recorded in the Learning Test Registry before implementation begins.
- A one-time, offline benchmark script runs the real LLMLingua compressor
  (GPT2-small, ~700MB weights) over FEAT-2675's locked 10-trace
  `general-task` set, purely as a benchmark comparator — not as a shipped
  runtime dependency. `llmlingua`/`transformers` are dev/benchmark-only
  dependencies, never installed by default for end users.
- If the heuristic's measured ratio on that set (from FEAT-2675) falls
  below **0.5× of LLMLingua's measured ratio**, the config gate
  `compression.heuristic_underperforms` (shipped with a `false` default by
  FEAT-2675) is flipped to reflect the benchmark's finding, per the
  recorded, reproducible comparator run.
- Shipping the LLMLingua integration itself (i.e., an actual runtime
  compressor that consumes `heuristic_underperforms == true`) is **out of
  scope** — this issue documents the benchmark result and leaves the gate
  in the state the benchmark implies; a follow-on issue would ship the
  LLMLingua runtime consumer if the gate needs to flip.

## Proposed Solution

1. **Prove the dependency**: run `/ll:explore-api llmlingua` (and
   `transformers` if needed) to prove the comparator invocation works;
   record proof in the Learning Test Registry (`ll-learning-tests`).
2. **Benchmark script** (dev/benchmark-only, not shipped in the installed
   package's runtime path): load FEAT-2675's locked 10-trace set, run the
   real LLMLingua compressor once offline, compute its reduction ratio
   using the same `len(text) // 4` token-estimation convention used
   elsewhere in the codebase (`session_store._estimate_tokens`,
   `session_store.py:2504`) so the two ratios are directly comparable.
3. **Record and apply the gate decision**: compare the heuristic's ratio
   (from FEAT-2675's test) against LLMLingua's ratio from step 2. Document
   the result (e.g. in a benchmark report/doc or test fixture) and set
   `compression.heuristic_underperforms`'s effective default per the
   0.5× threshold rule.

## Integration Map

### Files to Modify

- A new dev/benchmark script (not part of the installed package's runtime
  import path) — e.g. `scripts/little_loops/compression/_benchmark_llmlingua.py`
  or a `scripts/tests/` fixture-generation helper, exact location TBD
  during implementation but must not add `llmlingua`/`transformers` to the
  package's default install dependencies.
- `.ll/ll-config.json` — `compression.heuristic_underperforms` value, if
  the benchmark result implies flipping it from FEAT-2675's `false`
  default.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/compression/heuristic.py:compress()` (FEAT-2675) —
  called to produce the heuristic side of the comparison; do not
  reimplement compression logic here.
- FEAT-2675's locked 10-trace `general-task` set — reused as-is, not
  re-curated.

### Tests

- A benchmark/comparator test or script that records the LLMLingua ratio
  and asserts the 0.5× threshold logic against the heuristic ratio
  produced by FEAT-2675's `test_heuristic_compression.py`. Guard this test
  so it skips gracefully (rather than hard-failing) when `llmlingua`/
  `transformers` aren't installed in the current environment, following
  this repo's existing pattern for optional-tool gates (e.g. the Node
  conformance-suite gate, `scripts/tests/test_policy_builder_node_gate.py`)
  — required per this project's no-hosted-CI policy so contributors
  without the heavyweight ML deps aren't hard-blocked.

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section: note the benchmark
  result and the gate's current effective value.

## Acceptance Criteria

- Learning Test Registry record exists proving the `llmlingua` (and
  `transformers`, if needed) comparator invocation works
  (`/ll:explore-api llmlingua`).
- Offline LLMLingua comparator runs once over FEAT-2675's locked 10-trace
  set and records its reduction ratio.
- Gate (`compression.heuristic_underperforms`) flips correctly when the
  heuristic's ratio (from FEAT-2675) falls below 0.5× of LLMLingua's
  measured ratio on the same set — verified via this one-time offline
  benchmark comparator, not a runtime dependency.
- `llmlingua`/`transformers` are not added to the package's default
  install dependencies — benchmark-only, gated so the suite doesn't
  hard-fail for contributors without them installed.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: proving `llmlingua`/`transformers` via a Learning Test Registry
  record, the one-time offline LLMLingua comparator run, applying the
  0.5× threshold decision to `compression.heuristic_underperforms`.
- **Out**: shipping the real LLMLingua pip dependency as a runtime
  consumer (only the gate/toggle decision is in scope — file a follow-on
  issue if the benchmark shows the gate needs to flip and a real LLMLingua
  runtime path is required); re-curating the trace set (owned by
  FEAT-2675); the heuristic compressor implementation itself
  (FEAT-2675).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2599 | Parent — full original scope, confidence-check gap this issue resolves |
| FEAT-2675 | Sibling — owns the heuristic compressor, config gate default, and the locked trace set this issue reuses |
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Grandparent EPIC; § Children Tier 3 [TBD-13], Goal #9 |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier 3 prioritization, F4 benchmark open question (#3) |

## Impact

- **Priority**: P2 — resolves the learning-test gap blocking FEAT-2599's
  full acceptance criteria; not blocking (default gate value ships in
  FEAT-2675 regardless).
- **Effort**: Small-Medium — one-time benchmark script + Learning Test
  Registry proof; no runtime consumer to build.
- **Risk**: Low — offline/dev-only; no default-install dependency change.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `70567c71-f6fe-461a-8bdd-2032806ffba1.jsonl`
