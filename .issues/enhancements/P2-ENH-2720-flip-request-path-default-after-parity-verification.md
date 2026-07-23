---
id: ENH-2720
type: ENH
title: "Default-flip tranche: orchestration.request_path cli \u2192 sdk/batch after\
  \ parity verification"
priority: P2
status: done
size: Very Large
captured_at: '2026-07-21T17:22:20Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
depends_on:
- ENH-2719
labels:
- token-cost
- caching
- configuration
relates_to:
- EPIC-2456
- ENH-2719
- FEAT-2673
- FEAT-2674
- FEAT-2710
- FEAT-2716
decision_needed: false
confidence_score: 80
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-07-22T19:03:50Z'
---

# ENH-2720: Default-flip tranche — orchestration.request_path cli → sdk/batch after parity verification

## Summary

Most of EPIC-2456's shipped savings are dormant behind opt-in config: `orchestration.request_path` defaults to `"cli"` (`config-schema.json`), and the cache-marking oracle (FEAT-2673), deferred tool loading (FEAT-2672), tool catalog (FEAT-2679/2680), speculative warming (FEAT-2674), and Message Batches (FEAT-2710/2716) are all only consulted under `"sdk"` or `"batch"`. Flip the default to `"sdk"` — and set `"batch"` per-loop where latency-insensitive — once ENH-2719's measurement runs demonstrate CLI/SDK parity and realized savings. This converts already-written code into realized $/run reduction; it is likely the cheapest remaining lever in the epic.

## Motivation

The 0.1×-read prompt-caching discount and the flat 50% Batches discount only apply on requests that actually travel the SDK/Batches path. With the default at `"cli"`, every `ll-loop`/`ll-auto`/`ll-sprint` invocation on an unconfigured project gets none of it. A default flip is a one-line schema/config change whose entire cost is the verification discipline — which ENH-2719 provides.

## Current Behavior

- `config-schema.json` `orchestration.request_path`: enum `["cli", "sdk", "batch"]`, `default: "cli"`. The schema's own descriptions note the CLI shell path "never carries a cache_control parameter" and "never serializes a tool-definition catalog at all."
- `.ll/ll-config.json` in this repo does not set `orchestration.request_path`, so even the source project runs dormant.
- Compression (FEAT-2675) is **already default-on** (executor wired from `BRConfig.compression` in `cli/loop/run.py`, trigger-gated at `trigger_pct=0.4`) — explicitly out of scope here; no flip needed.

## Expected Behavior

- `orchestration.request_path` defaults to `"sdk"` in `config-schema.json` (and any generated-config template), with `"cli"` remaining a supported explicit opt-out and the automatic fallback when the `anthropic` SDK import or API-key resolution fails — the flip must never hard-break a host that only has the CLI.
- Latency-insensitive automation surfaces (e.g. verify loops, background summarization states — candidates identified in FEAT-2710) get documented `"batch"` opt-in defaults, per-loop rather than global.
- The flip lands only after the gate below passes.

## Proposed Solution

