---
id: 3460
title: Drift-gate sync for second-host registry entry (HOST_COMPATIBILITY, ARCHITECTURE, _remediation_hint, verify_host_map, test rename, __all__)
type: ENH
priority: P3
status: open
discovered_date: '2026-09-12'
labels: []
parent: ENH-3456
unproven_mechanism: false
spike_attempted: false
spike_completed: false
blocked_by:
- ENH-3459
relates_to:
- ENH-3453
- ENH-3456
---

## Summary

Decomposed from ENH-3456. Updates the existing repo infrastructure (docs, drift
gates, error-message hints, package exports) to keep it in sync with the second
fake host's registry entry introduced by ENH-3459. This is the "test/doc-only
update for already-shipped code" exception: the eight-host infrastructure is
already shipped; the second fake's registry entry breaks drift gates and the
existing tests/docs must catch up.

## Parent Issue

Decomposed from [ENH-3456](../P3-ENH-3456-prove-host-agnosticism-with-two-deliberately-divergent-fakes-not-one.md):
"Prove host-agnosticism with two deliberately divergent fakes, not one"

The composition test (the novel mechanism) lands in ENH-3459. This child ships the
surrounding drift-gate sync that the registry change trips.

## Why now

CI will fail until these touchups land. Specifically:

- `test_host_tier_table_matches_runner_registry`
  (`scripts/tests/test_wiring_guides_and_meta.py:381-392`) asserts equality between
  `HOST_COMPATIBILITY.md`'s orchestration-runner column and
  `_HOST_RUNNER_REGISTRY`. Without a matching doc-table row, the assertion fails
  with "Missing from doc: ['<fake-key>']".
- `test_has_all_eight_known_binaries`
  (`scripts/tests/test_host_runner.py:2359-2371`) hard-codes the eight basenames
  AND the test name encodes "eight"; will fail CI without rename + asserted-set
  update.
- `_check_runtime_contradiction()` (`cli/verify_host_map.py:116-128`) cross-validates
  `HOST_CAPABILITIES ∩ _HOST_RUNNER_REGISTRY`; the second fake's registry entry
  must be excluded from this intersection check, or `HOST_CAPABILITIES` must gain a
  matching entry.
- `_remediation_hint()` (`host_runner.py:2283-2289`) hard-codes the eight-host
  list in the static error message — the hint becomes stale as the registry grows.

These are the drift gates that the registry change breaks. ENH-3460 closes them.

## Scope

This child covers the drift-gate sync for *already-shipped* infrastructure:

- `scripts/little_loops/host_runner.py:2283-2289` — extend `_remediation_hint()` to
  mention the second fake's registry key, OR replace the static literal with
  `sorted(_HOST_RUNNER_REGISTRY)` so the hint stays in sync as the registry grows.
  [Agent 2]
- `scripts/tests/test_host_runner.py:2359-2371` — rename
  `test_has_all_eight_known_binaries` → `test_has_all_nine_known_binaries` and add
  the second fake's binary to the asserted set. The companion
  `test_matches_registry_describe_capabilities_binaries` at `:2348-2357` is
  registry-derived and invariant — no change needed there. [Agent 3]
- `scripts/tests/test_adapters.py:1533-1536, 2185-2188` — registry-presence checks
  for `kimi-code`/`qwen`; if the second fake has an analogous emitter, add
  `assert "<fake-key>" in _HOST_RUNNER_REGISTRY` here. [Agent 3]
- `scripts/tests/conformance/test_host_conformance.py:52-61` — `_HOST_BINARY`
  mapping for the second fake's binary if `shutil.which`-based skip-gating is
  desired. NOTE: this is also touched by ENH-3459. Whichever child owns the final
  state should be the source of truth.
- `scripts/little_loops/host_runner.py:50-75` — module `__all__` exports the
  Protocol/dataclass surface; if the second fake class is promoted into
  `host_runner.py` (not the spike package), add it to `__all__` and mirror in
  `scripts/little_loops/__init__.py:33-42, 96-103`. [Agent 1]
- `scripts/little_loops/__init__.py:33-42, 96-103` — package-level re-export of
  `HostRunner`/`HostInvocation`/`HostCapabilities`/`AutomationContext`/
  `CapabilityReport`/`CapabilityEntry`/`CapabilityNotSupported`/
  `apply_host_cli_from_config`; mirror if second fake class is promoted into
  production module. [Agent 1]
- `scripts/little_loops/cli/verify_host_map.py:100-128` — either (a) add the second
  fake to `HOST_CAPABILITIES` so `_check_runtime_contradiction` cross-validates
  it, OR (b) document the fake's exclusion from the runtime contradiction check
  (test-time shape, not a real adapter capability). [Agent 1]
- `docs/reference/HOST_COMPATIBILITY.md:22-31` — add a tier-table row for the
  second fake in the orchestration-runner column, OR document a "test-time-only"
  exclusion; without this, `test_host_tier_table_matches_runner_registry` fails.
  [Agent 1 / Agent 2]
- `docs/reference/HOST_COMPATIBILITY.md:462-472` — rename "eight concrete runners"
  prose to "nine" and enumerate the second fake by registry key. [Agent 2]
