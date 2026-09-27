---
id: ENH-3547
type: ENH
title: Wire model hint resolution through loop dispatch and lifecycle
priority: P2
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- multi-host
- loops
blocked_by:
- ENH-3527
relates_to:
- ENH-3533
learning_tests_required:
- anthropic
---

# ENH-3547: Wire model hint resolution through loop dispatch and lifecycle

## Summary

Wire `model_hint` resolution into every loop dispatch path: CLI actions, blocking evaluators, SDK/batch, and CLI downgrade. Preserve requested declarations through sub-loops, detach and resume, and add selection diagnostics to FSM events. This is piece 2 of ENH-3527's delivery split; ENH-3527 keeps piece 1 (declarations, resolver and config) and is the prerequisite.

## Current Behavior

- After ENH-3527, `model_hint` declarations parse and validate, but `FSMExecutor` fails fast with a not-yet-supported error before dispatch.
- CLI actions use `state.model or self.run_model` (`executor.py:2658`); evaluators use `state.model or self.fsm.llm.model` (`executor.py:3174,3221`); SDK/batch use `state.model or self.run_model or self.fsm.llm.model` (`executor.py:3570`).
- Evaluators have no SDK path: `fsm/evaluators.py` always dispatches through `resolve_host().build_blocking_json`, whatever the state's `request_path`.
- `FakeHostRunner.build_streaming` and `build_blocking_json` accept `model` but drop it from argv (`host_runner.py` ~L2095–2130), so no fake-host test can assert a resolved selection today.
- `ll-loop resume` has no `--model`/`--llm-model` flags, and loop persistence saves neither the run-level `--model` nor the `--llm-model` override. Detach forwards both (`cli/loop/runner.py:223-231`). Resume re-reads the loop YAML, so YAML declarations (including hints) survive, but run-level literal overrides are lost. This behavior predates this issue.
- Prompt compression sizes against `model=self.run_model` (`executor.py:2523`), not the state's effective model. This already happens with a literal `state.model`.

## Expected Behavior

Everything below is specified in ENH-3527 (Design → Declaration and precedence, Resolve against the effective backend, Supported artifact/host matrix, Lifecycle and model identity, Call Path). ENH-3527 remains the authoritative design; this issue owns delivering it:

- Resolve after `FSMExecutor._resolve_request_path`. SDK/batch always resolves against `anthropic-api`; a downgrade to CLI re-resolves the original declaration for that runner.
- Evaluator hints are resolved in `FSMExecutor._evaluate` against the CLI host `resolve_host()` returns (never `anthropic-api`, even on an `sdk`/`batch` state) and passed down as `model: str`; no config is threaded into `evaluators.py`.
- `FakeHostRunner` (and `FakeMinimalHostRunner`) append `--model <model>` to argv when `model` is set, so fake-host dispatch tests and the portability proof can assert the resolved sentinel (`fake-coding`, `fake-burst`, …; ENH-3527 built-in mapping). Check that `ll-fake-host` accepts or ignores the flag.
- Each dispatch adds `model_requested`, `model_resolved` and `model_backend` to its event payload and the run header. No DB columns; observed model identity stays in `usage_events.model` (ENH-3528/ENH-3538, done) and is never overwritten with a requested/resolved selection.
- **Resume (decided 2026-09-25).** Hints live only in the loop YAML, because there are no run-level hint flags. Resume re-reads the YAML, so resume preserves hint declarations without new persistence. Losing run-level `--model`/`--llm-model` on resume is older behavior for literals and **out of scope**. One consequence must be visible, not silent: a run started with `--llm-model X`, which cleared a YAML `llm.model_hint`, resumes with that hint active again. The resume header/event must show the new selection.
- **Compression.** Keep `compress_action_text(model=self.run_model)` unchanged here (out of scope, older behavior). Add a code comment that the window is sized against the run model, not the hint-resolved state model.

## Scope Boundaries

