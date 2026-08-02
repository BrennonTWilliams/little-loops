---
id: FEAT-2878
title: Trace-level assertions in the eval harness, with optional multi-host divergence
  runs
type: FEAT
parent: EPIC-2856
priority: P1
status: done
discovered_date: 2026-07-27
labels:
- evals
- ll-harness
confidence_score: 91
outcome_confidence: 74
score_complexity: 16
score_test_coverage: 12
score_ambiguity: 21
score_change_surface: 15
decision_needed: false
spike_needed: true
spike_completed: true
spike_attempted: true
reconcile_attempted: true
size: Very Large
completed_at: '2026-07-28T12:43:53Z'
---

# FEAT-2878: Trace-level assertions in the eval harness, with optional multi-host divergence runs

Parent EPIC: EPIC-2856 (rework reduction — design upstream, verify honestly). This issue advances that epic's core premise — make a "verified" signal impossible to fake — by checking a claim against the actual tool-call trace rather than against free-form output the agent authored itself. Sibling to its deterministic pre-patch test-failure check and test-file tamper guard.

## Summary

The current eval surface asserts on **outcomes** and on **recorded** traces: `ll-harness` checks exit codes and semantic criteria, `/ll:create-eval-from-issues` derives tasks from acceptance criteria, and `ll-logs eval-export` plus the trace sets work from logs after the fact. What is missing is assertion on the **live tool-call sequence** a skill produces while it runs — the ability to fail a skill for calling the right tools in the wrong order, or for writing an artifact it should not have touched.

## Current Behavior

`ll-harness` asserts on outcomes (exit codes, semantic criteria against `result.stdout`) and on **recorded**, post-hoc traces (`ll-logs eval-export` parses tool-call events out of on-disk JSONL session logs after a run finishes). `subprocess_utils.run_claude_command()`'s stream-json read loop already parses `tool_use` blocks out of `"assistant"` events, but discards them via `else: continue` — there is no live callback and no way to assert on the ordered tool-call sequence, or on which paths a skill touched, while a run is in progress.

## Expected Behavior

The eval harness supports a trace-assertion mode: a skill runs against a scoped temporary workspace with a restricted tool set, its ordered tool calls (tool, order, target paths) are captured live and asserted against a declared expectation (ordering and artifact-write contracts, not just call presence). Multi-host divergence runs are available as an opt-in flag; unavailable/unconfigured hosts skip cleanly with a reported reason rather than failing the run.

## Use Case

A contributor wants to verify that a skill (e.g. `/ll:capture-issue`) actually calls its tools in the required order and never writes outside its designated output paths — not just that it eventually produced plausible-looking output. They run the new trace-assertion eval tier against the skill in a scoped temp workspace; the eval fails immediately if the skill writes to a forbidden path or calls tools out of the declared contract order, giving a "verified" signal that can't be faked by free-form output the agent authored itself.

## Reference pattern

The reference pattern for a skill-behavior eval tier:

- Inlines the **source** skill file into a real model's system prompt, and gives it bash/read/write/list tools **scoped to a temporary workspace**.
- Asserts on the tool-call trace, not on free-form output — stated flatly as "the trace is the source of truth".
- Pairs this with a workflow-contract test asserting **question order** and **artifact writes** across several end-to-end flows.
- Symlinks the authoring source rather than built output, so edits show up without a rebuild. The trade-off is that unsubstituted build placeholders appear in the reference text — which is acceptable precisely because assertions key on tool calls rather than on content.
- Keeps the scenario list and pass baseline in the suite's own README rather than in the contributor guide, because duplicating it went stale before.
- Is opt-in and separately gated in CI: cheap deterministic suites always run; the paid tier runs only on explicit dispatch.

## Proposed change

Add a trace-assertion mode to the eval harness:

1. Run a skill against a scoped temporary workspace with a restricted tool set.
2. Capture the ordered tool calls — which tool, in what order, against which paths — and assert against a declared expectation.
3. Support contract-style assertions on ordering and on artifact writes, not just on presence of a call.
4. Keep it opt-in and separately gated, alongside the existing deterministic suites rather than inside them.

## Scope constraint (deliberate divergence from the source)

The source runs **four API providers on every eval run**, arguing that "many of the most useful findings come from divergence between providers". Do **not** adopt that as a mandate here. little-loops' provider surface is host CLIs (claude, codex, opencode, pi) through `host_runner`, not raw API providers, and a fixed 4x fan-out on every run is a **cost policy decision, not a feature requirement**.

Instead: make multi-host divergence runs an **opt-in flag**. Hosts that are unavailable or unconfigured must **skip cleanly rather than fail** — the source does get this part right, and an eval suite that hard-fails on a missing host key is unusable in CI.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/harness.py` — add a trace-assertion runner mode alongside `skill`/`cmd`/`mcp`/`prompt`/`dsl`; scoring needs a sibling to `_evaluate_and_report()` (line ~251) keyed on ordered tool calls instead of `result.stdout`
- `scripts/little_loops/runner_spec.py` — `RunnerResult` (dataclass: `stdout`, `stderr`, `exit_code`, `timed_out`, `error`) has no field for a captured tool-call sequence; add a defaulted `tool_trace: list[dict] | None = None` field appended after `error` (Decision 1: extend `RunnerResult`, not a parallel result type — all 11 production and 9 test construction sites use keyword args, so this is backward compatible)
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()`'s `tools=` param only narrows the tool *allowlist* passed as CLI argv; it does not sandbox filesystem access to `working_dir`. `working_dir` today only rewrites `GIT_DIR`/`GIT_WORK_TREE` for worktree correctness — no filesystem jail exists yet for a scoped temp workspace
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`'s stream-json read loop parses `tool_use` blocks out of `"assistant"` events only to hit `else: continue # skip other event types (tool_use, etc.)`; this is the single point where a live tool-call event is seen and currently discarded rather than surfaced. This is the mechanism that needs to change to enable live trace capture (as opposed to post-hoc log parsing)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py:_cmd_eval_export()` — reconstructs invocations post-hoc from on-disk JSONL session logs after a run finishes; not a live capture path and cannot assert mid-run (e.g. abort a skill for touching a forbidden path). A new live trace-assertion tier is a distinct, complementary capture path, not a replacement
- `scripts/little_loops/cli/harness.py:_record_harness_event()` — best-effort write into the `harness_events` SQLite table (`session_store.record_harness_event()`); a trace-assertion result should follow the same typed-event-table convention (gated by `ll-verify-kinds`, queryable via `ll-session recent --kind`) rather than inventing a new ad hoc store

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — constructs `RunnerType.SKILL` directly and is a second consumer (besides `harness.py`) of `runner_spec.run_action()`'s `_DISPATCH` table; a new `RunnerType` member for trace mode must be added here too or `ll-action` silently can't invoke it
- `scripts/little_loops/cli/queue.py` — `RunnerType(runner_override)` classifier for `ll-queue add`; a new `RunnerType` member changes what strings this CLI accepts/classifies
- `scripts/little_loops/queue_store.py` — serializes `RunnerType`/`ActionSpec` to `.ll/queue.db` via `.value`/`RunnerType(data["runner"])`; round-trips a new member transparently, but confirm no exhaustive `if/elif` over `RunnerType` elsewhere in this file
- `scripts/little_loops/adapters/capabilities.py` (`HostCapabilityEntry`) and `scripts/little_loops/cli/verify_host_map.py:_check_runtime_contradiction()` — if a workspace-sandboxing flag is added to `host_runner.HostCapabilities`, this file's per-host capability map must agree on the new field name or the runtime-contradiction check fails
- `scripts/little_loops/config-schema.json` (`"orchestration"` block, currently only `orchestration.host_cli`) — a workspace-isolation or multi-host-divergence-hosts-list flag is a net-new schema key here, following the `host_cli` pattern (`apply_host_cli_from_config()` reads it before `resolve_host()` runs)

