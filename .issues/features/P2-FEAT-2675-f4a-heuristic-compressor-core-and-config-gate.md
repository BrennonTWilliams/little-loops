---
id: FEAT-2675
title: "F4a \u2014 Heuristic prompt compressor core + config gate wiring"
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
completed_at: '2026-07-18T16:50:27Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2456
relates_to:
- ENH-2486
- FEAT-2676
- FEAT-2599
labels:
- token-cost
- fsm
- compression
- tier-3
decision_needed: false
confidence_score: 100
outcome_confidence: 84
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# FEAT-2675: F4a — Heuristic prompt compressor core + config gate wiring

## Summary

Add the in-house, zero-dependency heuristic prompt compressor
(`compression/heuristic.py`), hook it into `FSMExecutor._run_action()` in
`fsm/executor.py`, and wire the `compression.*` config namespace
(`.ll/ll-config.json` / `config-schema.json`). This is the fully
independently-shippable core of FEAT-2599: no external ML dependency, gate
defaults `false`/no-op, and the heuristic's own 3–6× reduction range is
validated against a locked trace set that this issue owns creating (but does
**not** require LLMLingua to measure).

## Parent Issue

Decomposed from FEAT-2599: F4-gated — Heuristic prompt compressor
(LLMLingua-gated fallback). FEAT-2599 covers two concerns with different
dependency profiles: (1) the zero-dependency heuristic compressor + its
config/wiring — ready to implement now — and (2) the LLMLingua-dependent
benchmark comparator that decides whether to flip
`compression.heuristic_underperforms` — blocked on an unproven
`llmlingua`/`transformers` Learning Test Registry record (the exact gap
`/ll:confidence-check` flagged on FEAT-2599: "No Learning Test Registry
record exists for `llmlingua` or `transformers`... Run `/ll:explore-api
llmlingua`... before implementing the benchmark/gate acceptance criterion").
Splitting lets this ready, dependency-free half proceed without waiting on
that learning-test gap. The LLMLingua-dependent half is FEAT-2676.

### Trigger Threshold

The window-relative trigger design from FEAT-2599 applies here in full —
carried over verbatim since it is core compressor behavior, not benchmark
behavior:

- `compression.trigger_pct` (default `0.4`) — compress once the prompt
  exceeds this fraction of the active model's `context_window`. Resolve via
  `context_window_for(model, override=None)`
  (`scripts/little_loops/context_window.py:39`) — precedence: explicit
  `override` → `LL_CONTEXT_LIMIT` env var → `[1m]` model-id suffix (1M) →
  exact lookup in `MODEL_CONTEXT_WINDOW` → `200_000` floor. No
  `HostRunner.list_models()`/"F7-lite" API exists in the codebase (confirmed
  by full-tree grep) — do not build against that name.
  `compaction/instant.py:compute_goal_tokens()` (line 72) does the
  structurally identical `pct * context_window_for(...)` calculation; model
  `compress()`'s trigger resolution on that function.
- `compression.trigger_tokens` (default `null`) — optional absolute
  floor/override for hosts that can't report a context window, or for
  small-context-model users who want a fixed cutoff.
- If both are set, the **lower absolute value wins** (most conservative —
  compress sooner, not later).

## Use Case

As an operator running large-context FSM loops (e.g. the autodev / rn-*
recursive loops that capture and re-interpolate large prior outputs), I want
repeated and stale prompt content trimmed automatically before each host
request so long-running loops stay under the active model's context window and
cost less per iteration — without pulling in an ML dependency and without
changing behavior for prompts that sit under the trigger.

## Current Behavior

FSM loop prompts are assembled and sent to the host CLI uncompressed. The only
prompt-size mechanism today is ENH-2486's `prompt_size_guard` in
`FSMExecutor._run_action()` (`fsm/executor.py`), which is WARN-only — it emits a
`prompt_size_warn` event when `len(action)` exceeds `warn_chars` (default
`50_000`) and never mutates or truncates the prompt. There is no `compression.*`
config namespace and no heuristic/extractive prompt compressor anywhere in the
codebase.

## Expected Behavior

- For any FSM prompt crossing the window-relative trigger,
  `compression/heuristic.py` runs before the request is sent:
  - Repeated tool results older than 5 turns are dropped.
  - Stable system blocks are deduped (and flagged as `cache_control`
    candidates in metadata, for the separate, not-yet-filed F1 child to
    consume later — no `cache_control` marking happens in this issue).
  - Assistant turns beyond N are tail-truncated.
- The heuristic compressor hits a **3–6× prompt-token reduction range** on a
  locked 10-trace `general-task` set that this issue creates and commits.
  This measurement compares the heuristic's own before/after token counts
  (`len(text) // 4` convention, `session_store._estimate_tokens`,
  `session_store.py:2504` — no BPE tokenizer exists anywhere in the
  codebase, follow the same convention rather than adding one) — it does
  **not** require LLMLingua or `transformers` to compute.
- `.ll/ll-config.json` gains a `compression.*` namespace including
  `compression.heuristic_underperforms` (default `false`),
  `compression.trigger_pct` (default `0.4`), and
  `compression.trigger_tokens` (default `null`). The
  `heuristic_underperforms` gate is wired (a config toggle FEAT-2676 flips
  after its benchmark) but this issue does not decide or set its runtime
  value — it only ships the config surface and default.

## Proposed Solution

1. **`scripts/little_loops/compression/heuristic.py`** (new, ~150 LOC):
   - `drop_stale_tool_results(messages, max_age_turns=5)`
   - `dedupe_stable_system_blocks(messages)` — returns deduped blocks + a
     `cache_control_candidate` flag list in metadata (consumed later by the
     separate F1 child, not wired here)
   - `tail_truncate_assistant_turns(messages, max_n)`
   - `compress(messages, context_window=None, trigger_pct=0.4, trigger_tokens=None) -> CompressedResult`
     — resolves the effective trigger from `trigger_pct * context_window`
     (when `context_window` is known) vs. `trigger_tokens`, taking the lower
     absolute value when both apply.
   - Adapt (do not reimplement from scratch) the eviction/boundary logic
     already proven in `compaction/instant.py` (FEAT-2598):
     `evict_sink_and_window(messages, sink_n, window_n)` (line 34) —
     sink+window eviction preserving `role == "system"` messages
     unconditionally, conceptually the same operation as "drop stale tool
     results older than 5 turns"; `is_valid_cutoff(messages, index)` (line
     60) — snaps a truncation cutoff to a `role == "user"` turn boundary so
     eviction never splits an assistant/tool-call sequence, directly
     applicable to `tail_truncate_assistant_turns`. These operate on
     `session_store` message rows rather than an FSM live-prompt string, so
     they aren't a drop-in import, but the logic should be adapted.
