---
id: EPIC-2456
type: EPIC
title: Token-Cost Reduction (Tier 0 + F1/F2/F3/F4-gated/F5/F6/F7-lite/F8/F10)
priority: P2
status: open
captured_at: '2026-07-02T00:00:00Z'
discovered_date: '2026-07-02'
discovered_by: deep-research / manual synthesis
labels:
- architecture
- token-cost
- fsm
- observability
- budgeting
- caching
- compression
- routing
- epics-candidate
- replication-not-integration
relates_to:
- EPIC-1707
- EPIC-1744
- ENH-1797
- FEAT-1689
- EPIC-2178
- EPIC-1463
- FEAT-2123
- ENH-2461
- EPIC-2258
- EPIC-2257
- FEAT-2470
- ENH-2471
- ENH-2475
- FEAT-2476
- ENH-2477
- FEAT-2478
- ENH-2479
- ENH-2486
- ENH-2490
- ENH-2499
- FEAT-2598
- FEAT-2671
- FEAT-2672
- FEAT-2673
- FEAT-2674
- FEAT-2675
- FEAT-2676
- FEAT-2680
- FEAT-2681
- FEAT-2710
- FEAT-2711
- ENH-2712
- ENH-2713
- ENH-2714
source_artifacts:
- thoughts/plans/2026-07-02-token-cost-reduction-architecture.md
- thoughts/plans/2026-07-02-token-cost-optimal-techniques.md
- thoughts/token-cost-reduction-arxiv-research-report.md
- thoughts/token-cost-reduction-gh-research-pass-2.md
- thoughts/wozcode-plugin-review.md
- .loops/runs/deep-research-20260702T113714/report.md
epic_role: container
confidence_score: 80
score_complexity: 9
score_test_coverage: 15
---

# EPIC-2456: Token-Cost Reduction (Tier 0 + F1/F3/F4-gated/F5/F6/F7-lite/F8/F10)

## Summary

Convert the deep-research catalog (13 repos, 4 adjacent plugins, 10 backlog features) into a single EPIC that **replicates** five features in-process (F3, F5, F7-lite, F8, F10), **integrates** one server-side primitive (F1, via the `anthropic` SDK), and gates one external library behind an in-house heuristic (F4-gated: LLMLingua stays opt-in behind a benchmark). The architecture is deliberate: little-loops already owns the call boundary (`resolve_host`), the iteration loop (`fsm/executor`), the prompt-assembly path (`fsm/runners`), and the prompt budget (`history.compaction`) — that surface is exactly where the open-source catalog's value lands, and most of it can be captured without new pip deps or sidecars.