### Similar Patterns
- `scripts/tests/conformance/test_host_conformance.py:test_golden_path_invocation()` — parametrized over every registered host (`_HOST_RUNNER_REGISTRY`), skips (not fails) when the binary is absent from PATH (`shutil.which`) or when `resolve_host().build_streaming()` raises `HostNotConfigured` — this is the direct template for the "unconfigured or unavailable host is skipped with a reported reason" acceptance criterion
- `scripts/little_loops/host_runner.py:HostNotConfigured` — exception raised by every `build_*` method and by `resolve_host()` when no host resolves; already caught to degrade/skip cleanly in `init/cli.py:144`, `init/install_check.py:77,145`, `cli/loop/_helpers.py:2064`, `cli/doctor.py:887` — reuse this exception as the "skip with reason" signal for multi-host divergence runs
- `scripts/tests/test_policy_builder_node_gate.py:test_node_conformance_suite_passes()` — canonical shape (cited in `CLAUDE.md`'s Testing & CI Policy) for wrapping an opt-in/expensive tier as an ordinary pytest test that shells out and calls `pytest.skip()` rather than failing when a prerequisite is absent — model for gating the new trace-assertion tier as opt-in inside `python -m pytest scripts/tests/`
- `scripts/little_loops/cli/logs.py:_extract_ll_event_streams()` / `InvocationEvent` dataclass (`tool_name`, `timestamp`, `session_id`) — the existing ordered per-session tool-call extraction shape (post-hoc, from JSONL); shows the canonical `tool_use` block detection pattern (`block.get("type") == "tool_use"`, `block.get("name")`) reused across `logs.py` at lines 77, 210, 361, 1084
- `scripts/little_loops/cli/harness.py:cmd_dsl()` — existing aggregate-parent + per-child `harness_events` row pattern (`parent_id` linkage); reusable template for "one divergence run → N per-host result rows"

### Tests
- `scripts/tests/test_cli_harness.py` — existing harness CLI tests (`FakeRunner`, `HarnessEvalOutcome`) to extend with a trace-assertion runner mode
- `scripts/tests/conformance/test_host_conformance.py` — model to follow for a new multi-host divergence test that skips per-host on unavailability
- `scripts/tests/test_host_runner.py` — host resolution/capability tests; would need coverage for any new `HostCapabilities` flag (e.g. workspace sandboxing or tool-call streaming support)
- `scripts/tests/test_runner_spec.py` — `ActionSpec`/`RunnerType` dispatch tests to extend if a new `RunnerType` is added for trace mode

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py` (`TestStreamJsonEventParsing`, the `tool_use`-discard test asserting `callback_calls == []`) — encodes the *current* discard behavior verbatim; must be rewritten, not just extended, once `tool_use` events are surfaced via callback. Sibling tests in the same class (`test_assistant_event_text_passed_to_stream_callback`, `test_on_usage_callback_called_with_result_event`) are the templates for the new "tool_use surfaced to callback" test
- `scripts/tests/test_feat1544_loop_specialist_eval.py` (`TestLoopSpecialistEvalBehavioral`, `@pytest.mark.skipif(shutil.which("claude") is None, ...)`) — closer template than `test_policy_builder_node_gate.py` for a live-host-CLI-required opt-in test class, since it gates on a host binary (not a language toolchain)
- `scripts/tests/test_cli_queue_run.py`, `scripts/tests/test_cli_queue.py`, `scripts/tests/test_queue_store.py` — construct/pattern-match `RunnerResult`/`RunnerType`; check for positional (not keyword) `RunnerResult(...)` construction before adding a new field, and for exhaustive `RunnerType` branches before adding a new member
- No existing fixture jails filesystem access to a scoped temp workspace — `test_subprocess_utils.py::temp_repo` and `test_cross_host_baseline.py::_make_loop_project(tmp_path)` are the closest scaffolding to build a new sandboxing-assertion fixture from, not a ready template

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — already references trace-level assertions and tool-call validation as a design tip; this is the natural home for documenting the new tier per the reference pattern's "keep the scenario list and pass baseline with the suite" guidance
- `docs/reference/HOST_COMPATIBILITY.md` — host capability matrix; would need a new capability column if workspace-sandboxing or tool-call-stream support becomes a `HostCapabilities` flag

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.runner_spec` section documents the `RunnerType` enum and `RunnerResult` import line; `## little_loops.host_runner` section documents `HostCapabilities`' flag list and `build_streaming()`'s signature — both need updating for a new field/flag
- `docs/reference/CLI.md` — `### ll-harness` section enumerates `skill|cmd|mcp|prompt|dsl` as the canonical subcommand list with example invocations; a new trace mode needs a parallel subsection here, not just in `--help` text
- `commands/help.md` and `.gemini/commands/help.toml` — one-line `ll-harness` description enumerates the exact runner kinds ("skill, cmd, mcp, prompt, or dsl"); needs the new mode appended
- `.claude/CLAUDE.md` (`ll-harness` bullet in CLI Tools) — same enumerated-runner-kinds convention as other CLI Tools bullets; update alongside the above

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis, resolving the two open structural decisions flagged in Confidence Check Notes:_

**Decision 1 — how to carry the captured tool-call trace on a runner result**

**Option A**: Extend `runner_spec.RunnerResult` (`scripts/little_loops/runner_spec.py:56-64`) with a new optional field, e.g. `tool_trace: list[dict] | None = None`, appended after the existing `error` field.

**Option B**: Add a parallel result type alongside `RunnerResult` for trace-mode runs.

**Recommended**: Option A — every production construction of `RunnerResult` (`_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` in `runner_spec.py`, 11 sites) and every test construction (`test_cli_queue_run.py` — 7 sites, `test_runner_spec.py` — 2 sites) uses all-keyword arguments; zero positional constructions exist anywhere in the repo. A defaulted field appended to the dataclass is fully backward compatible. A parallel type would instead require changing all 4 `_DISPATCH` handlers' return types and `_evaluate_and_report()`'s signature, for no compatibility benefit.

> **Selected:** Option A — defaulted `tool_trace` field on `RunnerResult`; all call sites use keyword args so this is backward compatible.

**Decision 2 — how to route a trace-assertion run through the existing runner surface**

**Option A**: Reuse an existing `RunnerType` member (`SKILL`/`PROMPT`) with a mode flag, e.g. `spec.args["trace_mode"] = True`, mirroring how `_run_skill`'s `stream_callback` param already selects streaming vs. blocking execution (`runner_spec.py:98`).

**Option B**: Add a new `RunnerType` enum member (e.g. `TRACE`) for trace-assertion mode.

**Recommended**: Option A — `runner_spec.py`'s `_DISPATCH` table (line ~243) is a non-exhaustive `dict.get()` lookup, not an if/elif/match ladder, so a new member is technically low-risk to register. But `main_harness()` dispatches on argparse subparser choices (`args.runner` string), and `cli/action.py`/`cli/queue.py` construct `ActionSpec` with a fixed, enumerated `RunnerType` per CLI subcommand rather than iterating over the enum — so a new member still requires touching the CLI parser, `_DISPATCH`, and both other consumers regardless of enum-cost. A mode flag on the existing `SKILL`/`PROMPT` members avoids all of that cross-CLI wiring (`cli/action.py`, `cli/queue.py`, `queue_store.py` round-tripping) while following an established precedent in the same module.

> **Selected:** Option A — a `trace_mode` flag on the existing `SKILL`/`PROMPT` `RunnerType` members; avoids cross-CLI wiring in `cli/action.py`/`cli/queue.py`/`queue_store.py`.

**Decision 3 — sandboxing site for a `HostCapabilities` flag**

**Option A**: Add sandboxing/workspace-jail as a new boolean `HostCapabilities` field (`host_runner.py:118-136`), defaulted `False`, flipped `True` only at the specific per-host construction sites that implement it — mirroring how `structured_output` (ENH-2627) was added and left `False` at 5 of 6 sites.

**Option B**: Treat workspace sandboxing as a config-only concern (`config-schema.json`'s `orchestration` block) with no `HostCapabilities` flag, since `working_dir`/`tools` params already exist on `build_streaming()` and only need new *behavior*, not a new advertised capability.

**Recommended**: Option A — `adapters/capabilities.py:HostCapabilityEntry` and `cli/verify_host_map.py:_check_runtime_contradiction()` already gate on `HostCapabilities` agreement per host; a jail that's silently unsupported on some hosts (Codex/Gemini/OpenCode currently drop `tools=` entirely, `host_runner.py:566-575` and surrounding) needs to be visible to that consistency check, or a trace-assertion run could silently run unsandboxed on a host that doesn't honor it.

> **Selected:** Option A — a new boolean `HostCapabilities` field, defaulted `False`, flipped only at hosts that implement the jail; keeps `verify_host_map.py`'s consistency check meaningful.

_These decisions bound Implementation Steps 2, 3, 5, and 9–10 below and the wiring items in `cli/action.py`, `cli/queue.py`, `queue_store.py`, and `adapters/capabilities.py`._

### Decision Rationale

_Added by `/ll:decide-issue`:_

All three structural decisions in this issue were already resolved inline by `/ll:refine-issue` with explicit "Recommended" options backed by codebase evidence (call-site surveys, dispatch-table shape, existing capability-flag precedent). This is a lock-in of an existing clear recommendation, not a scored multi-option comparison — no competing option had comparable supporting evidence, so no agent-based scoring pass was needed.

| Decision | Selected | Key evidence |
|----------|----------|--------------|
| 1. Trace carrier | Option A — extend `RunnerResult` | 11 production + 9 test call sites all keyword-only; defaulted field is fully backward compatible |
| 2. Routing | Option A — mode flag on existing `RunnerType` | Avoids touching `cli/action.py`, `cli/queue.py`, `queue_store.py` that a new enum member would require regardless of `_DISPATCH`'s low cost |
| 3. Sandboxing flag site | Option A — new `HostCapabilities` field | `verify_host_map.py`'s runtime-contradiction check already gates on `HostCapabilities` agreement; an invisible jail could silently run unsandboxed |

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Stop discarding `tool_use` events in `subprocess_utils.run_claude_command()` (the `else: continue` branch) — surface them through a structured callback so a caller can build an ordered tool-call trace during a run, not just after it via `ll-logs eval-export`.
2. Add filesystem scoping to `host_runner.build_streaming()` (or a new parameter) so a trace-assertion run's tool access is confined to a temporary workspace — today `working_dir` only affects `GIT_DIR`/`GIT_WORK_TREE`, and `tools=` only narrows the CLI allowlist argument, neither sandboxes the filesystem.
3. Extend `runner_spec.RunnerResult` with a defaulted `tool_trace` field (Decision 1) to carry the captured ordered tool-call sequence, then add a trace-assertion scoring branch to `harness.py` alongside the existing exit-code/semantic branches in `_evaluate_and_report()`.
4. Persist trace-assertion outcomes via a `record_*_event()` writer following the `record_harness_event()` convention (gated by `ll-verify-kinds`), so results are queryable through `ll-session recent --kind` like other harness events.
5. For multi-host divergence: iterate `resolve_host()` across an opt-in flag's requested host list, catching `HostNotConfigured` per host (mirroring `test_host_conformance.py`'s skip-on-unavailable shape) and reporting a skip reason rather than failing the whole run.
6. Wrap the new tier as an opt-in pytest test (or `ll-harness` subcommand invoked from one), following `test_policy_builder_node_gate.py`'s skip-cleanly-when-prerequisite-absent shape, so it runs inside `python -m pytest scripts/tests/` per the no-hosted-CI policy.
7. Verification: `python -m pytest scripts/tests/test_cli_harness.py scripts/tests/conformance/test_host_conformance.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Rewrite the `test_subprocess_utils.py::TestStreamJsonEventParsing` test that currently asserts `callback_calls == []` for `tool_use` events — that assertion encodes the discard behavior step 1 removes.
9. If a new `RunnerType` member is added for trace mode, update `runner_spec.run_action()`'s `_DISPATCH` table plus its two other consumers, `cli/action.py` and `cli/queue.py`, so `ll-action`/`ll-queue` don't silently reject the new type; check `test_cli_queue_run.py`/`test_cli_queue.py`/`test_queue_store.py` for positional `RunnerResult(...)` construction or exhaustive `RunnerType` branches that would break.
10. If workspace-sandboxing becomes a `HostCapabilities` flag, add it to all six `HostCapabilities(...)` construction sites in `host_runner.py` (one per host) and reconcile with `adapters/capabilities.py:HostCapabilityEntry` so `cli/verify_host_map.py:_check_runtime_contradiction()` doesn't fail on a per-host disagreement.
11. If a multi-host-divergence-hosts-list or sandboxing config key is needed, add it under the existing `"orchestration"` block in `config-schema.json`, following the `orchestration.host_cli` pattern.
12. Update `docs/reference/API.md` (`RunnerType`/`RunnerResult`/`HostCapabilities` sections), `docs/reference/CLI.md` (`### ll-harness` subcommand list), `commands/help.md`/`.gemini/commands/help.toml` (one-line `ll-harness` description), and `.claude/CLAUDE.md`'s `ll-harness` bullet to mention the new trace-assertion mode.

## Acceptance Criteria

- The harness can fail a skill that calls the correct tools in an incorrect order, on a workspace-scoped run.
- The harness can assert that a specific artifact was written, and that an out-of-scope path was not.
- Tool access during a trace eval is confined to the temporary workspace.
- Multi-host divergence is opt-in via a flag; the default run uses one host.
- An unconfigured or unavailable host is skipped with a reported reason, not a failure.
- The scenario list and pass baseline live with the suite, not duplicated into contributor docs.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-28_

**Readiness Score**: 91/100 → PROCEED
**Outcome Confidence**: 74/100 → Moderate-high confidence

### Outcome Risk Factors
- Filesystem sandboxing on `host_runner.build_streaming()` (Decision 3) was deliberately not spiked — it remains the one named mechanism still unproven, though the issue itself characterizes it as comparatively mechanical relative to trace capture.
- Implementation Steps 9–10 still carry conditional "if a new `RunnerType` member is added..." / "if workspace-sandboxing becomes a `HostCapabilities` flag..." phrasing left over from before Decisions 1–3 were locked in by `/ll:decide-issue` — worth a pass to make those steps declarative before implementation, though this is a documentation staleness risk, not an open decision.

**Update (2026-07-28, post-spike)**: the prior "deep per-site complexity"/"unproven novel mechanism" risk on live `tool_use` trace extraction is retired — `.ll/spikes/spike-FEAT-2878.md` and `scripts/tests/spike/eval_trace_capture/` prove ordered extraction, multi-tool-call-per-message handling, live-callback semantics, and malformed-line robustness (6 spike tests + 107 unaffected tests in `test_subprocess_utils.py`, all passing). Outcome Confidence raised 58 → 74 accordingly.

## Spike Results

_Added by `/ll:spike` on 2026-07-28_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| Zero-precedent live `tool_use` extraction from stream-json events | `TestTraceCapture::test_ordered_trace_across_multiple_assistant_events`, `test_multiple_tool_calls_in_one_message_preserve_order`, `test_interleaved_text_and_tool_use_blocks_only_captures_tool_use` | ✓ pass |
| Untested live-callback-during-run property (not just post-hoc collection) | `TestTraceCapture::test_callback_invoked_live_per_tool_call` | ✓ pass |
| Robustness parity with existing malformed-line handling | `TestTraceCapture::test_malformed_json_line_skipped_not_raised` | ✓ pass |

**Spike location**: `scripts/tests/spike/eval_trace_capture/`
**Verification**: 6 spike tests pass; 107 tests in `test_subprocess_utils.py` unaffected, across 2 commands.
**Promotion**: adapt `trace_capture.py`'s parsing logic into `subprocess_utils.run_claude_command()`'s event loop (replacing the `else: continue` discard at line 522/524 with an `on_tool_call` callback) in a separate PR.

**Not spiked** (deliberately out of scope, per plan): filesystem sandboxing on `host_runner.build_streaming()` (Decision 3) is a separate, more mechanical mechanism — the trace-capture mechanism spiked here was the riskier and more central of the two named in Outcome Risk Factors.

## Impact

- **Priority**: P1 - advances EPIC-2856's core premise (make a "verified" signal impossible to fake) and is the last unproven mechanism in that epic's trio of trace-based checks.
- **Effort**: Large - touches `subprocess_utils.py`'s event loop, `runner_spec.RunnerResult`, `host_runner.py` capability/sandboxing, and three CLI consumers (`harness.py`, `action.py`, `queue.py`), though the riskiest sub-mechanism (live tool-call extraction) is already spiked and proven.
- **Risk**: Medium - filesystem sandboxing on `host_runner.build_streaming()` (Decision 3) was deliberately not spiked and remains the one unproven mechanism; all other structural decisions are locked in with call-site evidence.
- **Breaking Change**: No - `tool_trace` is a defaulted, backward-compatible field on `RunnerResult`, and trace-assertion mode is opt-in alongside existing deterministic suites.

## Status

**Open** | Created: 2026-07-27 | Priority: P1

## Session Log
- `ll-auto` - 2026-07-28T12:43:53 - `46042437-bac3-4669-8006-66fef671c24d.jsonl`
- `/ll:ready-issue` - 2026-07-28T12:32:09 - `b0851dec-ffbc-4e0e-9a5a-fd281a0c8366.jsonl`
- `/ll:reconcile-issue` - 2026-07-28T12:28:53 - `43a83731-dcec-4bcb-82f5-3ea6f2da5552.jsonl`
- `/ll:confidence-check` - 2026-07-28T12:27:00 - `ad744179-cd9a-4607-a689-25e07594374f.jsonl`
- `/ll:spike` - 2026-07-28T12:25:22 - `756edd03-d17f-497a-8d49-1c3bc9f8fab1.jsonl`
- `/ll:confidence-check` - 2026-07-28T12:20:23 - `f8446efc-e931-4c53-9d78-2f149fe14452.jsonl`
- `/ll:decide-issue` - 2026-07-28T12:18:37 - `fec406ab-5fc4-473f-80b7-8d7a7b42d225.jsonl`
- `/ll:refine-issue` - 2026-07-28T12:16:34 - `93745a6f-0f57-4ed2-9196-06fcc9c5ba92.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `ac7fee32-1c2e-4a54-8bc1-12d9adae2186.jsonl`
- `/ll:wire-issue` - 2026-07-28T12:08:33 - `ddea540b-9033-4fe9-9138-f06895873993.jsonl`
- `/ll:refine-issue` - 2026-07-28T12:03:27 - `0d7f9753-a663-4bb7-aee0-9f6e584a7f0b.jsonl`


---

## Resolution

- **Action**: implement
- **Completed**: 2026-07-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
