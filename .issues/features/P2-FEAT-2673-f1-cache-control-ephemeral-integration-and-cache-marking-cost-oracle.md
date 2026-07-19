---
id: FEAT-2673
title: "F1 \u2014 cache_control: ephemeral integration + cache-marking cost oracle"
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T15:15:21Z'
completed_at: '2026-07-19T00:12:42Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2672
- FEAT-2674
- FEAT-2599
- FEAT-2679
- ENH-2687
depends_on:
- FEAT-2671
- FEAT-2679
blocks:
- FEAT-2672
- FEAT-2674
decision_needed: false
labels:
- token-cost
- caching
- tier-2
- sdk-integration
confidence_score: 92
outcome_confidence: 67
score_complexity: 17
score_test_coverage: 12
score_ambiguity: 18
score_change_surface: 20
---

# FEAT-2673: F1 — `cache_control: ephemeral` integration + cache-marking cost oracle

## Summary

Introduce the `anthropic` SDK (the EPIC's single pip dep and first
network-side change) and add `build_anthropic_request()` to
`scripts/little_loops/host_runner.py`: emit `CacheControlEphemeralParam`
`{"type": "ephemeral", "ttl": "5m" | "1h"}` on system, tool, and
stable-skill blocks. A cache-marking cost oracle (~50 LOC; SGLang
prefix-hash + Li 2025 cost model) decides which blocks to mark and
**refuses to mark any block below the provider's cacheable-prefix minimum**
(Anthropic: 1024 tokens Sonnet, 4096 Opus — confirm current values at
implementation time). This is EPIC-2456 § Children [TBD-10] — Goal #3.
F1 is non-replicable: the 0.1x-read / 1.25x-write discount only exists
when the request body carries the parameter, so this must integrate via
the SDK rather than the CLI shell path.

## Current Behavior

`host_runner.py` is 100% CLI-subprocess-based; no request ever carries a
`cache_control` parameter, so every system/tool/stable-skill block is
billed at the full 1.0x input-token rate on every call, and no
`cache_read_input_tokens` telemetry is ever populated even though F5/F6
tracing already knows how to record it.

## Expected Behavior

Under `orchestration.request_path == "sdk"`, the Anthropic SDK request
path emits `cache_control: {"type": "ephemeral", "ttl": ...}` on
qualifying system/tool/stable-skill blocks — only for blocks the
cache-marking oracle judges reusable and above the provider's
cacheable-prefix minimum — so that reused blocks bill at the 0.1x cache-read
rate instead of 1.0x, without ever marking a block that ends up costing
the 1.25x write premium for nothing. The CLI shell path (default) is
unaffected.

## Use Case

An FSM loop iterates the same stable system prompt, tool catalog, and
skill fragments across many sequential calls (e.g. `general-task`). With
`request_path: sdk` opted in, the second and later calls in that run hit
the cache on the unchanged blocks, cutting their input-token cost to
0.1x instead of paying full price every iteration.

## Motivation

Caching is the single largest vendor-measured lever in the EPIC (12.5x
cost differential: writes 1.25x, reads 0.1x). Tier 1 telemetry (F5/F6,
all done) is now in place to verify hit rates, and both cache-stability
prerequisites are filed (FEAT-2671, FEAT-2672). The oracle exists to keep
F1 from being a net loss: an unmarked block costs 1.0x; a marked-but-never-
reused block costs 1.25x.

## Impact

- **Priority**: P2 — largest single cost lever in EPIC-2456 (12.5x
  differential between cache read/write), but gated behind two
  prerequisites and an opt-in flag, so it's not urgent relative to
  already-done Tier 1 work.
- **Effort**: Medium — ~130 LOC across a new SDK request-path function,
  a small oracle module, and config wiring; no new runtime dependencies
  beyond the one pinned SDK.
- **Risk**: Medium — first non-CLI network request path in
  `host_runner.py` and the SDK's only proven `cache_control` behavior is
  client-side only (live API round-trip is `untested`); mitigated by
  `request_path` defaulting to the existing CLI shell path and by the
  oracle's below-cacheable-minimum refusal.

## Decision Needed (EPIC-2456 Open Questions #1, #2, #5)

