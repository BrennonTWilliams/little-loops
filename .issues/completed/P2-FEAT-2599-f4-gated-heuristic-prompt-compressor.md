---
id: FEAT-2599
title: "F4-gated \u2014 Heuristic prompt compressor (LLMLingua-gated fallback)"
type: FEAT
priority: P2
status: done
captured_at: '2026-07-11T00:00:00Z'
discovered_date: 2026-07-11
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2486
labels:
- token-cost
- fsm
- compression
- tier-3
decision_needed: false
learning_tests_required:
- llmlingua
- transformers
confidence_score: 85
outcome_confidence: 73
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 15
score_change_surface: 20
size: Very Large
completed_at: '2026-07-18T15:58:09Z'
---

# FEAT-2599: F4-gated — Heuristic prompt compressor

## Summary

Add an in-house, zero-dependency heuristic prompt compressor invoked from
`fsm/runners.py` for prompts that cross a **window-relative trigger**
(default: 40% of the active model's `context_window`, configurable —
see Trigger Threshold below): drop repeated tool results older than 5
turns, dedupe stable system blocks (flagging them as `cache_control`
candidates for the separate, not-yet-filed F1 caching child — no
coupling to F1's implementation, just a flag), and tail-truncate
assistant turns beyond N. The real LLMLingua ML compressor (GPT2-small,
~700MB weights, pulls in `transformers`) stays **out of scope and
disabled by default** — it is gated behind
`compression.heuristic_underperforms == true`, set only after a benchmark
proves the heuristic underperforms. This is EPIC-2456 § Children
[TBD-13] — directly serves Goal #9 in the EPIC.

### Trigger Threshold

The original draft of this issue hardcoded an **8K-token** trigger,
copied from LLMLingua's upstream benchmarks — which target GPT-3.5-era
models with 4K–8K context windows, where compression was often required
just to fit the prompt at all. That number does not fit little-loops'
actual profile: Claude models run 200K–1M context windows, and prompts
of several hundred K tokens are routine. A flat 8K floor would fire
heuristic (lossy) compression on nearly every non-trivial FSM prompt,
not just the cost outliers the epic is targeting, trading response
quality for savings that aren't needed yet.

Instead, the trigger is **window-relative and configurable**:

- `compression.trigger_pct` (default `0.4`) — compress once the prompt
  exceeds this fraction of the active model's `context_window`. Reads
  `context_window` from `HostRunner.list_models()` (F7-lite) when
  available; falls back to `compression.trigger_tokens` if the active
  host/model doesn't expose a context window yet.
- `compression.trigger_tokens` (default `null`) — optional absolute
  floor/override for hosts that can't report `context_window`, or for
  small-context-model users who want a fixed cutoff regardless of
  window size.
- If both are set, the **lower absolute value wins** (most
  conservative — compress sooner, not later).

## Motivation

The algorithmic compression LLMLingua achieves is real (up to ~20× per
upstream benchmarks), but reproducing the model from scratch is out of
scope, and shipping the pip dependency by default pulls in `transformers`
+ 700MB of weights for every install. The heuristic approach (adapted
from LLMLingua's extractive strategy and Jha's tool-result trimming)
replicates most of the *outcome* — dropping stale tool output, deduping
repeated system blocks, truncating verbose tails — without the dependency
tree. Gating the real LLMLingua behind a measured benchmark, rather than
defaulting to it, keeps the epic's "0 sidecars, minimal deps" posture
intact while leaving a documented escape hatch if the heuristic proves
insufficient.

## Current Behavior

- No prompt-compression step exists at the `fsm/runners.py`
  prompt-assembly boundary. Prompts grow unboundedly with tool-result
  history until other mechanisms (compaction, session boundaries) kick
  in.
- ENH-2486 (done 2026-07-06) added a prompt-size guard + artifact
  bounding at the same `fsm/runners.py` insertion point, but that is a
  guard/cap, not a compressor — it does not reduce token count via
  content-aware trimming.

## Expected Behavior

- For any FSM prompt crossing the window-relative trigger (default: 40%
  of the active model's `context_window`, or `compression.trigger_tokens`
  if set — see Trigger Threshold above), `compression/heuristic.py` runs
  before the request is sent:
  - Repeated tool results older than 5 turns are dropped.
  - Stable system blocks are deduped (and flagged as `cache_control`
    candidates in metadata, for the separate F1 child to consume later —
    no `cache_control` marking happens in this issue).
  - Assistant turns beyond N are tail-truncated.
- The heuristic compressor hits a **3–6× prompt-token reduction range**
  on a locked 10-trace `general-task` set (this issue owns locking that
  trace set — no other issue currently does).
- If the heuristic's measured ratio on that set falls below **0.5× of
  LLMLingua's measured ratio** (LLMLingua run once, offline, purely as a
  benchmark comparator — not as a shipped runtime dependency), the config
  gate `compression.heuristic_underperforms` is available to flip
  compression over to the real LLMLingua pip dependency. Shipping the
  LLMLingua integration itself is **out of scope** for this issue; only
  the benchmark run and the gate wiring are in scope.
