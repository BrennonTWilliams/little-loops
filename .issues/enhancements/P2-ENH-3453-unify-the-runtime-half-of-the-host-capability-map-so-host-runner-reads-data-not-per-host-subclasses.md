---
id: ENH-3453
title: Unify the runtime half of the host capability map so host_runner reads data, not per-host subclasses
type: ENH
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- multi-host
- ll-hosts
decision_needed: true
---

## Summary

The build-time half of the declarative host capability map shipped (ENH-2873, then ENH-2883 collapsing the emitters onto it): `adapters/capabilities.py` is data. The runtime half did not. `host_runner.HostCapabilities` is still one `describe_capabilities()` method per runner subclass, so adding a host still means writing a Python class, and the host seam cannot be isolated, tested as data, or versioned on vendor time separately from the engine.

Finish the half: have `host_runner` read runtime host capabilities from the same declarative map the adapter emitters already materialize at build time, so the runtime capability surface is data, not code.

## Current Behavior

Every runner subclass in `host_runner.py` implements its own `describe_capabilities()`, returning a `HostCapabilities` instance (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, …), defaulted false and flipped true per host. Meanwhile `adapters/capabilities.py` already declares per-host build-time capabilities as data, and the emitters' policy decisions are driven from it. Two views of "what a host supports" therefore exist — one declarative (build-time), one procedural (runtime) — held consistent only by convention.

## Expected Behavior

- Runtime host capabilities are read from the declarative map, the same source the adapter emitters materialize at build time — not from per-subclass methods. A runner subclass may still exist for behavior that genuinely varies, but capability *declaration* is data.
- Adding a host, or correcting a capability flag, is a data change rather than a new subclass method.
- The build-time and runtime views cannot drift: one source of truth, mechanically enforced — the same discipline the `HOST_COMPATIBILITY.md` drift test already applies to the compatibility matrix.
- Nothing outside `host_runner` changes: consumers of `HostCapabilities` see the same object with the same fields.

## Design

- Mirror the build-time precedent exactly: ENH-2873 landed the map as data first, ENH-2883 collapsed the emitters onto it. Here the runtime side collapses in one step — declare once, read everywhere.
- Keep `HostCapabilities` as the runtime object. What changes is where its values come from, not what consumers receive.
- Scope check: this issue is the runtime capability map only. A declarative stanza that also covers CLI invocation shape (request templates, auth types, probe endpoints — a YAML host in place of a class) is a larger, separate piece of work; do not absorb it here.

## Why it matters

The host seam is the fastest-moving surface in this codebase — host code changes in roughly half of releases — and it is the one seam with no standard coming. Until capability declaration is data on both sides of it, "host-agnostic" is a claim maintained by discipline rather than a property enforced by construction, and the seam cannot be isolated behind a stable, testable interface.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

The pattern-finder surfaced two live decisions the implementer must resolve knowingly (the ENH-2873 decision rationale at `.issues/enhancements/P2-ENH-2873...md:152-181` scored Option A 2/3 on Testability and 1/3 on Simplicity, Option B the inverse — the implementer inherits this trade-off):

**Option A** (extend `HostCapabilityEntry` with the runtime flag fields; `HostCapabilities` becomes a composition over the entry, not a separate frozen dataclass): single source of truth for both build-time and runtime halves; `_check_runtime_contradiction`'s `shared_fields` set becomes meaningful naturally; consumers see the same `HostCapabilities` object by derivation. Trade-off: the two dataclasses merge and `Option B`'s docstring-mirroring discipline ends.

**Option B** (preserve current shape-disjoint dataclasses; add a small mapping helper that derives `HostCapabilities` from `HostCapabilityEntry`, analogous to `_select_frontmatter_fields` at `adapters/core.py:119-182`): ENH-2873's chosen discipline is preserved; build-time and runtime halves stay individually readable. Trade-off: the mapping helper is a third place to update when a flag is added; `_check_runtime_contradiction` must enumerate shared fields explicitly.

