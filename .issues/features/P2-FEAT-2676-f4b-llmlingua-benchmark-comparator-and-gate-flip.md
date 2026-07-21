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
decision_needed: true
blocked_by:
- FEAT-2675
learning_tests_required:
- llmlingua
- transformers
confidence_score: 80
outcome_confidence: 70
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 14
score_change_surface: 18
size: Very Large
deferred_by: automation
deferred_date: '2026-07-21T05:24:42Z'
deferred_reason: low_readiness
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add `llmlingua`/`transformers` to `scripts/pyproject.toml:132`'s `llm`
   extras group, citing the new `.ll/learning-tests/llmlingua.md` record
   inline (same convention as the `anthropic` dep at lines 43-48).
5. Decide whether the gate flip lands as an `.ll/ll-config.json` instance
   override (no schema/dataclass edit needed) or a shipped default change
   (requires updating `config-schema.json:597-601`,
   `config/features.py:528-558`, and the four dependent test assertions
   in `test_config_schema.py`/`test_config.py` listed in the Tests
   section) — document the choice in the benchmark report so future
   readers know which path was taken.
6. Update `docs/reference/CONFIGURATION.md` (4 spots), `docs/guides/LOOPS_GUIDE.md:263-264`,
   `docs/reference/API.md:7664-7666`, and `config/features.py:537-540`'s
   docstring to match the benchmark's actual outcome, in addition to the
   already-planned `docs/ARCHITECTURE.md` update.
7. Write the new skip-guarded benchmark/comparator test following
   `test_otel_attributes.py`'s `find_spec` + `try/except Exception` +
   `pytest.skip` idiom — no new executor-level test is needed since
   `test_fsm_executor.py::test_heuristic_underperforms_bypasses` already
   covers the gate's `true` branch.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml:132` — add `llmlingua`/`transformers` pins to the
  existing empty `llm = []` extras group under `[project.optional-dependencies]`,
  following the citation-comment convention at lines 43-48 (the `anthropic`
  dep cites `.ll/learning-tests/anthropic.md` inline) — cite the new
  `.ll/learning-tests/llmlingua.md` record instead.
- `.ll/learning-tests/llmlingua.md` (and `transformers.md` if its usage
  surface isn't already pinned/trivial via llmlingua's own API) — new
  Learning Test Registry record proving the comparator invocation, per
  Proposed Solution step 1. Follow `.ll/learning-tests/phoenix.md` /
  `opentelemetry.md`'s format (pinned version-floor claim), not
  `anthropic.md`'s (default-installed runtime dep).