- `.ll/ll-config.json` gains a `compression.*` namespace including
  `compression.heuristic_underperforms` (default `false`),
  `compression.trigger_pct` (default `0.4`), and
  `compression.trigger_tokens` (default `null`).

## Proposed Solution

1. **`scripts/little_loops/compression/heuristic.py`** (new, ~150 LOC):
   - `drop_stale_tool_results(messages, max_age_turns=5)`
   - `dedupe_stable_system_blocks(messages)` — returns deduped blocks +
     a `cache_control_candidate` flag list in metadata (consumed later
     by the separate F1 child, not wired here)
   - `tail_truncate_assistant_turns(messages, max_n)`
   - `compress(messages, context_window=None, trigger_pct=0.4, trigger_tokens=None) -> CompressedResult`
     — resolves the effective trigger from `trigger_pct * context_window`
     (when `context_window` is known) vs. `trigger_tokens`, taking the
     lower absolute value when both apply.
2. **`scripts/little_loops/fsm/runners.py`**: hook `compress()` into the
   prompt-assembly path, resolving `context_window` from
   `HostRunner.list_models()` (F7-lite) for the active host/model when
   available. Confirm during implementation whether ENH-2486's existing
   size-guard call site is the right integration point (see Related Key
   Documentation) rather than adding a second, parallel threshold check.
3. **Benchmark harness**: lock a 10-trace `general-task` trace set (this
   issue documents and commits the set); run both the heuristic and a
   one-time offline LLMLingua comparator over it; record the ratio.
4. **Config gate**: add `compression.heuristic_underperforms` (default
   `false`), `compression.trigger_pct` (default `0.4`), and
   `compression.trigger_tokens` (default `null`) to `.ll/ll-config.json`
   + a matching `compression.*` block in `config-schema.json`. When
   `heuristic_underperforms` is `true`, the (out-of-scope) LLMLingua
   integration is expected to take over — this issue only wires the
   toggle and its default, not the LLMLingua consumer.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. Two of the issue's
load-bearing assumptions above do not match current code and need
correcting before implementation:_

- **The real prompt-assembly hook is `fsm/executor.py`, not
  `fsm/runners.py`.** `DefaultActionRunner.run()` (`fsm/runners.py:91`)
  only receives an already-fully-interpolated `action: str` — it decides
  *how* to execute it (slash-command vs. shell subprocess), it does not
  assemble the prompt. The actual `${...}` template interpolation, where
  ENH-2486's size guard already sits, happens in
  `FSMExecutor._run_action()` (`fsm/executor.py:1452`), specifically at
  the `interpolate(action_template, ctx)` call (`executor.py:1470`).
  ENH-2486's own resolution note makes the same correction: "the issue's
  original pointer to `fsm/runners.py:149` is only the `slash_command`
  branch, downstream of the split, and would miss `shell`/prompt paths."
  Step 2 above and the Integration Map should target `executor.py`'s
  `_run_action`, not `runners.py`.
- **`HostRunner.list_models()` / "F7-lite" does not exist anywhere in the
  codebase** — a full-tree grep for `list_models`, `F7-lite`, `F7_lite`
  returns zero code matches (only issue-file prose, across FEAT-2599,
  FEAT-2476, ENH-2477, and the EPIC). Context-window resolution already
  exists and ships today as `context_window_for(model, override=None)`
  in `scripts/little_loops/context_window.py:39` — precedence: explicit
  `override` → `LL_CONTEXT_LIMIT` env var → `[1m]` model-id suffix (1M) →
  exact lookup in `MODEL_CONTEXT_WINDOW` → `200_000` floor. This is the
  function to call for the window-relative trigger, not a not-yet-built
  `list_models()` API. `compaction/instant.py:compute_goal_tokens()`
  (line 72) already does the structurally identical
  `pct * context_window_for(...)` calculation for its own
  sliding-window budget — model `compress()`'s trigger resolution on that
  function.