- **In scope**: dispatch wiring on every loop path, CLI downgrade re-resolution, lifecycle preservation, event/header diagnostics, portability proof, removing ENH-3527's not-yet-supported guard.
- **Out of scope**: validate warnings and docs (ENH-3548); skill/agent frontmatter (ENH-3533); persisting run-level `--model`/`--llm-model` across resume (older literal behavior); making compression hint-aware.

## Program Design

### Types

- Uses ENH-3527's model declaration and resolved-selection types; no new types.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527 (no `operation` parameter, decided 2026-09-24), called at each dispatch seam.
- Evaluator functions keep `model: str`.

### Call Path

- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `build_anthropic_request` (SDK/batch)
- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `ClaudeCodeRunner.build_streaming` / `CodexRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `resolve_model_hint` (CLI backend only) → `evaluate_llm_structured` → `build_blocking_json`

## Integration Map

- `scripts/little_loops/fsm/{executor,evaluators,runners,persistence}.py`, `subprocess_utils.py`, `cli/loop/{run,lifecycle,runner,header,info}.py`.
- `scripts/little_loops/host_runner.py` — `FakeHostRunner` / `FakeMinimalHostRunner` forward `--model`; `scripts/little_loops/fake_host` if the executable must accept the flag.
- Tests: `test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_fsm_runners.py`, `test_ll_loop_execution.py`, `test_host_runner_dispatch.py`, `test_fake_host.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Existing dispatch seams that resolve a value per-backend do so via a private `FSMExecutor` method mirroring an existing fallback chain, not an inline expression: `_resolve_action_model()` (`executor.py:3555-3566`) explicitly mirrors `state.model or self.run_model`, and `_resolve_request_path()` (`executor.py:3446-3514`) resolves per-backend with a one-shot downgrade warning via `_warn_request_path_downgrade()` (`executor.py:3546-3553`). The CLI action dispatch site (`executor.py:2654`) is the one seam still inline (`state.model or self.run_model`) rather than delegated — a pre-existing inconsistency, not a convention to preserve.
- The not-yet-supported guard this issue removes lives in `FSMExecutor.run()` (`executor.py:640-652`) and is pinned by `test_model_hints.py::TestPreDispatchGuard` (lines 269-306), which asserts `result.terminated_by == "error"` and `runner.calls == []`; those tests need updating alongside the guard's removal.
- Event payloads have no shared builder — every event type builds its own `dict[str, Any]` literal at its `self._emit(...)` call site (`_emit` at `executor.py:3925`; `action_complete` payload at `2667-2716`; `evaluate` payload at `3178-3227`). Conditional-diagnostic fields follow `if value is not None: payload[key] = value` (e.g. `effort`, `is_batch`). `payload["model"]` is already occupied by the *observed* model from `usage_events[-1].model` — distinct from the requested/resolved/backend fields this issue adds, which need their own keys.
- The console run header (`cli/loop/header.py:_render_artifact_header_lines`, line 109) is a separate concept from the event payload; no persisted "header" exists in `fsm/persistence.py` (zero matches for the term). The one existing precedent for adding a diagnostic to the console header (ENH-2869's `effort`) appends onto the single `model:` display value via an `effort: str | None` kwarg threaded through every call site, not a new row — that precedent covers appending one value, not three at once.
- Every real host runner shares one idiom for conditional argv, at nine call sites in `host_runner.py`: `if model: args += ["--model", model]`. `FakeHostRunner`/`FakeMinimalHostRunner` already accept `model` in their signatures but drop it in the body (`host_runner.py:2173-2209`, `2252-2284`), matching this issue's own Current Behavior claim.
- Dispatch-level argv assertions follow one test method per runner class, named `test_build_streaming_with_model` (`test_host_runner.py:661-667` for `ClaudeCodeRunner`; `:800-823` for `CodexRunner`, with exact-count and exact-position assertions), paired with a `test_build_streaming_without_model_omits_flag` absence test. `TestFakeHostRunner`/`TestFakeMinimalHostRunner` (`test_host_runner.py:1178-1250`, `1253-1326`) exist as test classes but have no model test today.
- The "same script across multiple hosts, assert identical behavior" shape already exists as `TestFakesAreDivergent`/`TestCompositionThroughExecutor` (`scripts/tests/conformance/test_host_composition.py:285-396`) — drives both fakes through the real `run_claude_command`/`run_blocking_json` path and asserts equal `Observed` results across hosts.
- `ll-fake-host`'s `main()` (`fake_host.py:331`) never parses argv as flags — it scans for the one element containing the `@@fake` fence and ignores everything else positionally, so it already tolerates an extra `--model X` pair without change.
- Sub-loop children are already constructed with `run_model`/`run_effort` forwarded explicitly but not the parent's per-state `model_hint` (`executor.py:1288-1302`) — the child gets its own freshly-loaded `child_fsm`, so state-level declarations already don't propagate today. That half of the sub-loop AC needs a test, not a code change.
- `cmd_resume` (`cli/loop/lifecycle.py:564,639`) re-parses the loop YAML via `load_loop()` and restores only the persisted FSM *context* on top of it (`lifecycle.py:663-671`); it never reads `args.run_model`/`args.llm_model` (zero matches). `cmd_run` (`run.py:189-193`) has the "explicit model clears inherited hint" rule for the initial run path (`fsm.llm.model = args.llm_model; fsm.llm.model_hint = None`) — `cmd_resume` has no counterpart, confirming this issue's Current Behavior claim about lost run-level overrides on resume.

### Files to Modify
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/feed.py` — not previously listed. Imports and calls `header.py`'s `_render_artifact_header_lines` at two independent sites (`feed.py:367`, `feed.py:787`, import at `feed.py:26`) for the pinned-pane/streaming-diagram header used by `--show-diagrams`/`ll-loop monitor`; any signature change to carry `model_requested`/`model_resolved`/`model_backend` must update both call sites, not just `header.py`'s body.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py:775-776` (`cmd_resume`) and `:854-855` (`cmd_monitor`) — both call `run_foreground`/`StateFeedRenderer(...)` with `model=fsm.llm.model`, the same stale-model-display pattern already flagged for `cmd_run` in `run.py`; since `LLMConfig.model` stays at its default even when `model_hint` is set, both entry points will keep showing the unresolved default unless updated alongside `run.py`'s header fix.
- `scripts/little_loops/cli/loop/runner.py:390-394` — a second, independently-formatted inline header line (`model_line = model if effort is None else f"{model} {_effort_code(effort)}"`), separate from `header.py:136`'s `_render_artifact_header_lines`. Backs the "Model Header Display (ENH-1805)" example in `docs/reference/CLI.md`. Updating `header.py` alone will not change this render path.
- `scripts/little_loops/cli/loop/feed.py:843-849` (`StateFeedRenderer.handle_event`, `action_complete` branch) — already reads `event.get("model")`/`event.get("effort")` to mutate `self.model`/`self.effort` for the next header redraw. This is the existing live-update hook to extend for `model_requested`/`model_resolved`/`model_backend`; it is the direct mechanism, not a new one to invent.
- `scripts/little_loops/cli/loop/testing.py:263-269` — constructs `FSMExecutor(fsm, event_callback=..., action_runner=sim_runner, circuit=circuit)` and calls `executor.run()` directly, a caller outside `executor.py`/`persistence.py`. It substitutes its own `action_runner` (a simulation stub) rather than dispatching through a real host, so it does not need a code change for this issue — recorded here only so the dispatch-wiring work doesn't miss it while auditing `FSMExecutor.run()` callers.
- `scripts/little_loops/cli/loop/evidence.py:269,460-489` (`assemble_bundle`) — copies `evaluate` event fields through a fixed allowlist (`"reason", "evidence", "raw", "llm_model", "llm_prompt"`); the new `model_requested`/`model_resolved`/`model_backend` keys will not appear in evidence bundles unless this allowlist is extended. Not required by any Acceptance Criterion — flagged as an optional follow-on, not a blocking gap.
- `scripts/little_loops/fsm/persistence.py`'s `PersistentExecutor._handle_event()` (`persistence.py:1080`, usage-write block `:1090-1119`) copies a named-key allowlist into `usage.jsonl` and does **not** include the new fields — this already enforces the issue's "no DB columns / never overwrite observed identity" invariant with no code change needed. Confirmed, not a gap.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:1370` — currently states "Hint dispatch is not yet wired: a loop declaring `model_hint` currently stops at run start." This becomes false once this issue ships and belongs to ENH-3548 per this issue's own Scope Boundaries, but is flagged here because it directly contradicts this issue's Current Behavior section once implemented.
- `docs/reference/EVENT-SCHEMA.md:210-228` (`action_complete` field table) and the `evaluate` event section (`:305` onward) — do not list `model_requested`/`model_resolved`/`model_backend`; becomes incomplete once those fields ship.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` (`TestCmdResume`, lines 705-1105) — extensive `cmd_resume` coverage exists but zero tests set up a `model_hint`/`--llm-model` scenario; needed for AC10 (resume resolves afresh, reactivates a dropped `--llm-model` override's YAML hint).
- `scripts/tests/test_fsm_persistence.py` — covers `PersistentExecutor`, which passes `run_model`/`run_effort` through to `FSMExecutor` (`persistence.py:1035`); no `model_hint` coverage today.
- `scripts/tests/test_ll_loop_parsing.py` — covers `run_parser`/`resume_parser` argparse wiring including `--llm-model`; relevant regression check once dispatch resolution changes what `--llm-model` clears.
- `scripts/tests/test_cli_loop_dispatch.py` — covers `cmd_run`/`cmd_resume` dispatch; relevant regression check for the header/event changes at both entry points.
- **Existing test needing update, not just new coverage**: `scripts/tests/test_fsm_executor.py::test_execute_sub_loop_signature_drift_guard` (lines 9590-9645) is an AST-based guard asserting `FSMExecutor.__init__`'s parameters and the sub-loop call-site kwargs stay in lockstep. If dispatch wiring adds any new `FSMExecutor` parameter, this test **fails by design** unless both its `sig_params` set and the `_execute_sub_loop` call-site kwargs are updated together — treat a failure here as a signal to update the guard, not a bug in the guard.
- **Fixture gap for AC11 (portability proof)**: no loop YAML with `model_hint: coding`/`model_hint: burst` states exists anywhere in the repo (confirmed by repo-wide search — only `fsm/schema.py`'s field definition and issue markdown mention those hint names). The fixture must be created from scratch; follow the inline-YAML-fixture idiom already used for sub-loop tests in `test_fsm_executor.py` (e.g. around lines 9548-9557) rather than adding a new checked-in `.loops/` file, unless the portability proof specifically needs a standalone runnable loop.
- **Zero coverage today** for AC3 (an evaluator hint on a `request_path: sdk` state resolving against the CLI host, not `anthropic-api`) and for a resolved-hint (not literal) argv assertion on Codex/`FakeHostRunner`/`FakeMinimalHostRunner` — the closest templates are `test_host_runner.py:661-667`/`800-823` (`test_build_streaming_with_model`, literal-model pattern) and `test_fsm_evaluators.py:1717` (`test_dispatch_llm_structured_threads_model_kwarg`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `cli/loop/feed.py` — thread `model_requested`/`model_resolved`/`model_backend` through both `_render_artifact_header_lines` call sites (`:367`, `:787`) and the live-update hook in `StateFeedRenderer.handle_event`'s `action_complete` branch (`:843-849`).
- Update `cli/loop/lifecycle.py` — fix the header display at **both** `cmd_resume` (`:775-776`) and `cmd_monitor` (`:854-855`), not just `cmd_run`; both currently pass the stale, unresolved `fsm.llm.model`.
- Update `cli/loop/runner.py:390-394` — this inline header render is a separate implementation from `header.py`'s; update it in lockstep, not as a side effect of editing `header.py`.
- Update `scripts/tests/test_fsm_executor.py::test_execute_sub_loop_signature_drift_guard` if any new `FSMExecutor.__init__` parameter is added for hint forwarding.
- Create the AC11 portability-proof fixture loop (`coding`/`burst` states) — none exists today.

## Impact

- **Priority**: P2.
- **Effort**: Medium to high — ~10 source files, six test files, and a persistence-format check. If lifecycle proves large, split sub-loop/detach/resume/persistence from dispatch wiring.
- **Risk**: Medium — a precedence or backend mismatch silently selects the wrong model.

## Acceptance Criteria

Carried over from ENH-3527's original criteria (stated inline; ENH-3527's numbering has since changed):

- [ ] Tests cover every precedence row; no-hint behavior and literal CLI argv are unchanged.
- [ ] CLI action, blocking evaluator, SDK and batch paths share declaration semantics; a foreign configured CLI host never supplies an Anthropic request model; downgrade re-resolves.
- [ ] An evaluator hint on a `request_path: sdk` state resolves against the CLI host, not `anthropic-api`.
- [ ] Every advertised host/operation combination has a dispatch-level argv test, including Codex streaming and a config-only `orchestration.model_hints.codex` mapping reaching argv (moved from ENH-3527); opencode/pi and missing/disabled mappings error explicitly.
- [ ] `FakeHostRunner` forwards `--model`; a fake-host dispatch test asserts the resolved sentinel in argv.
- [ ] Sub-loop/detach/resume preserve requested declarations (resume via YAML re-read; run-level literal flags are out of scope); event payloads carry the three selection fields (`model_requested`, `model_resolved`, `model_backend`).
- [ ] Sub-loops follow ENH-3527's decided semantics: run `--model` inherits into children; a parent state's declaration does not propagate; children resolve against their own `llm`.
- [ ] A state with both a prompt action and an LLM evaluator resolves its single declaration separately for each and may yield two different model strings.
- [ ] `--llm-model` replaces the `llm` declaration and clears an inherited hint.
- [ ] Resuming under a changed mapping or host resolves afresh and makes the new selection visible (event/header), including a resume that drops an earlier `--llm-model` override and reactivates a YAML `llm.model_hint`.
- [ ] Portability proof: a fixture loop with `coding`/`burst` states runs unedited under the fake host (argv shows `fake-coding`/`fake-burst`), `claude-code` (argv shows `sonnet`/`haiku`), and `anthropic-api` (mocked SDK client receives `MODEL_ALIASES` IDs).

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers runtime dispatch, CLI downgrade re-resolution, and lifecycle wiring only; the resolver and config slice is ENH-3527 and validate-time warnings/docs are ENH-3548. ENH-3527 dropped the `operation` parameter (2026-09-24), so there is no `model_operation` event field.

## Verification Notes

Pre-implementation review 2026-09-25 made these changes:

- Added fake-host `--model` forwarding. It is needed for the portability proof and uses the ENH-3527 (landed) new `fake`/`fake-minimal` mapping.
- Evaluators resolve against the CLI host only.
- Moved the config-only Codex argv criterion here from ENH-3527.
- Decided resume scope: hint declarations survive through the YAML re-read, and run-level literal flags are out of scope.
- Recorded the compression sizing gap as older, out-of-scope behavior.
- Updated observed-identity wording now that ENH-3528/ENH-3538 are done.


## Session Log
- `/ll:wire-issue` - 2026-09-27T20:39:53 - `e3045b14-86be-4cd8-801e-cb4a91f14a76.jsonl`
- `/ll:refine-issue` - 2026-09-27T20:25:25 - `b7c94eba-e7a8-40c2-a5f2-39f525e86d43.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:56 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
