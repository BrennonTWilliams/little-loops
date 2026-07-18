---
id: FEAT-2672
title: "F1-prereq (b) \u2014 Deferred tool loading"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T15:15:21Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2673
- FEAT-2679
depends_on:
- FEAT-2673
- FEAT-2679
decision_needed: false
labels:
- token-cost
- caching
- tier-2
learning_tests_required:
- anthropic
confidence_score: 62
outcome_confidence: 41
score_complexity: 5
score_test_coverage: 19
score_ambiguity: 7
score_change_surface: 10
spike_needed: true
---

# FEAT-2672: F1-prereq (b) — Deferred tool loading

## Summary

New `scripts/little_loops/tools/deferred.py` (~90 LOC) implementing the
`defer_loading=True` + `tool_reference` pattern: full tool definitions are
withheld from the initial request and loaded on demand, so the cacheable
static prefix stays byte-stable while the tool catalog churns. This is
EPIC-2456 § Children [TBD-9], the second F1 cache-stability prerequisite.
Vendor-measured anchor: "cutting context usage by 90%+ while enabling
applications that scale to thousands of tools."

## Motivation

Tool-definition churn is the main threat to the F1 cache breakpoint: any
change in the serialized tool block invalidates the cached prefix and turns
reads back into 1.25x writes. Deferring tool bodies out of the static
prefix preserves the breakpoint across catalog churn, and independently
shrinks the initial prompt regardless of whether F1 caching is enabled.

## Implementation Steps

1. New module `scripts/little_loops/tools/deferred.py` (~90 LOC):
   `tool_reference` stub emission (name + one-line description + defer
   marker) and on-demand resolution of full definitions.
2. Integration point is the prompt-assembly path (`fsm/runners.py`) ahead
   of `resolve_host()`; behavior gated behind a config flag (default off
   until FEAT-2673 lands and measurements exist).
3. Use FEAT-2671's fragment hashes to verify prefix byte-stability across
   catalog churn in tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 2's stated integration point is stale/incorrect.** `resolve_host()`
  is not called anywhere in `scripts/little_loops/fsm/runners.py` (zero
  matches). It is called exactly once in this call chain, inside
  `run_claude_command()` at `scripts/little_loops/subprocess_utils.py:328`
  (`runner = resolve_host()`), one layer *below* `runners.py`'s
  `DefaultActionRunner.run()` (`fsm/runners.py:91`). This is the same kind
  of correction FEAT-2671 already needed (its wiring target moved from
  `fsm/runners.py` to `fsm/executor.py` for an analogous reason — see
  `.issues/features/P2-FEAT-2671-f1-prereq-content-hash-fragment-store.md`
  § Codebase Research Findings).