Posture is **"finish what's started, then layer on top"**. Two of the nine remaining F-features (F5, F6) are already partially built — `pricing.py` prices Opus/Sonnet/Haiku with cache fields, `cli/loop/_helpers.py:1676` prints a per-state cost table, `fsm/executor.py:1295–1305` already aggregates `cache_read`/`cache_creation` per state. The EPIC treats those as foundation, not as duplicates. Aggregate footprint: **~1,390 LOC, 1 pip dep (`anthropic`), 0 sidecars** (F2's ~160 LOC cut 2026-07-10; was ~1,550).

**Prioritization layer** lives in `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` — five execution tiers (Tier 0 behavioral → Tier 1 measurement → Tier 2 caching → Tier 3 compaction/compression → Tier 4 routing). The 9 F-features below map onto those tiers; Tier 0 (wozcode P6/P2/P1 + LogCleaner + stop-sequence/prefill JSON helpers, ~180 LOC) ships first because it is strictly dominant (no measurement infra needed, immediate savings).

## Goal

When this EPIC is done, every `ll-loop run` invocation:

1. ~~**Caps its own spend** at a configured USD ceiling (F2)~~ — **cut 2026-07-10**: a spend cap is governance/circuit-breaking, not token-cost reduction (it halts a run, it doesn't lower $/token spent); see FEAT-2476 Session Log.
2. **Reports per-state spend** in `ll-ctx-stats` and the loop CLI's existing cost table, with `cache_read`/`cache_creation` broken out (already 80% done; F6 finishes it).
3. **Sets Anthropic `cache_control: ephemeral`** on system + skill/tool blocks in every host invocation (F1).
4. **Compacts long session memory** via the cookbook's 6-section schema (User Intent / Completed Work / Errors & Corrections / Active Work / Pending Tasks / Key References) at the existing 4096-token cross-session budget boundary (F3).
5. **Reuses the same compaction schema for subagent handoff** so a parent's context shrinks before the child reads it (F8).
6. **Speculatively warms the cache** before long-running skills (>50K-token prompts) by firing an async warming request on the `SkillStart` hook, or via the `max_tokens=0` SDK warm primitive for deterministic cases (F10).
7. **Routes to small/large model pairs in-process** based on a configured decision table — no LiteLLM sidecar, just a 4-key dict in `resolve_host()` plus an FrugalGPT cascade skeleton (F7-lite).
8. **Emits OTel `gen_ai.usage.*` attributes** into `.ll/history.db` directly via the DES discriminated-union event schema (no OpenLLMetry SDK needed; F5).
9. **Compresses FSM prompts ≥8K tokens** via an in-house heuristic compressor (drop repeated tool results, dedupe stable system blocks, tail-truncate assistant turns); LLMLingua pip dep is gated behind a benchmark proving the heuristic underperforms (F4-gated).

End-state metric: a measurable reduction in $/run for any loop that currently runs hot. Vendor-measured anchors from `anthropic-cookbooks` notebooks: caching **12.5× cost differential** (writes 1.25×, reads 0.1×); compaction **88% (12,847 → 1,526)** semantic upper bound / **58.6% (122,392 saved)** on a 5-ticket workflow; output **20–40%** from stop-sequence/prefill JSON helpers; routing **up to 85% cost reduction at 95% GPT-4 performance on MT Bench** (first-turn-only caveat).

## Motivation

### Why replication beats integration for most of the catalog

The deep-research catalog (`.loops/runs/deep-research-20260702T113714/report.md` lines 268–491) defaults to pip-install / sidecar-deploy shapes. The report's own project-context line (`Preferred are libs and drop-in CLIs`) explicitly disfavors long-running services — yet several of the top-10 features ship LiteLLM or Phoenix sidecars by default.

little-loops has three structural advantages that change the calculus:

1. **Anthropic-only today.** The host runner (`scripts/little_loops/host_runner.py`) is built around the `claude` CLI. LiteLLM's 100-provider surface is dead weight; Portkey's 1600-model catalogue is moot. A 4-key dict in `resolve_host()` covers the routing we actually need.
2. **Owns the FSM iteration loop.** No surveyed library (langgraph, autogen, pydantic-ai, crewAI, agno — report lines 215–223) exposes per-state-transition cost attribution. That's a native opportunity (F6) we already have 80% of the surface for.
3. **Owns the prompt-assembly path.** `fsm/runners.py` builds the prompt before `resolve_host()` is called. That's the insertion point for F4 (compression), F3 (compaction), and F10 (speculative warming) — all before any network IO.

Replication gives us the savings without the deployment surface, the vendor lock-in, or the dependency tree (LLMLingua pulls in `transformers` + 700 MB of weights; LiteLLM pulls in 100-provider adapters; Phoenix requires ClickHouse + an OTel collector).

### Why we can't replicate everything

Two features are non-replicable:

- **F1 `cache_control: ephemeral`** — server-side primitive (report line 53: `cache_creation_input_tokens` at 1.25× base, `cache_read_input_tokens` at 0.1× base → 90% discount on reads). The Anthropic API only honors it when the request body carries the parameter — nothing in our process can synthesize that effect. We must integrate via the `anthropic` SDK.
- **F4 LLMLingua proper** — ML compressor (GPT2-small, 700 MB weights). The algorithmic compression is real (report line 84: up to 20×) but reproducing the model from scratch is out of scope. We replicate the *outcome* with heuristics, and gate the pip dep behind a benchmark that proves the heuristic underperforms.

### Why this matters now

- **Compounds across every loop run.** Per-run savings multiply across `ll-auto`, `ll-sprint`, `ll-parallel`, and ad-hoc `ll-loop` invocations — the spend surface is large, and the optimization surface is already partly built.
- **Moghadasi/Ghaderi audit finding.** Zero of eight surveyed agent benchmarks disclose inference cost — making cost telemetry first-class (F5) is a competitive differentiator for any consumer of `.ll/history.db`.
- **Specific gaps the plans make actionable.** Two report features (F5, F6) finish in-flight work; six pass-2 ports slot inside existing F-features without new dependencies; one behavioral tier ships at near-zero LOC ahead of any measurement infrastructure.

## Scope

### In scope

**Tier 0 — behavioral quick-wins (~180 LOC + 1 hook module; ships before any F-feature)**

| Source | Technique | Surface |
|---|---|---|
| wozcode P6 | Verbatim-output rule in audit skill bodies | ~6 `skills/*/SKILL.md` bodies |
| wozcode P2 | Haiku pin + dense-list template + 3–5-call budget on read-only audit agents | ~4 `agents/*.md` frontmatter — **extracted to ENH-2490 (deferred)**; not in the strictly-dominant tranche |
| wozcode P1 | Edit-batching nudge (`PostToolUse` on Edit/Write/MultiEdit) | `hooks/hooks.json` + hook module + test |
| LogCleaner [25] | Anti-event regex + duplicate-window pre-filter on tool/log output | new filter module |
| pass-2 #7 | Stop-sequence + prefill JSON output helpers (`extract_between_tags()`, `parse_prefilled_json()`, `rfind('{')` recipe) | new `scripts/little_loops/output/parse.py` |

**F-feature layer (~8 children; ordered by tier — F2 cut 2026-07-10)**

| ID | F-feature | Module family | Lines of code (est.) | Pip deps |
|---|---|---|---|---|
| F1 | `cache_control: ephemeral` integration + cache-marking cost oracle | `host_runner.py` (new SDK call site) + oracle | ~130 (80 + ~50 oracle) | `anthropic` |
| F1-prereq (a) | Content-hash fragment store | new `prompts/fragment_store.py` | ~40 | 0 |
| F1-prereq (b) | Deferred tool loading | new `tools/deferred.py` | ~90 | 0 |
| ~~F2~~ | ~~`--max-cost` accumulator + 80/100% guard + ELIS forecast~~ — **cut 2026-07-10** (governance, not reduction; see FEAT-2476) | ~~new `fsm/budget.py`~~ | ~~~160~~ | — |
| F3 | Session-memory compaction (StreamingLLM eviction + 6-section schema) | new `compaction/instant.py` + `compaction/result.py` | ~320 | 0 |
| F4-gated | Heuristic prompt compressor (≥8K tokens) | new `compression/heuristic.py` | ~150 | 0 |
| F5 | OTel `gen_ai.usage.*` emission (DES canonical schema) + streaming cache-accounting parity | new `observability/tracing.py` | ~150 (110 + ~30 parity) | 0 |
| F5.1 | Existing-event audit (DES adoption prerequisite) | new `observability/schema.py` + audit script | ~30 | 0 |
| F6 (finishes) | Per-state cost attribution in loop CLI | extend `_helpers.py:1676` + extend `executor.py:1295` | ~40 | 0 |
| F7-lite | In-process model router + FrugalGPT cascade + `list_models()` protocol method | extend `host_runner.py` | ~250 (150 + ~50 cascade + ~30 calibrate + list_models) | 0 |
| F8 | Subagent handoff compaction + parent-prefix hoisting | new `subagents/handoff.py` | ~130 (100 + ~30 hoisting) | 0 |
| F10 | Speculative cache warming hook (+ `max_tokens=0` alt) | new `skills/speculative.py` | ~80 | 0 |

### Out of scope (deliberate deferrals)

- **Full LiteLLM sidecar (F7-full)** — only justified if per-key isolation across many providers becomes a real need. The in-process router (F7-lite) covers Anthropic-only; LiteLLM becomes a follow-on.
- **Phoenix / Langfuse sidecar (F5-full)** — we emit OTel-shaped attributes into `.ll/history.db` (the consumer is whatever UI we later build). External collectors are a configuration decision, not an implementation one.
- **LLMLingua proper (F4-full)** — gated behind `compression.heuristic_underperforms == true` in `.ll/ll-config.json`. Set by benchmark, not by default.
- **Live streaming token-budget tracker** (report line 412): Anthropic cookbook issue #676 still open; revisit when shipped.
- **Cross-model tool-call schema fidelity benchmark** (report line 409): no surveyed library has this; we don't need it for Anthropic-only routing.
- **Host primitives that don't exist yet.** The Gemini `cachedContent` analogue is filed as a child of EPIC-2178 (re-using this architecture, re-deriving the write-premium constant against Gemini's multiplier). omp's per-provider caching is tracked under EPIC-2258.

### Cross-host scope (each tier's applicability)

| Tier | Technique | Claude Code | Codex | OpenCode | omp (EPIC-2258) | Gemini (EPIC-2178) |
|------|-----------|-------------|-------|----------|----|----|
| 0 | P6 verbatim-output (text edit) | ✓ | ✓ | ✓ | ✓ once OmpRunner lands | ✓ once GeminiRunner lands |
| 0 | P1 edit-batch hook | ✓ | ✓ | ✓ | ✓ once OmpRunner lands | ✓ once GeminiRunner lands |
| 0 | P2 haiku pin (model in agent frontmatter) | ✓ Claude-side | port: Codex subagent `.toml` `model:` | port: analogous field | port: omp analogous field | port: Gemini agent TOML (post-impl) |
| 1 | measurement (cost telemetry into history.db) | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | prompt caching (`cache_control`) | ✓ Claude-only | — | — | per-provider; file under EPIC-2258 | **file as child of EPIC-2178** (use `cachedContent`) |
| 3 | eviction + heuristic compression + LogCleaner | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4 | F7-lite + FrugalGPT cascade | ✓ | ✓ after `list_models()` adapter | ✓ | ✓ (per-`(provider,model)` latency buffer) | ✓ |

**P2 haiku pin is per-adapter, not shared config** — ⚠️ do not duplicate the Claude pin speculatively; a wrong `model:` field could silently route a subagent to a flagship instead of haiku, inflating spend. Cost-vs-safety defaults to *defer* until each host's pin primitive is confirmed.

### Boundary: what already exists in the tree

Children must extend the in-flight partials rather than duplicate them:

- ~~**F2 partial**~~ — **cut 2026-07-10**, see FEAT-2476 Session Log. `pricing.py`'s `MODEL_PRICING`/`estimate_cost_usd()` and `cli/loop/_helpers.py:1676`'s cost table remain as-is (F6's foundation); no `--max-cost` accumulator/guard will be built on top of them.
- **F5 partial**: `fsm/executor.py` lines 1295–1305 aggregate `cache_read_tokens` / `cache_creation_tokens` per state. `subprocess_utils.py:50–51, 462–465` capture the same fields into a `UsageEvent`. **Missing**: emission under OTel `gen_ai.usage.*` attribute names.
- **F6 partial**: same `cli/loop/_helpers.py:1665–1690` prints a cost table by state. **Missing**: a stable JSON schema for downstream consumers and per-state budget warnings (`cost_ceiling_per_state`).
- **F7-lite prerequisite**: `list_models()` on the `HostRunner` protocol must land before F7-lite body work — every adapter (`ClaudeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`, future `GeminiRunner`) needs the method for the cascade to have a model inventory to dispatch over.

> **Anchor-drift note (audit, 2026-07-05):** the `fsm/executor.py:1295–1305` anchor cited above (and in early child captures) has drifted — that range is now the `_resolve_next_state()` interceptor hook. The actual per-action token/cache aggregation lives at `fsm/executor.py:1382–1393` inside `FSMExecutor._run_action()`, and `_helpers.py:1676` sits inside `_print_usage_summary()` (`_helpers.py:1652–1714`). Child issues ENH-2475 / FEAT-2476 / ENH-2477 / FEAT-2478 / ENH-2479 have each verified and recorded the corrected anchors in their research findings; trust those, not the ranges above. Also verified by child research: the data source today is run-local `<run_dir>/usage.jsonl`, not a `history.db` `usage_event` table (that table is proposed by ENH-2461, not yet implemented), and `cost_limits.*` keys do not yet exist in `.ll/ll-config.json` / `config-schema.json` (FEAT-2476 introduces them).

## Children

Tier 0 and Tier 1 children are filed (IDs below); Tier 2–4 entries remain **planned** placeholders (`[TBD-n]`) to be captured next.

### Tier 0 — behavioral quick-wins (ship first)

- **FEAT-2470** — Tier 0 roll-up — verbatim-output rule (P6), edit-batch hook (P1), LogCleaner anti-event filter, stop-sequence/prefill JSON output helpers (`output/parse.py`). *(filed 2026-07-03, P2; was [TBD-1])* — **done 2026-07-06**: all four techniques shipped with tests (`edit_batch_nudge` hook + Codex mirror, `output/parse.py`, `output_cleaner.py`, verbatim rule on 6 audit skills).
- **ENH-2499** — Stateful edit-batch nudge — follow-on to FEAT-2470's P1 hook: fires only after a run of ≥3 consecutive unbatched single edits instead of on every edit. *(filed 2026-07-05, P3; **done 2026-07-06**)*
- **ENH-2490** — P2 haiku pin + dense-list template + call budget on read-only audit agents — **extracted from FEAT-2470 and deferred** (2026-07-05): no quality gate + fragile cross-host safety story make it unfit for the strictly-dominant Tier 0 tranche. *(deferred, P3)*
- **ENH-2471** — Tier 0 verification trace set (locked traces for before/after measurement) + P1 hook regression test. *(filed 2026-07-03, P2; was [TBD-2])* — trace count relaxed from 3–5 to ≥2 confirmed-stable traces per `/ll:decide-issue` 2026-07-05 (Option A); the hook-regression-test half landed with FEAT-2470/ENH-2499 (`test_edit_batch_hook.py`), leaving trace-set lock + baseline capture as remaining scope.

### Tier 1 — measurement foundation

- **ENH-2475** — F5.1 existing-event audit (DES adoption prerequisite): classify every currently-emitted `history.db` event into a DES variant; port non-conforming shapes. *(filed 2026-07-04, P2; was [TBD-3])*
- ~~**FEAT-2476** — F2 `--max-cost` accumulator + 80%/100% guard + ELIS one-line forecast~~ *(filed 2026-07-04, P2; was [TBD-4]; split 2026-07-08 into FEAT-2548/2549/2550)* — **cancelled 2026-07-10** (cascaded to all three grandchildren): a spend cap is governance, not token-cost reduction — see FEAT-2476 Session Log.
- **ENH-2477** — F6 per-state cost attribution (finishes): stable JSON output with `cache_read`/`cache_creation` broken out, `cost_ceiling_per_state` / `cost_warn_at` loop-YAML schema, new `fsm/cost_graph.py`. *(filed 2026-07-04, P2; was [TBD-5])*
- **FEAT-2478** — F5 OTel `gen_ai.usage.*` emission: new `observability/tracing.py`, `gen_ai.invocation.id` UUID stamping, `gen_ai.provider.vendor` addendum, streaming-vs-blocking parity check. Depends on ENH-2475 (DES audit). *(filed 2026-07-04, P2; was [TBD-6])*
- **ENH-2479** — F5 streaming-vs-blocking cache-accounting parity trace set: 3 locked fixtures (static-prefix-stable turn 2+, cache-write-then-read across tool result, tool-result-only cache hit); gates 0.1% parity threshold in `test_streaming_cache_parity.py`. *(filed 2026-07-04, P2; was [TBD-7])*

### Tier 2 — caching (needs Tier 1 to verify hit rates)

- **FEAT-2671** — F1-prereq (a) — content-hash fragment store: SHA-256 over `(skill_body, system_prompt, tool_definitions)`, skip re-serialization when key stable (new `prompts/fragment_store.py`). Adapted from `BerriAI/litellm/litellm/caching/caching.py`. *(filed 2026-07-18, P2; was [TBD-8])*
- **FEAT-2672** — F1-prereq (b) — deferred tool loading: `defer_loading=True` + `tool_reference` pattern (new `tools/deferred.py`); preserves cache breakpoint across catalog churn. Vendor-measured: "cutting context usage by 90%+ while enabling applications that scale to thousands of tools." *(filed 2026-07-18, P2; was [TBD-9])*
- **FEAT-2673** — F1 — `cache_control: ephemeral` integration + cache-marking cost oracle: introduce `anthropic` SDK; `build_anthropic_request()` in `host_runner.py`; oracle refuses to mark blocks below the provider cacheable-prefix minimum. Carries Open Questions #1/#2/#5 (`decision_needed: true`). Depends on FEAT-2671; blocks FEAT-2672 (deferred-tool-loading has nothing to attach to until `build_anthropic_request()` exists — sequencing corrected 2026-07-18 via `/ll:decide-issue`). *(filed 2026-07-18, P2; was [TBD-10])*
- **FEAT-2674** — F10 — Speculative cache warming: `SkillStart` hook fires async warming request on `cache.warmable == true` and prompt >50K tokens; SDK-level `max_tokens=0` primitive as cheaper background-warm alternative. Depends on FEAT-2673. *(filed 2026-07-18, P2; was [TBD-11])*
- **FEAT-2679** — F1-prereq (c) — Tool-definition JSON schema catalog for the Anthropic Messages API: assembles full `{"name","description","input_schema"}` tool definitions little-loops currently has no code path for (only bare tool names flow through `--tools` CSV). Blocks FEAT-2672 (nothing to defer) and FEAT-2673 (`build_anthropic_request()` has no tool blocks to mark `cache_control` on). *(filed 2026-07-18, P2)*

### Tier 3 — compaction and compression

- **FEAT-2598** — F3 — Session-memory compaction (StreamingLLM eviction instant pass + 6-section semantic summarization): new `compaction/instant.py` + `compaction/result.py` (`CompactResult` typed wrapper over existing `summary_nodes`); soft threshold 7,500 tokens fires background summarizer; new `skills/ll-compact-session/SKILL.md` for manual trigger. Builds on existing LCM compaction surface (`session_store._compact_session_conn`, ENH-1954 cross-session condensation). *(filed 2026-07-11, P2; was [TBD-12])*
- **FEAT-2599** — F4-gated — Heuristic prompt compressor: new `compression/heuristic.py` invoked from `fsm/runners.py` for prompts ≥8K tokens; drops repeated tool results older than 5 turns, dedupes stable system blocks, tail-truncates assistant turns beyond N. **LLMLingua pip dep only enabled when `compression.heuristic_underperforms == true`** in `.ll/ll-config.json`. *(filed 2026-07-11, P2; was [TBD-13])*
- **[TBD-14]** F8 — Subagent handoff compaction + parent-prefix hoisting: import `compaction/instant.py` from `subagents/handoff.py` (new); at subagent spawn, summarize parent's context using the 6-section schema and inject as the child's `system` block. **Parent-prefix hoisting (~30 LOC, greenfield, no upstream impl):** hash the parent's static prefix and emit one shared `cache_control` breakpoint; per-child delta is the second breakpoint.
- **[TBD-15]** F8 — Handoff trace set (locked 5 `ll-parallel` handoff traces) — gates the 50–70% handoff shrink metric.

### Tier 4 — routing (last, data-driven)

- **[TBD-16]** F7-lite prerequisite — `list_models()` on the `HostRunner` protocol (return `{model, input_cost_per_mtok, output_cost_per_mtok, context_window}` per row); land **before** body work.
- **[TBD-17]** `routing.precedence` config-schema entry — explicit `--model` flag > loop YAML `model:` > per-state ceiling-overshoot downshift. Add to `config-schema.json` + `.ll/ll-config.json` `orchestration.routing.precedence` enum **before** body work.
- **[TBD-18]** F7-lite — In-process model router + FrugalGPT cascade skeleton + RouteLLM quantile-calibration helper (new `routing/calibrate.py` ported verbatim). Per-worker spend tracked via a minimal, file-local accumulator owned by F7-lite (not a shared `fsm/` module — that scope was cancelled with F2; see Integration Map). **Latency/score ring buffer keyed by `(provider, model)`, not global** — required for correctness with omp's 40+ providers.

### Transport & waste tranche (captured 2026-07-21 — levers outside the original five tiers)

- **FEAT-2710** — Message Batches API request path: flat 50% discount on batchable automation (`ll-auto`, verify loops, background summarization); rides FEAT-2673's SDK path. *(filed 2026-07-21, P2)*
- **FEAT-2711** — FSM session reuse for continuity-of-reasoning chains: opt-in `session_mode: continue` threading the existing `HostRunner` `resume` primitive through `fsm/runners.py`; narrowed to sequential chains where state N+1 needs state N's working context (prefix-cost lever moved to ENH-2714; step-0 viability gate before implementation). *(filed 2026-07-21, re-scoped 2026-07-20, P2→P3)*
- **ENH-2712** — Wasted-run token attribution: `ll-ctx-stats waste` view joining F5/F6 telemetry against terminal run outcome; may reorder remaining epic priorities. *(filed 2026-07-21, P2)*
- **ENH-2713** — Per-state `model:` pinning in loop YAML (haiku for verdict states): static precursor to F7-lite with MR-1 as the quality gate; loop-YAML half of deferred ENH-2490. *(filed 2026-07-21, P3)*
- **ENH-2714** — Automation-context static-prefix pruning for FSM invocations: broadened from catalog-only to the full static prefix (catalog narrowing + gated SessionStart/memory/digest hook output + host-flag CLAUDE.md suppression); supersedes FEAT-2711 as the default per-invocation savings lever. *(filed 2026-07-21, re-scoped 2026-07-20, P3→P2)*

### Cross-tier verification

- **[TBD-19]** Joint cache × router 2×2 ablation matrix (`scripts/little_loops/dev/measure_cache_routing_interaction.py`) — greenfield research output; verify on representative `ll-loop` traces.

### Related non-child work

- **ENH-2486** — FSM per-invocation prompt-size guard + bounding of re-embedded growing artifacts *(done 2026-07-06; `relates_to` this epic, parented elsewhere)* — occupies the same `fsm/runners` prompt-assembly leverage point F4-gated targets. The F4-gated child should build on its guard/threshold surface, not duplicate it (see ENH-2486 § cross-check against `history.compaction` budget).

## Integration Map

### Primary Files (per tier)

- **Tier 0**: ~6 `skills/*/SKILL.md` bodies (P6) + ~4 `agents/*.md` frontmatter (P2) + `hooks/hooks.json` + hook module (P1) + new anti-event filter module (~60 LOC) + new `scripts/little_loops/output/parse.py` (~30 LOC).
- **F6**: extend `scripts/little_loops/cli/loop/_helpers.py:1676` + new `scripts/little_loops/fsm/cost_graph.py` (~50 LOC) + extend `scripts/little_loops/fsm/schema.py` (`cost_ceiling_per_state`).
- **F5**: new `scripts/little_loops/observability/tracing.py` (~110 LOC + ~30 LOC streaming parity) + extend `scripts/little_loops/subprocess_utils.py:462` (UsageEvent UUID stamping) + extend `scripts/little_loops/history_reader.py` (`cost_attribution()` query, `GROUP BY gen_ai.invocation.id`).
- **F5.1**: new `scripts/little_loops/observability/schema.py` (DES discriminated-union payload + audit script).
- **F1**: `scripts/little_loops/host_runner.py` (new `build_anthropic_request()`, ~80 LOC) + cache-marking cost oracle (~50 LOC) + new `scripts/little_loops/prompts/fragment_store.py` (~40 LOC) + new `scripts/little_loops/tools/deferred.py` (~90 LOC) + `scripts/pyproject.toml` (add `anthropic` SDK).
- **F3**: new `scripts/little_loops/compaction/result.py` (~50 LOC `CompactResult` wrapper) + new `scripts/little_loops/compaction/instant.py` (~270 LOC) + new `skills/ll-compact-session/SKILL.md`.
- **F8**: new `scripts/little_loops/subagents/handoff.py` (~100 LOC incl. ~30 LOC parent-prefix hoisting) — imports F3; optional shared `scripts/little_loops/lib/hashing.py` with `fragment_store`.
- **F4-gated**: new `scripts/little_loops/compression/heuristic.py` (~150 LOC) + extend `scripts/little_loops/fsm/runners.py` (≥8K threshold hook).
- **F10**: new `scripts/little_loops/skills/speculative.py` (~80 LOC, incl. `max_tokens=0` alt) + extend `hooks/hooks.json` (SkillStart hook entry).
- **F7-lite**: extend `scripts/little_loops/host_runner.py` (routing table + `HostRunner.list_models()` + FrugalGPT cascade skeleton) + new `scripts/little_loops/routing/calibrate.py` (~30 LOC) + new file-local per-worker spend accumulator inside the F7-lite module (decided 2026-07-10: not a shared `fsm/` module — that scope belonged to the now-cancelled F2/`fsm/budget.py`; `fsm/cost_graph.py` (F6) is confirmed post-hoc/static with no live accumulation to build on) + extend `config-schema.json` + `.ll/ll-config.json`.

### Dependent Files (callers / importers to update)

- `scripts/little_loops/cli/ctx_stats.py` — read cost attribution via `history_reader.cost_attribution()`.
- `scripts/little_loops/cli/loop/_helpers.py` — surface per-state budget warnings.

### Tests

- `scripts/tests/test_edit_batch_hook.py` (new) — Tier 0 P1 edit-batch nudge regression.
- `scripts/tests/test_json_output_parse.py` (new) — Tier 0 `output/parse.py` extract/prefill helpers.
- `scripts/tests/test_routing_budget.py` (new) — F7-lite's local per-worker spend accumulator: guard + forecast error ≤15%.
- `scripts/tests/test_cli_cost_table.py` (new) — F6 schema + per-state warnings.
- `scripts/tests/test_otel_attributes.py` (new) — F5 attribute emission + DES schema accepts 100% of current events.
- `scripts/tests/test_streaming_cache_parity.py` (new) — F5 streaming-vs-blocking `cache_read_input_tokens` match within 0.1%.
- `scripts/tests/test_fragment_store.py` (new) — F1 prereq SHA-256 stability / hit rate.
- `scripts/tests/test_deferred_tools.py` (new) — F1 prereq: cache breakpoint survives 5-skill catalog churn.
- `scripts/tests/test_cache_control.py` (new) — F1 SDK code path + oracle never logs a 1.25× write on unreused block.
- `scripts/tests/test_compaction.py` (new) — F3 eviction preserves system/CLAUDE.md blocks + 6-section schema, soft/hard thresholds.
- `scripts/tests/test_subagent_handoff.py` (new) — F8 reuse of F3 + parent-prefix hoisting preserves cache breakpoint.
- `scripts/tests/test_heuristic_compression.py` (new) — F4-gated heuristic on representative traces.
- `scripts/tests/test_speculative_warming.py` (new) — F10 cache hit verification (+ `max_tokens=0` path).
- `scripts/tests/test_routing_calibrate.py` (new) — F7-lite quantile calibration + `list_models()` inventory per host adapter.

### Documentation

- `docs/ARCHITECTURE.md` — add "Token cost layer" section after "History DB as context layer"; document `routing.precedence` rule (`--model` > loop YAML `model:` > per-state ceiling downshift).
- `docs/reference/API.md` — document `compaction/instant.py`, `observability/tracing.py`, `observability/schema.py` (DES), `prompts/fragment_store.py`, `tools/deferred.py`, `routing/calibrate.py`, F7-lite's local per-worker spend accumulator, `output/parse.py`, `host_runner.build_anthropic_request()` + `HostRunner.list_models()`.
- `config-schema.json` — add `orchestration.routing.precedence` enum + default (config-schema-level, before F7-lite body work).
- `.ll/ll-config.json` — add `cost_limits.*`, `compression.*`, `orchestration.routing.*` (incl. `precedence`), `cache.*` namespaces.

## Implementation Order

The dependency spine:

```
Tier 0  P6 → P2 → P1 → LogCleaner → JSON helpers (output/parse.py)   [independent; ship first]
F5.1 (existing-event audit)          [must precede F5's DES adoption]
F6  (per-state cost attribution)     [no deps; finishes existing cost table]
F5  (OTel/DES emission + streaming parity)   [no deps; wraps existing UsageEvent]
  └─ fragment_store + defer_loading  [F1 cache-stability prerequisites; must precede F1 enable]
       └─ F1  (cache_control + cache-marking oracle)  [adds anthropic SDK; first network-side change]
            └─ F10  (speculative warming / max_tokens=0)  [depends on F1 — meaningless without the primitive]
  └─ F3  (eviction + 6-section compaction)   [extends history.compaction; no new deps]
       └─ F8  (subagent handoff + parent-prefix hoisting)  [imports F3's compaction/instant.py]
  └─ F4-gated  (heuristic compressor)  [no deps; LLMLingua is opt-in via config flag]
list_models() on HostRunner → routing.precedence config → calibrate.py
  └─ F7-lite  (in-process routing + FrugalGPT cascade)  [F2 cut 2026-07-10 — per-worker budget now a local accumulator owned by F7-lite; orthogonal to caching + compression]
```

**Parallel-execution caveat:** Tiers 2 and 3 are work-stream-independent once foundation lands, but both touch `host_runner.py` and `fsm/` — parallel work is only safe in separate worktrees with a careful integration merge; default to sequential unless two reviewers are available.

## Impact

- **Priority**: **P2** — high-leverage but not blocking; savings compound across every loop run, but no current production user is blocked on absence.
- **Effort**: Medium per child (~100 LOC + tests each), Large aggregate (**~1,390 LOC** — Tier 0 ~180 + F-layer ~1,210 — plus tests). Distributed across ~8 children + Tier 0 (F2 cut 2026-07-10).
- **Risk**: **Low** for replication features (heuristic compressor + 6-section compaction are well-trodden patterns); **Medium** for F1 (first SDK integration; introduces a new network code path alongside the CLI shell path); **Low** for F7-lite (extends an already-typed Protocol); parent-prefix hoisting is greenfield (no upstream) but small and gated behind the F5 parity test.
- **Breaking Change**: **No** — every feature is additive; default behaviors unchanged. Existing loops run exactly as before unless they opt in via new config keys.

## Success Metrics

- **Tier 0**: before/after cost delta on a locked 3–5 trace set (measured via host CLI `usage` block, since Tier 1 telemetry isn't online yet) plus a P1-hook regression test; JSON output helpers deliver 20–40% output-token reduction on FSM verdict strings.
- **F1**: `cache_read_input_tokens` populated for >50% of FSM iterations in `general-task` runs; cache-marking oracle **never logs a 1.25× write on a block that wasn't reused within K subsequent calls**; fragment_store hit rate ≥80% across the locked Tier 0 trace set; deferred tool loading preserves the cache breakpoint across a 5-skill catalog churn (regression test).
- **F3**: Compaction triggers at the configured soft threshold (default 7,500 tokens); eviction preserves system/CLAUDE.md blocks (regression test); eviction+heuristic combo reduces context size to the **50–70% range** on the locked trace set (the 88% cookbook figure is the semantic-summarization upper bound, reserved for a future upgrade) without measurable quality regression on a held-out eval set.
- **F6**: Cost table in `ll-loop run` output breaks out `cache_read` / `cache_creation` and is stable across versions (lock the JSON schema in tests).
- **F5**: `gen_ai.usage.*` attributes parse cleanly under `phoenix serve` (verify in CI via a fixture run; Phoenix install is optional); DES schema accepts 100% of currently-emitted events (F5.1 audit gate). Per-CLI-invocation `gen_ai.invocation.id` UUID unique across all FSM iterations; `GROUP BY gen_ai.invocation.id` rollup returns one row per invocation with token sums matching raw `result`-event `usage` totals. Streaming parity: `cache_read_input_tokens` matches between `client.messages.create()` and `client.messages.stream()` within 0.1%.
- **F7-lite**: On a locked 5-loop trace set, the cascade dispatches the same model the baseline does on ≥80% of states (no quality regression) while shifting ≥30% of remaining states to a cheaper model; F7-lite's own local per-worker accumulator (not F2, which was cancelled) halts at 80% (warning) and 100% (hard stop) on `ll-parallel` runs of ≥2 workers; `list_models()` returns the expected inventory on every host adapter.
- **F8**: Subagent handoff context shrinks to the **50–70% range** on the locked 5-trace `ll-parallel` handoff set (gate flips below 30%; the earlier ≥70% point estimate was unverified) with the cache breakpoint preserved (parent-prefix hoisting regression test).
- **F10**: Cache hit rate on warmed long-running skills >80% (vs. ~0% without warming) on prompts >50K tokens.
- **F4-gated**: Heuristic compressor hits the **3–6× range** on the locked 10-trace `general-task` set; gate flips to LLMLingua below 0.5× LLMLingua's measured ratio.

## Open Questions for Refinement

Tracking the questions raised in the plan files that need resolution before filing individual children:

1. **`anthropic` SDK version pin + CI-free install verification** — F1 requires it; need a baseline test that proves SDK install + `cache_control` works in CI before the EPIC can ship F1.
2. **`cache_control` on the CLI shell path** — F1 only fits the SDK code path. Decision: add the SDK code path as an opt-in (`orchestration.request_path == "sdk"`); default remains CLI shell to preserve existing behavior.
3. **F4 benchmark definition** — lock a 10-trace `general-task` set; heuristic target 3–6× prompt-token reduction; gate flips below 0.5× LLMLingua ratio.
4. **F7-lite routing table** — confirm the decision signal: (a) explicit `--model` flag, (b) loop YAML `model:` field, (c) `cost_ceiling_per_state` overshoot downshift. Land `routing.precedence` in `config-schema.json` + `.ll/ll-config.json` before body work.
5. **Cache-marking oracle threshold** — what reuse frequency justifies the 1.25× write premium? Derive from Li 2025 cost model against real `history.db` reuse distributions before defaulting. **Concrete base layer:** below the provider's cacheable-prefix minimum (Anthropic 1024 Sonnet / 4096 Opus — confirm current) the oracle marks nothing.
6. **Locked trace sets** — nail down owners and members of: Tier 0 3–5 trace set; F4 10-trace `general-task` set; F8 5-trace `ll-parallel` handoff set; streaming-parity 3-trace set; cache × router 2×2 ablation set. Without stable sets every "win" is a moving target.
7. **Joint cache × router 2×2 ablation matrix** — greenfield (`scripts/little_loops/dev/measure_cache_routing_interaction.py`). Decide the trace set + cost metric before F1 ships.
8. **Parent-prefix hoisting design** — greenfield (no upstream impl). Lock the hash algorithm (share SHA-256 with `fragment_store` via `lib/hashing.py`, or accept + document duplication), the "static prefix" boundary detection, the breakpoint count.
9. **ELIS residual threshold** — ≤15% forecast error specified; consider tighter (≤10%) given how cheap the regression is to retrain.

## Related Key Documentation

| Document | Relevance | Notes |
|---|---|---|
| [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md) | **High** — will be updated with the new "Token cost layer" section; documents the `routing.precedence` rule | Integration Map calls for "Token cost layer" section after "History DB as context layer". |
| [docs/reference/API.md](../../../docs/reference/API.md) | **High** — will document new modules: `compaction/instant.py`, `observability/tracing.py`, `observability/schema.py`, `prompts/fragment_store.py`, `tools/deferred.py`, `routing/calibrate.py`, F7-lite's local per-worker spend accumulator, `output/parse.py`, `host_runner.build_anthropic_request()` + `HostRunner.list_models()`. | Per Integration Map documentation list. |

## Labels

`architecture`, `token-cost`, `fsm`, `observability`, `budgeting`, `caching`, `compression`, `routing`, `epic`, `captured`, `replication-not-integration`

## Status

**Open** | Created: 2026-07-02 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-21 - Filed the transport & waste tranche from a "higher-value levers we haven't considered" review: **FEAT-2710** (Message Batches API request path, 50% discount), **FEAT-2711** (FSM session reuse via existing `resume` primitive), **ENH-2712** (wasted-run token attribution view), **ENH-2713** (per-state model pinning in loop YAML), **ENH-2714** (FSM invocation catalog pruning). All parented here and added to `relates_to`; new Children subsection added between Tier 4 and Cross-tier verification.
- `/ll:decide-issue` - 2026-07-18T19:14:18 - `4fd1c868-e4bb-4ba3-ab7e-80d1d257cbcd.jsonl`
- `/ll:capture-issue` - 2026-07-18 - Filed the Tier 2 caching tranche: **FEAT-2671** (F1-prereq a, was [TBD-8]), **FEAT-2672** (F1-prereq b, was [TBD-9]), **FEAT-2673** (F1, was [TBD-10]; `decision_needed: true` for Open Questions #1/#2/#5), **FEAT-2674** (F10, was [TBD-11]; depends on FEAT-2673). Replaced the four TBD placeholders in Children and added all four to `relates_to`. Reminder recorded in FEAT-2673: decide [TBD-19] (cache x router ablation set, OQ #7) before F1 ships.
- `/ll:capture-issue` - 2026-07-11 - Filed **FEAT-2598** (F3, was [TBD-12]) and **FEAT-2599** (F4-gated, was [TBD-13]) from the Tier 3 section of both plan docs. Replaced the two TBD placeholder bullets in Children with real child references; added both to `relates_to`.
- epic-review - 2026-07-10 - **F7-lite budget re-scoping resolved**: chose option (a) — F7-lite owns a minimal, file-local per-worker spend accumulator (not a shared `fsm/` module) — over dropping the guard and relying on `ll-parallel --workers`. Researched first: `fsm/cost_graph.py` (F6) confirmed purely post-hoc (reads completed run artifacts only, no live accumulation, and its own scope explicitly excludes "cost ceiling guard"); F5 emits per-invocation OTel telemetry only; `ll-parallel --workers` is a pure concurrency cap with no dollar/token tracking, so it can't catch a single runaway worker. Updated Integration Map, Implementation Order diagram, Tests list, and Success Metrics to reflect the local-accumulator plan; renamed the planned test file `test_fsm_budget.py` → `test_routing_budget.py`.
- epic-review - 2026-07-10 - **F2 cut** (per user request, not deferred): FEAT-2476 and its three grandchildren (FEAT-2548/2549/2550) cancelled — a spend cap/circuit-breaker is cost *governance*, not *reduction* (it halts a run at a $ ceiling; it doesn't lower tokens/$ spent per unit of work, unlike F1/F3/F4/F7-lite). Removed F2 from Goal, Scope table, Boundary section, Children, Integration Map, Implementation Order, Success Metrics, and effort totals (~1,550 → ~1,390 LOC, 9 → 8 F-feature children). Flagged one follow-up: F7-lite's per-worker spend tracking was slated to reuse `fsm/budget.py`; that dependency needs re-scoping (either a minimal local accumulator or drop the per-worker guard) before F7-lite body work starts.

- epic-audit - 2026-07-06 (second pass) - Child cross-check: fixed FEAT-2478's mislabel of the `anthropic`-SDK prerequisite as "F1 (FEAT-2476)" (F1 is unfiled [TBD-10]; FEAT-2476 is F2, no pip deps); corrected FEAT-2476's stale "`.ll/ll-config.json` already documents `cost_limits.*`" Integration-Map line + stale executor anchor in Files to Modify; added reciprocal `relates_to` links (ENH-2461 ↔ FEAT-2476/ENH-2477/FEAT-2478); struck two stale ENH-2471 research notes (exit-code-0 nudge contract — shipped behavior is `exit_code=2` threshold-gated; haiku pin attributed to FEAT-2470 — moved to ENH-2490). Verified on disk: FEAT-2470/ENH-2499 artifacts all present; ENH-2471's `tier0_traces/` fixtures + `docs/observability/` not yet created (consistent with its open status). Statuses, parents, and blocks/depends_on pairs (ENH-2475→FEAT-2478, ENH-2479→FEAT-2478) all consistent.
- epic-audit - 2026-07-06 - Audit pass: added ENH-2486/ENH-2490/ENH-2499 to `relates_to`; recorded FEAT-2470 + ENH-2499 as done in Children; added ENH-2499 entry (stateful edit-batch nudge follow-on) and "Related non-child work" note for ENH-2486; noted ENH-2471 trace-count relaxation (3–5 → ≥2, decided 2026-07-05) and that its hook-regression-test half shipped with FEAT-2470; updated Children intro (Tier 0–1 filed, Tier 2–4 TBD).
- epic-audit - 2026-07-05 - Children section restructured: filed Tier 1 children (ENH-2475, FEAT-2476, ENH-2477, FEAT-2478, ENH-2479) moved from the Tier 0 list into the Tier 1 section, replacing the duplicate [TBD-3]–[TBD-7] placeholders. Added FEAT-2470/ENH-2471 to `relates_to` for consistency. Added anchor-drift note (executor.py 1295→1382–1393; usage.jsonl vs usage_event table; cost_limits.* keys not yet present).
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - initial EPIC capture from `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` + `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` (prioritization layer). Filing resolves Open Question #6 in both plan files. Captured ID `EPIC-2456` (next unique). Aggregate footprint ~1,550 LOC, 1 pip dep (`anthropic`), 0 sidecars.