2. **`scripts/little_loops/fsm/executor.py`**: hook `compress()` into
   `FSMExecutor._run_action()` (line 1452) around the
   `interpolate(action_template, ctx)` call (line 1470). This is the actual
   prompt-assembly point — `DefaultActionRunner.run()`
   (`fsm/runners.py:91`) only receives an already-interpolated `action: str`
   and decides *how* to execute it, not how the prompt is assembled.
   ENH-2486's existing prompt-size guard (`PromptSizeGuardConfig`,
   `fsm/schema.py:366-407`, attached to `FSMLoop.prompt_size_guard`,
   `schema.py:1128`) occupies the same call site but is a per-loop YAML
   field, WARN-only, and measures raw `len(action)` chars
   (`executor.py:1484`, default `warn_chars=50_000`) — it never truncates.
   Reuse the *location*, not that guard's config surface or metric.
3. **Config gate**: add `compression.heuristic_underperforms` (default
   `false`), `compression.trigger_pct` (default `0.4`), and
   `compression.trigger_tokens` (default `null`) to `.ll/ll-config.json` +
   a matching `compression.*` block in `config-schema.json`. Model
   `CompressionConfig` on `config/features.py:CompactionConfig` (line
   981-1012) + `config/core.py:BRConfig._parse_config()` (line 208) — the
   canonical pattern: a `from_dict`-classmethod dataclass in
   `config/features.py`, attached/parsed in `BRConfig`, re-exported from
   `config/__init__.py`, mirrored in `config-schema.json`. `history.compaction`
   (`config-schema.json:1819-1855`) is the closest actually-populated
   precedent to mirror (`additionalProperties: false`).
   - **`BRConfig.to_dict()` gotcha**: re-serializes config fields manually,
     field-by-field — not derived from `dataclasses.asdict()`. Each new
     `compression.*` field must be added explicitly to `to_dict()`'s output
     dict or it silently drops from config round-trips/dumps even though
     the dataclass has it.