**Recommended**: Option A — the build-time half already broke Option B's discipline the moment it shipped the `verify_host_map.py` runtime check (which exists *only* to mechanically catch the two views drifting), so the discipline no longer earns its keep. One source of truth removes the check's premise. Opencode/pi gap (currently runtime-only in `_HOST_RUNNER_REGISTRY`) is the principal implementer action: add entries to `HOST_CAPABILITIES` for both so `set(HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)` is achievable (per `test_keys_match_emitter_map` shape, `tests/test_verify_host_map.py:17-21`).

The companion public-surface decision is folded in:

**Option 1** (keep `describe_capabilities()` as a thin `return load_runtime_capabilities(self.name)` wrapper on the base `HostRunner`, mirroring the `AutomationContext` `resolve_automation` deprecation-shim shape at `host_runner.py:2223-2280`): zero consumer-side churn; preserves the public surface verbatim.

**Option 2** (delete `describe_capabilities()`; thread `load_runtime_capabilities(host_id)` through every consumer): cleaner; matches ENH-2883's full emitter collapse precedent. Touches ~30 consumer sites catalogued under `## Integration Map → Dependent Files`.

**Recommended**: Option 1 for v1 (the public surface is exported through `scripts/little_loops/__init__.py:33` and `scripts/little_loops/cli/__init__.py:66`; an in-place wrapper preserves every external caller). Option 2 is the right cleanup once the runtime map is the only source of truth and consumers have been migrated in a follow-up.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `load_runtime_capabilities(host_id)` (the single data-driven lookup); collapse the 9 `describe_capabilities()` overrides at lines 490, 662, 962, 1094, 1170, 1354, 1535, 1741, 1943 (ClaudeCodeRunner, CodexRunner, OpenCodeRunner, PiRunner, KimiRunner, QwenRunner, GeminiRunner, OmpRunner). Lines 1995-2004 hold `_HOST_RUNNER_REGISTRY`; the `name` class attribute on each runner is already the cross-reference key to `HOST_CAPABILITIES`.
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES` (line 68) is the source-of-truth map; `HostCapabilityEntry` (line 49) is the candidate shape to extend with the runtime flag fields (Option A) or to mirror via a mapping helper (Option B).
- `scripts/little_loops/cli/verify_host_map.py` — extend `_check_runtime_contradiction` (lines 100-128) so the runtime drift guardrail becomes meaningful (today `shared_fields` is empty by Option-B design, making the check a no-op).

### Dependent Files (Callers/Importers) — `describe_capabilities()` consumers
- `scripts/little_loops/cli/action.py:15` — `ll-action capabilities`
- `scripts/little_loops/cli/doctor.py:31` — `ll-doctor` aggregation; `_capability_check_results` at line 105; `_print_report` at line 1311; `_ADVISORY_CAPABILITIES` at line 102
- `scripts/little_loops/cli/loop/runner.py:31`, `loop/run.py:19`, `loop/lifecycle.py:15`
- `scripts/little_loops/cli/auto.py:23`, `harness.py:25`, `advise.py:9`, `parallel.py:35`, `queue.py:34`, `gitignore.py:11`, `verify_kinds.py:22`, `sprint/run.py:21`, `issues/link_epics.py:23`, `artifact/__init__.py:42`, `artifact/discover.py:29`, `artifact/extract.py:41`
- `scripts/little_loops/fsm/__init__.py:87`, `fsm/executor.py:81`, `fsm/evaluators.py:46`, `fsm/runners.py:23`, `fsm/handoff_handler.py:16`, `fsm/persistence.py:39`, `fsm/types.py:12`, `fsm/validation/structural_rules.py:74`
- `scripts/little_loops/parallel/worker_pool.py:23`, `advisor.py:34`, `subprocess_utils.py:24`, `runner_spec.py:39`, `worktree_utils.py:23`, `extension.py:29`, `extensions/reference_interceptor.py:10`, `codequery/codegraph.py:37`, `session_store/lifecycle.py:31`
- `scripts/little_loops/mcp_server/tools.py:214,224` — `ll-mcp` tools
- `scripts/little_loops/init/cli.py:108` — `runner_cls().describe_capabilities().binary`
- `scripts/little_loops/host_runner.py:2028-2030` — `HOST_BINARY_NAMES = frozenset(cls().describe_capabilities().binary for cls in _HOST_RUNNER_REGISTRY.values())` (the only consumer that instantiates a runner just to read capabilities; after this issue lands it can drop the `cls()` call entirely)

### Conventions in Force
- **Frozen dataclass + module-level dict map**: every per-host capability/role shape uses `@dataclass(frozen=True)` with defaulted fields and a module-level dict keyed by host_id (`adapters/capabilities.py:48-68`, `host_runner.py:288-313`, `host_runner.py:366-391`, `host_runner.py:344-364` for `AutomationContext`).
- **Registry maps host_id → runner class**: `_HOST_RUNNER_REGISTRY: dict[str, type[HostRunner]]` (`host_runner.py:1995-2004`) and `_EMITTER_MAP: dict[str, AdapterSpec]` (`adapters/core.py:53-60`); both keyed by the runner/adapter class's `name` attribute.
- **Per-flag docstring with rationale**: each `HostCapabilities` field carries a docstring naming the consuming feature (e.g. `structured_output` cites ENH-2627/BUG-2626 at `host_runner.py:307-311`; `workspace_sandboxed` cites FEAT-2878 at `host_runner.py:313-319`). Preserve this convention when extending the field set.
- **Single-flag consumer at call boundary**: `_structured_output_args` (`host_runner.py:2365-2383`) is the only existing site that reads `invocation.capabilities.<flag>` at the consumer; the field is read once and routed from there. No consumer reads a per-runner boolean or calls `describe_capabilities()` directly except via `HOST_BINARY_NAMES` (line 2028-2030).
- **Drift check via `_check_*` helpers**: every drift assertion in `scripts/little_loops/cli/verify_host_map.py` is a `_check_*() -> list[str]` helper registered in the module docstring (lines 1-30) and wired to both `main_verify_host_map` (CLI entry, line 217-239) and `_full_host_map_check()` (under `cli/doctor.py`). The runtime drift check extends `_check_runtime_contradiction` (lines 100-128).
- **Drift-test key-set parity**: `scripts/tests/test_verify_host_map.py:17-21` (`TestHostCapabilities::test_keys_match_emitter_map`) asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`. The runtime equivalent keys on `set(_HOST_RUNNER_REGISTRY)`. Keys are NOT congruent today — `_HOST_RUNNER_REGISTRY` adds `opencode` and `pi` with no current build-time entry.
- **Docstring-mirroring instead of inheritance** (Option B precedent, `adapters/capabilities.py:14-29`): "this map is a distinct build-time surface — 'what does `ll-adapt` write for this host' — cross-referenced by docstring only, with no inheritance from `host_runner.HostCapabilities`." ENH-2873 explicitly chose Option B (`.issues/enhancements/P2-ENH-2873...md:103-113, 152-181`).