1. **Gate (from ENH-2719's run set)**: N ≥ 10 real `ll-loop run` invocations under `request_path: "sdk"` across ≥2 distinct loops showing (a) exit-status/verdict parity with `"cli"` baselines on the same inputs, (b) no new failure modes in `usage_events`/run logs, and (c) measured `cache_read_input_tokens` share consistent with the F1 gate (>50% of iterations). Quantify realized $/run delta.
2. **Fallback audit**: confirm the SDK path's behavior when the `anthropic` package or `ANTHROPIC_API_KEY` is absent degrades to the CLI path (or a clear error) — the default must be safe on fresh installs and non-Anthropic hosts (Codex/OpenCode/omp adapters must be unaffected; `resolve_host()` scope check).
3. **Flip**: change the schema default; update `ll-init` template output if it stamps the key; CHANGELOG entry (concrete version section, not Unreleased).
4. **Batch tranche**: add `request_path: "batch"` (or per-state equivalent) to the identified latency-insensitive loop YAMLs, each with a note citing the 50% discount and the submit+poll latency tradeoff.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option A — fallback check inside `_resolve_request_path()`

**Reasoning**: Option A reuses the codebase's established "resolve, then dispatch once" idiom (`_resolve_request_path()` already mirrors `state.model or self.run_model`, and closely parallels `apply_host_cli_from_config()`/`resolve_host()`'s env-then-config-then-probe resolution shape) and has a direct precedent for the import-probe-and-downgrade mechanic itself (`format_analysis_yaml`'s `try/except ImportError` fallback). Option B has no structural precedent anywhere in the codebase for a try/except-and-retry-with-a-different-dispatcher around `_dispatch_live()` — the one comparable `except ImportError` handler (`transport.py`) raises rather than falls back — and it introduces new duplicate-call and state-mutation risk via the batch tracker's persisted `batch_id.json` write mid-dispatch.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — fallback inside `_resolve_request_path()` | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B — try/except around `_dispatch_live()` call site | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Option A: Direct structural precedent in `apply_host_cli_from_config()` (host_runner.py:1302-1327) and `resolve_host()` (host_runner.py:1254-1299) for layered env/config/probe resolution, plus `format_analysis_yaml`'s inline `try/except ImportError` downgrade (issue_history/formatting.py:94-100). Both existing call sites of `_resolve_request_path()` (executor.py:1584, 2040) consult the same resolver, so a downgrade there is automatically consistent everywhere. Minor cost: the probe would run on every prompt-mode dispatch (twice per state visit) rather than once.
- Option B: No existing pattern in the codebase performs try/except-and-retry-with-a-different-dispatcher for the same logical action; only one call site exists (executor.py:1585), so the "duplicated across call sites" framing in the option itself doesn't hold, but the control flow would be built from scratch and requires new test scaffolding — current `TestRequestPathDispatchWiring` tests assert mutual exclusivity (`mock_runner.calls == []` when SDK is used), which this option would break.

## Implementation Steps

1. Consume ENH-2719's parity/savings evidence; if the gate fails, close this as blocked-on-findings rather than flipping.
2. Audit and, if needed, harden the missing-SDK/missing-key fallback.
3. Flip the schema default + template output + docs + CHANGELOG.
4. Apply per-loop `"batch"` defaults.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json` (`orchestration.request_path` default)
- `.ll/ll-config.json` (this repo's own setting, if kept explicit)
- Loop YAMLs selected for `"batch"` (per FEAT-2710's candidate list)
- `CHANGELOG.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` (`build_anthropic_request()` / `build_batch_request()` dispatch — verify fallback behavior, likely no change)
- `scripts/little_loops/config/features.py` (CacheConfig/deferred-tools docstrings referencing the opt-in)
- `ll-init` config generation (`init/` templates) if it stamps `orchestration.*`

### Similar Patterns
- FEAT-2716's SDK/Batches dispatch wiring and its test coverage of path selection.

### Tests
- Extend existing request-path dispatch tests to assert the new default resolves to `"sdk"` and that missing-SDK environments fall back cleanly.
- Existing `test_cache_control.py` / batches tests unchanged.

### Documentation
- `docs/ARCHITECTURE.md` orchestration.request_path documentation; `docs/reference/HOST_COMPATIBILITY.md` (non-Anthropic hosts unaffected).

### Configuration
- `config-schema.json` default change is the deliverable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Config read path (schema → dataclass → executor), confirmed end-to-end:**
1. `scripts/little_loops/config-schema.json:1574-1579` — `orchestration.request_path` enum + `"default": "cli"`. The description prose itself embeds `"'cli' (default)"` — this repo's convention is that the prose and the JSON `default` key move together (see sibling `cache`/`deferred_tools` descriptions at lines 633/645 which cross-reference `request_path` by name).
2. `scripts/little_loops/config/orchestration.py:86` — `OrchestrationConfig.request_path: str = "cli"` (dataclass field default) **and** line 95, `from_dict()`'s `data.get("request_path", "cli")`. Both literals must move together; a drift here already has precedent as a bug class (`BUG-2321`, see below).
3. `scripts/little_loops/config/core.py:247-248,361-363` — `BRConfig.orchestration` materializes `OrchestrationConfig.from_dict(...)`.
4. Threaded into the executor at exactly two production call sites: `scripts/little_loops/cli/loop/run.py:574` and `scripts/little_loops/cli/loop/lifecycle.py:579` (`FSMExecutor(..., orchestration_config=_config.orchestration)`).
5. `scripts/little_loops/fsm/executor.py:2006-2019` (`_resolve_request_path`) — state-level `StateConfig.request_path` wins if set, else falls through to `self.orchestration_config.request_path`, else (no config threaded) hardcodes `"cli"`.
6. Dispatch branch at `executor.py:1584`: `elif action_mode == "prompt" and self._resolve_request_path(state) in ("sdk", "batch"): result = self._dispatch_live(state, action, ctx)` — every other combination (including `"cli"`) falls through to the pre-existing `ActionRunner`/host-CLI subprocess path (`executor.py:1586-1618`).
7. `_dispatch_live` (`executor.py:2021-2093`) calls `host_runner.dispatch_anthropic_request()` (sdk) or `dispatch_batch_request()`/`poll_batch_result()` (batch) — `host_runner.py:1502-1559`, `1562-1599`, `1606+`.

**Critical gap — the "safe fallback to cli" the Expected Behavior section requires does NOT exist today.** `anthropic` is a hard runtime dependency (`scripts/pyproject.toml:48`, `anthropic>=0.104,<1.0`), with no `try/except ImportError` anywhere around the three `import anthropic` call sites in `host_runner.py` (lines 1540, 1583, 1630). `dispatch_anthropic_request` only catches `anthropic.APIError` (which `AuthenticationError` subclasses, so a missing/invalid `ANTHROPIC_API_KEY` *is* caught there) — but it converts the failure into that **state's** failed `ActionResult(exit_code=1)`, not a reroute back to `request_path == "cli"`. No API-key presence check happens before attempting the SDK call anywhere. `dispatch_batch_request` has no try/except at all; its caller wraps submission in a bare `except Exception` that again just fails the state. Any exception outside those catches (e.g. a hypothetical `ImportError`) propagates uncaught to the executor's top-level handler (`executor.py:772-773`) and ends the **entire run** in `"error"` status. None of the existing `TestRequestPathDispatchWiring` tests (`test_fsm_executor.py:9358-9572`) or `TestDispatchAnthropicRequest`/`TestDispatchBatchRequest` (`test_host_runner_dispatch.py`) exercise a missing-package or missing-API-key scenario. **This means Implementation Step 2 ("Fallback audit") is actually a build, not just an audit** — see the decision block below for where to add it.

**`resolve_host()`/host-CLI selection is orthogonal — confirms non-Anthropic hosts are unaffected.** `resolve_host()` (`host_runner.py:1254-1299`) and `apply_host_cli_from_config()` (lines 1302-1327) consume `orchestration.host_cli`, a completely separate `OrchestrationConfig` field from `request_path`. When `request_path` resolves to `"sdk"`/`"batch"`, `_dispatch_live` calls `host_runner.dispatch_anthropic_request`/`dispatch_batch_request` directly against `anthropic.Anthropic()` — `resolve_host()` is never consulted for those states. Codex/OpenCode/pi hosts remain fully governed by `host_cli` only when `request_path` stays `"cli"`. No code change needed here per the issue's own claim; this confirms it.

**`ll-init` never stamps `orchestration.request_path` today.** `scripts/little_loops/init/cli.py` and every file under `scripts/little_loops/init/` have zero references to `orchestration`/`request_path` (confirmed via directory-wide grep; the one hit is an unrelated OpenCode print-message string). The schema-default-flip therefore silently takes effect for both existing and newly-`ll-init`'d projects with **no init-layer migration needed** — Implementation Step 3's "update `ll-init` template output if it stamps the key" is a no-op; there's nothing to update because nothing stamps it.

**Existing per-loop override machinery already covers the "Batch tranche" step (#4) — no new plumbing needed.** `StateConfig.request_path` (`fsm/schema.py:630,707-708,804`) + `_resolve_request_path()`'s state-override-wins logic (`executor.py:2006`) is already the exact per-loop/per-state override mechanism the issue's step 4 needs: a loop YAML state sets `request_path: "batch"` and it wins over the global config default with zero code changes. (Note: `LoopsConfig.run_defaults`/`LoopRunDefaults` in `scripts/little_loops/config/features.py:701-740` is a *different, unrelated* mechanism — CLI-flag persistent defaults like `clear`/`show_diagrams` for `ll-loop run` — do not confuse the two.)

**Prior precedent for this exact "flip default after gate" shape**: `BUG-2321` (`.issues/bugs/P2-BUG-2321-autoprompt-enabled-default-mismatch-silently-disables-feature.md`, status `done`) is a directly analogous prior default-flip issue. Its structure to reuse: a Decision Rationale table (Consistency/Simplicity/Testability/Risk columns) before committing, an explicit **canary test list** that must stay green, and a CHANGELOG entry format `- **<Title>** — <one-line what/why>. (BUG-2321)` (`CHANGELOG.md:864`). The canary-test-list idea maps directly onto ENH-2720's own test surface (listed below).

**Test surface to update/extend (all current tests assume the `"cli"` default and assert no fallback, since none exists):**
- `scripts/tests/test_config_schema.py:749` — `test_orchestration_request_path_batch_in_schema` (enum membership only, no default assertion — safe from the flip).
- `scripts/tests/test_config.py:3208` — `test_from_dict_request_path_defaults_cli` — **must be updated/renamed**, this asserts the value the flip changes.
- `scripts/tests/test_cache_control.py:298,303` — `OrchestrationConfig().request_path == "cli"` default assertion — **must be updated**.
- `scripts/tests/test_fsm_executor.py:9358-9572` (`TestRequestPathDispatchWiring`) — `test_request_path_cli_default_unaffected` (line 9449) name/assertion should be re-examined once `"sdk"` is the default; add new fallback-specific tests here (missing package / missing key scenarios) once the fallback is built.
- `scripts/tests/test_host_runner_dispatch.py` — `test_api_error_returns_nonzero_exit_code` (line 88) is the only existing error-path test; it mocks generic `anthropic.APIError`, not `AuthenticationError`/`ImportError` specifically — add targeted tests for those once the fallback exists. Mocking convention: `patch("anthropic.Anthropic", ...)` at the lazy-import site (file docstring explains this mirrors `test_fsm_runners.py`'s `subprocess.Popen` mocking convention).
- `scripts/tests/test_transport.py:693,852` — reference pattern for simulating "package not installed" via `mock.patch("builtins.__import__", side_effect=...)` (not `sys.modules` deletion) — reusable for a future `import anthropic`-missing test.

**Decision needed — where to add the missing SDK/API-key fallback** (blocks Implementation Step 2):

> **Selected:** Option A — reuses the existing single-resolution-point idiom (`apply_host_cli_from_config`, `resolve_host()`) with a direct import/env-probe-and-downgrade precedent (`format_analysis_yaml`); Option B has no codebase precedent for try/except-and-retry-with-a-different-dispatcher and adds duplicate-call/state-mutation risk via the batch tracker.

**Option A**: Add the fallback check inside `_resolve_request_path()` (`executor.py:2006-2019`) — before returning `"sdk"`/`"batch"`, probe `anthropic` importability and `ANTHROPIC_API_KEY` presence (env var, matching `apply_host_cli_from_config`'s env-first precedent at `host_runner.py:1302-1327`); on failure, downgrade the resolved value to `"cli"` before dispatch ever begins, so the state falls through the normal `ActionRunner` branch untouched.

**Option B**: Wrap the `_dispatch_live()` call sites in `executor.py:1584-1586` with a pre-flight try/except around the SDK/batch dispatch attempt, and on `ImportError`/`AuthenticationError`/missing-key detection, fall through to `self.action_runner.run(...)` (the `"cli"` path) as a same-state retry.

**Recommended**: Option A — a single resolution point matches the existing architecture (`_resolve_request_path` is already the sole per-state/per-config decision point, mirroring `state.model or self.run_model`), avoids any risk of a partial/duplicated SDK call before falling back, and needs no new retry/state-mutation logic inside `_dispatch_live`. It also keeps the fallback probe cheap (import + env check) rather than requiring a live API round-trip to detect failure.

## Impact

- **Priority**: P2 — cheapest remaining $/run lever in EPIC-2456; converts shipped, dormant code into realized savings.
- **Effort**: Small once gated — the flip itself is a one-line default plus fallback audit; the gate's cost lives in ENH-2719.
- **Risk**: Medium — changes the default network path for every Anthropic-host invocation; mitigated by the parity gate and a hard requirement that missing-SDK environments degrade to CLI.
- **Breaking Change**: No for behavior/outputs (parity-gated); yes for the default transport, which is why the gate exists.

## Related Key Documentation

| Document | Relevance | Notes |
|---|---|---|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | **High** | Documents orchestration request-path dispatch (SDK/Batches, FEAT-2716). |
| [thoughts/plans/2026-07-02-token-cost-optimal-techniques.md](../../thoughts/plans/2026-07-02-token-cost-optimal-techniques.md) | Medium | Tier 2 caching rationale and vendor-measured anchors the flip unlocks by default. |

## Labels

`token-cost`, `caching`, `configuration`, `captured`

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-22_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- `depends_on: ENH-2719` is still `open` — the parity/savings measurement runs (N ≥ 10 `ll-loop run` invocations across ≥2 loops) that gate the actual default flip (Implementation Steps 3-4) haven't happened yet. Only Steps 1-2 (consume the gate once it lands; build/harden the missing-SDK/missing-key fallback) can proceed independently right now.
- Implementation Step 2 ("Fallback audit") is not an audit — the codebase research confirms no `try/except`-and-downgrade path exists anywhere today for missing `anthropic` import or missing `ANTHROPIC_API_KEY`; this is new code to build inside `_resolve_request_path()` (per the Decision Rationale's Option A), with new test coverage for the missing-package/missing-key scenarios.

## Session Log
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `b6fef5f9-1f0d-4aaf-9f70-145b66681d56.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00 - `b8987387-144f-4d80-8c06-31d6c6481325.jsonl`
- `/ll:decide-issue` - 2026-07-22T18:58:25 - `04044445-94db-4521-b724-9e512c0e4211.jsonl`
- `/ll:refine-issue` - 2026-07-22T18:54:34 - `90c4e529-e0c4-40d7-9fcf-13d83b56f5e6.jsonl`
- `/ll:capture-issue` - 2026-07-21T17:22:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9384c3a9-e5cf-4f15-a503-33c5d34b10c7.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-22
- **Reason**: Issue too large for single session (score 11/11, Very Large) — the confidence-check notes already identified two independent readiness states within it: unblocked fallback work vs. gate-blocked default flip.

### Decomposed Into
- ENH-2737: orchestration.request_path — fall back to cli on missing anthropic package or API key
- ENH-2738: Flip orchestration.request_path default to sdk once ENH-2719 gate passes; apply per-loop batch tranche

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-22
- **Decomposed into**: ENH-2737, ENH-2738

Work for ENH-2720 is now carried by its child issues; this parent was closed by rn-decompose.
