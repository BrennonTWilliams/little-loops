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
confidence_score: 100
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3547: Wire model hint resolution through loop dispatch and lifecycle

## Summary

Wire `model_hint` resolution into every loop dispatch path: CLI actions, blocking evaluators, SDK/batch, and CLI downgrade. Preserve requested declarations through sub-loops, detach and resume, and add selection diagnostics to FSM events. This is piece 2 of ENH-3527's delivery split; ENH-3527 keeps piece 1 (declarations, resolver and config) and is the prerequisite.

## Current Behavior

- After ENH-3527, `model_hint` declarations parse and validate, but `FSMExecutor` fails fast with a not-yet-supported error before dispatch.
- CLI actions use `state.model or self.run_model` (`executor.py:2654`); evaluators use `state.model or self.fsm.llm.model` (`executor.py:3170,3217`); SDK/batch use `state.model or self.run_model or self.fsm.llm.model` (`executor.py:3566`).
- Evaluators have no SDK path: `fsm/evaluators.py` always dispatches through `resolve_host().build_blocking_json`, whatever the state's `request_path`.
- `FakeHostRunner.build_streaming` and `build_blocking_json` accept `model` but drop it from argv (`host_runner.py:2173-2209`, `2252-2284`), so no fake-host test can assert a resolved selection today.
- `ll-loop resume` has no `--model`/`--llm-model` flags, and loop persistence saves neither the run-level `--model` nor the `--llm-model` override. Detach forwards both (`cli/loop/runner.py:223-231`). Resume re-reads the loop YAML, so YAML declarations (including hints) survive, but run-level literal overrides are lost. This behavior predates this issue.
- Prompt compression sizes against `model=self.run_model` (`executor.py:2519`), not the state's effective model. This already happens with a literal `state.model`.

## Expected Behavior

Everything below is specified in ENH-3527 (Design → Declaration and precedence, Resolve against the effective backend, Supported artifact/host matrix, Lifecycle and model identity, Call Path). ENH-3527 remains the authoritative design; this issue owns delivering it:

- **Precedence (copied from ENH-3527 so AC1's rows are stated here).** Select a declaration first, then resolve it:

  | Path | Highest to lowest precedence |
  |------|------------------------------|
  | CLI action | State model-or-hint → run `--model` → host default (`model=None`) |
  | Evaluator (always CLI host) | State model-or-hint → effective `llm` model-or-hint → existing evaluator default |
  | SDK/batch action | State model-or-hint → run `--model` → effective `llm` model-or-hint → existing API default |

  Two rules are easy to break: `llm.model_hint`, when set, wins over the default `llm.model` value; and an `llm` declaration (hint or literal) is **not** a CLI-action default. It feeds only evaluators and the SDK/batch fallback.
- **Resolve only where a model is consumed.** `evaluate()` receives `model=` for every explicit evaluator type (`executor.py:3217`), and the implicit prompt-mode verdict is gated on `self.fsm.llm.enabled` (`executor.py:3162`). Resolve an evaluator declaration only when the evaluator is `llm_structured` (explicit, or the implicit prompt-mode verdict) and LLM evaluation is enabled. Resolve an action declaration only when `action_mode == "prompt"`. Eager resolution would raise on valid loops, for example a shell + `exit_code` state under `llm.model_hint` on an unmapped host, or a prompt + `output_contains` state on `request_path: sdk` whose CLI host has no mapping.
- **Backend key and overrides.** The CLI backend key is `resolve_host().name`; runner names already match `hint_backend_keys()` (`claude-code`, `codex`, `fake`, `fake-minimal`, …). SDK/batch uses `ANTHROPIC_API_BACKEND`. Overrides come from `self.orchestration_config.model_hints`; a `None` `orchestration_config` (bare test constructions) means `overrides=None`. The config already reaches run (`run.py:657`), resume (`lifecycle.py:744`) and sub-loops (`executor.py:1295`).
- **`resolve_host()` can raise (reviewed 2026-09-27).** `resolve_host()` (`host_runner.py:2624`) raises `HostNotConfigured` when `LL_HOST_CLI`/`LL_HOOK_HOST` are unset and no host binary is on PATH. The test conftest clears `LL_HOST_CLI` (`conftest.py:1186`), so the lookup falls back to a binary probe, and GitHub-hosted CI runners have no `claude` binary. Today only the real runners and `evaluate_llm_structured` call it, and tests mock those. This issue adds executor-level calls, so:
  - Call `resolve_host()` for resolution only when a **hint** must be resolved against the CLI host.
  - For a **literal** selection, fill `model_backend` from a lookup that catches `HostNotConfigured` and leaves the field out. Never let a diagnostic field end a run that would dispatch through a mocked runner today.
  - The preflight catches `HostNotConfigured` next to `ModelHintError` and ends the run with `"error"` and a message that names the hint and says no host CLI was found.
  - Every test that asserts `model_backend` for a CLI host sets `monkeypatch.setenv("LL_HOST_CLI", ...)`. Without it, the test passes locally (where `claude` is on PATH) and fails on CI.
- **Failure mode (decided 2026-09-27).** Replace the not-yet-supported guard in `FSMExecutor.run()` (`executor.py:642-652`) with a **run-start preflight**. Keep it in the same place, after the `loop_start` emit at `:640`, so a failed run still has a start event. The preflight resolves every declaration against the backend its state will actually use: the CLI host for prompt-mode CLI actions and consuming evaluators, and `anthropic-api` for prompt actions whose effective request path is `sdk`/`batch`. The effective path comes from the pure `_compute_request_path` (below), including the BUG-2831 skill/`tools:` downgrades and the import/credential probes. The preflight must also cover `type: learning` states (see **Learning-state remedy** below), which `_action_mode(state)` does not classify as prompt mode. A `ModelHintError` there ends the run with `self._finish("error", error=<message naming hint and backend>)` before any state runs. After this change, a dispatch-time `ModelHintError` can happen only if the probe result changes mid-run. It also ends the run and never goes to `on_error` or to a default model. **One mechanism covers every path (revised 2026-09-27):** add an `except ModelHintError as exc:` clause to `run()`'s top-level handler, before the generic `except Exception` (`:1081`). It always returns `self._finish("error", error=str(exc))`, whatever `self._phase` is. Each path only has to let the exception reach it:
  - **Action path.** Resolution happens inside `_run_action` (`:2654`). That is called from `_run_action_or_route`, whose `except Exception` (`:3868`) sends every exception to `state.on_error`. Add `ModelHintError` to the re-raise next to `HeredocCollisionError` (`:3864`, BUG-3354 precedent).
  - **Evaluator path.** `_evaluate` runs with `_phase == "decide"`, so the generic handler would end it as `no_route`; the dedicated clause ends it as `"error"`. Let the exception propagate out of `_evaluate`. **Do not** use `self._pending_error` and return: `_evaluate` returns into `_execute_state` (`:2246`), which then still runs the prepatch check, the tamper guard (whose `revert` policy rewrites the working tree), the `captured` verdict write, stall detection and route interpolation. `_pending_error` is only checked at `:930`, after `_execute_state` returns.
- **Learning-state remedy (reviewed 2026-09-27).** `_execute_learning_state` dispatches `/ll:explore-api <target>` through `self._run_action(..., _dc_replace(state, action_type="slash_command"), ctx)` (`executor.py:1527`). This is a fifth `_run_action` call site, outside `_run_action_or_route`. Because the replaced state is prompt mode, the CLI path resolves the learning state's own `state.model`/`state.model_hint`. But `_action_mode(state)` on the original state is not `"prompt"`, so a preflight keyed only on `_action_mode` would skip it. An unmapped hint would then pass the preflight and fail mid-run, after earlier states ran. The preflight treats a state with `type == "learning"` and a `learning` config as a prompt-mode CLI action consumer. Its request path is always `cli`, because `/ll:explore-api` matches `_SKILL_INVOKE_RE`. No local handler wraps this call: a dispatch-time `ModelHintError` propagates to `run()`'s new top-level clause.
- **Child loops (decided 2026-09-27: propagate).** Each child builds its own executor and runs its own preflight. Today a child that ends with `terminated_by="error"` is routed to the parent's `on_error` (or `on_no`) by `_execute_sub_loop` (around `:1366-1391`), which would turn a config error into a normal route. Add `model_hint_error: bool = False` to `ExecutionResult` (`fsm/types.py`) and set it from the preflight and from the new `ModelHintError` handler. **Mechanism:** `_finish(terminated_by, error)` has no parameter for it and builds the result itself (`executor.py:4516`). Add a keyword-only `model_hint_error: bool = False` parameter to `_finish` and pass it into that `ExecutionResult(...)` construction. The preflight and the `run()` clause call `self._finish("error", error=..., model_hint_error=True)`. The other construction sites (`:799`, `:4564`) keep the default. Before the routing branches, when a child result has it set, `_execute_sub_loop` raises `ModelHintError(f"sub-loop '<loop>': <child error>")`, and the parent's top-level clause ends the parent run with `"error"`. Separately, `ModelHintError` subclasses `ValueError`, so `_execute_state`'s sub-loop `except (FileNotFoundError, ValueError, InterpolationError)` (`:2096`) would also send it to `on_error`. Re-raise it there too.
- **Pure request-path helper.** `_resolve_request_path` (`:3446`) has side effects: it emits the one-shot `request_path_downgrade` event, writes to stderr, and sets `_request_path_downgrade_warned`. Split it into `_compute_request_path(state) -> tuple[str, str | None]` (path, and the downgrade reason or `None`), which has no side effects, and keep `_resolve_request_path` as the dispatch-site wrapper that warns. The preflight calls only `_compute_request_path`.
- Resolve after the request path is known. SDK/batch always resolves against `anthropic-api`; a downgrade to CLI re-resolves the original declaration for that runner.
- **Resolve the selection once per action (reviewed 2026-09-27).** Today `_run_action` calls `_resolve_request_path` at `:2563`, `_dispatch_live` calls it again at `:3600`, and `_dispatch_live` resolves its own model at `:3598`. But the `action_complete` payload is built back in `_run_action` (`:2667`). `_run_action` must compute the request path and the `ModelSelection` once, pass the selection into `_dispatch_live` (new `selection: ModelSelection` parameter, replacing its `_resolve_action_model` call and its second `_resolve_request_path` call), and use the same object for the payload fields. That guarantees `model_resolved` is exactly the string the request or runner received.
- Evaluator hints are resolved in `FSMExecutor._evaluate` against the CLI host `resolve_host()` returns (never `anthropic-api`, even on an `sdk`/`batch` state) and passed down as `model: str`; no config is threaded into `evaluators.py`.
- `FakeHostRunner` (and `FakeMinimalHostRunner`) add `--model <model>` to argv when `model` is set, so fake-host dispatch tests and the portability proof can assert the resolved sentinel (`fake-coding`, `fake-burst`, …; ENH-3527 built-in mapping). **Put the flag before the prompt (reviewed 2026-09-27):** `["--model", m, prompt]` for `FakeHostRunner` and `["run", "--model", m, prompt]` for `FakeMinimalHostRunner`, in both `build_streaming` and `build_blocking_json`. Do not use the real runners' append idiom (`args += ["--model", model]`). `ll-fake-host`'s `main()` (`fake_host.py:331`) reads the prompt as the argv element that contains the `@@fake` fence, and falls back to `args[-1]` when no element does. With the flag appended after the prompt, a fence-less prompt would be parsed as the directive script `fake-coding`. Fenced prompts would still work, so the defect would show up only in some tests.
- Each dispatch adds `model_requested`, `model_resolved` and `model_backend` to its event payload. **Rule (decided 2026-09-27): emit the three fields whenever a model is passed to the runner or request** (a literal or a hint), following the existing `if value is not None: payload[key] = value` idiom.
  - A CLI action with no declaration (host default, `model=None`) omits them, so its `action_complete` payload stays byte-identical.
  - Evaluator dispatches that **consume** a model, and SDK/batch dispatches, **always** pass one, because `LLMConfig.model` defaults to `DEFAULT_LLM_MODEL` and the default can't be told apart from an explicit `sonnet`. So `llm_structured` `evaluate` events (explicit, or the implicit prompt-mode verdict, with LLM evaluation enabled) and SDK/batch `action_complete` events gain the three fields for every loop, and `_resolve_model(..., "evaluator" | "sdk")` never returns `None`. Every other `evaluate` event carries **none** of the three fields, because nothing was resolved: `exit_code`, `output_contains`, `mcp_result`, `contract`, `comparator`, `classify`, contributed evaluators, and `llm_structured` under `--no-llm`. Update any payload snapshots this breaks. The known `evaluate`-payload consumers are `test_feat3182_evidence_bundle.py` (`llm_model` at `:120`, `:332`, `:374`) and the `assemble_bundle` allowlist in `cli/loop/evidence.py`. `test_cross_host_baseline.py:130` is an argparse `Namespace` default, not a payload pin.
  - `model_resolved` is the exact model string sent over the wire. On `claude-code` it is the alias (`sonnet`). On `anthropic-api` it is always the concrete ID (for example `claude-sonnet-5`), for **literals as well as hints** (reviewed 2026-09-27). `build_anthropic_request` applies `resolve_model_alias` to every model it receives (`host_runner.py:3028`). Without a matching step, a literal `sonnet` would emit `model_resolved: "sonnet"` while the API received `claude-sonnet-5`, but a `coding` hint would emit `claude-sonnet-5`. So `_resolve_model(..., "sdk")` also passes a literal through `resolve_model_alias`. The second call in `build_anthropic_request` is idempotent. Tests assert against the mocked **SDK client** (`messages.create` / `batches.create` receive the `model`), not a mocked `dispatch_anthropic_request`, which sees the pre-alias value. On `evaluate` events it duplicates the existing `llm_model` detail (`evaluators.py:1269`); keep both. No DB columns; observed model identity stays in `usage_events.model` (ENH-3528/ENH-3538, done) and is never overwritten with a requested/resolved selection.
- **Resume (decided 2026-09-25).** Hints live only in the loop YAML, because there are no run-level hint flags. Resume re-reads the YAML, so resume preserves hint declarations without new persistence. Losing run-level `--model`/`--llm-model` on resume is older behavior for literals and **out of scope**. One consequence must be visible, not silent: a run started with `--llm-model X`, which cleared a YAML `llm.model_hint`, resumes with that hint active again. The resumed run's dispatch events must show the new selection. The console header part of this moved to ENH-3638.
- **Header display: moved to ENH-3638 (2026-09-27).** The console header, `feed.py` live update, `runner.py:390`, the `lifecycle.py` header arguments and `info.py` are out of scope here. This issue only emits the event fields that ENH-3638 reads.
- **Compression.** Keep `compress_action_text(model=self.run_model)` unchanged here (out of scope, older behavior). Add a code comment that the window is sized against the run model, not the hint-resolved state model.

## Scope Boundaries

- **In scope**: dispatch wiring on every loop path, CLI downgrade re-resolution, lifecycle preservation, event-payload diagnostics, portability proof, replacing ENH-3527's not-yet-supported guard with the run-start preflight, stopping `ModelHintError` from reaching `on_error` (action, evaluator and sub-loop paths), and the pure `_compute_request_path` split. Two docs edits made false or incomplete by this issue itself also ship here: remove the "Hint dispatch is not yet wired" sentence at `docs/reference/CONFIGURATION.md:1370`, and add the three fields to the `action_complete` and `evaluate` tables in `docs/reference/EVENT-SCHEMA.md`.
- **Out of scope**: console header, `feed.py` live update, `runner.py:390` and `info.py` display (ENH-3638); validate warnings and the remaining hint documentation (ENH-3548); skill/agent frontmatter (ENH-3533); persisting run-level `--model`/`--llm-model` across resume (older literal behavior); making compression hint-aware; routing a declaration into the `contract` and `comparator` evaluators. Both already call an LLM with `DEFAULT_LLM_MODEL` and ignore `state.model` (`evaluators.py` `evaluate_contract`/`evaluate_blind_comparator` are called without `model=`). That is older behavior, and they do not consume a hint either.

## Program Design

### Types

- `ModelSelection` — new frozen dataclass in `fsm/executor.py` (or beside `resolve_model_hint` in `host_runner.py`): `requested: str` (the literal or hint as declared), `resolved: str` (the string passed to the runner or request), `backend: str` (`resolve_host().name` or `ANTHROPIC_API_BACKEND`), `is_hint: bool`. ENH-3527 described a resolved selection only in prose; no such type exists in `scripts/little_loops` today.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527 (no `operation` parameter, decided 2026-09-24), called only through the helpers below.
- `FSMExecutor._resolve_model(state: StateConfig, path: Literal["cli", "sdk", "evaluator"]) -> ModelSelection | None` — selects the declaration per the precedence table, resolves it against the path's backend, and returns `None` only for a `"cli"` path with nothing declared (host default). On the `"sdk"` path it also passes a literal through `resolve_model_alias`, so `resolved` is the wire ID. The `"evaluator"` and `"sdk"` paths always return a selection, because they fall back to `llm.model`. Replaces the inline `state.model or self.run_model` at `executor.py:2654` and the two evaluator expressions at `:3170`/`:3217`. `_resolve_action_model` (`:3555`) either delegates to it or is removed.
- `FSMExecutor._preflight_model_hints() -> str | None` — the run-start check that replaces the guard; returns an error message, or `None` when every reachable declaration resolves.
- `FSMExecutor._compute_request_path(state: StateConfig) -> tuple[str, str | None]` — the side-effect-free core of `_resolve_request_path`; returns the effective path and the downgrade reason (or `None`). `_resolve_request_path` keeps its signature and only adds the one-shot warning.
- `ExecutionResult.model_hint_error: bool = False` — new field (`fsm/types.py`) that the parent's `_execute_sub_loop` reads to propagate a child's hint failure instead of routing it.
- `FSMExecutor._finish(terminated_by: str, error: str | None = None, *, model_hint_error: bool = False) -> ExecutionResult` — gains the keyword-only flag and copies it into the `ExecutionResult` it builds.
- `FSMExecutor._dispatch_live(state, action, ctx, selection: ModelSelection) -> ActionResult` — gains the `selection` parameter; drops its own `_resolve_action_model` and second `_resolve_request_path` calls.
- Evaluator functions keep `model: str`.

### Call Path

- `FSMExecutor._run_action` → `FSMExecutor._resolve_model` → `resolve_model_hint` → `FSMExecutor._dispatch_live` → `dispatch_anthropic_request` / `dispatch_batch_request` (SDK/batch)
- `FSMExecutor._run_action` → `FSMExecutor._resolve_model` → `resolve_model_hint` → `ActionRunner.run(model=...)` → `run_claude_command` → `ClaudeCodeRunner.build_streaming` / `CodexRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `FSMExecutor._resolve_model` → `resolve_model_hint` (CLI backend only) → `evaluate_llm_structured` → `build_blocking_json`
- `FSMExecutor.run` → `FSMExecutor._preflight_model_hints` → `FSMExecutor._compute_request_path` → `resolve_model_hint`
- `FSMExecutor._execute_learning_state` → `FSMExecutor._run_action` → `FSMExecutor._resolve_model` → `resolve_model_hint` (learning remedy, always CLI)

## Integration Map

- `scripts/little_loops/fsm/{executor,evaluators,runners,persistence,types}.py`, `subprocess_utils.py`. The `cli/loop/{run,lifecycle,runner,header,feed,info}.py` display work moved to ENH-3638.
- `scripts/little_loops/host_runner.py` — `FakeHostRunner` / `FakeMinimalHostRunner` forward `--model`, placed before the prompt. `ll-fake-host` needs no change **on that condition** (see research below).
- Tests: `test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_fsm_runners.py`, `test_ll_loop_execution.py`, `test_host_runner_dispatch.py`, `test_fake_host.py`, `test_model_hints.py` (rewrite `TestPreDispatchGuard`, lines 269-306, to assert the preflight — for example `LL_HOST_CLI=codex` with no config mapping ends with `terminated_by == "error"` and `runner.calls == []` — instead of the blanket not-supported error). **`test_llm_hint_blocks` must flip, not just be reworded:** its loop is a shell + exit_code state under `llm.model_hint`, which AC15 says must now run to `terminated_by == "terminal"` with `runner.calls == ["echo"]`. Also `test_host_runner.py` (`TestFakeHostRunner`/`TestFakeMinimalHostRunner` model tests), `conformance/test_host_composition.py` (portability-proof shape), and `test_feat3182_evidence_bundle.py` (`evaluate` payload fixtures; check that they still pass with the added `llm_structured` fields).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Existing dispatch seams that resolve a value per-backend do so via a private `FSMExecutor` method mirroring an existing fallback chain, not an inline expression: `_resolve_action_model()` (`executor.py:3555-3566`) explicitly mirrors `state.model or self.run_model`, and `_resolve_request_path()` (`executor.py:3446-3514`) resolves per-backend with a one-shot downgrade warning via `_warn_request_path_downgrade()` (`executor.py:3546-3553`). The CLI action dispatch site (`executor.py:2654`) is the one seam still inline (`state.model or self.run_model`) rather than delegated — a pre-existing inconsistency, not a convention to preserve.
- The not-yet-supported guard this issue removes lives in `FSMExecutor.run()` (`executor.py:640-652`) and is pinned by `test_model_hints.py::TestPreDispatchGuard` (lines 269-306), which asserts `result.terminated_by == "error"` and `runner.calls == []`; those tests need updating alongside the guard's removal.
- Event payloads have no shared builder — every event type builds its own `dict[str, Any]` literal at its `self._emit(...)` call site (`_emit` at `executor.py:3925`; `action_complete` payload at `2667-2716`; `evaluate` payload at `3178-3227`). Conditional-diagnostic fields follow `if value is not None: payload[key] = value` (e.g. `effort`, `is_batch`). `payload["model"]` is already occupied by the *observed* model from `usage_events[-1].model` — distinct from the requested/resolved/backend fields this issue adds, which need their own keys.
- The console run header (`cli/loop/header.py:_render_artifact_header_lines`, line 109) is a separate concept from the event payload; no persisted "header" exists in `fsm/persistence.py` (zero matches for the term). The one existing precedent for adding a diagnostic to the console header (ENH-2869's `effort`) appends onto the single `model:` display value via an `effort: str | None` kwarg threaded through every call site, not a new row — that precedent covers appending one value, not three at once.
- Every real host runner shares one idiom for conditional argv, at nine call sites in `host_runner.py`: `if model: args += ["--model", model]`. `FakeHostRunner`/`FakeMinimalHostRunner` already accept `model` in their signatures but drop it in the body (`host_runner.py:2173-2209`, `2252-2284`), matching this issue's own Current Behavior claim.
- Dispatch-level argv assertions follow one test method per runner class, named `test_build_streaming_with_model` (`test_host_runner.py:661-667` for `ClaudeCodeRunner`; `:800-823` for `CodexRunner`, with exact-count and exact-position assertions), paired with a `test_build_streaming_without_model_omits_flag` absence test. `TestFakeHostRunner`/`TestFakeMinimalHostRunner` (`test_host_runner.py:1178-1250`, `1253-1326`) exist as test classes but have no model test today.
- The "same script across multiple hosts, assert identical behavior" shape already exists as `TestFakesAreDivergent`/`TestCompositionThroughExecutor` (`scripts/tests/conformance/test_host_composition.py:285-396`) — drives both fakes through the real `run_claude_command`/`run_blocking_json` path and asserts equal `Observed` results across hosts.
- `ll-fake-host`'s `main()` (`fake_host.py:331`) never parses argv as flags — it scans for the one element containing the `@@fake` fence and ignores everything else positionally, so it already tolerates an extra `--model X` pair without change. **Correction (2026-09-27):** that holds only for fenced prompts. When no element contains the fence, `main()` falls back to `args[-1]`, so `--model X` must come before the prompt, or `X` is parsed as the script.
- Sub-loop children are already constructed with `run_model`/`run_effort` forwarded explicitly but not the parent's per-state `model_hint` (`executor.py:1288-1302`) — the child gets its own freshly-loaded `child_fsm`, so state-level declarations already don't propagate today. That half of the sub-loop AC needs a test, not a code change.
- `cmd_resume` (`cli/loop/lifecycle.py:564,639`) re-parses the loop YAML via `load_loop()` and restores only the persisted FSM *context* on top of it (`lifecycle.py:663-671`); it never reads `args.run_model`/`args.llm_model` (zero matches). `cmd_run` (`run.py:189-193`) has the "explicit model clears inherited hint" rule for the initial run path (`fsm.llm.model = args.llm_model; fsm.llm.model_hint = None`) — `cmd_resume` has no counterpart, confirming this issue's Current Behavior claim about lost run-level overrides on resume.

### Files to Modify
_Wiring pass added by `/ll:wire-issue`:_
- ~~`scripts/little_loops/cli/loop/feed.py`~~ — moved to ENH-3638 (2026-09-27). Its two `_render_artifact_header_lines` call sites (`feed.py:367`, `:787`) take the precomputed display string, not the three fields.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- Header display call sites (`lifecycle.py:775-776` `cmd_resume`, `:854-855` `cmd_monitor`; `runner.py:390-394`; `feed.py:843-849` live-update hook) — moved to ENH-3638 (2026-09-27).
- `scripts/little_loops/fsm/types.py` (`ExecutionResult`) — gains `model_hint_error`. Check `ExecutionResult`'s serializers and `test_fsm_executor.py`'s field-set assertions, if any, so the new field defaults cleanly.
- `scripts/little_loops/cli/loop/testing.py:263-269` — constructs `FSMExecutor(fsm, event_callback=..., action_runner=sim_runner, circuit=circuit)` and calls `executor.run()` directly, a caller outside `executor.py`/`persistence.py`. It substitutes its own `action_runner` (a simulation stub) rather than dispatching through a real host, so it does not need a code change for this issue — recorded here only so the dispatch-wiring work doesn't miss it while auditing `FSMExecutor.run()` callers.
- `scripts/little_loops/cli/loop/evidence.py:269,460-489` (`assemble_bundle`) — copies `evaluate` event fields through a fixed allowlist (`"reason", "evidence", "raw", "llm_model", "llm_prompt"`); the new `model_requested`/`model_resolved`/`model_backend` keys will not appear in evidence bundles unless this allowlist is extended. Not required by any Acceptance Criterion — flagged as an optional follow-on, not a blocking gap.
- `scripts/little_loops/fsm/persistence.py`'s `PersistentExecutor._handle_event()` (`persistence.py:1080`, usage-write block `:1090-1119`) copies a named-key allowlist into `usage.jsonl` and does **not** include the new fields — this already enforces the issue's "no DB columns / never overwrite observed identity" invariant with no code change needed. Confirmed, not a gap.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:1370` — currently states "Hint dispatch is not yet wired: a loop declaring `model_hint` currently stops at run start." This becomes false once this issue ships, so removing it is in scope here (see Scope Boundaries).
- `docs/reference/EVENT-SCHEMA.md:210-228` (`action_complete` field table) and the `evaluate` event section (`:305` onward) — do not list `model_requested`/`model_resolved`/`model_backend`; becomes incomplete once those fields ship.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` (`TestCmdResume`, lines 705-1105) — extensive `cmd_resume` coverage exists but zero tests set up a `model_hint`/`--llm-model` scenario; needed for AC10 (resume resolves afresh, reactivates a dropped `--llm-model` override's YAML hint).
- `scripts/tests/test_fsm_persistence.py` — covers `PersistentExecutor`, which passes `run_model`/`run_effort` through to `FSMExecutor` (`persistence.py:1035`); no `model_hint` coverage today.
- `scripts/tests/test_ll_loop_parsing.py` — covers `run_parser`/`resume_parser` argparse wiring including `--llm-model`; relevant regression check once dispatch resolution changes what `--llm-model` clears.
- `scripts/tests/test_cli_loop_dispatch.py` — covers `cmd_run`/`cmd_resume` dispatch; relevant regression check for the event changes at both entry points.
- **Existing test needing update, not just new coverage**: `scripts/tests/test_fsm_executor.py::test_execute_sub_loop_signature_drift_guard` (lines 9590-9645) is an AST-based guard asserting `FSMExecutor.__init__`'s parameters and the sub-loop call-site kwargs stay in lockstep. If dispatch wiring adds any new `FSMExecutor` parameter, this test **fails by design** unless both its `sig_params` set and the `_execute_sub_loop` call-site kwargs are updated together — treat a failure here as a signal to update the guard, not a bug in the guard.
- **Fixture gap for AC17 (portability proof)**: no loop YAML with `model_hint: coding`/`model_hint: burst` states exists anywhere in the repo (confirmed by repo-wide search — only `fsm/schema.py`'s field definition and issue markdown mention those hint names). The fixture must be created from scratch; follow the inline-YAML-fixture idiom already used for sub-loop tests in `test_fsm_executor.py` (e.g. around lines 9548-9557) rather than adding a new checked-in `.loops/` file, unless the portability proof specifically needs a standalone runnable loop.
- **Zero coverage today** for AC3 (an evaluator hint on a `request_path: sdk` state resolving against the CLI host, not `anthropic-api`) and for a resolved-hint (not literal) argv assertion on Codex/`FakeHostRunner`/`FakeMinimalHostRunner` — the closest templates are `test_host_runner.py:661-667`/`800-823` (`test_build_streaming_with_model`, literal-model pattern) and `test_fsm_evaluators.py:1717` (`test_dispatch_llm_structured_threads_model_kwarg`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- `feed.py`, `lifecycle.py` header arguments, and `runner.py:390-394` — moved to ENH-3638 (2026-09-27).
- Add the `except ModelHintError` clause to `run()` before `:1081`. Update `_run_action_or_route` (`:3864`) and `_execute_state`'s sub-loop handler (`:2096`) to re-raise `ModelHintError`. Update `_execute_sub_loop` to raise `ModelHintError` when a child result has `model_hint_error` set.
- Pass the `ModelSelection` from `_run_action` into `_dispatch_live` (new parameter).
- Split `_resolve_request_path` into the pure `_compute_request_path` plus the warning wrapper.
- Update `scripts/tests/test_fsm_executor.py::test_execute_sub_loop_signature_drift_guard` if any new `FSMExecutor.__init__` parameter is added for hint forwarding.
- Extend `_preflight_model_hints` to cover `type: learning` states (their `/ll:explore-api` remedy dispatch at `executor.py:1527` is prompt-mode CLI).
- Add the keyword-only `model_hint_error` parameter to `_finish` and pass it into `ExecutionResult`.
- Create the AC17 portability-proof fixture loop (`coding`/`burst` states) — none exists today.

## Impact

- **Priority**: P2.
- **Effort**: Medium — mostly `fsm/executor.py`, plus `host_runner.py` fakes, `fsm/types.py` and two docs edits. The header/display work was split to ENH-3638 on 2026-09-27.
- **Risk**: Medium — a precedence or backend mismatch silently selects the wrong model.

## Acceptance Criteria

Carried over from ENH-3527's original criteria (stated inline; ENH-3527's numbering has since changed):

- [ ] **AC1.** Tests cover every precedence row; no-hint behavior and literal CLI argv are unchanged.
- [ ] **AC2.** CLI action, blocking evaluator, SDK and batch paths share declaration semantics; a foreign configured CLI host never supplies an Anthropic request model; downgrade re-resolves.
- [ ] **AC3.** An evaluator hint on a `request_path: sdk` state resolves against the CLI host, not `anthropic-api`.
- [ ] **AC4.** Every advertised host/operation combination has a dispatch-level argv test (moved from ENH-3527):
  - `claude-code` with built-in mappings;
  - `fake`/`fake-minimal` with sentinel mappings;
  - one parametrized test for the config-only hosts `codex`, `gemini`, `omp`, `kimi-code` and `qwen`, showing an `orchestration.model_hints.<host>` mapping reaching `--model` argv on the streaming build, and on the blocking-JSON build where that host exposes one. Each runner already appends `--model` when `model` is set;
  - `opencode`/`pi`, and missing/disabled mappings, error explicitly.
- [ ] **AC5.** `FakeHostRunner` forwards `--model`; a fake-host dispatch test asserts the resolved sentinel in argv. Both fakes place `--model <m>` before the prompt, on the streaming and blocking-JSON builds. A test runs `ll-fake-host`'s `main()` on the built argv for a **fence-less** prompt with `model` set, and asserts it gives the same result as the same prompt with no model.
- [ ] **AC6.** Sub-loop/detach/resume preserve requested declarations (resume via YAML re-read; run-level literal flags are out of scope); event payloads carry the three selection fields (`model_requested`, `model_resolved`, `model_backend`).
- [ ] **AC7.** Sub-loops follow ENH-3527's decided semantics: run `--model` inherits into children; a parent state's declaration does not propagate; children resolve against their own `llm`.
- [ ] **AC8.** A state with both a prompt action and an LLM evaluator resolves its single declaration separately for each and may yield two different model strings.
- [ ] **AC9.** `--llm-model` replaces the `llm` declaration and clears an inherited hint. **Test only:** already implemented at `run.py:189-193` (ENH-3527); do not rewrite it.
- [ ] **AC10.** Resuming under a changed mapping or host resolves afresh, and the resumed run's dispatch events show the new selection. This includes a resume that drops an earlier `--llm-model` override and reactivates a YAML `llm.model_hint`. The console header is ENH-3638.
- [ ] **AC11.** A hint that cannot resolve on its effective backend fails the run-start preflight with `terminated_by == "error"`, an error naming the hint and backend, and no runner call. The failed run still emits `loop_start`, and the preflight emits no `request_path_downgrade` event. A hint that needs the CLI host when no host CLI can be found (`HostNotConfigured`) fails the preflight the same way.
- [ ] **AC12.** A dispatch-time `ModelHintError` ends the run with `terminated_by == "error"` (not `no_route`) on both the action path and the evaluator path, even when the state declares `on_error`. It never falls back to a default model. On the evaluator path, no post-evaluation step runs (tamper guard, prepatch check, `captured` verdict write, stall detection, routing).
- [ ] **AC13.** With `LL_HOST_CLI`/`LL_HOOK_HOST` unset and no host binary on PATH, a loop using literal models and mocked runners/evaluators runs exactly as it does today. The literal selection's `model_backend` is left out; the run does not fail.
- [ ] **AC14.** A child loop whose hint fails its preflight ends the **parent** run with `terminated_by == "error"`, and the error names the sub-loop. The parent's `on_error`/`on_no` does not fire.
- [ ] **AC15.** Hints resolve only where a model is consumed: a shell + `exit_code` state under `llm.model_hint`, and a prompt + non-`llm_structured` evaluator state, never resolve an evaluator hint, even on a host with no mapping. `--no-llm` skips evaluator resolution.
- [ ] **AC16.** A CLI action with no declaration (`model=None`) emits none of the three selection fields, and its `action_complete` payload is byte-identical to today's. `llm_structured` `evaluate` events (LLM enabled) and SDK/batch `action_complete` events always carry all three. Other `evaluate` events, including `llm_structured` under `--no-llm`, carry none. An SDK/batch event's `model_resolved` equals the `model` the mocked **SDK client** received (the concrete ID), for a literal (`sonnet` → `claude-sonnet-5`) as well as a hint.
- [ ] **AC17.** Portability proof: a fixture loop with `coding`/`burst` states runs unedited under the fake host (argv shows `fake-coding`/`fake-burst`), `claude-code` (argv shows `sonnet`/`haiku`), and `anthropic-api` (mocked SDK client receives `MODEL_ALIASES` IDs).
- [ ] **AC18.** A `type: learning` state whose `model_hint` cannot resolve on the CLI host fails the run-start preflight (AC11), with no runner call and without running any earlier state. When it resolves, the `/ll:explore-api` remedy dispatch receives the resolved model and its `action_complete` carries the three selection fields.
- [ ] **AC19.** The preflight and the `run()` `ModelHintError` clause return an `ExecutionResult` with `model_hint_error == True`. Every other termination, including a non-hint `"error"`, leaves it `False`.

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

Pre-implementation review 2026-09-27 made these changes:

- Specified the failure mode: a run-start preflight replaces the guard, and every `ModelHintError` ends the run through `_finish("error")`, never through `on_error`.
- Added the rule to resolve only where a model is consumed, because eager resolution would raise on valid shell/`exit_code` and non-`llm_structured` states.
- Corrected "no new types": ENH-3527 shipped no resolved-selection type. Added `ModelSelection`, `_resolve_model` and `_preflight_model_hints`.
- Copied the three-row precedence table inline and named the two rules most likely to break.
- Named the backend-key source (`resolve_host().name`) and the overrides source (`orchestration_config.model_hints`).
- Defined when the event fields are emitted, and the header format and live update.
- Pulled the `CONFIGURATION.md:1370` sentence and the `EVENT-SCHEMA.md` field rows into scope, because ENH-3548 is blocked by this issue and they would otherwise be wrong in the meantime.
- Added `info.py` and the missing test files. Fixed Current Behavior line anchors (−4 drift).

Second pre-implementation review 2026-09-27 made these changes:

- **Error routing.** The dispatch-time `ModelHintError` would have been sent to `on_error` by `_run_action_or_route` (`:3868`). It now re-raises there, following the `HeredocCollisionError` precedent. The evaluator path uses `_pending_error`, because a raise during `decide` ends as `no_route`.
- **Child loops.** A child's hint failure would have become a normal parent route to `on_error`/`on_no`. Decided to propagate it through `ExecutionResult.model_hint_error`. The sub-loop `ValueError` catch (`:2096`) also re-raises it.
- **Preflight side effects.** Calling `_resolve_request_path` from the preflight would have emitted the one-shot downgrade warning at run start. It is now split into the pure `_compute_request_path`. The preflight now resolves against the effective backend, including the credential/import probes.
- **Event fields.** Decided on "always emit when a model is passed". `evaluate` and SDK/batch events therefore always carry the fields, since `llm.model` is never empty. The byte-identical guarantee is narrowed to no-declaration CLI actions.
- **Header display.** Split out to ENH-3638, which also covers the non-raising display helper for unconsumed, unmapped `llm.model_hint`.
- Marked the `--llm-model` AC as test-only. Fixed the fake-runner and guard anchors. Removed the stale "belongs to ENH-3548" docs clause.

Third pre-implementation review 2026-09-27 made these changes:

- **CI risk from `resolve_host()`.** It raises `HostNotConfigured` with no host on PATH, and the conftest clears `LL_HOST_CLI`, so GitHub-hosted runners would fail. Resolution now calls it only for hints; the literal-selection `model_backend` lookup is non-raising; the preflight catches `HostNotConfigured`; backend-asserting tests set `LL_HOST_CLI`. Added an AC for this.
- **Evaluator error path.** Replaced "set `_pending_error` and return" with a dedicated `except ModelHintError` clause in `run()`. The old approach would have let `_execute_state` run the tamper guard, `captured` write, stall detection and routing after the failed evaluation. Sub-loop propagation now raises through the same clause.
- **Evaluate event fields.** Narrowed "always" to `llm_structured` events with LLM enabled, which resolves the contradiction with AC15 and the resolve-only-where-consumed rule.
- **SDK selection.** `_run_action` resolves the path and selection once and passes the selection into `_dispatch_live`, so the payload matches the request. Rewrote the Call Path to match the real call chain (`dispatch_anthropic_request`, `ActionRunner.run` → `run_claude_command`) and added the preflight chain.
- Fixed the `test_cross_host_baseline.py:130` misattribution. Noted that `test_llm_hint_blocks` flips polarity. Named every host in the argv AC. Put `contract`/`comparator` model routing out of scope.

Fourth pre-implementation review 2026-09-27 made these changes:

- **Learning-state remedy.** `_execute_learning_state` calls `_run_action` directly (`executor.py:1527`) with a prompt-mode copy of the state, so it resolves the learning state's declaration. A preflight keyed on `_action_mode(state)` would have missed it, and an unmapped hint would have failed mid-run. The preflight now covers learning states. Added AC18.
- **`model_hint_error` mechanism.** `_finish` had no way to set the field. Added a keyword-only `model_hint_error` parameter to `_finish`. Added AC19.
- **SDK literal `model_resolved`.** `build_anthropic_request` alias-resolves every model, so a literal would have reported the pre-alias string. `_resolve_model(..., "sdk")` now alias-resolves literals too, and tests assert at the SDK-client mock. Updated AC16.
- **Fake-host argv order.** The "`ll-fake-host` needs no change" claim held only for fenced prompts. `main()` falls back to `args[-1]`, so an appended `--model X` would be parsed as the script. The fakes now put `--model` before the prompt. Updated AC5.
- Numbered the ACs and fixed the stale cross-references (portability proof is AC17; resolve-only-where-consumed is AC15; routing tests are AC12/AC14).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- Broad-but-narrowed surface: ~8-10 change sites concentrated in `executor.py` (guard removal, new `_preflight_model_hints`/`_resolve_model`/`_compute_request_path`, `_dispatch_live`'s new `selection` param, `ModelHintError` handling at four call sites, `_execute_sub_loop` propagation) plus `host_runner.py`'s two fake-runner classes and `fsm/types.py` — narrower than the prior assessment now that the header/display work split to ENH-3638, but still a control-flow change (exception routing) rather than a uniform substitution — mitigate by landing the `ModelSelection`/`_resolve_model`/`_preflight_model_hints` core and its exception routing first, verified in isolation, before wiring the remaining dispatch call sites.
- Moderate depth: threading a single resolved `ModelSelection` through `_run_action`/`_dispatch_live` and re-routing `ModelHintError` around four different exception handlers (`run()`, `_run_action_or_route`, `_execute_state`'s sub-loop catch, `_execute_sub_loop`) is cross-function/cross-module logic with shared state, not a mechanical edit — get the routing tests (AC12/AC14) green before extending to the remaining paths.
- Issue itself flags zero test coverage today for AC3 (evaluator hint on an `sdk` state resolving against the CLI host) and a from-scratch fixture gap for AC17 (portability proof) — write these tests before or alongside the corresponding code change, not after.

_Verified 2026-09-27: all deterministic gates clean (learning test target "anthropic" proven, Program Design gate passes, `blocked_by: ENH-3527` resolved/done, zero format-check gap findings). Spot-checked every cited `executor.py`/`host_runner.py`/`fsm/types.py` anchor against current source — all resolve to the exact lines the issue cites, confirming the guard and inline fallback expressions are still unimplemented and the codebase-research claims still hold.

## Session Log
- `/ll:confidence-check` - 2026-09-27T23:51:56 - `9ec66b6d-aabf-4e14-8dd4-76aef25da24d.jsonl`
- `/ll:confidence-check` - 2026-09-27T21:59:52 - `f000b0e2-afd6-484c-86d4-f9adb2596b9a.jsonl`
- `/ll:confidence-check` - 2026-09-27T21:02:32 - `75a0f181-d47d-4633-992b-de27bddbd43d.jsonl`
- `/ll:wire-issue` - 2026-09-27T20:39:53 - `e3045b14-86be-4cd8-801e-cb4a91f14a76.jsonl`
- `/ll:refine-issue` - 2026-09-27T20:25:25 - `b7c94eba-e7a8-40c2-a5f2-39f525e86d43.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:56 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