### Tests
- `scripts/tests/test_host_runner.py:2017-2156` — `TestDescribeCapabilities`: per-runner report assertions at lines 1019, 1488, 1680, 2018-2127, 2350-2355. Cross-runner flag test `test_structured_output_capability_flag_per_host` at line 2047-2055. Pattern-D consistency `test_codex_warnings_consistent_with_describe_capabilities` at line 2127-2156.
- `scripts/tests/test_host_runner.py:2348-2371` — `TestHostBinaryNames`: asserts `HOST_BINARY_NAMES` (derived via `describe_capabilities()` today).
- `scripts/tests/test_verify_host_map.py:17-21` — `test_keys_match_emitter_map`; the host-set guard template for the runtime equivalent.
- `scripts/tests/test_action.py:49` — defines its own `describe_capabilities` test stub returning a `CapabilityReport`.
- `scripts/tests/test_cli_doctor.py:103, 181, 190` — uses `ClaudeCodeRunner.describe_capabilities()` and `CodexRunner.describe_capabilities()` directly.
- `scripts/tests/conformance/test_host_conformance.py:35` — host conformance suite (FEAT-3455 enforcement target).

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:337,378` — explicit citations of `describe_capabilities()` outputs (e.g. `permission_skip`).
- `docs/reference/API.md:10347,10360,10367,10395,10420` — full `HostCapabilities` / `CapabilityReport` / `describe_capabilities()` reference.
- `docs/reference/CLI.md` — `ll-action capabilities`, `ll-doctor` capability reporting.
- `docs/ARCHITECTURE.md:859,873` — `HostRunner` protocol table (lists `describe_capabilities()` as a contract member); `CapabilityReport` / `CapabilityEntry`.
- `docs/development/CONFORMANCE.md` — conformance methodology doc that `test_host_conformance.py` implements.

### Configuration
- `scripts/little_loops/config/orchestration.py` — names the configured host (the value `host_id` is resolved through `resolve_host()`).

### Behavior Parity
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/little_loops/host_runner.py:490,662,962,1094,1170,1354,1535,1741,1943` (per-subclass `describe_capabilities()`) | Returns `HostCapabilities(...)` instance per runner with class-specific flag flips | CHANGED | Replaced by single data-driven lookup; thin wrapper or deleted per `## Proposed Solution` |
| `_HOST_RUNNER_REGISTRY[host].capabilities` (class-level `HostCapabilities` instance on each runner, e.g. `ClaudeCodeRunner` at `host_runner.py:506-516`) | Class-level default for the per-host capability flags | CHANGED | Either removed in favor of map lookup or kept as a fallback for hosts not in `HOST_CAPABILITIES` |
| `scripts/little_loops/adapters/capabilities.py:68` (`HOST_CAPABILITIES`) | Build-time per-host capability map, consumed by adapter emitters | PRESERVED | Source of truth for both build-time and runtime halves after this issue lands |
| `scripts/little_loops/cli/verify_host_map.py:100-128` (`_check_runtime_contradiction`) | Drift check that compares `HOST_CAPABILITIES[host]` to `_HOST_RUNNER_REGISTRY[host].capabilities` | CHANGED | Becomes the runtime drift guardrail (currently a no-op because `shared_fields` is empty by Option-B design) |