- **ENH-2486's guard is a per-loop YAML field, not a `.ll/ll-config.json`
  namespace** — `PromptSizeGuardConfig` (`fsm/schema.py:366-407`) lives
  on `FSMLoop.prompt_size_guard` (`schema.py:1128`), configured per-loop
  in loop YAML, not read from project config. It measures raw
  `len(action)` chars (`executor.py:1484`, default `warn_chars=50_000`)
  and is WARN-only — it emits a `prompt_size_warn` event
  (`PROMPT_SIZE_WARN_EVENT`, `executor.py:102`) and never truncates or
  reduces content. This issue's `compression.*` gate is intentionally a
  different shape (project-level `.ll/ll-config.json`, and it actually
  reduces content) — that's fine, but "confirm whether ENH-2486's
  existing size-guard call site is the right integration point" (Step 2)
  resolves to: reuse the *location* (`_run_action`, post-interpolation)
  but not the guard's config surface or its char-count metric.
- **Reusable message-transform prior art exists in
  `compaction/instant.py`** (FEAT-2598): `evict_sink_and_window(messages,
  sink_n, window_n)` (line 34) — sink+window eviction that preserves
  `role == "system"` messages unconditionally, conceptually the same
  operation as this issue's "drop stale tool results older than 5
  turns"; `is_valid_cutoff(messages, index)` (line 60) — snaps a
  truncation cutoff to a `role == "user"` turn boundary so eviction never
  splits an assistant/tool-call sequence, directly applicable to
  `tail_truncate_assistant_turns`. These operate on `session_store`
  message rows rather than an FSM live-prompt string, so they aren't a
  drop-in import for `heuristic.py`, but the eviction/boundary logic
  should be adapted rather than reimplemented from scratch. Token
  estimation throughout the codebase uses the single `len(text) // 4`
  convention (`session_store._estimate_tokens`, `session_store.py:2504`)
  — no BPE tokenizer exists anywhere in the codebase; `heuristic.py`
  should follow the same convention for consistency rather than adding a
  tokenizer dependency.

## Integration Map

### Files to Modify

- `scripts/little_loops/compression/heuristic.py` (new)
- `scripts/little_loops/fsm/executor.py` — window-relative compression
  hook, in `FSMExecutor._run_action()` (line 1452) around the
  `interpolate(action_template, ctx)` call (line 1470) — corrected from
  `fsm/runners.py`; see Codebase Research Findings under Proposed
  Solution.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — re-export `CompressionConfig`
  (import block + `__all__`), following the exact pattern already used for
  `CompactionConfig` (currently the only config dataclass at this
  namespace level, line ~47). Without this, `from little_loops.config
  import CompressionConfig` fails even though `BRConfig` itself parses the
  namespace correctly — confirmed by direct read of `config/__init__.py`.

### Dependent Files (Callers/Importers)

- ENH-2486's prompt-size guard (`PromptSizeGuardConfig`,
  `fsm/schema.py:366-407`) occupies the same `executor.py:_run_action`
  leverage point but is a per-loop YAML field (`FSMLoop.prompt_size_guard`),
  WARN-only, char-count based — not a `.ll/ll-config.json` namespace to
  build on. Reuse the hook *location*, not its config surface.
- `scripts/little_loops/context_window.py:context_window_for()` (line
  39) — resolves the active model's context window for the
  `trigger_pct` calculation; no `HostRunner.list_models()`/F7-lite exists
  to call instead (see Codebase Research Findings).

### Similar Patterns

- `scripts/little_loops/compaction/instant.py` — `evict_sink_and_window()`
  (line 34), `is_valid_cutoff()` (line 60), `compute_goal_tokens()` (line
  72) — closest existing message-list eviction/threshold prior art,
  operating on a different data shape (session_store rows) but adaptable
  logic; see Codebase Research Findings above.
- `scripts/little_loops/config/features.py:CompactionConfig` (line
  981-1012) + `scripts/little_loops/config/core.py:BRConfig._parse_config()`
  (line 208) — the canonical pattern for wiring a new top-level
  `.ll/ll-config.json` namespace: a `from_dict`-classmethod dataclass in
  `config/features.py`, attached/parsed in `BRConfig`, re-exported from
  `config/__init__.py`, and mirrored in `config-schema.json` — model
  `CompressionConfig` on this rather than `events.otel` (which has no
  live `.ll/ll-config.json` block to compare against in this project;
  `history.compaction` is the actually-populated precedent).

### Tests

- `scripts/tests/test_heuristic_compression.py` (new) — unit tests for
  each of the three heuristic passes, plus the 3–6× reduction-range
  assertion on the locked 10-trace set.