- **Conditional, only if the gate flip changes the *default* (not just
  `.ll/ll-config.json`'s instance value)**: `scripts/little_loops/config-schema.json:597-601`
  (`"default": false` + description prose) and
  `scripts/little_loops/config/features.py:528-558` (`CompressionConfig.heuristic_underperforms: bool = False`
  dataclass field default + class docstring at lines 537-540) both assert
  `false` as the default and must be updated together if implementation
  changes the shipped default rather than layering an override in
  `.ll/ll-config.json`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/compression/heuristic.py:compress()` (FEAT-2675) —
  called to produce the heuristic side of the comparison; do not
  reimplement compression logic here.
- FEAT-2675's locked 10-trace `general-task` set — reused as-is, not
  re-curated.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:229,706` — constructs
  `CompressionConfig` from `.ll/ll-config.json` and serializes
  `heuristic_underperforms` back out (e.g. for `ll-config get`); no code
  change expected, but confirms this is the only mechanical passthrough
  besides the executor gate.
- `scripts/little_loops/cli/loop/run.py:573` — passes `compression_config`
  into `FSMExecutor` init; downstream of the same config object, no
  change expected but part of the consumption chain if debugging the
  flipped gate's effect.
- `scripts/little_loops/fsm/executor.py:1542` — sole runtime consumer of
  the flag (`if cc is not None and not cc.heuristic_underperforms and
  action_mode == "prompt":`); already documented in this issue's
  Codebase Research Findings, restated here for the Integration Map.
  Confirmed via grep this is the *only* behavioral branch on this flag in
  the codebase.

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

_Wiring pass added by `/ll:wire-issue`:_
- New test module (e.g. `scripts/tests/test_llmlingua_benchmark.py`, flat
  in `scripts/tests/` — no `benchmarks/`/`optional/` subdirectory
  convention exists) following `test_otel_attributes.py`'s
  `_phoenix_conversion()` idiom (`importlib.util.find_spec("llmlingua") is
  None` guard + `try/except Exception` + `pytest.skip(...)`), not
  `test_policy_builder_node_gate.py`'s subprocess/binary-probe variant
  (that targets external non-Python tools).
- **No new executor-level test needed** — `scripts/tests/test_fsm_executor.py:245-250`,
  `TestCompressionHook.test_heuristic_underperforms_bypasses`, already
  proves the "gate flipped to `true` → compression bypassed" branch by
  constructing `CompressionConfig(heuristic_underperforms=True)` directly;
  it doesn't depend on `.ll/ll-config.json`'s value. Confirmed no gap
  here.
- **Conditional, only if the *default* changes** (see Files to Modify
  above): `scripts/tests/test_config_schema.py:308-309` (schema default
  assertion) and `scripts/tests/test_config.py:2817-2823,2848-2852,2865-2874`
  (three dataclass-default assertions in `TestCompressionConfig` /
  `TestBRConfigCompressionIntegration`) — all assert `is False` today and
  will break if the shipped default flips rather than an
  `.ll/ll-config.json` override.

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section: note the benchmark
  result and the gate's current effective value.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — four spots assert the `false`
  default and need review on a gate flip: line 120 (top-level JSON
  example), lines 1480-1481 (prose: "Default `false` runs it"), line 1485
  (reference table row), line 1494 (second worked JSON example).
- `docs/guides/LOOPS_GUIDE.md:263-264` — "Set
  `compression.heuristic_underperforms: true` to bypass the heuristic"
  framing reads oddly if the shipped default becomes `true`; update
  wording to match the benchmark's outcome.
- `docs/reference/API.md:7664-7666` — `little_loops.compression` module
  docstring currently says "The LLMLingua-gated benchmark comparator is
  FEAT-2676" as a forward reference; update to describe the actual
  comparator script's location/entry point once implemented.
- `scripts/little_loops/config/features.py:537-540` — `CompressionConfig`
  class docstring prose repeats the default-false/gate-flip framing;
  distinct from the dataclass field default itself (already listed under
  Files to Modify).
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md:157,217` — FYI only:
  epic-level status prose ("Set by benchmark, not by default") should get
  a status note when this issue closes; not a blocking edit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`heuristic_underperforms` is a live, already-consumed flag, not inert
  plumbing.** `scripts/little_loops/fsm/executor.py` gates prompt-mode
  compression on it directly: `if cc is not None and not
  cc.heuristic_underperforms and action_mode == "prompt":` (around line
  1542). Flipping the flag to `true` today **disables compression
  outright** — there is no LLMLingua runtime consumer to take over yet,
  which matches this issue's own "Scope Boundaries: Out" note but is worth
  stating explicitly so implementation doesn't assume a fallback path
  exists.
- **Locked 10-trace set — exact location**: `scripts/tests/fixtures/heuristic_traces/manifest.json`
  + `general-task-00.json` … `general-task-09.json` (sibling files, same
  dir). Each trace file is a bare JSON array of `{role, content}` dicts —
  the same shape `compress()` consumes directly, no adapter needed.
  `manifest.json._meta` records `owner: "FEAT-2675"`,
  `measurement: "heuristic self before/after, session_store._estimate_tokens (len//4)"`,
  and `command_options.reduction_band: [3.0, 6.0]` (the heuristic's own
  acceptance band — distinct from this issue's 0.5× comparator threshold).
- **Reuse `test_heuristic_compression.py`'s exact call shape** for the
  heuristic side of the comparison: `compress(messages,
  context_window=None)` (forces unconditional triggering) →
  `result.reduction_ratio`, a computed property on `CompressedResult`
  (`original_tokens / compressed_tokens`). `TestReductionBand.test_mean_in_band`
  already computes the mean ratio across all 10 traces this same way — the
  comparator can call this directly rather than re-deriving it.
- **Stale anchor in this issue's own `## Proposed Solution` step 2**: the
  `session_store._estimate_tokens` reference cites `session_store.py:2504`
  — the function is currently at **line 2936**, not 2504 (the repo has
  moved since that citation was authored). `heuristic.py` doesn't import
  this function though — it redefines `_estimate_tokens()` locally
  (`len(text) // 4`, lines 34-40) to avoid pulling `session_store` into the
  FSM hot path. The benchmark script should inline the same one-line
  convention rather than importing `session_store`, matching that
  precedent.
- **`pyproject.toml` already has an empty `llm` extras group** —
  `scripts/pyproject.toml`'s `[project.optional-dependencies]` defines
  `llm = []` as a placeholder alongside `dev`, `otel`, `webhooks`. This is
  the natural place to add `llmlingua`/`transformers` as an extras-only
  dependency (never in base `dependencies`), following the existing
  convention of citing the Learning Test Registry record inline next to
  the pin (see the `anthropic` dependency's comment citing
  `.ll/learning-tests/anthropic.md`).
- **Optional-dependency test-skip pattern to follow**: `scripts/tests/test_otel_attributes.py`'s
  `_phoenix_conversion()` helper (lines 37-52) probes
  `importlib.util.find_spec("phoenix") is None` and wraps the actual
  import in `try/except Exception`, returning `None` on any failure; the
  test body then does `if convert is None: pytest.skip(...)`. This
  import-probe idiom fits `llmlingua`/`transformers` (both importable
  Python packages) better than `test_policy_builder_node_gate.py`'s
  subprocess/binary-probe variant (which targets external non-Python
  tools like `node`).
- **Learning Test Registry record format** (`.ll/learning-tests/<slug>.md`,
  YAML frontmatter, empty body) — closest existing templates for a
  heavyweight/optional dependency are `.ll/learning-tests/phoenix.md` and
  `.ll/learning-tests/opentelemetry.md` (vs. `anthropic.md`, which is a
  default-installed runtime dep). `phoenix.md` records a pinned
  version-floor claim (`"Safe _HAS_PHOENIX guard floor: arize-phoenix >=
  15.10.0"`) — the `llmlingua`/`transformers` record should carry an
  analogous pinned-version claim. Confirmed no `llmlingua.md` or
  `transformers.md` record currently exists in `.ll/learning-tests/`
  (`ll-learning-tests check --stale-aware llmlingua` and `... transformers`
  both exit 1, "no record found"). Full authoring lifecycle documented in
  `skills/explore-api/SKILL.md`.
- **No existing 0.5×-threshold ratio-comparison code exists anywhere in
  the repo** (grepping `heuristic_underperforms` across the tree surfaces
  only the boolean consumption site and config plumbing). This confirms
  the threshold comparator logic is genuinely new; the closest structural
  precedent is `TestReductionBand`'s simple `MIN <= ratio <= MAX` band
  assertion with an f-string diagnostic on failure.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Learning Test Registry hard override)