- `docs/reference/HOST_COMPATIBILITY.md:491-507` — `[^orch]` footnote lists 8
  runners in prose; the second fake does not fit the "Orchestration runner" tier
  semantically (it's a test-time shape), so this footnote should NOT grow —
  instead, document the fake's exclusion from the tier table source-of-truth.
  [Agent 2]
- `docs/ARCHITECTURE.md:221, 859-869` — `Host Runner Layer` table enumerates 8
  production runners; the second fake needs an analogous row, OR the table
  reflects registry minus fakes (the registry → table derivation at
  `test_wiring_guides_and_meta.py:381-392` is the source-of-truth gate).
  [Agent 2]
- `docs/development/CONFORMANCE.md:9, 57` — references `_HOST_RUNNER_REGISTRY`
  parametrization for the conformance suite; update if the composition test's
  relationship to the registry-driven parametrization needs to be documented.
  [Agent 1]

NOT in this child (handled by ENH-3459):
- Second-fake class definition, registry entry, composition test classes, spike
  promotion.

## Implementation Steps

1. Wait for ENH-3459 to land (registry entry must exist before drift gates can be
   resolved).
2. Run `python -m pytest scripts/tests/test_wiring_guides_and_meta.py -v` to
   confirm the tier-table drift gate fires (precondition).
3. Update `docs/reference/HOST_COMPATIBILITY.md:22-31` — add a row for the second
   fake OR document the "test-time-only" exclusion.
4. Update `docs/reference/HOST_COMPATIBILITY.md:462-472` — rename "eight" → "nine"
   in the prose enumeration.
5. Update `docs/ARCHITECTURE.md:221, 859-869` — add the second fake row to the
   `Host Runner Layer` table.
6. Update `scripts/tests/test_host_runner.py:2359-2371` — rename
   `test_has_all_eight_known_binaries` → `test_has_all_nine_known_binaries` and
   add the second fake's binary to the asserted set.
7. Update `scripts/tests/test_adapters.py:1533-1536, 2185-2188` — add the second
   fake's registry-presence assertion if the pattern applies.
8. Update `scripts/little_loops/host_runner.py:2283-2289` — replace the static
   eight-host literal in `_remediation_hint()` with `sorted(_HOST_RUNNER_REGISTRY)`.
9. Update `scripts/little_loops/cli/verify_host_map.py:100-128` — choose between
   (a) adding the fake to `HOST_CAPABILITIES` or (b) documenting the exclusion.
10. (Conditional) If the second fake class is promoted into `host_runner.py`:
    update `__all__` (`host_runner.py:50-75`) and mirror the re-export in
    `scripts/little_loops/__init__.py:33-42, 96-103`.
11. Verify `python -m pytest scripts/tests/ -v` passes with no drift-gate
    failures.

## Conventions in Force

- Registry vs doc-table derivation is the source-of-truth gate
  (`test_host_tier_table_matches_runner_registry`,
  `test_wiring_guides_and_meta.py:381-392`).
- `HOST_BINARY_NAMES` is derived from `_HOST_RUNNER_REGISTRY` (drift-tested at
  `test_host_runner.py:2348-2357`); not hand-maintained.
- Built-ins shadow extensions: collision policy precedent at
  `host_runner.py:1992-1994` cites `hooks/__init__.py:_dispatch_table`.
- Documented tier semantics in `HOST_COMPATIBILITY.md:491-507` exclude
  test-time shapes from the "Orchestration runner" tier.

## Tests

- `scripts/tests/test_wiring_guides_and_meta.py:381-392` —
  `test_host_tier_table_matches_runner_registry` (drift gate).
- `scripts/tests/test_host_runner.py:2359-2371` — `test_has_all_nine_known_binaries`
  (renamed).
- `scripts/tests/test_adapters.py:1533-1536, 2185-2188` — registry-presence checks.

## Files to Modify

- `scripts/little_loops/host_runner.py:2283-2289` — `_remediation_hint()`
- `scripts/little_loops/host_runner.py:50-75` — `__all__` (conditional)
- `scripts/little_loops/__init__.py:33-42, 96-103` — package re-export (conditional)
- `scripts/little_loops/cli/verify_host_map.py:100-128` — `HOST_CAPABILITIES` /
  contradiction-check exclusion
- `scripts/tests/test_host_runner.py:2359-2371` — test rename + asserted-set update
- `scripts/tests/test_adapters.py:1533-1536, 2185-2188` — registry-presence assertions
- `docs/reference/HOST_COMPATIBILITY.md:22-31, 462-472, 491-507` — tier table + prose
- `docs/ARCHITECTURE.md:221, 859-869` — `Host Runner Layer` table
- `docs/development/CONFORMANCE.md:9, 57` — conformance suite description

## Related Issues (Dependencies)

- ENH-3459 (open, P3, this decomposition) — provides the registry entry; this
  child is blocked until the entry exists. [Agent 1 / Agent 2 / Agent 3 findings]
- ENH-3456 (open, P3) — parent decomposition.
- ENH-3453 (open, P2) — collapses the runtime half of the host capability map onto
  a declarative source; this child's `verify_host_map.py` update should harmonize
  with ENH-3453 if both land.

## Reference Documentation

- Parent: `ENH-3456` — full wiring-pass findings, integration map, drift-gate
  inventory.
- `.claude/CLAUDE.md` § Host CLI Abstraction.
- `docs/reference/API.md#little_loopshost_runner`.

## Session Log
- `/ll:issue-size-review` - 2026-09-12T06:09:09 - `a6c3ba7b-8baf-4ae7-b742-fb9d4cbad25c.jsonl`