## Program Design

### Types

- `HostCapabilities`: existing dataclass — shape preserved (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, …)
- `RuntimeHostCapabilities`: materialized view of `adapters/capabilities.CAPABILITIES` for a single host_id at runtime (same fields, source differs)

### Signatures

- `load_runtime_capabilities(host_id: str) -> HostCapabilities` — reads the declarative map (the same one the adapter emitters materialize at build time) and returns a `HostCapabilities` instance
- `HostRunner.describe_capabilities(self) -> HostCapabilities` — becomes a thin wrapper: `return load_runtime_capabilities(self.host_id)` (or is deleted if the public surface moves to the factory)

### Call Path

`resolve_host(host_id)` (the factory) → `load_runtime_capabilities(host_id)` → reads `adapters/capabilities.CAPABILITIES[host_id]` → returns `HostCapabilities(...)` → consumers see the same object as before

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

1. A `load_runtime_capabilities(host_id: str) -> HostCapabilities` function lives in `scripts/little_loops/host_runner.py` and reads from the same `HOST_CAPABILITIES` map the adapter emitters already use (`adapters/capabilities.py:68`) — verified by an explicit test asserting the new function returns equivalent data to today's per-subclass methods for every host in `_HOST_RUNNER_REGISTRY`.

2. Every `HostCapabilities` flag declared on `host_runner.py:288-313` is expressible from a `HostCapabilityEntry` (or successor) so the runtime map can carry the booleans directly — verified by `set(f.name for f in dataclasses.fields(HostCapabilities)) <= set(f.name for f in dataclasses.fields(HostCapabilityEntry))`.