**Outcome Confidence**: 70/100 → Moderate

### Concerns
- `ll-learning-tests check --stale-aware llmlingua` and `... transformers` both exit 1 ("no record found") as of this check — `learning_tests_required` is unresolved, which triggers this skill's hard override regardless of the aggregate readiness score.
- Otherwise the issue is strong: `blocked_by: FEAT-2675` is satisfied (Status: Completed), the locked trace fixtures exist at `scripts/tests/fixtures/heuristic_traces/`, and the `llm = []` extras group / skip-guard test idiom cited in the Integration Map are confirmed present in the current codebase.

### Gaps to Address
- Run `/ll:explore-api llmlingua` (and `transformers` if its usage surface isn't already pinned/trivial via llmlingua's own API) and record proof in the Learning Test Registry before starting implementation, per this issue's own Proposed Solution step 1.

### Outcome Risk Factors
- Wiring step 5 (instance override in `.ll/ll-config.json` vs. shipped default change in `config-schema.json`/`features.py`) is an open decision point deferred to implementation time — resolve before implementing to avoid rework across the four dependent test assertions listed in the Tests section.

## Session Log
- `/ll:confidence-check` - 2026-07-21T05:30:00 - re-check, no state change since prior run
- `/ll:decide-issue` - 2026-07-21T05:21:25 - `b712b0aa-dce5-4c80-8ba8-6f455a2947ee.jsonl`
- `/ll:refine-issue` - 2026-07-21T05:20:00 - `cbec2efa-fce3-4a24-ac33-e0c2553114f0.jsonl`
- `/ll:refine-issue` - 2026-07-21T05:18:43 - `4d72f490-5875-470e-b2b2-46de31f1f854.jsonl`
- `/ll:confidence-check` - 2026-07-21T05:16:43 - `109a86e3-e1dc-4dff-be3f-26141e6618f4.jsonl`
- `/ll:wire-issue` - 2026-07-21T05:14:43 - `4e00fd75-61c8-4cea-aa7b-d851dccd9efb.jsonl`
- `/ll:refine-issue` - 2026-07-21T05:08:13 - `4f97edc2-37b6-474e-91d0-b705c0264d09.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `70567c71-f6fe-461a-8bdd-2032806ffba1.jsonl`