4. **Lock the 10-trace `general-task` benchmark set**: curate and commit
   the 10-trace set (this issue owns locking it) alongside a script/test
   that measures the heuristic's own reduction ratio against it. FEAT-2676
   reuses these same committed trace files (data only, no code coupling) to
   run its offline LLMLingua comparator — do not duplicate trace curation
   there.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all pre-existing
anchors in this issue were re-verified and remain current):_

- **Locked trace-set: reuse the ENH-2518 `tier0_traces` fixture pattern (same
  EPIC).** The issue's "locked 10-trace `general-task` set" has a directly
  analogous, already-committed precedent under EPIC-2456:
  `scripts/tests/fixtures/tier0_traces/` (owner ENH-2518), with test module
  `scripts/tests/test_tier0_traces.py`. Model curation on it rather than
  inventing a layout:
  - Commit under `scripts/tests/fixtures/<set-name>/` (the dominant idiom;
    **not** the `scripts/tests/data/...` path guessed during locate), with a
    `manifest.json` carrying a `_meta` envelope (`owner`, `epic: EPIC-2456`,
    `tier`, `lock_date`, `command_options`) + a `traces[]` list of
    `{id, path, loop}` rows.
  - Test module idiom: module-level `FIXTURES_DIR = Path(__file__).parent /
    "fixtures" / "<set-name>"`; mirror the locked IDs as a module-scope
    `LOCKED_TRACE_IDS` tuple (so `@pytest.mark.parametrize` collects even
    before fixtures exist — Red-phase safe); use `pytest.fail(...)` (not
    `pytest.skip`) in loaders so a missing fixture is a hard failure. Separate
    manifest-level gates (existence, owner/tier, count, ID-set agreement) from
    per-trace gates.
  - FEAT-2676 consumes these committed files as **data only** — same
    fixtures/ dir, no code import — so lock the layout here.

- **`CompressionConfig` is a TOP-LEVEL namespace — attach it like
  `learning_tests`, not like `compaction`.** `CompactionConfig` is nested
  *under* `HistoryConfig` (`config/features.py`), so it is parsed indirectly
  via `HistoryConfig.from_dict(...)`, not directly in `BRConfig._parse_config`.
  For a standalone `compression.*` block the closer wiring template is the
  sibling top-level `learning_tests` / `decisions` namespaces in
  `config/core.py`: parse directly in `_parse_config()`
  (`self._compression = CompressionConfig.from_dict(self._raw_config.get("compression", {}))`),
  add a matching `@property compression` accessor, add the
  `from little_loops.config.features import (... CompressionConfig ...)` entry
  in `core.py`'s import block, and emit a sibling `"compression": {...}` dict
  literal in `to_dict()` (currently at `core.py:563`; the `history.compaction`
  sub-block it mirrors is at `core.py:736-743`). The dataclass *shape* (plain
  field defaults + lenient `from_dict` classmethod) still mirrors
  `CompactionConfig` as the issue states.

- **Executor hook ordering (avoid double-firing the ENH-2486 guard).** In
  `FSMExecutor._run_action()`: `interpolate()` is the call at line 1470;
  the prompt-size guard block is lines 1473–1495 (entry check `if
  guard.enabled` at 1477–1478, `size = len(action)` measurement at 1484,
  `prompt_size_warn` emit at 1486–1495); `action_start` is emitted at line
  1497. The guard is **purely observational** — it emits an event and never
  mutates `action`. So `compress()` must run *after* 1470 (needs the
  interpolated prompt) and *before* 1497 (so the emitted/executed prompt is
  the compressed one), and to keep the guard from measuring stale
  (uncompressed) length it should run **before** the guard block (1473) — or,
  if placed after, recompute `size = len(action)` post-compression.

- **Extra reusable trimming utility.** Beyond the three functions the issue
  already cites in `compaction/instant.py`, `select_sliding_window()`
  (`instant.py:82-110`) is structurally close to
  `tail_truncate_assistant_turns`: it walks messages backward accumulating
  `len(str(content)) // 4` token estimates against a budget, then snaps the
  cutoff forward via `is_valid_cutoff()`. Note these operate on
  `list[dict]` message rows (`role`/`content`), whereas the FSM `_run_action`
  site operates on a single already-interpolated `str` — adapt the logic, it
  is not a drop-in import (as the issue already notes).