- `scripts/tests/test_config_schema.py:test_history_compaction_in_schema`
  (line 463) — model a `test_compression_in_schema` test after this:
  asserts `additionalProperties: false`, property types/defaults.
- `scripts/tests/test_config.py:TestLearningTestsConfig` (line 2601) and
  `TestBRConfigLearningTestsIntegration` (line 2675) — model
  `CompressionConfig.from_dict()` defaults/override tests and the
  `BRConfig(...).to_dict()` round-trip assertion after these.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:TestPromptSizeGuardWarn` (line
  112-175) — add a sibling test class asserting the new `compress()` hook
  and the existing `PromptSizeGuardConfig`/`prompt_size_warn` guard (same
  call site, `_run_action()` around line 1470-1495) coexist without
  double-firing or interfering with each other's fixtures. Current guard
  fixtures top out at `"x" * 500` — well below any plausible compression
  trigger default, so no existing test in this class breaks, but nothing
  currently asserts the two mechanisms don't conflict once both are live.

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section (shared across
  EPIC-2456 children).
- `docs/reference/API.md` — document `compression/heuristic.py`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — the doc that enumerates the actual
  `.ll/ll-config.json` surface: add a `compression` block to the
  top-of-file "Full Configuration Example" JSON, plus a dedicated section
  (prose + `Key | Type | Default | Description` table + JSON example)
  styled exactly like the existing `#### history.compaction` section.
  Missing this doc leaves the new namespace undocumented even though
  `config-schema.json` and `.ll/ll-config.json` both list it.
- `CONTRIBUTING.md` — the `scripts/little_loops/` package-layout tree
  diagram lists `compaction/` as a sub-package with a 3-line
  file/purpose annotation; add a sibling `compression/` entry for
  `heuristic.py` in the same style.

### Configuration

- `.ll/ll-config.json` — new `compression.*` namespace:
  `compression.heuristic_underperforms` (default `false`),
  `compression.trigger_pct` (default `0.4`),
  `compression.trigger_tokens` (default `null`), plus whatever tuning
  knobs the implementation needs (e.g. `max_tool_result_age_turns`,
  `max_assistant_tail_turns`).
- `config-schema.json` — matching `compression` object with an explicit
  property list (mirror the `additionalProperties: false` convention used
  elsewhere in this schema — `history.compaction`,
  `config-schema.json:1819-1855`, is the closest actually-populated
  precedent to mirror; `events.otel` is declared in schema but has no
  matching live block in `.ll/ll-config.json`).
- **`BRConfig.to_dict()` gotcha** (`config/core.py`): re-serializes
  config fields manually, field-by-field — it does not derive from
  `dataclasses.asdict()`. Each new `compression.*` field must be added
  explicitly to `to_dict()`'s output dict, or it silently drops from
  config round-trips/dumps even though the dataclass has it.

## Acceptance Criteria

- Heuristic compressor hits the **3–6× range** on the locked 10-trace
  `general-task` set.
- Gate (`compression.heuristic_underperforms`) flips correctly when the
  heuristic falls below 0.5× of LLMLingua's measured ratio on the same
  set (verified via the one-time offline benchmark comparator, not a
  runtime dependency).
- `compression.heuristic_underperforms` defaults to `false` and
  round-trips through `.ll/ll-config.json` / `config-schema.json`.
- `compression.trigger_pct` (default `0.4`) and `compression.trigger_tokens`
  (default `null`) round-trip through `.ll/ll-config.json` /
  `config-schema.json`; the effective trigger resolves relative to the
  active model's `context_window` when known, falling back to
  `trigger_tokens` otherwise, with the lower absolute value winning when
  both apply.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

> ⚠ _Added by `/ll:refine-issue`: "≥8K-token hook in `fsm/runners.py`"
> below is stale — superseded by the window-relative trigger in
> § Trigger Threshold (`compression.trigger_pct`/`trigger_tokens`) and
> by the corrected hook location (`fsm/executor.py`, see Codebase
> Research Findings under Proposed Solution). Read "In" as: heuristic
> compressor (3 passes), window-relative compression hook in
> `fsm/executor.py`._

- **In**: heuristic compressor (3 passes), ≥8K-token hook in
  `fsm/runners.py`, locked 10-trace benchmark set, config gate wiring,
  one-time offline LLMLingua comparator run for calibration.
- **Out**: shipping the real LLMLingua pip dependency as a runtime
  consumer (only the gate/toggle is in scope — file a follow-on if the
  benchmark shows the gate needs to flip); any `cache_control` marking
  (tracked under the separate, not-yet-filed F1 child — this issue only
  flags candidates).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

