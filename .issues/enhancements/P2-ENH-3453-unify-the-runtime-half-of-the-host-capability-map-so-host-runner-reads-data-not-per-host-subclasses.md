---
id: ENH-3453
title: Unify the runtime half of the host capability map so host_runner reads data,
  not per-host subclasses
type: ENH
priority: P2
status: open
discovered_date: '2026-09-11'
labels:
- multi-host
- ll-hosts
decision_needed: false
verify_verdict: VALID
confidence_score: 91
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
---

## Summary

The build-time half of the declarative host capability map shipped (ENH-2873, then ENH-2883 collapsing the emitters onto it): `adapters/capabilities.py` is data. The runtime half did not. `host_runner.HostCapabilities` is still one `describe_capabilities()` method per runner subclass, so adding a host still means writing a Python class, and the host seam cannot be isolated, tested as data, or versioned on vendor time separately from the engine.

Finish the half: have `host_runner` read runtime host capabilities from a declarative runtime map — a sibling of the build-time map, same discipline (frozen entry dataclass + module-level dict keyed by host id), disjoint fields — so the runtime capability surface is data, not code. It cannot literally be the *same* map: the build-time and runtime fields have different semantics (codex is `agents=True` at build time but `agent_select=False` at runtime), and `test_keys_match_emitter_map` pins `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)`, which `opencode`/`pi` are not in.

**Two objects, not one (corrected 2026-09-12 review):** the runtime surface today is (a) the six-boolean `HostCapabilities` class-level literal on each runner (`capabilities = HostCapabilities(...)`, flowing into `HostInvocation.capabilities` via `self.capabilities`), and (b) `describe_capabilities() -> CapabilityReport` — `binary`, `version=""`, and ~45 hand-written 3-valued `CapabilityEntry(name, status, note)` rows across 12 distinct names (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, `json_schema`, `claude_md_suppression`, `token_reporting`, `host`, …). Both become data in this issue; `describe_capabilities()` becomes a thin wrapper that renders the report from the runtime entry.

## Current Behavior