## Integration Map

### Files to Modify

- `scripts/little_loops/compression/heuristic.py` (new)
- `scripts/little_loops/fsm/executor.py` — window-relative compression
  hook, in `FSMExecutor._run_action()` (line 1452) around the
  `interpolate(action_template, ctx)` call (line 1470).
- `scripts/little_loops/config/features.py` — new `CompressionConfig`
  dataclass.
- `scripts/little_loops/config/core.py` — parse `compression.*` in
  `BRConfig._parse_config()` and `to_dict()`.
- `scripts/little_loops/config/__init__.py` — re-export `CompressionConfig`
  (import block + `__all__`), following the exact pattern already used for
  `CompactionConfig` (line ~47).
- `.ll/ll-config.json`, `config-schema.json` — new `compression.*`
  namespace.

### Dependent Files (Callers/Importers)

- ENH-2486's prompt-size guard (`PromptSizeGuardConfig`,
  `fsm/schema.py:366-407`) — same `executor.py:_run_action` call site;
  confirm `compress()` and `prompt_size_warn` coexist without
  double-firing.
- `scripts/little_loops/context_window.py:context_window_for()` (line 39)
  — resolves the active model's context window for `trigger_pct`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — loads/resumes `FSMExecutor`;
  confirm the compression config (or its resolved trigger) carries through the
  executor persist/resume path so a resumed loop compresses identically to a
  fresh one [Agent 1 finding].
