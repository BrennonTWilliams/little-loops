---
id: ENH-2738
type: ENH
title: "Flip orchestration.request_path default to sdk once ENH-2719 gate passes; apply per-loop batch tranche"
priority: P2
status: open
captured_at: '2026-07-22T00:00:00Z'
discovered_date: '2026-07-22'
discovered_by: issue-size-review
parent: ENH-2720
depends_on:
- ENH-2719
- ENH-2737
relates_to:
- ENH-2720
- EPIC-2456
- FEAT-2710
labels:
- token-cost
- caching
- configuration
size: Medium
---

# ENH-2738: Flip orchestration.request_path default to sdk once ENH-2719 gate passes; apply per-loop batch tranche

## Summary

Once ENH-2719's parity/savings measurement runs demonstrate CLI/SDK parity,
flip `orchestration.request_path`'s default from `"cli"` to `"sdk"` in
`config-schema.json`, and add `request_path: "batch"` overrides to the
latency-insensitive loop YAMLs identified by FEAT-2710. This is the
gate-blocked half of ENH-2720 — it cannot start until ENH-2719 closes, and
requires ENH-2737's fallback to exist first (Option A's downgrade path
protects this flip).

## Parent Issue

Decomposed from ENH-2720: Default-flip tranche — orchestration.request_path
cli → sdk/batch after parity verification.

## Blocking Gate

Do not start until:
1. **ENH-2719** closes with: N ≥ 10 real `ll-loop run` invocations under
   `request_path: "sdk"` across ≥2 distinct loops showing (a) exit-status/
   verdict parity with `"cli"` baselines on the same inputs, (b) no new
   failure modes in `usage_events`/run logs, and (c) measured
   `cache_read_input_tokens` share consistent with the F1 gate (>50% of
   iterations). Quantified realized $/run delta.
2. **ENH-2737** merges — the missing-SDK/missing-API-key fallback must exist
   before the default flip, or a fresh install/non-Anthropic host with the
   new default would hard-fail instead of degrading to `"cli"`.

If ENH-2719's gate fails to demonstrate parity, close this issue as
blocked-on-findings rather than flipping.

## Proposed Solution

1. Change `scripts/little_loops/config-schema.json`'s
   `orchestration.request_path` default from `"cli"` to `"sdk"`
   (lines 1574-1579), and the mirrored dataclass/`from_dict()` literals in
   `scripts/little_loops/config/orchestration.py:86,95`
   (`OrchestrationConfig.request_path` default and `data.get("request_path", "cli")`)
   — both must move together per the existing `BUG-2321` drift precedent.
2. Add a concrete-version CHANGELOG entry (not `[Unreleased]`), following the
   `BUG-2321` format: `- **<Title>** — <one-line what/why>. (ENH-2720)`
   (`CHANGELOG.md:864` is the reference entry).
3. `ll-init` needs **no change** — confirmed via directory-wide grep that
   nothing under `scripts/little_loops/init/` stamps `orchestration.request_path`
   today, so the schema default flip applies uniformly to new and existing
   projects with no init-layer migration.
4. Add `request_path: "batch"` to the loop-state YAMLs FEAT-2710 identified as
   latency-insensitive (e.g. background verify/summarization states), using
   the existing per-state override mechanism —
   `StateConfig.request_path` (`fsm/schema.py:630,707-708,804`) already wins
   over the global config default via `_resolve_request_path()`'s
   state-override-first logic (`executor.py:2006`); no new plumbing is
   required. Each override needs a one-line comment citing the 50% Batches
   discount and the submit+poll latency tradeoff.
5. Update `docs/ARCHITECTURE.md` (orchestration.request_path section) and
   `docs/reference/HOST_COMPATIBILITY.md` to note non-Anthropic hosts are
   unaffected (confirmed: `resolve_host()`/`host_cli` is a separate config
   field, never consulted when `request_path` resolves to `"sdk"`/`"batch"`).

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json`
- `scripts/little_loops/config/orchestration.py`
- `.ll/ll-config.json` (this repo's own setting, if kept explicit)
- Loop YAMLs selected for `"batch"` per FEAT-2710's candidate list
- `CHANGELOG.md`
- `docs/ARCHITECTURE.md`, `docs/reference/HOST_COMPATIBILITY.md`

### Tests
- `scripts/tests/test_config.py:3208` — `test_from_dict_request_path_defaults_cli` must be updated/renamed to assert `"sdk"`.
- `scripts/tests/test_cache_control.py:298,303` — `OrchestrationConfig().request_path == "cli"` default assertions must be updated to `"sdk"`.
- `scripts/tests/test_fsm_executor.py:9449` — `test_request_path_cli_default_unaffected` name/assertion needs re-examination once `"sdk"` is the default.
- `scripts/tests/test_config_schema.py:749` — `test_orchestration_request_path_batch_in_schema` (enum membership only) is unaffected by the default flip — no change needed.

## Acceptance Criteria

- `orchestration.request_path` defaults to `"sdk"` with `"cli"` remaining a
  supported explicit opt-out.
- Fresh installs and non-Anthropic hosts (Codex/OpenCode/pi) are unaffected
  (verified via ENH-2737's fallback and `resolve_host()`'s scope check).
- Identified latency-insensitive loop states carry `request_path: "batch"`.
- CHANGELOG entry lands under a concrete version section.
- Full test suite green with the updated default-value assertions.

## Impact

- **Priority**: P2 — the actual $/run-realizing change in EPIC-2456.
- **Effort**: Small once the gate passes — mechanical schema/dataclass/doc edits plus per-loop YAML edits.
- **Risk**: Medium — changes the default network path for every Anthropic-host invocation; mitigated by the parity gate (ENH-2719) and the fallback (ENH-2737).
- **Breaking Change**: No for behavior/outputs (parity-gated); yes for the default transport, which is why the gate exists.

## Labels

`token-cost`, `caching`, `configuration`

## Status

**Open** | Created: 2026-07-22 | Priority: P2 | Blocked on: ENH-2719, ENH-2737

## Session Log
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `04044445-94db-4521-b724-9e512c0e4211.jsonl`