Every runner subclass in `host_runner.py` implements its own `describe_capabilities()`, returning a `HostCapabilities` instance (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`, …), defaulted false and flipped true per host. Meanwhile `adapters/capabilities.py` already declares per-host build-time capabilities as data, and the emitters' policy decisions are driven from it. Two views of "what a host supports" therefore exist — one declarative (build-time), one procedural (runtime) — held consistent only by convention.

## Expected Behavior

- Runtime host capabilities (the six `HostCapabilities` flags, the host binary name, and the `CapabilityReport` rows) are read from a declarative runtime map — not from per-subclass literals and hand-built report methods. A runner subclass may still exist for behavior that genuinely varies, but capability *declaration* is data.
- Adding a host, or correcting a capability flag or report note, is a data change rather than a new subclass method.
- The build-time and runtime maps cannot drift on key set: every host in `_HOST_RUNNER_REGISTRY` has a runtime entry, and every host in both maps agrees on identity — mechanically enforced by `ll-verify-host-map`, the same discipline the `HOST_COMPATIBILITY.md` drift test already applies to the compatibility matrix. (Field-level agreement between the two maps is not a goal: their fields are disjoint by design.)
- Nothing outside `host_runner` changes: consumers of `HostCapabilities` and `CapabilityReport` see the same objects with the same fields and values.

## Design

- Mirror the build-time precedent exactly: ENH-2873 landed the map as data first, ENH-2883 collapsed the emitters onto it. Here the runtime side collapses in one step — declare once, read everywhere.
- Keep `HostCapabilities` as the runtime object. What changes is where its values come from, not what consumers receive.
- Scope check: this issue is the runtime capability map only. A declarative stanza that also covers CLI invocation shape (request templates, auth types, probe endpoints — a YAML host in place of a class) is a larger, separate piece of work; do not absorb it here.
- **Where the runtime map lives:** in `host_runner.py`, immediately after `CapabilityReport` and before the first runner class, so runner classes can reference it at class-definition time and `adapters/capabilities.py` keeps its current import graph (it does not import `host_runner`; `host_runner` does not import `adapters`). Cross-reference by docstring only, per the Option B discipline.
- **Report rows are data too:** the 3-valued `CapabilityEntry.status` and prose `note` cannot be derived from a boolean (Codex `agent_select` is `False` yet reported `"partial"` with a workaround note). The runtime entry therefore carries the report rows verbatim as a tuple of `CapabilityEntry`, alongside the six flags and the binary name. The only flag/row consistency rule enforced is: a row named after one of the six flags may not be `"full"` while that flag is `False`. `"partial"` with `False` (Codex `agent_select`) stays legal.

## Why it matters

The host seam is the fastest-moving surface in this codebase — host code changes in roughly half of releases — and it is the one seam with no standard coming. Until capability declaration is data on both sides of it, "host-agnostic" is a claim maintained by discipline rather than a property enforced by construction, and the seam cannot be isolated behind a stable, testable interface.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

The pattern-finder surfaced two live decisions the implementer must resolve knowingly (the ENH-2873 decision rationale at `.issues/enhancements/P2-ENH-2873...md:152-181` scored Option A 2/3 on Testability and 1/3 on Simplicity, Option B the inverse — the implementer inherits this trade-off):

**Option A** (extend the build-time entry dataclass with the runtime flag fields; the runtime flags dataclass becomes a composition over the entry, not a separate frozen dataclass): one dict for both halves. Trade-offs: reverses the 2026-07-28 decision; build-time and runtime field semantics diverge (codex is agents-true at build time but agent-select-false at runtime), so shared names would mislead; forces opencode/pi into the build-time map, which breaks the emitter-map key-parity test unless emitters are added for hosts that have none; and the adapters package would have to import the runtime dataclasses from the host runner module.

**Option B** (preserve shape-disjoint dataclasses — `HostCapabilityEntry` / `HOST_CAPABILITIES` on the build-time side, `HostCapabilities` / `CapabilityEntry` / `CapabilityReport` on the runtime side; add a **sibling runtime map** `RUNTIME_HOST_CAPABILITIES: dict[str, RuntimeHostEntry]` in `host_runner.py`, keyed like `_HOST_RUNNER_REGISTRY`, read via `load_runtime_capabilities(host_id)` and rendered via `render_capability_report(entry)`, cross-referenced by docstring only): ENH-2873's discipline is preserved; each half stays individually readable; no import-graph change; `opencode`/`pi` get runtime entries without touching the emitter map; every runner's `capabilities` class attribute is assigned from the entry. Trade-off: two dicts to keep key-congruent — enforced by the drift check, not convention.

> **Selected:** Option B — ENH-2873 explicitly chose Option B 11/12 vs Option A 4/12 on 2026-07-28, codified at `adapters/capabilities.py:14-29` ("Option B, decided 2026-07-28"). **Correction (2026-09-12 review):** an earlier draft of this issue described Option B as "a mapping helper that derives `HostCapabilities` from `HostCapabilityEntry`". That is not implementable — the two dataclasses share zero field names by design, so there is nothing to map from, and steps that required `fields(HostCapabilities) <= fields(HostCapabilityEntry)` were Option A in disguise. Option B as now specified is a *second* declarative map beside the first. The `CapabilityReport` 3-valued `Literal["full","partial","unsupported"]` surface with prose `note` strings (consumed by `cli/doctor.py`, `cli/action.py`, `mcp_server/tools.py`) is carried on the runtime entry as data rows. The mapping-helper precedents (`_select_frontmatter_fields` at `adapters/core.py:119-182`; `CheckResult` at `cli/doctor.py:61-79`) still apply to the `describe_capabilities()` render step (entry → `CapabilityReport`).

The companion public-surface decision is folded in:

**Option 1** (keep `describe_capabilities()` as a thin wrapper — look the entry up by the runner's name, then render it — that returns `CapabilityReport` from `RUNTIME_HOST_CAPABILITIES`, and keep the `capabilities` class attribute on every runner assigned from the same entry, mirroring the `AutomationContext` `resolve_automation` deprecation-shim shape at `host_runner.py:2223-2280`): zero consumer-side churn; preserves the public surface verbatim. Note `describe_capabilities()` returns `CapabilityReport`, not `HostCapabilities` — the wrapper must build the report, not return the flags.

> **Selected:** Option 1 — preserves every external caller via the in-place wrapper; Option 2 is the right cleanup once consumers have been migrated in a follow-up.

**Option 2** (delete the describe-capabilities method; thread the runtime lookup through every consumer): cleaner; matches ENH-2883's full emitter collapse precedent. Touches ~30 consumer sites catalogued under `## Integration Map → Dependent Files`.

**Recommended**: Option 1 for v1 (the public surface is exported through `scripts/little_loops/__init__.py:33` and `scripts/little_loops/cli/__init__.py:66`; an in-place wrapper preserves every external caller). Option 2 is the right cleanup once the runtime map is the only source of truth and consumers have been migrated in a follow-up.

### Decision Rationale

**Decision point:** Option A vs Option B (data model — extend `HostCapabilityEntry` to absorb the runtime surface vs preserve disjoint dataclasses with a sibling runtime map in `host_runner.py`)

**Selected:** Option B (sibling runtime map)

**Reasoning:** ENH-2873 explicitly chose Option B 11/12 vs Option A 4/12 on 2026-07-28, codified at `adapters/capabilities.py:14-29` ("Option B, decided 2026-07-28"). Option A reverses that decision and has three concrete costs found in review: build-time/runtime field semantics diverge (codex `agents=True` vs `agent_select=False`), `test_keys_match_emitter_map` breaks when `opencode`/`pi` are added to `HOST_CAPABILITIES`, and `adapters/capabilities.py` would import from `host_runner`. The `CapabilityReport` 3-valued `Literal["full","partial","unsupported"]` surface with prose `note` strings (consumed by `cli/doctor.py`, `cli/action.py`, `mcp_server/tools.py`) has no shape-compatible home on `HostCapabilityEntry`, so even under Option A two views of capability data remain. The mapping-helper pattern has direct working precedents in this codebase (`_select_frontmatter_fields` at `adapters/core.py:119-182`; `CheckResult` at `cli/doctor.py:61-79`) and is reused for the entry → `CapabilityReport` render.

**Scoring summary:**

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 1/3 | 3/3 |
| Simplicity | 2/3 | 1/3 |
| Testability | 2/3 | 3/3 |
| Risk | 2/3 | 2/3 |
| **Total** | **7/12** | **9/12** |

**Trade-off accepted:** Option B costs ~3 places per new flag (field on `HostCapabilities`, field on `RuntimeHostEntry`, the flag→row render rule) plus one data-row edit per host; the per-runner class literal and per-runner `describe_capabilities()` body go away. Option A would be ~3 places too, but buys a partial unification that does not reach the `CapabilityReport` consumers and breaks the emitter-map key parity test.

## Integration Map

### Codebase Research Findings

### Stale-path follow-up (post-2026-09-11 host_compose spike updates)

The `scripts/tests/spike/host_compose/test_host_compose.py` references in this issue (110-119, 204, 235-239, 255, 359-372) were re-verified against the file changed 2026-09-11T23:43:47-05:00. Confirmed anchors:
- `test_host_compose.py:255` — `bad.describe_capabilities()` (regression guard) — drift-resolved; issue's prior listing omitted this line.
- `test_host_compose.py:358-372` — `test_host_capabilities_field_count` enumerates exactly six `HostCapabilities` flags. This issue does not change `HostCapabilities` under either option, so the count stays six regardless; the new `RuntimeHostEntry` is a separate dataclass.

### Additional per-runner anchors (verified, not previously listed)

Per-runner class-level `capabilities=` literals — issue lists `host_runner.py:506-516` (ClaudeCodeRunner only); the other seven runner class literals also exist at:
- `host_runner.py:757` — `ClaudeCodeRunner` second literal / `CodexRunner`
- `host_runner.py:1046` — `CodexRunner` / `OpenCodeRunner`
- `host_runner.py:1122` — `OpenCodeRunner` / `PiRunner`
- `host_runner.py:1211` — `PiRunner` / `GeminiRunner`
- `host_runner.py:1428` — `GeminiRunner` / `OmpRunner`
- `host_runner.py:1621` — `OmpRunner` / `KimiRunner`
- `host_runner.py:1827` — `KimiRunner` / `QwenRunner`

`scripts/little_loops/host_runner.py:490` — confirmed as the `HostRunner` Protocol stub `describe_capabilities()` (not a per-runner override); all other lines 662, 962, 1094, 1170, 1354, 1535, 1741, 1943 are per-runner overrides.

### Additional test files (not previously enumerated)

- `scripts/tests/test_verify_host_map.py:70-72` — `TestCheckRuntimeContradiction::test_current_tree_has_no_contradiction`. Existing assertion that `_check_runtime_contradiction` returns empty on `main`; must still pass after Implementation Step #4.
- `scripts/tests/test_text_utils.py:500-504` — imports `HOST_CAPABILITIES` to derive per-host `config_dir` prefixes (separate from capability flags). Passes unchanged — only flag data shape is affected.
- `scripts/tests/test_adapters.py:1304` — patches `little_loops.adapters.capabilities.HOST_CAPABILITIES`. Passes unchanged under Option 1.
- `scripts/tests/test_wiring_skills_and_commands.py:455, 460` — imports `HOST_CAPABILITIES` for capability-driven parametrization. Passes unchanged.
- `scripts/tests/spike/host_compose/__init__.py` — package docstring only (spike root for `.ll/spikes/spike-FEAT-3456.md`); no `describe_capabilities` content. Spike-file scope expands to four files: `__init__.py`, `fakes.py`, `executor_shim.py`, `test_host_compose.py`.

### Additional doc citations (drift-resolved)

- `docs/reference/API.md:10558` — `HostCapabilities.structured_output` (additional reference; issue lists 10347, 10360, 10367, 10395, 10420, 10452).
- `docs/reference/API.md:12915` — `workspace_sandboxed` reference (issue omits).
- `docs/reference/HOST_COMPATIBILITY.md:267, 349, 405` — companion runtime/`HostCapabilities` cross-references (issue lists 337, 378).
- `docs/reference/HOST_COMPATIBILITY.md:393` — Option B "distinct surface from" docstring cite (issue omits).
- `docs/reference/CLI.md:4797` — additional `host_runner.HostCapabilities` cross-check shape citation (issue lists 51, 1009).
- `docs/development/CONFORMANCE.md` — methodology doc only; no `describe_capabilities`/`HostCapabilities` citations. No re-anchor needed.

### Additional source-of-truth files (not previously listed)

- `scripts/little_loops/__init__.py:33-42` — public export block re-exports `CapabilityEntry`, `CapabilityReport`, `HostInvocation`, `HostRunner`, `apply_host_cli_from_config`. `load_runtime_capabilities` enters here if exported; otherwise stays module-private.
- `scripts/little_loops/cli/__init__.py:66` — re-exports `main_doctor`. Passes unchanged.
- `scripts/little_loops/text_utils.py:291, 293` — `HOST_CAPABILITIES` derivation site (`config_dir` prefixes). Build-time data only; passes unchanged.
- `scripts/little_loops/cli/doctor.py:1431` — `report = runner.describe_capabilities()` (issue lists 31 import + 102, 105, 1311 but not this call site).
- `scripts/little_loops/cli/action.py:342` — `runner.describe_capabilities()` (issue lists 15 import only).
- `scripts/little_loops/mcp_server/tools.py:224` — `resolve_host().describe_capabilities()` (issue lists 214; verified 2026-09-12 — the call site is line 224, not 222 as an earlier draft of this correction stated; `_tool_capabilities()`'s docstring mention is line 214, the actual call is line 224).
- `scripts/little_loops/init/cli.py:108` — `runner_cls().describe_capabilities().binary` (matches issue's Dependent File entry).
- `scripts/little_loops/adapters/{codex,gemini,kimi,qwen,omp}.py:11-46` — each imports `HOST_CAPABILITIES`; the build-time side unchanged by this issue.
- `scripts/tests/spike/host_compose/executor_shim.py:44` — `describe_capabilities` literal in `ALLOWED_RUNNER_PROTOCOL_ATTRS` (issue lists 12, 24 only); `runner.describe_capabilities()` reference in `execute_invocation` docstring at line 94.

### Decision-log cross-references (rationale anchors)

- `.issues/enhancements/P2-ENH-2873-introduce-a-declarative-host-capability-map-for-adapter-hosts.md:64` — declares Option B as the chosen discipline for the build-time half; the cross-reference rule is at lines 117-119. The Option B selection here preserves the precedent's rationale.
- `.issues/enhancements/P2-ENH-2874-generate-degraded-mode-agent-fallbacks-for-hosts-without-subagent-support-with-mandatory-disclosure.md:144` — documents `_check_runtime_contradiction` as the runtime/registry diff-check (relevant to Implementation Step #4 extension).
- `.ll/decisions.yaml:1555` — references `_HOST_RUNNER_REGISTRY` as the precedent that gates the file fork.
- `.ll/decisions.d/ea9c6f4e-9b01-493c-a3c7-73f230acadce.json:12` — corrected 2026-09-12: this is the EPIC-3154 Qwen host-admission `rule` field, and it names `_HOST_RUNNER_REGISTRY`, `_EMITTER_MAP`, `HOST_CAPABILITIES`, and `_KNOWN_HOSTS` as the seams a new host key must be threaded through — it does **not** mention `describe_capabilities`, and it is not framed as a "spike" decision (no spike file is cited; the source is `thoughts/qwen-code-host-integration-report.md`). Relevance to this issue is narrower than the earlier wording implied: it corroborates that `HOST_CAPABILITIES` is one of several host-keyed seams, not that `describe_capabilities` was cross-validated against it.

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `RuntimeHostEntry` (frozen dataclass: `host`, `binary`, `flags: HostCapabilities`, `report_rows: tuple[CapabilityEntry, ...]`), the `RUNTIME_HOST_CAPABILITIES` dict, and `load_runtime_capabilities(host_id) -> RuntimeHostEntry` plus `render_capability_report(entry) -> CapabilityReport`, placed after `CapabilityReport` (line ~391) and before `ClaudeCodeRunner`. Collapse the 8 per-runner `describe_capabilities()` overrides at lines 662, 962, 1094, 1170, 1354, 1535, 1741, 1943 (the hand-written `CapabilityEntry` rows move verbatim, comments included, into the map) and the 8 class-level `capabilities = HostCapabilities(...)` literals at lines 506, 757, 1046, 1122, 1211, 1428, 1621, 1827 (each becomes `capabilities = RUNTIME_HOST_CAPABILITIES["<name>"].flags`). Line 490 is the Protocol stub and stays. `HOST_BINARY_NAMES` (2028-2030) drops the `cls()` instantiation and reads `entry.binary` from the map. Lines 1995-2004 hold `_HOST_RUNNER_REGISTRY`; the `name` class attribute on each runner is the shared key.
- `scripts/little_loops/adapters/capabilities.py` — **data unchanged.** Only the module docstring (lines 14-29) gains a sentence pointing at `host_runner.RUNTIME_HOST_CAPABILITIES` as the runtime-side sibling. `HostCapabilityEntry` is not extended.
- `scripts/little_loops/cli/verify_host_map.py` — rewrite `_check_runtime_contradiction` (lines 100-128): its field-agreement loop is a permanent no-op (fields disjoint by design). Replace with (a) key parity `set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)`, (b) `entry.host == key` and `entry.flags is RunnerClass.capabilities` for each host, (c) flag/row consistency: no report row named after one of the six flags may be `"full"` while the flag is `False`.

### Dependent Files (Callers/Importers) — `describe_capabilities()` consumers
- `scripts/little_loops/cli/action.py:15` — `ll-action capabilities`
- `scripts/little_loops/cli/doctor.py:31` — `ll-doctor` aggregation; `_capability_check_results` at line 105; `_print_report` at line 1311; `_ADVISORY_CAPABILITIES` at line 102
- `scripts/little_loops/cli/loop/runner.py:31`, `loop/run.py:19`, `loop/lifecycle.py:15`
- `scripts/little_loops/cli/auto.py:23`, `harness.py:25`, `advise.py:9`, `parallel.py:35`, `queue.py:34`, `gitignore.py:11`, `verify_kinds.py:22`, `sprint/run.py:21`, `issues/link_epics.py:23`, `artifact/__init__.py:42`, `artifact/discover.py:29`, `artifact/extract.py:41`
- `scripts/little_loops/fsm/__init__.py:87`, `fsm/executor.py:81`, `fsm/evaluators.py:46`, `fsm/runners.py:23`, `fsm/handoff_handler.py:16`, `fsm/persistence.py:39`, `fsm/types.py:12`, `fsm/validation/structural_rules.py:74`
- `scripts/little_loops/parallel/worker_pool.py:23`, `advisor.py:34`, `subprocess_utils.py:24`, `runner_spec.py:39`, `worktree_utils.py:23`, `extension.py:29`, `extensions/reference_interceptor.py:10`, `codequery/codegraph.py:37`, `session_store/lifecycle.py:31`
- `scripts/little_loops/mcp_server/tools.py:214,224` — `ll-mcp` tools
- `scripts/little_loops/init/cli.py:108` — `runner_cls().describe_capabilities().binary`
- `scripts/little_loops/host_runner.py:2028-2030` — `HOST_BINARY_NAMES = frozenset(cls().describe_capabilities().binary for cls in _HOST_RUNNER_REGISTRY.values())` (the only consumer that instantiates a runner just to read capabilities; after this issue lands it reads `e.binary for e in RUNTIME_HOST_CAPABILITIES.values()` — note `HostCapabilityEntry` has no `binary` field, which is another reason the runtime entry must be its own dataclass)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/decisions.py:797,802` — second load-bearing consumer of `invocation.capabilities.structured_output` for the decisions verification path (`getattr(invocation.capabilities, "structured_output", False)`). Matches the same consumer pattern as `host_runner.py:2365-2383` (`_structured_output_args`) at `host_runner.py:2376`. The plan's "single-flag consumer at call boundary" convention (Integration Map → Conventions in Force) covers both sites, but this site is the previously unlisted second occurrence.
- `scripts/little_loops/adapters/core.py:22, 131, 573` — imports `HOST_CAPABILITIES`; reads via `HOST_CAPABILITIES.get(getattr(emitter, "name", ""))` at line 573 (build-time-side `EmitterRegistry` resolution). The build-time half is unchanged by this issue, but the import graph means a refactor that touches `HOST_CAPABILITIES` (e.g., extending `HostCapabilityEntry` with runtime flags under Option A) crosses this import boundary.
- `scripts/little_loops/cli/adapt.py:12, 126` — `HOST_CAPABILITIES.get(args.host)` for `ll-adapt` host selection. Same build-time invariant; under Option A the surface would shift and this site would be re-evaluated.
- `scripts/little_loops/mcp_server/tools.py:225-235` — `_tool_capabilities()` JSON response shape construction (`host`, `binary`, `version`, `capabilities` list of `{name, status, note}`, `project_root`). The MCP `capabilities` tool consumer sees the same shape; only the `CapabilityReport` source changes. Under Option 1 the response is invariant; under Option 2 the call site (line 224) routes through `load_runtime_capabilities(host_id)` and the response shape is preserved verbatim.
- `scripts/little_loops/init/cli.py:102-104, 138, 270, 355` — `_HOST_RUNNER_REGISTRY` import sites (alongside `HostNotConfigured`, `resolve_host`); the registry is unchanged by this issue but these import sites are part of the surface touched if a follow-up renames or moves the registry.
- `scripts/little_loops/adapters/capabilities.py:14-29, 36` — Option B rationale docstring ("this map is a distinct **build-time** surface — 'what does `ll-adapt` write for this host' — cross-referenced by docstring only, with no inheritance from `host_runner.HostCapabilities`") must remain accurate under Option B (the issue's selection); under Option A the paragraph requires rewriting. `__all__ = ["HostCapabilityEntry", "HOST_CAPABILITIES", "SubagentSupport"]` at line 36 is unchanged under Option B; under Option A a new `RuntimeCapabilityEntry` would extend this list.

### Conventions in Force
- **Frozen dataclass + module-level dict map**: every per-host capability/role shape uses `@dataclass(frozen=True)` with defaulted fields and a module-level dict keyed by host_id (`adapters/capabilities.py:48-68`, `host_runner.py:288-313`, `host_runner.py:366-391`, `host_runner.py:344-364` for `AutomationContext`).
- **Registry maps host_id → runner class**: `_HOST_RUNNER_REGISTRY: dict[str, type[HostRunner]]` (`host_runner.py:1995-2004`) and `_EMITTER_MAP: dict[str, AdapterSpec]` (`adapters/core.py:53-60`); both keyed by the runner/adapter class's `name` attribute.
- **Per-flag docstring with rationale**: each `HostCapabilities` field carries a docstring naming the consuming feature (e.g. `structured_output` cites ENH-2627/BUG-2626 at `host_runner.py:307-311`; `workspace_sandboxed` cites FEAT-2878 at `host_runner.py:313-319`). Preserve this convention when extending the field set.
- **Single-flag consumer at call boundary**: `_structured_output_args` (`host_runner.py:2365-2383`) is the only existing site that reads `invocation.capabilities.<flag>` at the consumer; the field is read once and routed from there. No consumer reads a per-runner boolean or calls `describe_capabilities()` directly except via `HOST_BINARY_NAMES` (line 2028-2030).
- **Drift check via `_check_*` helpers**: every drift assertion in `scripts/little_loops/cli/verify_host_map.py` is a `_check_*() -> list[str]` helper registered in the module docstring (lines 1-30) and wired to both `main_verify_host_map` (CLI entry, line 217-239) and `_full_host_map_check()` (under `cli/doctor.py`). The runtime drift check extends `_check_runtime_contradiction` (lines 100-128).
- **Drift-test key-set parity**: `scripts/tests/test_verify_host_map.py:17-21` (`TestHostCapabilities::test_keys_match_emitter_map`) asserts `set(HOST_CAPABILITIES) == set(_EMITTER_MAP)` and **must keep passing** — do not add `opencode`/`pi` to `HOST_CAPABILITIES`. The runtime equivalent is `set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)`; the build-time map remains a strict subset of the runtime map by design.
- **Docstring-mirroring instead of inheritance** (Option B precedent, `adapters/capabilities.py:14-29`): "this map is a distinct build-time surface — 'what does `ll-adapt` write for this host' — cross-referenced by docstring only, with no inheritance from `host_runner.HostCapabilities`." ENH-2873 explicitly chose Option B (`.issues/enhancements/P2-ENH-2873...md:103-113, 152-181`).

### Tests
- `scripts/tests/test_host_runner.py:2017-2156` — `TestDescribeCapabilities`: per-runner report assertions at lines 1019, 1488, 1680, 2018-2127, 2350-2355. Cross-runner flag test `test_structured_output_capability_flag_per_host` at line 2047-2055. Pattern-D consistency `test_codex_warnings_consistent_with_describe_capabilities` at line 2127-2156.
- `scripts/tests/test_host_runner.py:2348-2371` — `TestHostBinaryNames`: asserts `HOST_BINARY_NAMES` (derived via `describe_capabilities()` today).
- `scripts/tests/test_verify_host_map.py:17-21` — `test_keys_match_emitter_map`; the host-set guard template for the runtime equivalent.
- `scripts/tests/test_action.py:49` — defines its own `describe_capabilities` test stub returning a `CapabilityReport`.
- `scripts/tests/test_cli_doctor.py:103, 181, 190` — uses `ClaudeCodeRunner.describe_capabilities()` and `CodexRunner.describe_capabilities()` directly.
- `scripts/tests/conformance/test_host_conformance.py:35` — host conformance suite (FEAT-3455 enforcement target).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/conftest.py:19, 251` — imports `HOST_BINARY_NAMES` and uses it as the live-spawn guard (`if binary not in HOST_BINARY_NAMES: return None`). The symbol stays; the derivation source moves. Passes unchanged under Option 1.
- `scripts/tests/test_fsm_evaluators.py:1066, 1071` — instantiates `HostCapabilities(structured_output=False)` for the `--json-schema` consumer-side flag test (`test_json_schema_omitted_when_host_lacks_structured_output`). Public `HostCapabilities` shape preserved → passes unchanged.
- `scripts/tests/test_wiring_guides_and_meta.py:382-389` — `TestHostTierTable` reads `_HOST_RUNNER_REGISTRY` to cross-validate `docs/reference/HOST_COMPATIBILITY.md`'s "Orchestration runner" column against the canonical Python set. Implementation Step #5 adds `opencode` and `pi` to `HOST_CAPABILITIES`; the runtime registry itself doesn't change, but a follow-up may need to re-check this assertion to confirm the docs table tracks the runtime registry after the opencode/pi entries are added to `HOST_CAPABILITIES`.
- `scripts/tests/spike/host_compose/fakes.py:23-30, 88, 108, 125, 171, 184, 199, 235` — FEAT-3456 spike fakes (`VerboseFakeRunner`, `MinimalFakeRunner`, `BadConcreteRunner`) implement `describe_capabilities()` overrides to satisfy the `HostRunner` Protocol structurally. Pass unchanged under Option 1 (in-place wrapper). Under Option 2 (full deletion) every override becomes a class-level data fixture keyed on `load_runtime_capabilities(fake_name)` — which fails for unregistered fake names, so Option 2 needs to keep the override surface or thread fake-name entries into `HOST_CAPABILITIES` for the spike.
- `scripts/tests/spike/host_compose/executor_shim.py:12, 24` — references `HostCapabilities` in `invocation.capabilities` field. Passes unchanged under Option 1.
- `scripts/tests/spike/host_compose/test_host_compose.py:110-119, 204, 235-239, 255, 359-372` — spike asserts on `describe_capabilities().binary`, `HOST_BINARY_NAMES` (line 118-119, 235, 255), `audited.capabilities == invocation.capabilities` (line 204), and `HostCapabilities.__dataclass_fields__` field count (line 359-362: `TestHostCapabilitiesShape::test_host_capabilities_field_count` enumerates exactly six flags). That test counts `HostCapabilities` fields, which this issue never changes; it is unaffected by whether `HostCapabilityEntry` or `RuntimeHostEntry` gains fields. Passes unchanged.
- `scripts/tests/spike/host_compose/test_host_compose.py` also includes `_BadConcreteRunner.describe_capabilities()` at lines 235-239 (the regression-guard that overrides the wrapper to mutate the report) — under Option 1 the override stays valid; under Option 2 it must be rewritten.
- `scripts/tests/test_host_runner.py:1028-1032` (`TestCodexRunner.test_capabilities_flags`), `1297-1301` (`TestGeminiRunner.test_capabilities_flags`), `1476-1482` (`TestKimiRunner.test_capabilities_flags`), `1667-1674` (`TestQwenRunner.test_capabilities_flags`), `1855-1860` (`TestOmpRunner.test_capabilities_flags`) — five additional per-runner `test_capabilities_flags` tests reading `Runner().capabilities.<flag>` (class-level literal attribute, not `invocation.capabilities`). Under Option 1 these pass via the wrapper; under Option 2 the class attribute must be kept as a shim or each test rewritten to call `load_runtime_capabilities(runner_name)`.
- `scripts/tests/test_host_runner.py:118, 126, 136, 172, 182, 192` — `TestProjectChildEnv*` `capabilities=HostCapabilities()` kwarg literals. Pass unchanged under Option 1; invariant under Option 2 (the dataclass shape is preserved).
- `scripts/tests/test_host_runner.py:1400` (KimiRunner), `1571, 1613` (QwenRunner) — consumer-side reads of `invocation.capabilities.workspace_sandboxed` and `invocation.capabilities.structured_output`. Pass unchanged under both options (the consumer-side read surface is the issue's public-surface compatibility guarantee per Implementation Step #6).
- `scripts/tests/test_host_runner.py:1884` — `assert isinstance(invocation.capabilities, HostCapabilities)` default-invocation test. Passes unchanged — `HostCapabilities` shape preserved.
- `scripts/tests/test_verify_host_map.py:29-32` (`test_gemini_agents_true_matches_degraded_emission`), `39-45` (`test_omp_agents_true_matches_native_emission`), `54-67` (`TestCheckDocParity` — `patch.dict` on `HOST_CAPABILITIES`), `75-129` (`TestCheckEmitterAgreement` — three disagreement tests with `bad_map` injection), `132-155` (`TestRun::test_clean_state_returns_zero` + `TestMainVerifyHostMap` entry-point smoke test) — full suite breakdown beyond the known `test_keys_match_emitter_map` (line 17-21) and `test_current_tree_has_no_contradiction` (line 70-72). The `TestCheckEmitterAgreement` pattern (`patch("little_loops.cli.verify_host_map.HOST_CAPABILITIES", bad_map)` → assert error string in helper output) is the direct template for the `_check_runtime_contradiction` field-disagreement test Implementation Step #4 needs to add.
- `scripts/tests/test_adapters.py:1271-1320` — `TestFixtureHostRegistration::test_fixture_host_emits_skills_commands_and_agents`. Uses `patch.dict("little_loops.adapters.capabilities.HOST_CAPABILITIES", {"fixturehost": fixture_entry}, clear=False)` to inject a synthetic `HostCapabilityEntry`. This is the direct precedent template for Implementation Step #5's new runtime-side fixture-host test (analogous test that injects a synthetic entry and asserts `load_runtime_capabilities("fixturehost")` returns the expected `HostCapabilities`).
- `scripts/tests/test_adapters.py:1533-1536` (`TestResolveEmitterKimi::test_kimi_emitter_name_matches_runner_key`), `2185-2188` (`TestResolveEmitterQwen::test_qwen_emitter_name_matches_runner_key`) — `_HOST_RUNNER_REGISTRY` membership assertions. Pass unchanged (registry is invariant).
- `scripts/tests/test_cli_doctor.py:41-45` — `_make_runner(report)` helper uses `runner.describe_capabilities.return_value = report` mock setup. Every downstream test in the file (lines 84, 136, 165, 204, 230, 249, 270, 290, 311, 365, 430, 484, 511, 537, 566, 599, 625, 646, 672, 698, 724, 778, 800, 822) inherits this mock pattern; passes unchanged under Option 1. The mock targets the runner instance method, so Option 2's deletion of `describe_capabilities()` on real runners does not affect these tests.
- `scripts/tests/test_cli_doctor_full.py:320-324, 342-346` — `CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])` construction in two distinct test bodies. Passes unchanged (`CapabilityReport` shape preserved).
- `scripts/tests/test_cli_doctor_install_checks.py:720, 744` — `HostNotConfigured` import (unrelated to capability surface; invariant).
- `scripts/tests/test_wiring_reference_docs.py:170, 171, 173` — doc cross-validation table entries `(docs/reference/API.md, "CapabilityReport", "FEAT-1462")`, `(..., "CapabilityEntry", ...)`, `(..., "describe_capabilities", ...)`. Under Option 1 all three strings remain in API.md (the wrapper preserves the public surface). Under Option 2, the `describe_capabilities` string would need to be replaced with `load_runtime_capabilities` and the table entry updated; the test would fail otherwise.
- `scripts/tests/spike/host_compose/test_host_compose.py:127-158, 144-158` — `TestCompositionThroughExecutor::test_executor_returns_capabilities_from_host_invocation` exercises `compose_through_executor()` reading `results["verbose"]["capabilities"]` and `results["minimal"]["capabilities"]` as dicts (`verbose_caps["streaming"]`). End-to-end through the executor across two divergent fakes — proves the executor reads capability flags round-trip. Under Option 1 the data flow is preserved; under Option 2 the executor would call `load_runtime_capabilities(runner.name)`.
- `scripts/tests/spike/host_compose/test_host_compose.py:300-322` — `TestSpikeIsolation::test_spike_fakes_register_in_host_runner_registry` asserts fake runners register in `_HOST_RUNNER_REGISTRY`. Invariant under both options.
- `scripts/tests/spike/host_compose/executor_shim.py:134-139` — `compose_through_executor()` builds a `"capabilities"` dict from six per-flag attribute reads on `target.capabilities` (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`). Under Option 1 these pass unchanged; under Option 2 the dict shape is invariant but the source moves to `load_runtime_capabilities(target.name)`.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:337,378` — explicit citations of `describe_capabilities()` outputs (e.g. `permission_skip`).
- `docs/reference/API.md:10347,10360,10367,10395,10420` — full `HostCapabilities` / `CapabilityReport` / `describe_capabilities()` reference.
- `docs/reference/API.md:10452` — additional `CapabilityEntry` reference line (per the wired caller trace).
- `docs/reference/CLI.md:51` — `cmd_capabilities` text discusses "Returns the full `CapabilityReport` for the configured host"; line 1009 references `host_runner.HostCapabilities` in the `ll-verify-host-map` section; line 5411 / 5466 cover MCP `capabilities` tool description.
- `docs/ARCHITECTURE.md:859,873` — `HostRunner` protocol table (lists `describe_capabilities()` as a contract member); `CapabilityReport` / `CapabilityEntry`.
- `docs/ARCHITECTURE.md:1330-1336` — the canonical doc paragraph "this is distinct from `host_runner.HostCapabilities` (Option B, decided 2026-07-28)" — the Option B selection in this issue keeps this paragraph accurate; under Option A it would need to be rewritten.
- `docs/development/CONFORMANCE.md` — conformance methodology doc that `test_host_conformance.py` implements.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/codex/usage.md:137, 180, 182` — describes Codex-specific structured-output behavior referencing `describe_capabilities` status (`partial` `permission_skip`) and `HostCapabilities.structured_output` for the inline `--json-schema` gating logic. Data flow description (per-host `structured_output` bool) is unchanged after ENH-3453; only the source of the value moves from method to map.
- `docs/qwen/automation.md:62` — documents Qwen's `structured_output=True` flag and the evaluators' `--json-schema` append behavior. Same shape after ENH-3453.
- `docs/kimi/automation.md:94` — documents Kimi's `structured_output=False` and the prompt-and-parse fallback. Same shape after ENH-3453.
- `.ll/spikes/spike-FEAT-3456.md:67-78, 149` — spike plan cites specific line numbers in `host_runner.py` (288-313 for `HostCapabilities`, 316-341 for `HostInvocation`, 366-376 / 379-391 for `CapabilityEntry` / `CapabilityReport`, 394 for the `HostRunner` Protocol) as the spike's read-only production references. If the collapse moves line numbers (Option 1 inserts the `load_runtime_capabilities` definition near `host_runner.py:288-313`), these citations drift and the spike plan needs re-anchoring.
- `docs/codex/README.md:40` — behavioral prose "`agent_select` is now `partial` instead of `unsupported`" in the `--agent` section, citing `describe_capabilities()` and `ll-doctor` exit-code behavior. Not in the listed doc set; the prose is invariant under Option 1 (the data value doesn't move), and the reference is stable under both options.
- `docs/kimi/getting-started.md:102` — first-run verification prose lists `streaming / permission skip / agent selection` as the flags `ll-doctor` should print for kimi-code. Invariant under both options.
- `docs/qwen/getting-started.md:110` — first-run verification prose lists `streaming / permission skip / json_schema / structured_output` as the flags `ll-doctor` should print for qwen. Invariant under both options.
- `docs/reference/API.md:10258` — `### HostInvocation` import-block example references `HostCapabilities`. Not previously enumerated; the `HostCapabilities` symbol is preserved as a public re-export so the import block stays accurate.
- `docs/reference/API.md:10282` — `HostInvocation.capabilities: HostCapabilities = field(default_factory=HostCapabilities)` field declaration. The dataclass field declaration is preserved verbatim; the import block and field type are stable under both options.
- `docs/reference/API.md:10389` — `CapabilityEntry.name` description includes the example identifiers `"streaming"` / `"permission_skip"`. Invariant under both options.
- `scripts/little_loops/adapters/capabilities.py:14-29` — module docstring explicitly preserves the Option B rationale ("this map is a distinct **build-time** surface — 'what does `ll-adapt` write for this host' — cross-referenced by docstring only, with no inheritance from `host_runner.HostCapabilities`"). Under Option B (issue's selection) this paragraph stays accurate; under Option A it requires rewriting. This is the load-bearing docstring that anchors the build-time/runtime split — Implementation Steps must explicitly preserve it under the chosen option.

### Configuration
- `scripts/little_loops/config/orchestration.py` — names the configured host (the value `host_id` is resolved through `resolve_host()`).

### Behavior Parity
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/little_loops/host_runner.py:490,662,962,1094,1170,1354,1535,1741,1943` (per-subclass `describe_capabilities()`) | Returns `HostCapabilities(...)` instance per runner with class-specific flag flips | CHANGED | Replaced by single data-driven lookup; thin wrapper or deleted per `## Proposed Solution` |
| `_HOST_RUNNER_REGISTRY[host].capabilities` (class-level `HostCapabilities` instance on each runner, e.g. `ClaudeCodeRunner` at `host_runner.py:506-516`) | Class-level default for the per-host capability flags | CHANGED | Attribute name and type kept; value assigned from `RUNTIME_HOST_CAPABILITIES["<name>"].flags` instead of an inline literal. Every existing `Runner().capabilities.<flag>` read stays valid. |
| `scripts/little_loops/adapters/capabilities.py:68` (`HOST_CAPABILITIES`) | Build-time per-host capability map, consumed by adapter emitters | PRESERVED | Unchanged data; stays build-time-only. Docstring gains a pointer to the runtime sibling. |
| `scripts/little_loops/host_runner.py` (`RUNTIME_HOST_CAPABILITIES`, new) | — | NEW | Runtime per-host map: six flags + binary + report rows, keyed like `_HOST_RUNNER_REGISTRY` |
| `scripts/little_loops/cli/verify_host_map.py:100-128` (`_check_runtime_contradiction`) | Drift check that compares `HOST_CAPABILITIES[host]` to `_HOST_RUNNER_REGISTRY[host].capabilities` field-by-field (permanent no-op: no shared fields) | CHANGED | Becomes key-parity + identity + flag/row consistency check between `RUNTIME_HOST_CAPABILITIES` and `_HOST_RUNNER_REGISTRY` |

## Program Design

### Types

- `HostCapabilities`: existing dataclass — shape preserved (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`)
- `CapabilityEntry` / `CapabilityReport`: existing dataclasses — shape preserved
- `RuntimeHostEntry` (new, `host_runner.py`, `@dataclass(frozen=True)`): `host: str`, `binary: str`, `flags: HostCapabilities`, `report_rows: tuple[CapabilityEntry, ...]`. One per host in `_HOST_RUNNER_REGISTRY`, held in `RUNTIME_HOST_CAPABILITIES: dict[str, RuntimeHostEntry]`. Cross-referenced with `adapters.capabilities.HostCapabilityEntry` by docstring only; no shared fields.

### Signatures

- `load_runtime_capabilities(host_id: str) -> RuntimeHostEntry` — dict lookup with a `KeyError` → `HostNotConfigured`-style message naming the missing host
- `render_capability_report(entry: RuntimeHostEntry) -> CapabilityReport` — `CapabilityReport(host=entry.host, binary=entry.binary, version="", capabilities=list(entry.report_rows))`
- `HostRunner.describe_capabilities(self) -> CapabilityReport` — unchanged signature; every concrete runner's body becomes `return render_capability_report(load_runtime_capabilities(self.name))` (implemented once on a shared mixin/base or duplicated as a one-liner — implementer's call; Protocol stub at line 490 stays)
- `<Runner>.capabilities: HostCapabilities` — class attribute kept; value is `RUNTIME_HOST_CAPABILITIES["<name>"].flags`

### Call Path

`resolve_host(host_id)` → `RunnerClass()` → `build_*()` sets `HostInvocation.capabilities = self.capabilities` (now sourced from `RUNTIME_HOST_CAPABILITIES[name].flags`) → consumers read `invocation.capabilities.<flag>` unchanged.
`runner.describe_capabilities()` → `load_runtime_capabilities(self.name)` → `render_capability_report(entry)` → `CapabilityReport` identical to today's hand-built one (verified by the per-host equivalence test).

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

0. **Capture the baseline before touching anything.** Write a test (or a one-off script kept as a test fixture) that snapshots, for every host in `_HOST_RUNNER_REGISTRY`, today's `RunnerClass.capabilities` and `RunnerClass().describe_capabilities()`; the equivalence test in step 1 compares against this snapshot so the move is provably value-preserving.

1. `RuntimeHostEntry`, `RUNTIME_HOST_CAPABILITIES`, `load_runtime_capabilities(host_id) -> RuntimeHostEntry`, and `render_capability_report(entry) -> CapabilityReport` live in `scripts/little_loops/host_runner.py` between `CapabilityReport` and `ClaudeCodeRunner`. The existing hand-written `CapabilityEntry` rows (with their rationale comments — BUG-2759, ENH-2627, ENH-2714, ENH-1529, ENH-1530, …) move verbatim into each entry's `report_rows`. Verified by a per-host equivalence test: `render_capability_report(load_runtime_capabilities(name)) == <baseline report>` and `load_runtime_capabilities(name).flags == <baseline flags>` for every registry host.

2. `adapters/capabilities.py` data is untouched; `HostCapabilityEntry` gains no fields. Verified by `git diff --stat` on that file showing docstring-only changes and `test_keys_match_emitter_map` still passing.

3. The 8 per-runner `describe_capabilities()` bodies at `host_runner.py:662,962,1094,1170,1354,1535,1741,1943` collapse to the one-line render wrapper (line 490 is the Protocol stub and stays), and the 8 class-level `capabilities = HostCapabilities(...)` literals at `:506,757,1046,1122,1211,1428,1621,1827` become `capabilities = RUNTIME_HOST_CAPABILITIES["<name>"].flags`. Verification: `grep -c 'CapabilityEntry(' scripts/little_loops/host_runner.py` counts only the rows inside `RUNTIME_HOST_CAPABILITIES`, and `grep -n 'capabilities = HostCapabilities(' scripts/little_loops/host_runner.py` returns zero hits.

4. `_check_runtime_contradiction` in `scripts/little_loops/cli/verify_host_map.py:100-128` is rewritten from the no-op field-agreement loop to: (a) `set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)`, (b) per host `entry.host == key` and `_HOST_RUNNER_REGISTRY[key].capabilities is entry.flags`, (c) no `report_rows` row named after one of the six flags is `"full"` while that flag is `False`. Docstring at lines 101-108 rewritten accordingly. Verified by `ll-verify-host-map` returning `OK` on `main` and by three new tests that inject a bad map via `patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map)` (one per rule) and assert the named error string.

5. `RUNTIME_HOST_CAPABILITIES` has entries for `opencode` and `pi` (today their runtime surface is `HostCapabilities()` all-false plus the single `"host"/"unsupported"` report row — carried over as-is). `HOST_CAPABILITIES` does **not** gain these keys. Verified by the key-parity rule in step 4 and by `test_keys_match_emitter_map` still passing.

6. The cross-runner flag test `test_structured_output_capability_flag_per_host` at `scripts/tests/test_host_runner.py:2047-2055` continues to pass unchanged — the consumer-side flag read (`invocation.capabilities.<flag>`, e.g. `_structured_output_args` at `host_runner.py:2365-2383`) sees the same values as before. This is the public-surface compatibility guarantee from the issue's Expected Behavior.

7. `HOST_BINARY_NAMES` (`host_runner.py:2028-2030`) is derived from `entry.binary for entry in RUNTIME_HOST_CAPABILITIES.values()` with no runner instantiation. Verified by `TestHostBinaryNames` (`test_host_runner.py:2348-2371`) passing unchanged and `conftest.py:251`'s live-spawn guard still seeing the same frozenset.

8. `adapters/capabilities.py:14-29` docstring and `docs/ARCHITECTURE.md:1330-1336` gain one sentence naming `host_runner.RUNTIME_HOST_CAPABILITIES` as the runtime sibling; `docs/reference/API.md` `host_runner` section documents `RuntimeHostEntry`, `RUNTIME_HOST_CAPABILITIES`, `load_runtime_capabilities`, `render_capability_report`; `docs/reference/HOST_COMPATIBILITY.md:337,378` prose stays accurate (values unchanged). Verified by `test_wiring_reference_docs.py` passing and the `ll-audit-docs`/mirror gates clean.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. Plain bullets — they are not part of the parent step sequence._

- Verify `scripts/little_loops/cli/issues/decisions.py:797,802` — second load-bearing `invocation.capabilities.structured_output` consumer for the decisions verification path. Under Option 1 it is invariant (`getattr(invocation.capabilities, "structured_output", False)` reads the same field); under Option 2 the call must thread `load_runtime_capabilities(host_id)` (the caller already has the runner via `resolve_host().build_blocking_json(...)`).
- Confirm `scripts/tests/conftest.py:19, 251` `HOST_BINARY_NAMES` import stays valid — the symbol's derivation source moves but its name and type are unchanged.
- Verify `scripts/tests/test_fsm_evaluators.py:1066, 1071` `HostCapabilities(structured_output=False)` instantiation — the public `HostCapabilities` shape is preserved end-to-end, so the test stays valid.
- `scripts/tests/test_wiring_guides_and_meta.py:382-389` — reads `_HOST_RUNNER_REGISTRY`, which is unchanged; Implementation Step #5 no longer touches `HOST_CAPABILITIES`, so this passes as-is.
- Verify `scripts/tests/spike/host_compose/fakes.py:23-30, 88, 108, 125, 171, 184, 199, 235` — all `describe_capabilities()` overrides stay valid under Option 1. Under Option 2 the overrides would need to be replaced with class-level data fixtures keyed on `load_runtime_capabilities(fake_name)` — which fails for unregistered fake names; a follow-up under Option 2 must either preserve the override surface or thread fake-name entries into `HOST_CAPABILITIES` for the spike.
- Verify `scripts/tests/spike/host_compose/executor_shim.py:12, 24` — references `HostCapabilities` in `invocation.capabilities`; invariant under Option 1.
- Verify `scripts/tests/spike/host_compose/test_host_compose.py:110-119, 204, 235-239, 255, 359-372` — asserts on `describe_capabilities().binary`, `HOST_BINARY_NAMES`, `audited.capabilities == invocation.capabilities`, and `HostCapabilities.__dataclass_fields__` field count (six flags). Unaffected: `HostCapabilities` is not modified by this issue (`RuntimeHostEntry` is a separate dataclass that *contains* a `HostCapabilities`).
- Re-anchor `docs/codex/usage.md:137, 180, 182` and `docs/qwen/automation.md:62` and `docs/kimi/automation.md:94` if Implementation Steps shift line numbers — these cite `describe_capabilities` outputs and `HostCapabilities.structured_output` behavior; the data-flow description is unchanged but specific citations may drift.
- Confirm `docs/ARCHITECTURE.md:1330-1336` (the "distinct from `host_runner.HostCapabilities` (Option B, decided 2026-07-28)" paragraph) stays accurate — Option B selection in this issue keeps it; Option A would require rewriting it.
- Re-anchor `.ll/spikes/spike-FEAT-3456.md:67-78, 149` — spike plan cites specific line numbers in `host_runner.py` (288-313, 316-341, 366-376, 379-391, 394). If `load_runtime_capabilities` is inserted near `host_runner.py:288-313` (Option 1), line citations drift. The spike plan must be updated to the post-collapse references.
- Add new test cases to `scripts/tests/test_verify_host_map.py` for Implementation Step #4 (`_check_runtime_contradiction` rewrite). Three categories, mirroring the existing `TestCheckEmitterAgreement` pattern at lines 75-129 but patching `little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES`: (a) key-parity — drop one registry host from the patched map, assert a `"missing runtime entry for '<host>'"`-style error; (b) identity — patch an entry whose `flags` is a fresh `HostCapabilities()` not identical to `RunnerClass.capabilities`, assert the named error; (c) flag/row consistency — patch an entry with `flags.streaming=False` and a `CapabilityEntry("streaming", "full")` row, assert the named error. Keep `test_current_tree_has_no_contradiction` (lines 70-72) as the green-path guard.
- Add new test to `scripts/tests/test_verify_host_map.py` for Implementation Step #5 (runtime-registry key parity), mirroring `TestHostCapabilities::test_keys_match_emitter_map` at lines 17-21: assert `set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY)`. `test_keys_match_emitter_map` itself must remain green (build-time map unchanged).
- Add per-host equivalence test for the render path: for every host in `_HOST_RUNNER_REGISTRY`, assert `render_capability_report(load_runtime_capabilities(name)) == <baseline CapabilityReport>` and `load_runtime_capabilities(name).flags == <baseline HostCapabilities>` where the baselines are the pre-change values captured in Implementation Step #0. Mirror the precedent shape `scripts/tests/spike/omp_agent_output_frontmatter_passthrough/test_output_passthrough.py:21-80` (input fixture → helper call → assert equivalence). This is Implementation Step #1's verification test.
- Verify `scripts/tests/test_host_runner.py:1028-1032, 1297-1301, 1476-1482, 1667-1674, 1855-1860` — five `Test*.test_capabilities_flags` sites reading class-level `Runner().capabilities.<flag>` literals. Under Option 1 these pass via the wrapper; under Option 2 either the class attribute is preserved as a shim or each test is rewritten to `load_runtime_capabilities(runner.name)`. Implementation must select one path explicitly.
- Verify `scripts/tests/test_wiring_reference_docs.py:170, 171, 173` — strings `"CapabilityReport"`, `"CapabilityEntry"`, `"describe_capabilities"` are wired to `docs/reference/API.md` under `FEAT-1462`. Under Option 1 all three remain load-bearing strings (the public surface is preserved). Under Option 2 the `"describe_capabilities"` string must be replaced with `"load_runtime_capabilities"` in API.md and the cross-validation table updated; missing this update breaks the wiring-reference-docs test.
- Verify `scripts/little_loops/mcp_server/tools.py:225-235` — `_tool_capabilities()` JSON response shape (`host`, `binary`, `version`, `capabilities` list of `{name, status, note}`, `project_root`). The MCP consumer sees the same dict under both options; only the `CapabilityReport` source changes. Under Option 2 line 224 routes through `load_runtime_capabilities(host_id)` and the response shape is preserved verbatim.
- Verify `scripts/tests/test_adapters.py:1271-1320` — `TestFixtureHostRegistration::test_fixture_host_emits_skills_commands_and_agents` is the direct precedent template for a runtime-side fixture-host test. The build-time test injects a synthetic `HostCapabilityEntry` via `patch.dict("little_loops.adapters.capabilities.HOST_CAPABILITIES", {"fixturehost": fixture_entry}, clear=False)`. The runtime equivalent injects a synthetic `RuntimeHostEntry` via `patch.dict("little_loops.host_runner.RUNTIME_HOST_CAPABILITIES", {"fixturehost": entry}, clear=False)` and asserts `load_runtime_capabilities("fixturehost") is entry` and `render_capability_report(entry)` has the expected `binary`/rows.
- Verify `scripts/tests/spike/host_compose/test_host_compose.py:127-158, 144-158` — `TestCompositionThroughExecutor::test_executor_returns_capabilities_from_host_invocation` exercises the executor's end-to-end read of `invocation.capabilities` across two divergent fakes. Under Option 1 the data flow is preserved via the wrapper; under Option 2 the executor routes through `load_runtime_capabilities(runner.name)`. The test must continue to pass under the chosen option.
- Verify `scripts/tests/spike/host_compose/executor_shim.py:134-139` — `compose_through_executor()` builds the `"capabilities"` dict from six per-flag attribute reads on `target.capabilities`. Under Option 2 the source moves to `load_runtime_capabilities(target.name)`; the dict shape is invariant under both options.
- Verify `scripts/little_loops/adapters/capabilities.py:14-29, 36` — Option B rationale docstring and `__all__` list. Under Option B (issue's selection) both stay accurate; under Option A the docstring paragraph requires rewriting (the load-bearing change the issue's `## Scope Boundaries` flags but does not enumerate) and `__all__` is extended only if a new `RuntimeCapabilityEntry` is added.
- Verify `docs/codex/README.md:40`, `docs/kimi/getting-started.md:102`, `docs/qwen/getting-started.md:110`, and `docs/reference/API.md:10258, 10282, 10389` — prose and example-identifier citations of `describe_capabilities`/`HostCapabilities` outputs. Invariant under both options; the prose and field types are preserved.
- Verify `scripts/tests/test_cli_doctor.py:41-45` — `_make_runner(report)` helper using `runner.describe_capabilities.return_value = report` mock pattern. Mock targets the runner instance method, so Option 2's deletion of `describe_capabilities()` on real runners does not affect these tests.

## Impact

- **Priority**: P2 — host seam moves fastest in the codebase, but the runtime half is bounded: one new lookup function and per-subclass `describe_capabilities` removal.
- **Effort**: Medium — collapses N per-subclass methods (one per host) onto a single data-driven lookup; touches `host_runner.py` subclasses and the host-factory wiring.
- **Risk**: Medium — touches the *source* of every `HostCapabilities` and `CapabilityReport` value (shapes unchanged), so a transcription slip while moving ~45 report rows would silently change `ll-doctor`/`ll-action capabilities` output. Mitigated by the Step #0 baseline snapshot + per-host equivalence test. The rewritten `_check_runtime_contradiction` keeps the runtime map and the registry from drifting again.
- **Breaking Change**: No — `HostCapabilities` fields and call sites are unchanged; only the source of the values moves from per-subclass methods to a declarative map.

## Scope Boundaries

- **In scope**: runtime capability *declaration* — replace per-subclass `capabilities` literals and hand-built `describe_capabilities()` bodies with a data-driven lookup from a sibling runtime map in `host_runner.py`, following the same frozen-entry + dict discipline as `adapters/capabilities.py`.
- **Out of scope**: declarative CLI invocation shape — request templates, auth types, probe endpoints, replacing host subclasses with a YAML host (this is a larger, separate piece of work; ENH-3454 / 3456 territory).
- **Out of scope**: changing the `HostCapabilities`, `CapabilityEntry`, or `CapabilityReport` dataclass shapes or any consumer-side field access.
- **Out of scope**: adding runtime fields (or `opencode`/`pi` keys) to `HostCapabilityEntry` / `HOST_CAPABILITIES`; the build-time map stays a strict, emitter-keyed subset.
- **Out of scope**: reconciling `"partial"` report rows with `False` flags (e.g. Codex `agent_select`) — carried over verbatim; only `"full"`-with-`False` is flagged as drift.
- **Out of scope**: build-time emitter consolidation (already done in ENH-2873 / ENH-2883).

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

`/ll:verify-issues --auto`, 2026-09-12. `ll-verify-evidence` returned `ok: true` (no quote-existence findings). No `## Blocked By` / `## Blocks` sections exist, so there is nothing to check against `ll-issues list --json --status all`. No active required decision rules exist in this repo (`ll-issues decisions list --type rule --enforcement required --active-only` returns none), so `DECISIONS_VIOLATION` was not in play. Not a regression check candidate (no matching completed issue).

**Line-number/anchor spot-check (systemic drift check):** re-verified every class/def/dict boundary the issue cites in `host_runner.py` — `HostCapabilities` (289), `HostInvocation` (317), `AutomationContext` (345), `CapabilityEntry` (367), `CapabilityReport` (380), `HostRunner` Protocol (395) with its `describe_capabilities` stub (490), all 8 runner classes and their `capabilities = HostCapabilities(...)` literals (506/757/1046/1122/1211/1428/1621/1827) and `describe_capabilities()` overrides (662/962/1094/1170/1354/1535/1741/1943), `_HOST_RUNNER_REGISTRY` (1995-2004), `HOST_BINARY_NAMES` (2028-2030), `resolve_automation` (2223), and `_structured_output_args` (2365) — every one matches exactly. `cli/verify_host_map.py`'s `_check_runtime_contradiction` (100-128) and its docstring (101-108) also match exactly, and its "permanent no-op" claim was confirmed directly: `HostCapabilityEntry`'s fields (`host, config_dir, skill_output_format, command_output_format, agent_output_format, frontmatter_fields_read, agents, commands, hooks, subagents`) share zero names with `HostCapabilities`'s six flags. No systemic drift found — the 2026-09-12 refine/wire passes' line numbers are still current as of this check.

**Proposal-vs-code consequence check:** walked the proposed `RuntimeHostEntry`/`RUNTIME_HOST_CAPABILITIES`/`load_runtime_capabilities`/`render_capability_report` design and the rewritten `_check_runtime_contradiction` against the real per-runner data. Read all 8 runners' `capabilities` literals and `describe_capabilities()` bodies directly: every runner's `name` class attribute matches its `_HOST_RUNNER_REGISTRY` key exactly (so `host=self.name` and the proposed `entry.host` agree); every `describe_capabilities()` body hardcodes `version=""` (matches `render_capability_report`'s `version=""`); and applying the proposed flag/row consistency rule ("no report row named after one of the six flags may be `\"full\"` while that flag is `False`") to every existing runner's data today produces zero violations (spot-checked Codex `agent_select=False`/`"partial"`, Kimi `agent_select=True`/`"partial"`, Qwen `structured_output=True`/`"full"`, and all six-flag rows on `ClaudeCodeRunner`/`GeminiRunner`/`OmpRunner`) — so `test_current_tree_has_no_contradiction` (verify_host_map.py:70-72) will still pass unchanged after Implementation Step #4, as the issue claims. `HostCapabilityEntry` genuinely has no `binary` field (confirmed by reading the dataclass), supporting the issue's rationale for why `RuntimeHostEntry` must be its own dataclass. No exception-handling gaps or test-fixture invalidation found in the sampled sites (`test_cli_doctor.py`'s mocks target the runner instance method directly, not a module-level function, so they are unaffected by the wrapper rewrite). No PROPOSAL_UNSOUND finding.

**Causal/identity claims (item 6):** read `.issues/enhancements/P2-ENH-2873-....md:169-172` directly — confirmed the scoring table verbatim: Option A 4/12, Option B 11/12, decided 2026-07-28, matching this issue's "11/12 vs 4/12" claim exactly. Confirmed `adapters/capabilities.py:14` literally contains "Option B, decided 2026-07-28" and `docs/ARCHITECTURE.md:1330` literally contains "This is distinct from `host_runner.HostCapabilities` (Option B, decided". Confirmed `.ll/decisions.yaml:1555` does name `_HOST_RUNNER_REGISTRY`. However, `.ll/decisions.d/ea9c6f4e-9b01-493c-a3c7-73f230acadce.json:12` did **not** say what the issue claimed — read directly, it is the EPIC-3154 Qwen host-admission `rule` field (source `thoughts/qwen-code-host-integration-report.md`, no spike file cited), and it never mentions `describe_capabilities`; it names `_HOST_RUNNER_REGISTRY`/`_EMITTER_MAP`/`HOST_CAPABILITIES`/`_KNOWN_HOSTS` as host-keyed seams. **Fixed**: reworded the citation in `## Integration Map → Decision-log cross-references` to describe the fragment's actual content instead of the inaccurate "describe_capabilities cross-validation in the spike-decision rationale body" framing.

**Corrections applied this pass:**
1. `## Integration Map → Files to Modify` (mcp_server/tools.py bullet, formerly two bullets): the call site `resolve_host().describe_capabilities()` is at `mcp_server/tools.py:224`, not `222` as an earlier drift-correction stated (the docstring mention referencing the same call is at line 214). Consolidated the duplicate "same caller, second line" bullet into the corrected one.
2. `## Integration Map → Decision-log cross-references`: corrected the `.ll/decisions.d/ea9c6f4e-....json:12` citation description (see above) — it does not mention `describe_capabilities` and is not a "spike-decision".

No other citations sampled (Files to Modify, Program Design signatures, Behavior Parity table, a representative cross-section of Dependent Files/Tests/Documentation, and the `adapters/capabilities.py`/`cli/verify_host_map.py`/`cli/issues/decisions.py`/`adapters/core.py`/`cli/adapt.py` wiring-phase call sites) showed drift. Graph tool used: `ll-code --json status` (provider=codegraph, freshness=fresh) and `ll-code --json callers-of describe_capabilities`, which corroborated (not originated) the `test_host_runner.py:1019,1488,1680`, `test_cli_doctor.py:181,190`, `cli/doctor.py:1431`, and `mcp_server/tools.py:224` citations; all graph findings were cross-checked with a direct `Read`/`grep`.

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md#little_loopshost_runner` | `HostCapabilities` dataclass + `HostRunner.describe_capabilities()` are the surfaces this issue collapses onto a data-driven lookup |
| `docs/ARCHITECTURE.md` (host abstraction) | Describes `_HOST_RUNNER_REGISTRY`, `resolve_host()`, and the build-time/runtime capability-map split this issue unifies |
| `.claude/CLAUDE.md` § Host CLI Abstraction | Mandates `resolve_host()` as the only entry point for new host call sites; the data-driven lookup extends that factory |

## Session Log
- `/ll:verify-issues` - 2026-09-12T17:12:38 - `1e2ab216-51bc-448b-8f81-d875cf66efd8.jsonl`
- `/ll:verify-issues` - 2026-09-12T17:03:11 - `48586f2c-123a-4528-b5db-0e5822d417e7.jsonl`
- `/ll:confidence-check` - 2026-09-12T05:27:45 - `a7d5ab8d-b8bf-4135-accb-3507f8725874.jsonl`
- `/ll:wire-issue` - 2026-09-12T05:23:40 - `4b886059-62a6-4459-bb5d-6dea0195e090.jsonl`
- `/ll:refine-issue` - 2026-09-12T05:05:00 - `aec83a29-efa0-4682-927d-beee25b9d4d8.jsonl`
- `/ll:wire-issue` - 2026-09-12T04:57:31 - `c5717503-aeae-42d0-b23a-777fa1078d80.jsonl`
- `/ll:decide-issue` - 2026-09-12T04:45:13 - `4d557e48-0501-409c-ace4-f84bc66f4547.jsonl`
- `/ll:refine-issue` - 2026-09-12T04:00:17 - `b183c7f4-04a5-40c0-a07a-17f902d66b2e.jsonl`
- `/ll:format-issue` - 2026-09-12T03:48:54 - `d9feb271-85a4-4dac-ac6d-ad5d11e623a8.jsonl`