3. The 9 per-subclass `describe_capabilities()` overrides at `host_runner.py:490,662,962,1094,1170,1354,1535,1741,1943` are collapsed — either (a) replaced by a thin `return load_runtime_capabilities(self.name)` wrapper or (b) deleted with consumers updated to call `load_runtime_capabilities(host_id)`. Verification: `grep -n 'def describe_capabilities' scripts/little_loops/host_runner.py` returns at most 1 hit (the wrapper, if kept).

4. `_check_runtime_contradiction` in `scripts/little_loops/cli/verify_host_map.py:100-128` is extended so its `shared_fields` set is no longer empty — verified by `ll-verify-host-map` returning `OK` on `main` and failing with a named disagreement when a fixture flips one `HostCapabilities` flag without updating the map.

5. The `HOST_CAPABILITIES` key set covers every host in `_HOST_RUNNER_REGISTRY` (the build-time/runtime congruence gap: today `_HOST_RUNNER_REGISTRY` has `opencode, pi` and `HOST_CAPABILITIES` does not) — verified by an assertion analogous to `tests/test_verify_host_map.py:17-21`'s `test_keys_match_emitter_map` but for the runtime registry.

6. The cross-runner flag test `test_structured_output_capability_flag_per_host` at `scripts/tests/test_host_runner.py:2047-2055` continues to pass unchanged — the consumer-side flag read (`invocation.capabilities.<flag>`, e.g. `_structured_output_args` at `host_runner.py:2365-2383`) sees the same values as before. This is the public-surface compatibility guarantee from the issue's Expected Behavior.

7. The `CapabilityEntry.status: Literal["full", "partial", "unsupported"]` closed set is preserved end-to-end. The collapse must define how a 2-valued `HostCapabilities` bool maps to a 3-valued `CapabilityEntry.status` (today's `"partial"` rows are hand-typed, e.g. Codex `agent_select` partial at `host_runner.py:974-981`). Either a richer flag shape (`"partial" | "full" | "unsupported"` per flag) or a per-flag companion dict on `HostCapabilityEntry` is needed — see `## Proposed Solution` decision point.

## Impact

- **Priority**: P2 — host seam moves fastest in the codebase, but the runtime half is bounded: one new lookup function and per-subclass `describe_capabilities` removal.
- **Effort**: Medium — collapses N per-subclass methods (one per host) onto a single data-driven lookup; touches `host_runner.py` subclasses and the host-factory wiring.
- **Risk**: Medium — touches the public `HostCapabilities` shape and every consumer that reads it. Mechanical guardrail (HOST_COMPATIBILITY drift test extended to runtime surface) keeps build-time and runtime views from drifting again.
- **Breaking Change**: No — `HostCapabilities` fields and call sites are unchanged; only the source of the values moves from per-subclass methods to a declarative map.

## Scope Boundaries

- **In scope**: runtime capability *declaration* — replace per-subclass `describe_capabilities()` with a data-driven lookup sourced from the same map `adapters/capabilities.py` already uses.
- **Out of scope**: declarative CLI invocation shape — request templates, auth types, probe endpoints, replacing host subclasses with a YAML host (this is a larger, separate piece of work; ENH-3454 / 3456 territory).
- **Out of scope**: changing the `HostCapabilities` dataclass shape or any consumer-side field access.
- **Out of scope**: build-time emitter consolidation (already done in ENH-2873 / ENH-2883).

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopshost_runner` | `HostCapabilities` dataclass + `HostRunner.describe_capabilities()` are the surfaces this issue collapses onto a data-driven lookup |
| `docs/ARCHITECTURE.md` (host abstraction) | Describes `_HOST_RUNNER_REGISTRY`, `resolve_host()`, and the build-time/runtime capability-map split this issue unifies |
| `.claude/CLAUDE.md` § Host CLI Abstraction | Mandates `resolve_host()` as the only entry point for new host call sites; the data-driven lookup extends that factory |

## Session Log
- `/ll:refine-issue` - 2026-09-12T04:00:17 - `b183c7f4-04a5-40c0-a07a-17f902d66b2e.jsonl`
- `/ll:format-issue` - 2026-09-12T03:48:54 - `d9feb271-85a4-4dac-ac6d-ad5d11e623a8.jsonl`