5. Re-export `CompressionConfig` from `scripts/little_loops/config/__init__.py`
   (import block + `__all__`) alongside the existing `CompactionConfig`
   re-export.
6. Add a `TestPromptSizeGuardWarn`-adjacent test in
   `scripts/tests/test_fsm_executor.py` confirming `compress()` and the
   `prompt_size_warn` guard coexist at the same `_run_action()` call site
   without double-firing.
7. Add a `compression` block to `docs/reference/CONFIGURATION.md`'s "Full
   Configuration Example" + a dedicated `#### compression` section
   modeled on `#### history.compaction`.
8. Add a `compression/` entry to the `scripts/little_loops/` package-tree
   diagram in `CONTRIBUTING.md`, styled after the existing `compaction/`
   entry.

_Advisory (design decision, not a firm file list): if `compress()` ends up
emitting a new FSM event (sibling to `PROMPT_SIZE_WARN_EVENT`,
`executor.py:102`) rather than purely transforming `action` in place, that
event constant needs the same three-way fanout `PROMPT_SIZE_WARN_EVENT`
already has: re-export in `fsm/__init__.py`, a new events-table row in
`docs/reference/API.md`, and a new registry entry in
`scripts/little_loops/generate_schemas.py` (which produces a new
`docs/reference/schemas/*.json` file). Confirm during implementation
whether `compress()` needs its own event before treating this as required._

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Children Tier 3 [TBD-13], Goal #9 |
| `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` | EPIC-CHILD-8 spec detail, LLMLingua gating rationale |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier 3 prioritization, F4 benchmark open question (#3) |
| ENH-2486 | Existing `fsm/runners.py` prompt-size guard — confirm exact hook point before duplicating |

## Impact

- **Priority**: P2 — high-leverage, compounds on every large-prompt FSM
  iteration, but not blocking (no production user currently blocked).
- **Effort**: Medium — ~150 LOC + benchmark harness + trace-set curation.
- **Risk**: Low — zero pip deps for the shipped path; well-trodden
  extractive-compression pattern; LLMLingua itself stays opt-in.
- **Breaking Change**: No — additive; default behavior unchanged for
  prompts under the window-relative trigger (default 40% of the active
  model's `context_window` — see § Trigger Threshold; the "<8K tokens"
  figure here is stale, from the same superseded flat-threshold draft
  flagged under Scope Boundaries).

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18_

**Readiness Score**: 85/100 → STOP — ADDRESS GAPS (learning test hard override)
**Outcome Confidence**: 73/100 → Moderate

### Concerns
- No Learning Test Registry record exists for `llmlingua` or `transformers`,
  both required for the one-time offline benchmark comparator run in the
  acceptance criteria.

### Gaps to Address
- Run `/ll:explore-api llmlingua` (and `transformers` if its usage surface
  isn't trivial/pinned by llmlingua's own API) to prove the comparator
  invocation actually works before implementing the benchmark/gate
  acceptance criterion; record proof in the Learning Test Registry.

### Outcome Risk Factors
- Moderate ambiguity: the FSM event-emission question for `compress()` is
  deferred to implementation time rather than resolved now (flagged as
  advisory in the issue, not blocking, but adds a mid-implementation
  judgment call).

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-18
- **Reason**: Issue too large for single session (score 11/11 — Very Large); split along the zero-dependency vs. LLMLingua-dependency boundary that `/ll:confidence-check` had already flagged as the readiness gap.

### Decomposed Into
- FEAT-2675: F4a — Heuristic prompt compressor core + config gate wiring
- FEAT-2676: F4b — LLMLingua benchmark comparator + heuristic_underperforms gate flip

## Session Log
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `70567c71-f6fe-461a-8bdd-2032806ffba1.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `47c356f5-9422-4341-a630-d5022102caa1.jsonl`
- `/ll:wire-issue` - 2026-07-18T15:51:17 - `da5b8bc1-37d4-4cbd-8b47-e527c3010512.jsonl`
- `/ll:refine-issue` - 2026-07-18T15:44:14 - `7e3225e9-9335-4060-8082-56c665d84af5.jsonl`
- `/ll:capture-issue` - 2026-07-11T00:00:00Z - filed from EPIC-2456 § Children [TBD-13] per `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` (EPIC-CHILD-8) and `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` (Tier 3).

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-18
- **Decomposed into**: FEAT-2675, FEAT-2676

Work for FEAT-2599 is now carried by its child issues; this parent was closed by rn-decompose.