- **No tool-definition catalog exists to defer.** The only "tools" surface
  that flows through `fsm/runners.py` → `subprocess_utils.run_claude_command()`
  → `host_runner.py` is a flat `list[str]` of tool *names* (the
  `ActionRunner.run()` Protocol's `tools` param, `fsm/runners.py:36-51`),
  threaded straight to `ClaudeCodeRunner.build_streaming()` as a `--tools`
  CSV flag (`host_runner.py:263-264`). There are no full JSON tool-schema
  bodies assembled anywhere in this path today — so "withholding full tool
  definitions from the initial request" has no current data structure to
  hook into. Per-host support for even the name-list also diverges:
  `CodexRunner`/`GeminiRunner` silently ignore `tools` with a
  `CapabilityNotSupported` warning (`host_runner.py:501-510`, `871-878`);
  `OpenCodeRunner`/`PiRunner` raise `HostNotConfigured` unconditionally.
- **"Deferred tools" already means something else in this codebase.** The
  term currently refers to Claude Code's own host-side `Skill`/`ToolSearch`
  lazy-loading mechanism (see `.issues/bugs/P2-BUG-946-ll-loop-slash-command-steps-fail-toolsearch-timeout.md`
  and the comment at `fsm/runners.py:125-128`). little-loops currently
  *relies on* that host mechanism rather than implementing its own —
  `skill_expander.py`'s `expand_skill()` (line 99) does the *opposite*:
  pre-expanding a skill/command body into a self-contained prompt string to
  *avoid* the ToolSearch dependency for non-interactive subprocess spawns
  (`skill_expander.py:1-10` docstring). It is the closest structural
  precedent for a stub/resolve boundary (`str | None` return, "fall back to
  original on any failure" contract) even though it runs in the inverse
  direction.
- **FEAT-2671 is `status: deferred`, not implemented.** Its target module
  (`scripts/little_loops/prompts/fragment_store.py`) and the `prompts/`
  package itself do not exist yet. Step 3 above ("use FEAT-2671's fragment
  hashes... in tests") cannot be executed until FEAT-2671 lands — this
  issue's `relates_to: [FEAT-2671]` is informational only; FEAT-2671 does
  not list FEAT-2672 in its own `blocks:`. Sequence FEAT-2671 before Step 3
  of this issue, or scope Step 3's regression test to a synthetic hash
  input until the real fragment store exists.
- **Corrected integration point**: hook alongside the `resolve_host()` call
  site in `run_claude_command()` (`subprocess_utils.py:282-328`), the same
  choke point both `runners.py` call sites (slash-command and any future
  tool-catalog assembly) pass through — not `fsm/runners.py` directly,
  which never touches `resolve_host()` or a tool-definition list.
- **Config-gate pattern to follow**: `CompressionConfig`
  (`scripts/little_loops/config/features.py:528-558`, FEAT-2675's sibling
  EPIC-2456 child) — plain dataclass, lenient `from_dict()` ignoring
  unknown keys, wired at four sites: `config/core.py:226` (parse),
  `config/core.py:303-305` (property accessor), `config/core.py:682-688`
  (`to_dict()` — must be listed explicitly, not `dataclasses.asdict()`),
  and `config/__init__.py:48,96` (re-export + `__all__`), plus a matching
  `config-schema.json` block (`additionalProperties: false`). The
  `None`-default-param pattern at the call site
  (`fsm/executor.py:207-211`, `compression_config: CompressionConfig | None
  = None`) guarantees "constructed without the new param behaves exactly
  like before" — the same contract this issue's "default-off, no behavior
  change" AC needs.
- **Module layout precedent**: `scripts/little_loops/compression/__init__.py`
  (28 lines) re-exporting from `compression/heuristic.py` (297 lines) is the
  template for `scripts/little_loops/tools/__init__.py` re-exporting from
  `tools/deferred.py`. `scripts/little_loops/tools/` does not exist yet.
- **Test pattern to follow**: `scripts/tests/test_fsm_executor.py:178-267`
  `class TestCompressionHook` — `test_none_config_leaves_action_identical`,
  `test_short_action_passes_through` style assertions are the direct model
  for this issue's "default-off; no behavior change" AC. Config-dataclass
  tests follow `scripts/tests/test_config.py:2789-2856`
  `TestCompressionConfig`/`TestBRConfigCompressionIntegration` (including a
  `test_reexported_from_config_package` re-export check), and schema tests
  follow `scripts/tests/test_config_schema.py:295-316`
  `test_compression_in_schema`.
- **Gap-analysis follow-up (2026-07-18) — MCP ruled out as the missing tool
  catalog.** The confidence-check's central blocker ("no tool-definition
  catalog exists to defer against") was re-checked against the one other
  candidate source of full tool JSON schemas in this codebase: MCP.
  `scripts/little_loops/mcp_call.py` does perform a JSON-RPC
  `tools/list`/`tools/call` handshake against servers declared in
  `.mcp.json` (currently `{"mcpServers": {}}`, empty in this repo), but it
  is a standalone one-shot CLI (`mcp-call server/tool-name '{...}'`) — it
  queries and invokes a single tool per process, and does not assemble a
  tool-schema catalog into any prompt-assembly path (`fsm/runners.py`,
  `subprocess_utils.run_claude_command()`, `host_runner.py`). This confirms
  the confidence-check's finding with no remaining unexamined candidate:
  the codebase has no code path, MCP or otherwise, that serializes full
  tool-definition JSON into a request the way the Anthropic Messages API's
  `defer_loading`/`tool_reference` pattern expects. The architectural
  question flagged in Confidence Check Notes § Gaps to Address remains
  unresolved and still blocks implementation — this only narrows the
  remaining open question to "should this issue instead target Claude
  Code's host-side Skill/ToolSearch deferred-loading surface (the mechanism
  little-loops currently relies on rather than reimplements, per the
  "Deferred tools" already means something else finding above), or is it
  out of scope until little-loops makes a direct Anthropic Messages API
  call somewhere?"
- **Gap-analysis follow-up (2026-07-18, later pass) — the "FEAT-2671 is
  `status: deferred`" finding above is now stale.** `FEAT-2671` completed
  at `2026-07-18T18:39:16Z` (`status: done`) and its target module
  `scripts/little_loops/prompts/fragment_store.py` now exists on disk
  (confirmed via `ls`), per commit `67acb1e6 feat(prompts): content-hash
  fragment store for cache stability (FEAT-2671)`. This resolves the
  "Dependency risk" Outcome Risk Factor and the matching "Gaps to Address"
  bullet below: Step 3's cache-breakpoint regression test can now run
  against real fragment hashes rather than a synthetic input. This does
  not affect the `blocks`/`depends_on` sequencing correction below (that
  was about FEAT-2673 being the missing SDK call site, unrelated to
  FEAT-2671's status).
- **Refinement pass (2026-07-18) — the open architectural question above is
  now answerable: the missing SDK call site is planned, in FEAT-2673, and
  sequenced on the wrong side of this issue.** Grepped the whole repo for
  `import anthropic`/`anthropic.Anthropic`/`anthropic.Client` (agent-verified,
  not a re-guess): the only hits are `scripts/tests/test_release_gate.py`
  (synthetic strings written to `tmp_path` fixtures to test a lint rule) and
  a conditional `python -c "import anthropic"` in
  `scripts/tests/fixtures/streaming_parity/rebuild.sh:47`. `scripts/pyproject.toml`
  does not list `anthropic` as a dependency in any group (`llm = []` is
  empty). There is no direct-SDK call site today, confirming the earlier
  finding — but `.issues/features/P2-FEAT-2673-f1-cache-control-ephemeral-integration-and-cache-marking-cost-oracle.md`
  (F1 itself, `relates_to: [FEAT-2672]`) is exactly that call site under
  construction: its Implementation Steps add `anthropic` to
  `scripts/pyproject.toml` and introduce `build_anthropic_request()` in
  `host_runner.py` (~80 LOC) which marks `cache_control: ephemeral` on
  "system, tool, and stable-skill blocks" — i.e. FEAT-2673 is the first (and
  currently only planned) place in this codebase where full tool-definition
  JSON would be serialized into a request. **This issue currently has
  `blocks: [FEAT-2673]` and FEAT-2673 has `depends_on: [FEAT-2671,
  FEAT-2672]` (EPIC-2456 Children table, line 203) — the sequencing this
  issue's own frontmatter encodes is backwards from what the architecture
  requires.** Deferred-tool-loading has nothing to attach to until
  `build_anthropic_request()` exists; this issue should `depends_on:
  FEAT-2673`, not gate it. Recommend resolving via `/ll:decide-issue` or a
  manual EPIC-2456 sequencing correction (swap the `blocks`/`depends_on`
  edges on both FEAT-2672 and FEAT-2673, and update the EPIC's Children
  table) before this issue is implementation-ready — this refine pass did
  not modify cross-issue relationship fields, since that's a multi-file
  sequencing decision outside `/ll:refine-issue`'s single-issue scope.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

4. Wire `BRConfig.deferred_tools` into `FSMExecutor` construction in
   `scripts/little_loops/cli/loop/run.py`, mirroring the existing
   `compression_config` wiring.
5. Verify `scripts/little_loops/fsm/executor.py`'s `ActionRunner.run()`
   dispatch (lines 779, 1562) and `scripts/little_loops/fsm/persistence.py`'s
   `PersistentExecutor` don't need changes if the `tools` param shape is
   preserved; update both if it changes.
6. Check `scripts/little_loops/issue_manager.py` and
   `scripts/little_loops/parallel/worker_pool.py` — independent
   `run_claude_command()` call sites outside `fsm/runners.py` — for the same
   gated behavior.
7. Update `docs/reference/CONFIGURATION.md` with a `## deferred_tools`
   section mirroring `## compression`.
8. Add `TestDeferredToolsConfig`/`TestBRConfigDeferredToolsIntegration` to
   `scripts/tests/test_config.py`, `test_deferred_tools_in_schema` to
   `scripts/tests/test_config_schema.py`, and `TestDeferredToolsHook` to
   `scripts/tests/test_fsm_executor.py`, following the `CompressionConfig`
   test templates.
9. Re-run `scripts/tests/test_fsm_runners.py::test_tools_kwarg_forwarded`,
   `test_subprocess_utils.py::TestRunClaudeCommandAgentToolsFlags`, and
   `test_host_runner.py`'s `tools`/`CapabilityNotSupported` assertions to
   confirm no shape regression.

### Wiring Phase — Round 2 (added by `/ll:wire-issue`)

_A second wiring pass (this issue already had one prior pass) surfaced a
handful of items missed the first time — mostly documentation parity and
specific test classes, not new architectural surface:_

10. Add `tools/` entry to `CONTRIBUTING.md`'s package-tree diagram once the
    sub-package exists.
11. Add a parallel `## little_loops.tools` section to `docs/reference/API.md`
    mirroring `## little_loops.compression`.
12. Update `docs/development/TESTING.md`'s `MockActionRunner` snippet if the
    `tools` param shape changes.
13. Update `scripts/little_loops/fsm/fsm-loop-schema.json`'s state-level
    `tools` property and `docs/generalized-fsm-loop.md` /
    `skills/create-loop/reference.md`'s `tools:` field docs if the
    loop-authoring `tools:` YAML field's meaning changes (this is the
    loop-YAML schema, distinct from `config-schema.json`).
14. Extend gated-behavior test coverage into the specific test classes named
    in the Tests section round-2 addendum (`test_issue_manager.py`,
    `test_worker_pool.py`, `test_runner_spec.py`) rather than adding wholly
    new test files for those three call paths.

## Files to Modify

- new `scripts/little_loops/tools/deferred.py` (~90 LOC)
- `scripts/little_loops/fsm/runners.py` (gated wiring)
- new `scripts/tests/test_deferred_tools.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Corrected/additional wiring sites (see Implementation Steps findings
  above for rationale):
  - `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
    (lines 282-328), the actual `resolve_host()` call site
  - `scripts/little_loops/config/features.py` — new `DeferredToolsConfig`
    dataclass, modeled on `CompressionConfig` (lines 528-558)
  - `scripts/little_loops/config/core.py` — parse (~226), accessor
    (~303-305), `to_dict()` (~682-688)
  - `scripts/little_loops/config/__init__.py` — re-export + `__all__`
    (~48, 96)
  - `scripts/little_loops/config-schema.json` — matching schema block
  - new `scripts/little_loops/tools/__init__.py` — re-export shim
- `scripts/little_loops/fsm/runners.py` may still need a small touch
  (`ActionRunner.run()`'s `tools` param, lines 36-51) if the deferred-stub
  representation changes what gets passed as `tools`, but it is not the
  `resolve_host()` integration point the original Step 2 described.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` (round 2):_
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()`
  (lines ~263-264) is the actual site that serializes the `tools` list into
  the `--tools` CSV flag; not previously listed as its own Dependent Files
  bullet even though the Codebase Research Findings above already cite it.
  [Agent 1 finding, round 2]
- `scripts/little_loops/cli/generate_skill_descriptions.py` — imports
  `run_claude_command`; check whether it passes a `tools` kwarg that a
  deferred-stub representation would affect. [Agent 1 finding, round 2]
- `scripts/little_loops/workflow_sequence/__init__.py` — imports
  `run_claude_command`; independent call path outside `fsm/runners.py`.
  [Agent 1 finding, round 2]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — dispatches `ActionRunner.run()`
  (call sites at lines 779, 1562) that threads the `tools` param through to
  `run_claude_command()`; also the file holding the
  `compression_config: CompressionConfig | None = None` wiring pattern
  (line ~207-211) this issue's config wiring must mirror. [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` wraps
  `FSMExecutor`, inheriting the same `tools`/config-flow surface. [Agent 1
  finding]
- `scripts/little_loops/cli/loop/run.py` — wires `BRConfig.compression` into
  `FSMExecutor(compression_config=...)`; the equivalent
  `BRConfig.deferred_tools` → `FSMExecutor` wiring must be added here.
  [Agent 1 finding]
- `scripts/little_loops/issue_manager.py` — calls `run_claude_command()` and
  `expand_skill()` directly, a call path independent of
  `fsm/runners.py`/`DefaultActionRunner.run()`. [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py` — calls
  `run_claude_command()` from concurrent workers (ll-parallel). [Agent 1
  finding]
- `scripts/little_loops/runner_spec.py` — `ActionSpec`/`RunnerType`
  dispatch abstraction (post c835911a refactor) that also imports
  `resolve_host()`/`run_claude_command()`; check whether the shared
  dispatch layer needs a `tools`-shape touch. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` (round 2):_
- `CONTRIBUTING.md` — maintained `scripts/little_loops/` package-tree diagram
  (around the `compression/` entry, ~line 315-317) needs a parallel `tools/`
  entry once the new sub-package lands; this tree tracks what's actually
  implemented (FEAT-2671's `prompts/` is correctly absent since it's
  `status: deferred`). [Agent 2 finding, round 2]
- `docs/reference/API.md` § `## little_loops.compression` (~line 7539) — the
  module-reference-section precedent; a parallel `## little_loops.tools`
  section is the documented convention for the new `tools/deferred.py`
  module, distinct from the already-flagged `#### run_claude_command`/
  `#### ActionRunner Protocol` entries. [Agent 2 finding, round 2]
- `docs/development/TESTING.md` — `MockActionRunner` example snippet
  (~line 616-630) reproduces `ActionRunner.run()`'s signature including
  `tools: list[str] | None`; a third site (beyond API.md and
  `fsm/runners.py`) that goes stale if the `tools` shape changes. [Agent 2
  finding, round 2]
- `scripts/little_loops/fsm/fsm-loop-schema.json` — the FSM **loop-YAML**
  schema's state-level `tools` property (~line 509-515, distinct from
  `config-schema.json`, which governs project config, not loop authoring);
  update if the deferred-stub representation changes what a state's
  `tools:` field accepts. [Agent 2 finding, round 2]
- `docs/generalized-fsm-loop.md` — FSM field reference table's `tools:`
  entry (~line 350), documents the same loop-YAML field for loop authors.
  [Agent 2 finding, round 2]
- `skills/create-loop/reference.md` § `#### tools (Optional)` (~line
  490-509) — create-loop skill's own explanation of the `tools:` field.
  [Agent 2 finding, round 2]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### run_claude_command` (~2358-2374) and
  `#### ActionRunner Protocol` (~5334-5352) reproduce the current
  signatures verbatim (already stale independent of this change); update
  if `tools`' shape changes. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `## compression` section
  (~1420-1458, field-by-field table + JSON example) is the doc pattern a
  new `## deferred_tools` section must mirror for `DeferredToolsConfig`.
  [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — documents per-host `tools`
  support gaps (Codex/Gemini `CapabilityNotSupported`, OpenCode/Pi
  `HostNotConfigured`); note if deferred-loading changes what's supported.
  [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue` (round 2):_
- `scripts/tests/test_issue_manager.py` — `TestRunClaudeCommand` (~1141),
  `TestRunWithContinuation` (~1205, guillotine/option-j/sentinel methods),
  `TestDecisionNeededGate` (~3693), `TestAutoManagerLearningGate` (~3794),
  `TestFallbackVerification` (~2446), `TestReadyIssueErrorHandling` (~1914)
  — all patch `little_loops.issue_manager.run_claude_command`; add
  gated-behavior assertions here for the `issue_manager.py` call path.
  [Agent 3 finding, round 2]
- `scripts/tests/test_worker_pool.py` — `TestWorkerPoolRunClaudeCommand`
  (~2433), `TestRunWithContinuation` (~2518), `TestWorkerPoolProcessIssue`
  (~1997), `TestWorkerPoolDecisionNeededGate` (~2904) — worker-pool analogs
  patching `worker_pool._run_claude_command`. [Agent 3 finding, round 2]
- `scripts/tests/test_runner_spec.py` — `TestRunActionDispatch` (~67:
  `test_skill_dispatch_matches_legacy_shape`, `test_prompt_dispatch_matches_legacy_shape`,
  `test_mcp_dispatch_matches_legacy_shape`, `test_cmd_dispatch_matches_legacy_shape`)
  — dispatch-shape tests per `RunnerType` that a `tools`/deferred-tools kwarg
  addition to `ActionSpec` would need to touch, particularly SKILL/PROMPT
  dispatch. [Agent 3 finding, round 2]
- No exact config-schema.json key-enumeration test exists (confirmed by
  Agent 3) — `test_config_schema.py` only does per-key presence checks, so
  no test needs updating purely for exhaustive-key-set reasons when
  `deferred_tools` is added. [Agent 3 finding, round 2]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add `TestDeferredToolsConfig` mirroring
  `TestCompressionConfig` (~2789-2856): `test_reexported_from_config_package`,
  `test_from_dict_defaults`, `test_from_dict_with_values`,
  `test_from_dict_ignores_unknown_keys`, plus a
  `TestBRConfigDeferredToolsIntegration` mirroring
  `TestBRConfigCompressionIntegration`. [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_deferred_tools_in_schema`
  mirroring `test_compression_in_schema` (~295-316). [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add a `TestDeferredToolsHook` class
  mirroring `TestCompressionHook` (~178-267), starting with a
  `test_none_config_leaves_action_identical`-style default-off assertion.
  [Agent 3 finding]
- `scripts/tests/test_fsm_runners.py::test_tools_kwarg_forwarded` (~465) —
  existing coverage of the `tools` kwarg forwarding
  (`DefaultActionRunner.run()` → `run_claude_command`); update if the
  deferred-stub representation changes what's passed as `tools`. [Agent 3
  finding]
- `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandAgentToolsFlags`
  (~1786-1932) — six tests asserting exact `--tools` CSV-join construction;
  breaks if `tools` serialization changes shape. [Agent 3 finding]
- `scripts/tests/test_host_runner.py::test_build_streaming_includes_agent_and_tools`
  (~147) and `test_claude_runner_matches_legacy_args` (~121) — asserts
  `ClaudeCodeRunner.build_streaming()`'s `--tools` output; also the
  `CapabilityNotSupported` `match="tool"` assertions for Codex/Gemini
  (~502-510, ~871-878) — re-validate if warning text or `tools` truthiness
  changes. [Agent 3 finding]

## Acceptance Criteria

- [ ] Cache breakpoint (static-prefix hash per FEAT-2671) survives a
      5-skill catalog churn (regression test, per EPIC-2456 Success
      Metrics F1 row).
- [ ] Deferred stubs round-trip: a deferred tool invoked by the model
      resolves to its full definition without error.
- [ ] Default-off; no behavior change unless the config flag is set.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18; re-scored 2026-07-18 (later
pass) after FEAT-2671 completed and the FEAT-2672/FEAT-2673 sequencing was
corrected — see Gap-Analysis Correction above._

**Readiness Score**: ~~45/100~~ **62/100** → STOP — NOT READY
**Outcome Confidence**: ~~38/100~~ **41/100** → VERY LOW

### Gaps to Address
- No tool-definition catalog exists in this codebase for "deferred tool
  loading" to defer against: little-loops passes tool *names* as a
  `--tools` CSV flag to host CLI subprocesses (`host_runner.py`), not full
  Anthropic Messages API tool JSON schemas via a direct SDK call. The AC
  "a deferred tool invoked by the model resolves to its full definition"
  has no existing data structure to attach to. Resolve what "deferred"
  means in a CLI-flag architecture (or prove a direct-SDK path exists)
  before wiring config plumbing around it. **Still open** — FEAT-2673
  (the planned SDK call site) has not landed yet.
- ~~FEAT-2671 (fragment store), which Step 3's cache-breakpoint regression
  test depends on, is `status: deferred` and not implemented~~ —
  **RESOLVED 2026-07-18**: FEAT-2671 is `status: done`;
  `scripts/little_loops/prompts/fragment_store.py` exists. Step 3 can now
  target real fragment hashes.
- Architecture Compliance concern: the corrected integration point
  (`subprocess_utils.run_claude_command`) is a CLI-arg assembly shim, not
  an Anthropic API request builder — confirm "withholding full tool
  definitions from the initial request" is achievable at all in a
  subprocess/host-CLI architecture before building the `DeferredToolsConfig`
  plumbing. **Still open.**
- New (this pass): this issue's `depends_on` now correctly points to
  FEAT-2673 (sequencing corrected via `/ll:decide-issue`, 2026-07-18), but
  FEAT-2673 is itself `status: open` — the dependency is correctly
  ordered but not yet satisfied.

### Outcome Risk Factors
- Deep architectural complexity: the deferred-loading pattern has no
  internal precedent in this codebase's host-CLI subprocess architecture —
  no existing test exercises a tool-definition catalog to defer, making
  this a novel mechanism that should be proven with a spike before the
  surrounding config plumbing is built.
- Broad blast radius: 6 downstream call sites (`fsm/executor.py`,
  `fsm/persistence.py`, `cli/loop/run.py`, `issue_manager.py`,
  `parallel/worker_pool.py`, `runner_spec.py`) require review even for a
  default-off config flag.
- ~~Dependency risk: FEAT-2671 (fragment store), which Step 3's
  cache-breakpoint regression test relies on, is `status: deferred` and
  not yet implemented.~~ **RESOLVED 2026-07-18** — see Gap-Analysis
  Correction below. Residual dependency risk: FEAT-2673 (the SDK call
  site this issue now correctly `depends_on`) is `status: open`, not yet
  implemented.

### Gap-Analysis Correction (2026-07-18)

_Added by `/ll:refine-issue --gap-analysis` — the score above is stale on
one input:_ FEAT-2671 is now `status: done` (completed
`2026-07-18T18:39:16Z`; `scripts/little_loops/prompts/fragment_store.py`
exists). The "Dependency risk" Outcome Risk Factor and its matching "Gaps
to Address" bullet above no longer hold — that removes one of three
readiness gaps and one of three risk factors. The remaining two Gaps to
Address (no tool-definition catalog to defer against; CLI-shim vs.
SDK-request-builder architecture concern) are unaffected and still block
implementation. Re-run `/ll:confidence-check FEAT-2672` for an updated
score.

## Session Log
- `/ll:confidence-check` - 2026-07-18T19:24:20 - `4fd1c868-e4bb-4ba3-ab7e-80d1d257cbcd.jsonl`
- `/ll:refine-issue` - 2026-07-18T19:22:46 - `4fd1c868-e4bb-4ba3-ab7e-80d1d257cbcd.jsonl`
- `/ll:decide-issue` - 2026-07-18T19:08:23 - `b87fa325-b414-4446-90d5-717323b3c962.jsonl`
- `/ll:wire-issue` - 2026-07-18T19:02:03 - `b56911e2-d36a-4d3d-ad87-565351fc7609.jsonl`
- `/ll:refine-issue` - 2026-07-18T18:47:15 - `e1a29e23-79a5-40a2-84d8-5118e300d506.jsonl`
- `/ll:refine-issue` - 2026-07-18T17:37:16 - `834aee9c-ae29-4bf7-aa8b-89d6413a8ac1.jsonl`
- `/ll:confidence-check` - 2026-07-18T17:45:00 - `49b96ed6-2d83-486c-917f-ea670d4d9c34.jsonl`
- `/ll:wire-issue` - 2026-07-18T17:31:02 - `28188d09-16b4-4278-b5fc-226cc7200e93.jsonl`
- `/ll:refine-issue` - 2026-07-18T17:25:27 - `3c8acda0-fa9f-4e4f-b3a1-45231b42b447.jsonl`
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-9] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2)

## Status

**Open** | Created: 2026-07-18 | Priority: P2