- `scripts/little_loops/cli/loop/run.py` (lines 152–155) — nearest CLI-flag
  precedent at the same call site: `--no-prompt-size-guard` /
  `--prompt-size-warn-chars N` already override `fsm.prompt_size_guard.*` per
  run. `compression.*` is a project-level `.ll/ll-config.json` namespace (no
  per-run flag required by this issue's scope), but this is the template if a
  future `--no-compression` override is wanted [Agent 2 finding].
- `scripts/little_loops/cli/ctx_stats.py` (`ll-ctx-stats`) — FYI only: the CLI
  billed as showing "context savings" reads `post_tool_use`-persisted per-tool
  byte metrics, not FSM prompt-assembly bytes, so an FSM-side `compress()`
  reduction has **no data path here today**. Out of scope, but it's where a
  user would look for compression stats and find none [Agent 2 finding].

**Conditional — only if `compress()` emits a new DES event** (the current
Proposed Solution does not mandate one; if a `compression_applied`/reduction-
ratio event is added):
- `scripts/little_loops/observability/schema.py` — add a `DESVariant`
  subclass (model on `PromptSizeWarnVariant`, line 200–203) and append it to
  the `DES_VARIANTS` tuple (line 563), or `ll-verify-des-audit` fails (exit 1)
  on the unregistered emit-site string [Agent 2 finding].
- `scripts/little_loops/generate_schemas.py` — add a matching `_schema(...)`
  entry or `docs/reference/schemas/` silently omits the new event's JSON
  Schema (caught by `test_generate_schemas.py`) [Agent 2 finding].
- `docs/reference/EVENT-SCHEMA.md` — add a `###` section + summary-table row
  for the new event (model on the `prompt_size_warn` section, line 473)
  [Agent 2 finding].

### Similar Patterns

- `scripts/little_loops/compaction/instant.py` — `evict_sink_and_window()`
  (line 34), `is_valid_cutoff()` (line 60), `compute_goal_tokens()` (line
  72).
- `scripts/little_loops/config/features.py:CompactionConfig` (line
  981-1012) + `config/core.py:BRConfig._parse_config()` (line 208).

### Tests

- `scripts/tests/test_heuristic_compression.py` (new) — unit tests for
  each of the three heuristic passes, plus the 3–6× reduction-range
  assertion on the locked 10-trace set (measured against the heuristic's
  own output only — no LLMLingua dependency).
- `scripts/tests/test_config_schema.py:test_history_compaction_in_schema`
  (line 463) — model a `test_compression_in_schema` test after this.
- `scripts/tests/test_config.py:TestLearningTestsConfig` (line 2601) and
  `TestBRConfigLearningTestsIntegration` (line 2675) — model
  `CompressionConfig.from_dict()` defaults/override tests and the
  `BRConfig(...).to_dict()` round-trip assertion after these.
- `scripts/tests/test_fsm_executor.py:TestPromptSizeGuardWarn` (line
  112-175) — add a sibling test class asserting the new `compress()` hook
  and the existing `PromptSizeGuardConfig`/`prompt_size_warn` guard (same
  call site) coexist without double-firing or interfering with each
  other's fixtures. Current guard fixtures top out at `"x" * 500` — well
  below any plausible compression trigger default, so no existing test in
  this class breaks, but nothing currently asserts the two mechanisms
  don't conflict once both are live.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_compaction.py` — **the pattern template for the new
  heuristic unit tests.** It tests the exact `compaction/instant.py` functions
  this issue adapts, one class per pure function
  (`TestEvictSinkAndWindow` line 32–62, `TestIsValidCutoff` line 65–83,
  `TestSelectSlidingWindow` line 97–107): list-of-dict message fixtures,
  order/boundary-preservation assertions, **no LLM mock** (only the LLM-backed
  `summarize_6_section` needs `patch(subprocess.run)`). Model
  `test_heuristic_compression.py`'s three pure passes on these, not on the
  mocked pattern [Agent 3 finding].
- **Config-namespace pattern: `decisions` is the closer top-level analogue
  than `learning_tests`.** `compression.*` is a standalone top-level namespace
  like `decisions` (not nested like `compaction`). Model the three-tier test
  set on `test_config.py:TestDecisionsConfig` + `TestBRConfigDecisionsIntegration`
  (line 2732–2786) and `test_config_schema.py:test_decisions_in_schema`
  (line 270–293, which documents the `additionalProperties: false` rejection
  rationale) rather than the `learning_tests` variants already cited [Agent 3
  finding].
- `scripts/tests/test_config.py` — add a re-export import assertion: no test
  currently asserts `from little_loops.config import CompressionConfig`
  succeeds. Mirror the `DecisionsConfig` re-export lines (`test_config.py:48`
  import, `:94` list membership) so a missing `config/__init__.py` re-export is
  caught [Agent 3 finding].
- `scripts/tests/test_fsm_executor.py:TestPromptSizeGuardWarn.test_warn_emitted_above_threshold`
  (line 128–143) — **concrete regression risk.** It asserts `warns[0]["size"]
  == 200` for a 200-char action. If `compress()` runs **before** the guard's
  `size = len(action)` measurement (executor.py:1484), the guard measures the
  post-compression size and this exact-value assertion breaks. The new sibling
  test class must pin the intended pre-vs-post-compression ordering explicitly
  [Agent 3 finding].
- `scripts/tests/test_fsm_executor.py` `TestCapture*` cases (exact-substring
  assertions on `mock_runner.calls[N]` at lines 892, 925, 962, 1019, 1051,
  1082, 1168) — **will break only if `compress()` runs unconditionally** (no
  size/config gate). All fixtures are short, so a size-gated `compress()`
  leaves them untouched; a design that mutates every action regardless of size
  breaks them. Treat as a guard-rail confirming the trigger must actually gate
  [Agent 3 finding].
- **New E2E gap:** no integration test currently runs a real `.yaml` loop with
  a large captured-then-reused prompt through `FSMExecutor`
  (`test_ll_loop_execution.py` / `integration/test_loop_run_e2e.py` have no
  large-prompt/threshold case). Add a local `TestCompressionEndToEnd` (per the
  no-hosted-CI policy) combining a large captured action with a downstream
  state interpolating `${captured.x.output}`, asserting compression still
  round-trips through capture/interpolation [Agent 3 finding].
- Locked-trace-set loader: the `scripts/tests/fixtures/tier0_traces/`
  `manifest.json` + `test_tier0_traces.py` loader (module-level
  `LOCKED_TRACE_IDS` tuple, `pytest.fail()` on missing fixture, `_meta`
  owner/epic/tier gate) is the confirmed shape to mirror **only if** F4a needs
  a locked before/after corpus. If `test_heuristic_compression.py` uses inline
  list-of-dict fixtures (the `test_compaction.py` precedent), no manifest is
  needed [Agent 3 finding].

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section (shared across
  EPIC-2456 children).
- `docs/reference/API.md` — document `compression/heuristic.py`.
- `docs/reference/CONFIGURATION.md` — add a `compression` block to the
  top-of-file "Full Configuration Example" JSON, plus a dedicated section
  (prose + `Key | Type | Default | Description` table + JSON example)
  styled exactly like the existing `#### history.compaction` section.
- `CONTRIBUTING.md` — the `scripts/little_loops/` package-layout tree
  diagram lists `compaction/` as a sub-package with a 3-line
  file/purpose annotation; add a sibling `compression/` entry for
  `heuristic.py` in the same style.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — the "### Prompt-Size Guard
  (prompt_size_guard)" subsection (line 220–244) is the most detailed existing
  prose on the exact `_run_action` call site this issue hooks into (WARN-only
  semantics, event payload shape, "hard-cap is a follow-on" note). Explain how
  `compress()` and the guard coexist there, matching the "coexist without
  double-firing" acceptance criterion [Agent 2 finding].
- `docs/guides/LOOPS_REFERENCE.md` — the loop feature-flag summary table has a
  `prompt_size_guard` row (line ~127); add a parallel `compression.*` gate row
  in the same style [Agent 2 finding].

### Configuration

- `.ll/ll-config.json` — new `compression.*` namespace:
  `compression.heuristic_underperforms` (default `false`),
  `compression.trigger_pct` (default `0.4`),
  `compression.trigger_tokens` (default `null`), plus whatever tuning
  knobs the implementation needs (e.g. `max_tool_result_age_turns`,
  `max_assistant_tail_turns`).
- `config-schema.json` — matching `compression` object with an explicit
  property list, `additionalProperties: false`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

1. **Gate `compress()` on the trigger — do not run it unconditionally.** The
   `TestCapture*` exact-substring assertions in `test_fsm_executor.py` (and the
   design intent) require `compress()` to no-op below the resolved trigger.
   Verify short actions pass through byte-identical.
2. **Decide compress-vs-guard ordering and pin it in a test.** Placing
   `compress()` before the guard block (executor.py:1473) makes
   `TestPromptSizeGuardWarn.test_warn_emitted_above_threshold`'s `size == 200`
   assertion measure post-compression length — update that expectation (or
   recompute `size` post-compression) and add the sibling test class asserting
   the chosen order.
3. **Confirm executor persist/resume carries compression config**
   (`fsm/persistence.py`) so a resumed loop compresses identically to a fresh
   run.
4. **Update `docs/guides/LOOPS_GUIDE.md` and `LOOPS_REFERENCE.md`** alongside
   the four docs already listed — the guard subsection and feature-flag table
   are the sibling-mechanism prose that must mention the new layer.
5. **Add the `config/__init__.py` re-export import test** and model the
   config-namespace tests on the `decisions` (top-level) pattern, not
   `learning_tests`.
6. **Only if a new compression DES event is emitted:** register a `DESVariant`
   in `observability/schema.py` + `DES_VARIANTS`, add a `generate_schemas.py`
   entry, and an `EVENT-SCHEMA.md` section — or `ll-verify-des-audit` fails.

## Acceptance Criteria

- Heuristic compressor (`drop_stale_tool_results`,
  `dedupe_stable_system_blocks`, `tail_truncate_assistant_turns`,
  `compress()`) implemented and unit-tested.
- Heuristic compressor hits the **3–6× range** on the locked 10-trace
  `general-task` set, measured via the codebase's `len(text) // 4` token
  convention — no LLMLingua/transformers dependency required for this
  measurement.
- `compress()` is hooked into `FSMExecutor._run_action()` and coexists with
  ENH-2486's `prompt_size_warn` guard without double-firing.
- `compression.heuristic_underperforms` (default `false`),
  `compression.trigger_pct` (default `0.4`), and `compression.trigger_tokens`
  (default `null`) round-trip through `.ll/ll-config.json` /
  `config-schema.json`; `CompressionConfig` is re-exported from
  `config/__init__.py`.
- The effective trigger resolves relative to the active model's
  `context_window` when known, falling back to `trigger_tokens` otherwise,
  with the lower absolute value winning when both apply.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: heuristic compressor (3 passes + `compress()`), window-relative
  compression hook in `fsm/executor.py`, `compression.*` config namespace
  and wiring, locked 10-trace `general-task` set + its own 3–6× reduction
  measurement, docs.
- **Out**: the offline LLMLingua comparator run and the logic that decides
  whether to flip `compression.heuristic_underperforms` based on that
  comparison (FEAT-2676); shipping the real LLMLingua pip dependency as a
  runtime consumer; any `cache_control` marking (tracked under the
  separate, not-yet-filed F1 child — this issue only flags candidates).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2599 | Parent — full original scope, codebase research findings, wiring analysis |
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Grandparent EPIC; § Children Tier 3 [TBD-13], Goal #9 |
| ENH-2486 | Existing prompt-size guard — confirm exact hook point before duplicating |
| FEAT-2676 | Sibling — LLMLingua benchmark comparator + gate-flip, depends on this issue's trace set + `compress()` |

## Impact

- **Priority**: P2 — high-leverage, compounds on every large-prompt FSM
  iteration, but not blocking.
- **Effort**: Medium — ~150 LOC + config wiring + trace-set curation +
  docs.
- **Risk**: Low — zero pip deps; well-trodden extractive-compression
  pattern; additive, default behavior unchanged for prompts under the
  window-relative trigger.
- **Breaking Change**: No.

## Resolution

Implemented (2026-07-18):

- **`scripts/little_loops/compression/heuristic.py`** (new sub-package) — three
  extractive passes (`drop_stale_tool_results`, `dedupe_stable_system_blocks`
  returning `cache_control` candidate indices, `tail_truncate_assistant_turns`)
  plus `compress()`/`CompressedResult` with window-relative trigger resolution
  (`trigger_pct * context_window` vs `trigger_tokens`, lower wins; both unset =
  unconditional). `len(text)//4` token convention; adapts `compaction/instant.py`
  logic. Also `compress_action_text()` — the byte-safe executor string adapter.
- **`fsm/executor.py`** — `compression_config` param threaded through
  (`PersistentExecutor` `**kwargs` → `cli/loop/run.py` passes `_config.compression`);
  hook in `_run_action()` runs **after** the ENH-2486 guard measurement (guard
  still reports the original assembled size → `prompt_size_warn` coexists without
  double-firing) and before `action_start`, **prompt-mode only**.
- **`CompressionConfig`** (`config/features.py`) parsed/served/serialized in
  `config/core.py`, re-exported from `config/__init__.py`, mirrored in
  `config-schema.json` (`additionalProperties: false`) and `.ll/ll-config.json`.
  Fields: `heuristic_underperforms` (false), `trigger_pct` (0.4),
  `trigger_tokens` (null), `max_tool_result_age_turns` (5),
  `max_assistant_tail_turns` (8).
- **Locked trace set** `scripts/tests/fixtures/heuristic_traces/` (10
  `general-task` message-list traces + manifest; ENH-2518 layout, owner
  FEAT-2675). Heuristic lands **4.23×** (in the 3–6× band) measured on its own
  before/after token counts — no LLMLingua. FEAT-2676 reuses these as data only.
- Tests: `test_heuristic_compression.py` (32), config namespace tests, executor
  `TestCompressionHook` coexistence/ordering. Docs: ARCHITECTURE, API,
  CONFIGURATION, CONTRIBUTING, LOOPS_GUIDE.

**Out of scope (per issue):** LLMLingua comparator/gate-flip (FEAT-2676),
`cache_control` marking (future F1 child — candidates only flagged here).

Verification: `python -m pytest scripts/tests/` → 15304 passed, 37 skipped;
`ruff check` clean; `mypy` clean on changed modules.

## Status

**Done** | Created: 2026-07-18 | Completed: 2026-07-18 | Priority: P2

## Session Log
- `/ll:manage-issue implement` - 2026-07-18T16:49:49Z - `26661046-eff4-48ae-879f-f2427ab04deb.jsonl`
- `/ll:ready-issue` - 2026-07-18T16:13:54 - `c4bc0260-c394-4406-929b-01d11d12c6f3.jsonl`
- `/ll:wire-issue` - 2026-07-18T16:10:14 - `520b1ac7-9220-4204-8158-91ef0ed360d9.jsonl`
- `/ll:refine-issue` - 2026-07-18T16:03:26 - `d4681c23-b2ae-49f4-b8c7-849044907d3c.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `70567c71-f6fe-461a-8bdd-2032806ffba1.jsonl`