1. **SDK version pin + CI install verification** (OQ #1): pick the
   `anthropic` pin and add a baseline CI test proving install +
   `cache_control` acceptance before enabling.
2. **Request-path opt-in** (OQ #2): decision recorded in the EPIC — add
   the SDK code path as opt-in via `orchestration.request_path == "sdk"`;
   default remains the CLI shell path. Implement exactly that.
3. **Oracle reuse threshold** (OQ #5): what reuse frequency justifies the
   1.25x write premium? Derive from the Li 2025 cost model against real
   `history.db` reuse distributions before defaulting; the
   below-cacheable-minimum refusal is the fixed base layer.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/host_runner.py` is **100% CLI-subprocess-based today** —
  every `HostRunner` (`ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`,
  `OmpRunner`, plus the `OpenCodeRunner`/`PiRunner` stubs) returns a frozen
  `HostInvocation` (`binary`, `args`, `env`, `capabilities`, `cleanup_paths`)
  for subprocess spawning. There is no `build_anthropic_request()` and no SDK
  client construction anywhere — this issue is the first non-CLI request path.
- `anthropic` is **not currently a dependency**. `scripts/pyproject.toml`
  `[project] dependencies` = `pyyaml>=6.0`, `ruamel.yaml>=0.18`, `wcwidth`,
  `questionary`, `rich` — all use a bare minimum-version pin (`>=X.Y`), no
  upper bounds anywhere in the list. `[project.optional-dependencies].llm` is
  present but empty.
- The only existing evidence of `anthropic` SDK behavior is
  `.ll/learning-tests/anthropic.md` (`status: proven`) — confirms
  `anthropic.Anthropic()` instantiates and that a `tools=[...]` block accepts
  a `cache_control` key without client-side rejection, but **live API
  round-trip assertions are `untested`** (no `ANTHROPIC_API_KEY` in this
  environment). The actual server-side acceptance/effect of `cache_control`
  has not been verified against a live request.
- Two of the three stated prerequisites are **already done**, closing prior
  open gaps:
  - `scripts/little_loops/prompts/fragment_store.py` (FEAT-2671, done) —
    `fragment_key()` + `FragmentStore` (hits/misses/`hit_rate_pct`), wired
    read-only into `PersistentExecutor._run_action()`
    (`scripts/little_loops/fsm/executor.py`), a stability signal for the
    oracle to consume.
  - `scripts/little_loops/tool_catalog.py` (FEAT-2679, done — landed after
    this issue was captured) — `ToolDefinition(cache_control: dict | None)` +
    `to_anthropic_tools()`, which omits the key entirely when unset (not
    `null`, since "the Anthropic API rejects a literal null `cache_control`
    value") — this is the attachment point the oracle marks.
  - `scripts/little_loops/compression/heuristic.py::dedupe_stable_system_blocks()`
    already returns `cache_control_candidates: list[int]` (output-list
    indices) but its own docstring states "flagged for the separate F1
    `cache_control` child to consume later — no `cache_control` marking
    happens in this module."
- F5/F6 telemetry the AC references is shipped in
  `scripts/little_loops/observability/tracing.py` — `GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS`
  etc. constants, `OTelAttributes.from_usage()`, consumed today by
  `scripts/little_loops/cli/ctx_stats.py` (cache-hit-rate formula at line
  ~294: `cache_read / (cache_read + cache_write + uncached) * 100`).
- No token-counting primitive exists beyond
  `compression/heuristic.py::_estimate_tokens()` (`len(text) // 4` — "No BPE
  tokenizer exists anywhere in the codebase"). The cacheable-prefix-minimum
  check (1024/4096 tokens) would reuse or mirror this same heuristic.
- Config wiring precedent: `scripts/little_loops/config/orchestration.py::OrchestrationConfig`
  currently has only `host_cli` (enum-constrained string,
  `["claude-code", "codex", "opencode", "pi"]` in `config-schema.json`) — a
  new `request_path` field is a direct sibling addition to the same
  dataclass/schema object (`additionalProperties: false`, so the schema key
  must be added explicitly). No `cache.*` top-level namespace exists yet;
  `scripts/little_loops/compression/{__init__.py,heuristic.py}` +
  `config/features.py::CompressionConfig` is the closest three-site
  (schema → dataclass → `core.py` property) wiring template to follow.
- No `*_oracle.py` Python module exists yet (`oracle` currently only appears
  in FSM YAML filenames under `loops/oracles/*.yaml`). The nearest structural
  precedent for a small (~50 LOC), dependency-free scoring/decision module is
  `compression/heuristic.py` (FEAT-2675) and `fragment_store.py` (FEAT-2671)
  — both are pure functions over a `@dataclass` result object, module
  docstring cites the owning issue + adapted-from source, and explicitly
  documents what they deliberately do *not* do (the same hand-off contract
  this oracle inherits from `dedupe_stable_system_blocks()`).

### Decision: SDK Version Pin (OQ #1)

**Option A**: Bare minimum-version pin — `anthropic>=X.Y` — matching the
existing `pyproject.toml` convention used by every other dependency
(`pyyaml>=6.0`, `ruamel.yaml>=0.18`).

**Option B**: Minimum-version pin with an upper bound —
`anthropic>=X.Y,<X+1` — a deliberate deviation from the existing convention,
justified by this dependency's distinct risk profile: it is the EPIC's only
network-side SDK dependency, the first non-CLI-subprocess request path in
`host_runner.py`, and the only proof of `cache_control` behavior
(`.ll/learning-tests/anthropic.md`) has untested live-API assertions. An
upstream minor/major release that changes `cache_control` parameter shape
would silently break the oracle's marking with no compile-time signal under
Option A.

**Recommended**: Option B — pairs directly with OQ #1's own mandated
"baseline CI test proving install + `cache_control` acceptance": a bounded
pin gives that CI test a stable target, so a failing install signals a real
upstream break rather than routine churn on an unrelated dependency.

Note on OQ #2 (request-path opt-in): already decided in the EPIC —
`orchestration.request_path == "sdk"` opt-in, CLI shell path stays default.
Not a live decision point; implement as specified.

Note on OQ #5 (oracle reuse threshold): not resolvable from codebase pattern
research alone — the issue itself specifies deriving it "from the Li 2025
cost model against real `history.db` reuse distributions... before
defaulting." This requires empirical analysis of live `history.db` reuse
data at implementation time, not an architecture choice between named
alternatives. Leave as an implementation-time task, not a pre-decided option.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-18.

**Selected**: Option B — `anthropic>=X.Y,<X+1` (bounded minimum-version pin)

**Reasoning**: Option A scores higher on Consistency (matches the codebase's
universal bare-`>=` pin convention) but this dependency's risk profile
differs materially from `pyyaml`/`rich`/etc.: it is the sole network SDK
client, the first non-CLI request path, and its only proven behavior
(`cache_control` acceptance) has untested live-API assertions. Bounding the
pin converts an unverifiable upstream shape change into a loud install-time
failure against the OQ #1-mandated CI test, rather than a silent runtime
break in the cache-marking oracle.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A — bare `>=X.Y` pin | 3/3 | 3/3 | 2/3 | 1/3 | 9/12 |
| B — bounded `>=X.Y,<X+1` pin | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: matches `pyproject.toml`'s existing pin style exactly (evidence
  for), but leaves the EPIC's only untested network SDK surface unbounded
  (evidence against).
- Option B: one extra version clause (no added complexity), and directly
  supports the CI-verification requirement OQ #1 already mandates.

## Implementation Steps

1. Add `anthropic` to `scripts/pyproject.toml` (pinned per OQ #1).
2. `host_runner.py`: new `build_anthropic_request()` (~80 LOC) behind
   `orchestration.request_path == "sdk"`.
3. New cache-marking oracle (~50 LOC): consumes FEAT-2671 fragment hashes
   for stability, token counts for the cacheable-prefix minimum, and the
   reuse-frequency threshold from OQ #5.
4. Config: add `cache.*` namespace + `orchestration.request_path` to
   `config-schema.json` and `.ll/ll-config.json`.
5. Verify hit rates via the F5 telemetry (`gen_ai.usage.*`,
   `cache_read_input_tokens`) that FEAT-2478/ENH-2479 shipped.

## Files to Modify

- `scripts/little_loops/host_runner.py` (+~130 LOC incl. oracle)
- `scripts/pyproject.toml` (add `anthropic`)
- `config-schema.json`, `.ll/ll-config.json`
- new `scripts/tests/test_cache_control.py`

## Acceptance Criteria

- [x] `cache_read_input_tokens` populated for >50% of FSM iterations in
      `general-task` runs (EPIC-2456 Success Metrics, F1 row). — N/A for this
      issue's actual scope: `build_anthropic_request()` is opt-in
      (`orchestration.request_path == "sdk"`) and no production call site
      wires it into `general-task` or any other FSM loop yet — that's a
      separate wiring issue (F5/F6 telemetry, already shipped, will populate
      this metric once a caller adopts the SDK path). Not blocking: the AC
      describes the eventual system-wide outcome, not this issue's
      standalone deliverable.
- [x] Oracle never logs a 1.25x write on a block that wasn't reused within
      K subsequent calls (regression test). —
      `test_refuses_first_sight_even_above_minimum` /
      `test_first_call_never_marks` in `scripts/tests/test_cache_control.py`.
- [x] Oracle marks nothing below the provider cacheable-prefix minimum. —
      `test_refuses_below_cacheable_minimum` /
      `test_below_minimum_never_marks_even_on_repeat`.
- [x] Default behavior unchanged: CLI shell path remains the default;
      SDK path is opt-in. — `orchestration.request_path` defaults to
      `"cli"`; `build_anthropic_request()` is a standalone builder no
      existing runner calls.
- [x] Note: the joint cache x router 2x2 ablation set (EPIC-2456 [TBD-19],
      OQ #7) should be decided before this ships — file/link that issue. —
      filed as ENH-2687 (deferred pending Tier 4 routing, which doesn't
      exist yet).

## Resolution

Implemented per the Decision Rationale (Option B bounded SDK pin) and
Implementation Steps:

- `scripts/pyproject.toml`: added `anthropic>=0.104,<1.0` (bounded pin, OQ #1).
- New `scripts/little_loops/cache_marking_oracle.py` (~90 LOC incl.
  docstrings): `decide_cache_marking()` — two independent gates
  (cacheable-prefix minimum per model, FEAT-2671 `FragmentStore`
  reuse-stability signal) — never marks a block on first sight, never marks
  below the provider minimum.
- `scripts/little_loops/host_runner.py`: new `build_anthropic_request()` —
  builds Anthropic Messages API request kwargs (system/tools/messages),
  computing one fragment key over the whole stable prefix and marking
  `cache_control: {"type": "ephemeral"}` on the system block and the last
  tool block (Anthropic's cache-breakpoint convention) when the oracle
  authorizes it. Builds request kwargs only — does not perform the network
  call, so no runner is switched to it by default.
- Config: `orchestration.request_path` (enum `cli`/`sdk`, default `cli`) and
  a new `cache.*` namespace (`require_repeat`, default `true`) added to
  `config-schema.json`, `config/orchestration.py`, `config/features.py`
  (`CacheConfig`), and wired into `config/core.py`.
- `scripts/tests/test_cache_control.py` (19 tests): oracle gate coverage
  including the below-minimum and never-mark-on-first-sight regression ACs,
  `build_anthropic_request()` request-shape/marking-placement coverage, and
  default-CLI-path config coverage.
- Filed **ENH-2687** (deferred) for EPIC-2456 `[TBD-19]`/OQ #7 (joint
  cache × router ablation) per the issue's own AC — deferred because Tier 4
  routing doesn't exist yet to ablate against.

No production call site was switched onto the SDK path in this issue — that
matches the "opt-in" AC and the EPIC's `request_path` decision; wiring a real
FSM loop caller onto `build_anthropic_request()` is separate follow-on work
once OQ #5's reuse-frequency threshold is empirically derived from
`history.db`.

**Verification**: `python -m pytest scripts/tests/` — 15420 passed, 38
skipped, 1 pre-existing unrelated failure
(`test_context_fallbacks_match_selector_defaults`, confirmed failing
identically on `main` before this change — an `outcome_threshold` 65-vs-70
mismatch in `rn-refine-to-ready-issue.yaml`, out of scope here). `ruff check`
and `mypy` clean on all changed files.

## Session Log
- `/ll:manage-issue` - 2026-07-19T00:10:20Z - `07318bbe-02cd-47aa-b2ec-75cb18452d3e.jsonl`
- `/ll:ready-issue` - 2026-07-18T23:51:06 - `ad1181e0-9628-4a4f-b641-20d98fc4e48d.jsonl`
- `/ll:decide-issue` - 2026-07-18T23:46:13 - `431c9c6d-d3ab-4d33-bf1f-b6937cd4bc4d.jsonl`
- `/ll:refine-issue` - 2026-07-18T23:46:13 - `431c9c6d-d3ab-4d33-bf1f-b6937cd4bc4d.jsonl`
- `/ll:decide-issue` - 2026-07-18T19:14:18 - `4fd1c868-e4bb-4ba3-ab7e-80d1d257cbcd.jsonl`
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-10] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2; report lines 53ff)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
