---
id: BUG-3704
type: BUG
title: Native 1M models use stale 200k context limits
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-03T01:25:23Z'
reconcile_attempted: true
verify_verdict: VALID
missing_artifacts: true
confidence_score: 85
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
deferred_by: automation
deferred_date: '2026-10-03T02:04:07Z'
deferred_reason: low_readiness
---

# BUG-3704: Native 1M models use stale 200k context limits

## Summary

Native 1M Claude models currently fall back to 200 000 tokens in Python and the shell context monitor. This prematurely triggers handoff and compression. Correcting the table also needs to preserve lower effective host limits; raising the denominator without that handling could delay a handoff past the actual limit. Split from BUG-3701 during its pre-implementation review with `/ll:advise` (Opus, 2026-10-02).

## Current Behavior

- `scripts/little_loops/context_window.py:19` has no Claude 5.x entries; all existing entries equal the 200 000 floor, including a fictitious `claude-opus-3-7` entry.
- `hooks/scripts/context-monitor.sh:179` handles `[1m]` but otherwise returns 200 000. Its caller at line 335 supplies the environment override.
- Live [Sonnet 5.5 specifications](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) and [Claude Code model configuration](https://code.claude.com/docs/en/model-config) confirm native 1M for Sonnet 5/5.5. The latter also documents `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`, gateway limits, and other host-specific caps. API maximum and effective host window are different contracts.
- The table also understates some 4.x native windows according to the current Claude Code docs (Opus 4.7/4.8); verify exact IDs individually before changing them.

## Expected Behavior

Resolve the effective window used by each consumer, with explicit LL overrides taking precedence and verified model defaults used only when no lower host constraint applies. Python and shell must agree for equivalent inputs. Preserve the conservative 200k floor for unknown IDs and retain real legacy model entries regardless of whether they have pricing coverage.

## Motivation

The stale denominator triggers avoidable continuation and compression on native-1M sessions. A safe correction must preserve lower deployment limits while sizing unconstrained sessions accurately; changing only the constants could suppress a required handoff.

## Proposed Solution

1. Audit consumers before choosing a shared model-capacity helper versus a host-aware effective-window resolver. Known consumers include `issue_manager.py`, `subprocess_utils.py`, `parallel/worker_pool.py`, `compression/heuristic.py`, `compaction/instant.py`, and the shell context monitor. Record which consumes an observed model, an API request model, or no model.
2. Verify exact native windows from official model specifications. At minimum cover Sonnet 5/5.5, Opus 5.5, and Fable 5.1; audit legacy 5.x and Opus 4.7/4.8 separately. Remove fictitious `claude-opus-3-7`; retain real `claude-sonnet-4-5`. Do not require context-window keys to be a subset of `MODEL_PRICING`.
3. For Claude Code consumers, account for documented native-1M caps such as `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`. Define precedence relative to explicit LL overrides and `[1m]` before implementation. Do not inject CLI-only caps into SDK compression. For unobservable provider/gateway limits, document the existing explicit override instead of guessing the deployment capacity.
4. Mirror model defaults in the shell layer and require automated, environment-isolated parity tests. Exercise explicit/config and positive environment overrides, `[1m]`, verified native windows, a lower host cap, and unknown-model fallback. Test source-extracted functions or a supported test seam without executing the hook's main routine.
5. Check the affected models' official long-context pricing before release. [Current pricing](https://platform.claude.com/docs/en/about-claude/pricing) and Claude Code docs state standard pricing for current native-1M models; preserve that evidence and keep unrelated TTL/geography pricing out of scope.

## Integration Map

### Files to Modify

- `scripts/little_loops/context_window.py` — model capacities and documented effective-window contract, after consumer audit
- `hooks/scripts/context-monitor.sh` — shell resolution and matching precedence
- `scripts/tests/test_context_window.py` — native-window, override, cap, and Python/shell parity cases
- `docs/reference/API.md` — context-window contract and examples
- Consumer files listed below only where the audited host/API boundary requires an explicit effective-window argument

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-handoff-sentinel.sh` — second shell resolver (state `.context_limit` → `LL_CONTEXT_LIMIT` → config `context_limit_estimate` → hard-coded `"200000"` at lines ~64/66); has no model map, so a lower host cap or native-1M default applied only in `context-monitor.sh` must still reach this Stop-hook denominator via the state file — confirm, don't assume [Agent 1/2 finding]
- `scripts/little_loops/cli_args.py` — `add_context_limit_arg` help text (~205): "200000 for known Claude 4 models, 1000000 for 1M-context sessions" goes stale with the table [Agent 1/2 finding]
- `scripts/little_loops/config-schema.json` — `context_limit_estimate` description (~974-979): "known claude-*-4* base variants -> 200000" (`maximum: 2000000` unchanged) [Agent 1/2 finding]
- `hooks/scripts/context-monitor.sh:main` — three further sites that scale with the resolved `CONTEXT_LIMIT` and move when the denominator changes: the post-compaction reset (~250, `CONTEXT_LIMIT * POST_COMPACT_PERCENT / 100`), the sanity clamp (~439, `NEW_TOKENS > CONTEXT_LIMIT * 3`, comment cites "1517046/200000"; the clamp rises from 600K to 3M for a 1M model), and the `get_context_limit` header comment (~178, "all other models -> 200000"). `LL_CONTEXT_LIMIT` is applied at ~335 via `${LL_CONTEXT_LIMIT:-$(get_context_limit …)}`, so any `CLAUDE_CODE_DISABLE_1M_CONTEXT` handling inside the function is bypassed whenever the env override is set [Agent 2 finding]
- `scripts/tests/conftest.py` — add `CLAUDE_CODE_DISABLE_1M_CONTEXT` to `_CMD_RUN_ENV_VARS` (~1193) if either layer reads it; `test_hooks_integration.py` hook subprocesses inherit `os.environ`, so an ambient export would leak into every hook test [Agent 2/3 finding]
- `scripts/tests/test_hooks_integration.py` — `TestContextMonitor` is the parity/threshold locus (see Tests below) [Agent 1/3 finding]
- `docs/reference/CONFIGURATION.md` — `context_limit_estimate` row (~533) and compression-trigger prose (~1881-1896) [Agent 1/2 finding]
- `docs/guides/SESSION_HANDOFF.md` — `context_limit_estimate` table row (~283: "known Claude 4 base models → 200000 ... auto-upgrades"), sample state JSON (~385), `context_limit` field description (~410) [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — `context_limit_estimate` description (~324) [Agent 1/2 finding]
- `skills/configure/areas.md` — "Limit" question option `"200k (standard Claude 4 models)"` (~639); edit trips the mirror gates, so regenerate `.gemini/`, `.kimi-code/`, `.qwen/` copies with `ll-adapt --host <gemini|kimi-code|qwen> --apply` [Agent 2 finding]

### Dependent Files

- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/subprocess_utils.py`, `scripts/little_loops/parallel/worker_pool.py`
- `scripts/little_loops/compression/heuristic.py`, `scripts/little_loops/compaction/instant.py`
- `scripts/tests/test_issue_manager.py`, `scripts/tests/test_worker_pool.py`, and compression/compaction tests for changed consumers

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — FEAT-2675 compression block passes `model=self.run_model` (~2567) to `compress_action_text`; the only production caller where a native-1M table entry moves a threshold (full model ID only; aliases stay at the floor) [Agent 2 finding]
- `scripts/little_loops/issue_manager.py:run_with_continuation` / `process_issue_inplace` — `run_with_continuation` (def at 260) carries the signature default `context_limit: int = 200_000` (271) and docstring "default 200K" (304), literals independent of the table; `process_issue_inplace` (def at 720) declares `context_limit: int | None = None` (731) and its call `context_window_for(None, override=context_limit)` (1336) is the injection seam, so no `Update` bullet — redirect any host cap to the value passed here, not the default [Agent 1/2 finding]
- `scripts/little_loops/subprocess_utils.py:detect_context_handoff` / `build_continuation_prompt` — `context_window_for(None)` (452) and `token_stats.get("context_limit") or context_window_for(None)` (506); model-blind, table change has no effect [Agent 1/2 finding]
- `scripts/little_loops/cli/auto.py` (96), `cli/parallel.py` (242), `cli/sprint/run.py` (378), `cli/loop/run.py` (267) — export `--context-limit` as `LL_CONTEXT_LIMIT`; `auto.py`/`parallel.py` reject values < 50000, `loop/run.py` has no minimum. `cli/loop/runner.py` (271-273) re-forwards the flag to a background child. `LL_CONTEXT_LIMIT` is the existing cross-process carrier, so a CLI-side host cap would enter here, not in `context_window_for`, to keep SDK compression unaffected [Agent 1/2 finding]
- `scripts/little_loops/hooks/adapters/qwen/stop.sh` — invokes `context-handoff-sentinel.sh` (lines 7, 24); keep filename/path stable [Agent 1 finding]
- `hooks/hooks.json` — registers `context-monitor.sh` (~137) and `context-handoff-sentinel.sh` (~225) by path only; no edit unless filenames change [Agent 1 finding]
- Not dependents (confirmed no code dependency): `config/features.py` docstring ("`context_window_for()` is not consulted"), `doc_counts.py` docstring, `hooks/pre_compact.py` comments, `.claude-plugin/plugin.json`, all loop YAMLs, and `.claude/worktrees/agent-*/` stale copies [Agent 1/2 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_context_window.py::TestContextWindowFor::test_known_opus_returns_200k` (`claude-opus-4-8`) and `test_known_sonnet_returns_200k` (`claude-sonnet-4-6`) — hard-code 200k; break only if the audit moves those 4.x IDs to 1M. `test_known_haiku_returns_200k` is probably safe [Agent 3 finding]
- `scripts/tests/test_context_window.py` — new cases: Sonnet 5/5.5, Opus 5.5, Fable 5.1 resolve to 1M; `claude-opus-3-7` asserted absent; `CLAUDE_CODE_DISABLE_1M_CONTEXT` cap and its precedence against `LL_CONTEXT_LIMIT` and `[1m]` (follow the `monkeypatch.setenv` style of the `LL_CONTEXT_LIMIT` cases at ~32-48) [Agent 2/3 finding]
- `scripts/tests/test_compaction.py::TestComputeGoalTokens::test_default_sliding_window_percentage` — asserts `int(0.7 * 200_000)` for `claude-opus-4-8`; breaks if that ID changes [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestContextMonitor::test_known_model_auto_detection` (~639) — `claude-sonnet-4-6` with a 180K baseline expects exit 2 and `"200000"` in stderr; breaks if sonnet-4-6 becomes 1M [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestContextMonitor::test_1m_model_limit_resolution` (~1231) — uses `claude-opus-4-8` with a 250K baseline to exercise the shell-only auto-upgrade (`context-monitor.sh:411-414`); stays green if opus-4-8 goes native-1M but stops testing the auto-upgrade — switch to a model that stays at 200k (haiku or unknown) [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestContextMonitor::test_1m_model_suffix_auto_detection` / `test_sentinel_1000000_honored_as_explicit_override` / `test_unknown_model_config_fallback` — model for the new hook-subprocess cases (transcript fixture with `message.model`, baseline chosen so exit 0/2 proves the denominator, then assert state-file `context_limit`) [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestContextHandoffSentinel` (~3118) — writes `context_limit: 200000` into the state file; unaffected unless the sentinel's resolution changes [Agent 3 finding]
- Parity test (new): no function-extraction precedent exists for bash (`context-monitor.sh` calls `main` unconditionally at ~592; `get_context_limit` spans ~179-190). Closest patterns: `TestSharedConfigFunctionsBashSmoke::test_common_sh_still_defines_bash_primitives` (`bash -c 'source … && …'`) and `test_record_hook_event_shim.py` bash-version matrix (`_available_bashes()`, includes macOS `/bin/bash` 3.2); extract the function text by regex, then run it under `bash -c` with an isolated env (`env=` built explicitly, not `os.environ.copy()`) [Agent 3 finding]
- `scripts/tests/test_issue_manager.py::TestAutoManagerModelDetection::test_context_window_sizes_from_resolved_model_not_alias` — still holds (bare alias stays at floor); new regression should assert the `context_limit` handed to the mocked `process_issue_inplace` [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` (compression tests ~237-380) and `test_heuristic_compression.py::TestCompressActionText` — no test derives the window from a native-1M `run_model` (existing cases pass `trigger_tokens` explicitly); add one executor-level case [Agent 3 finding]
- `scripts/tests/test_bug3689_gate_env.py:43` pins the exact `HERMETIC_ENV_VARS` tuple (`LL_PYTHON`, `COLUMNS`, `LINES`) — update in lockstep if `CLAUDE_CODE_DISABLE_1M_CONTEXT` is added there [Agent 3 finding]
- `scripts/tests/test_wiring_guides_and_meta.py` (~165) pins the TROUBLESHOOTING.md `hooks/scripts/context-monitor.sh` link; `test_docs_audience_gate.py` applies to the docs edits (no `scripts/tests/…` paths in `docs/guides`/`docs/reference`) [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_context_window.py::TestContextWindowFor` (~37-52) — the `LL_CONTEXT_LIMIT` precedence cases use `claude-opus-4-8` as the "base model"; they stay valid only if the audit leaves 4.8 at 200k, otherwise repoint them to haiku or an unknown ID [Agent 2 finding]
- `scripts/tests/test_heuristic_compression.py::TestCompressActionText` (~242) — `compress_action_text(text, model="claude-opus-4-8") == text` relies on the 200k trigger window; re-check if Opus 4.8 moves to 1M [Agent 2 finding]
- `scripts/tests/test_hooks_integration.py::TestContextMonitor::test_impossible_legacy_count_does_not_trigger` (~1347) — asserts `state["estimated_tokens"] <= 200000` (~1386); the sanity clamp scales with `CONTEXT_LIMIT * 3`, so this ceiling is limit-dependent [Agent 2/3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` (~489) and `::test_skill_mirrors_carry_companions` (~614) — fail if `skills/configure/areas.md` is edited without regenerating the `.gemini/`, `.kimi-code/`, `.qwen/` mirrors; this is the gate behind the `ll-adapt --apply` step [Agent 2/3 finding]
- `scripts/tests/test_cli_args.py` (~481-553, `add_skip_arg`/`add_json_arg` help-text pattern) — no existing `--context-limit` help-text assertion, so the `cli_args.py` rewording breaks nothing; add one only if a regression guard is wanted [Agent 3 finding]
- Hermetic bash template for the parity test: combine the `bash -c` call of `TestSharedConfigFunctionsBashSmoke::test_common_sh_still_defines_bash_primitives` (~2118) with the filtered-env dict of `test_bug3689_gate_env.py::test_suite_passes_with_ambient_gate_env` (~68), dropping `LL_CONTEXT_LIMIT` and `CLAUDE_*` so the `case` statement alone decides [Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — beyond the `context_window_for` section (~2861-2896, where `claude-opus-4-8` → `200_000` at ~2891 and the precedence list live): consumer bullets at ~13688/13709 ("falls back to `context_window_for(None)`") and `compute_goal_tokens` / `compress_action_text` descriptions (~9695, ~9873) [Agent 1/2 finding]
- `docs/reference/CLI.md` — `--context-limit` rows (~27, 692, 753, 821, 940, 1248) carry no model claim; edit only if the `cli_args.py` help is reworded [Agent 2 finding]
- Generated `site/` HTML is git-tracked (`site/reference/CONFIGURATION/index.html`, `site/guides/SESSION_HANDOFF/index.html`, `site/search/search_index.json`) and repeats "claude-*-4* → 200 000"; regenerate through the docs build rather than hand-editing [Agent 1/2 finding]
- No `CHANGELOG.md` entry under `[Unreleased]` (project convention) [Agent 2 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `context_limit_estimate` description text only; no Python reader exists (`config/features.py` has no field, value is read only by shell via `ll_config_value`), so no dataclass or `test_config_schema.py` change [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Consumer audit (model source → use).** `AutoManager._process_issue` (`issue_manager.py:2155`) passes the resolved model from the first completed issue (`None` for the first issue); `process_issue_inplace` (`:1336`) always re-resolves with `model=None` plus its `context_limit` as override; `WorkerPool._run_with_continuation` (`worker_pool.py:1069`) and `write_sentinel` (`subprocess_utils.py:452`) pass `None`; `compute_goal_tokens` (`compaction/instant.py:78`) passes its caller's model; `compress_action_text` (`compression/heuristic.py:276`) is called from `fsm/executor.py` (~2567) with `self.run_model`, the raw `--model` string (may be an alias, which hits the floor), and runs for both CLI and SDK/batch request paths.
- **Only two consumers make a size/percentage decision.** `compress_action_text` (compression trigger = lower of `trigger_pct × window` and `trigger_tokens`) and `context-monitor.sh` (usage %, handoff exit 2). The `issue_manager` / `worker_pool` / `subprocess_utils` paths use the value for display text and the guillotine prompt only (the `usage_ratio` trigger was removed in BUG-2280); `write_sentinel` and `select_sliding_window`/`compute_goal_tokens` have no production caller outside tests/docs. Raising the table therefore changes compression and shell-hook thresholds materially, and the rest only cosmetically.
- **Python and shell already diverge in precedence.** Python: override arg > `LL_CONTEXT_LIMIT` (positive int only; invalid/zero/negative fall through) > `[1m]` > table > floor. Shell: `LL_CONTEXT_LIMIT` (applied verbatim by the `:-` expansion in `main()`, no numeric validation, literal `0` accepted) > config `context_limit_estimate` > `[1m]` > floor. The shell function has no table at all — its `claude-*-4*` branch equals the default. A parity test has to pin these differences deliberately rather than assume equivalence.
- **Shell-only auto-upgrade (no Python counterpart).** After resolution, `main()` (~`context-monitor.sh:411-414`) promotes a limit ≤200000 to 1000000 when the transcript baseline exceeds the limit and is ≤1100000. A correct native-1M table interacts with this: it must stay consistent with a lower host cap rather than being silently overridden by it.
- **Second shell resolver.** `hooks/scripts/context-handoff-sentinel.sh` (lines ~58-66) resolves the limit independently of `get_context_limit` (state-file `.context_limit` → `LL_CONTEXT_LIMIT` → config `context_limit_estimate` → 200000). It is a Stop-hook consumer of the same denominator and is not listed under Files to Modify.
- **No test seam in `context-monitor.sh`.** It runs `set -euo pipefail`, `INPUT=$(cat)`, config resolution and a bare trailing `main` at top level, with no `BASH_SOURCE` guard, so it cannot be sourced to call `get_context_limit`. `get_context_limit` has zero references under `scripts/tests`. Existing hook tests (`test_hooks_integration.py::TestContextMonitor`) run the whole hook via `subprocess.run` with a transcript fixture and `LL_CONTEXT_LIMIT`; `lib/common.sh` is sourced via `bash -c` elsewhere. A parity test must either extract the function body or run the hook end to end and read `.context_limit` from its state file.
- **`CLAUDE_CODE_DISABLE_1M_CONTEXT` is read nowhere** (code, shell, tests, docs, conftest `_CMD_RUN_ENV_VARS`); it appears only in this issue file.
- **Stale 200k claims outside the listed files.** `--context-limit` help text in `cli_args.py` (~205) and the `context_limit_estimate` description in `config-schema.json` both state "200000 for known Claude 4 models, 1000000 for 1M-context sessions"; `docs/reference/API.md` (~2861-2896) lists only `issue_manager`/`subprocess_utils`/`worker_pool` as consumers and omits `compression`/`compaction`.
- **Existing test that does not assert the threshold it implies.** `test_issue_manager.py::TestAutoManagerModelDetection::test_context_window_sizes_from_resolved_model_not_alias` recomputes `context_window_for(...)` itself and never asserts the `context_limit` handed to the mocked `process_issue_inplace`; consumer-threshold regression coverage for `_process_issue` does not exist today. `test_context_window.py` has no 5.x, cap, or shell-comparison cases.

## Implementation Steps

1. Record exact vendor sizes and the cap/override precedence, including where a CLI-only cap enters (the `LL_CONTEXT_LIMIT` seam). The consumer audit is already in Codebase Research Findings: only `compress_action_text` and `context-monitor.sh` make size/percentage decisions.
2. Implement the smallest host-aware correction in `context_window.py` and add the model defaults the shell resolver lacks (it has no table today); reconcile the shell-only 200k→1M auto-upgrade with any lower host cap.
3. Add automated Python/shell parity tests that pin the deliberate precedence differences (extracted `get_context_limit` or end-to-end hook run with an isolated env) and executor/`context-monitor.sh` threshold regressions; update affected documentation.
4. Run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `hooks/scripts/context-monitor.sh` — rewrite the `get_context_limit` case (it currently has a redundant `claude-*-4*` branch equal to the default) and reconcile the 200k→1M auto-upgrade at ~411-414 with a lower host cap
- Update `hooks/scripts/context-handoff-sentinel.sh` — confirm it inherits the effective limit through the state file; its `"200000"` defaults (~64/66) are otherwise a third resolver
- Inject at `scripts/little_loops/cli/auto.py` / `cli/parallel.py` / `cli/sprint/run.py` / `cli/loop/run.py` — `LL_CONTEXT_LIMIT` export is the seam for a CLI-only host cap; do not change `context_window_for(None)` callers in `subprocess_utils.py` / `worker_pool.py`
- Update `scripts/tests/conftest.py` — add `CLAUDE_CODE_DISABLE_1M_CONTEXT` to `_CMD_RUN_ENV_VARS` if read by either layer
- Update `scripts/tests/test_context_window.py`, `test_compaction.py`, and `test_hooks_integration.py::TestContextMonitor` — repoint the 200k assertions for any ID that moves; swap the auto-upgrade test to a model that stays at 200k
- Add Python/shell parity test (source-extracted `get_context_limit` under isolated env) and a `_process_issue` / executor consumer-threshold regression
- Update `scripts/little_loops/cli_args.py` and `scripts/little_loops/config-schema.json` — reword the "200000 for known Claude 4 models" claims
- Update `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md`, `docs/guides/BUILTIN_HOOKS_GUIDE.md` — effective-window contract and stale 200k prose
- Update `skills/configure/areas.md`, then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` for the three mirrors
- Update `hooks/scripts/context-monitor.sh` — re-check the sanity clamp (~439) and post-compaction reset (~250) once the limit can be 1M, and refresh the `get_context_limit` header comment (~178); then confirm `test_impossible_legacy_count_does_not_trigger` still holds
- Verify `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` and `::test_skill_mirrors_carry_companions` pass after regenerating the mirrors

## Program Design

### Types

- `MODEL_CONTEXT_WINDOW: dict[str, int]` — existing exact-ID capacity table; verified native-1M entries and removal of the fictitious entry
- Effective host window — a positive token count after the relevant consumer's host cap and explicit overrides; the consumer audit chooses whether to expose a wrapper or pass this value at the CLI boundary

### Signatures

- `context_window_for(model: str | None, override: int | None = None) -> int` — existing generic resolver; preserve its caller contract while separating API capacity from CLI caps
- `get_context_limit()` — existing shell resolver accepting model and config override; keep equivalent model defaults and documented override behavior

### Call Path

`issue_manager.py` / `compression/heuristic.py` / `compaction/instant.py` -> `context_window_for` -> model capacity and explicit LL override. `hooks/scripts/context-monitor.sh:main` -> `get_context_limit` -> effective CLI denominator. `parallel/worker_pool.py:_run_with_continuation` also calls `context_window_for(None)`, so it has no model ID to infer a native window from; preserve that fallback unless the consumer audit explicitly adds model detection.

The remaining design decision is where CLI-only caps enter this call path. Record the audited choice and its precedence before implementation; do not treat a source-confirmed model maximum as a proven deployment limit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- `_process_issue` resolves its limit before `process_issue_inplace` runs, so the first issue of an `ll-auto` run always gets the `model=None` result; any fix that depends on the observed model only helps from the second issue onward unless the model is known earlier.
- `compress_action_text` receives the user-supplied run model, not a resolved ID: aliases (e.g. `sonnet`) miss both the table and `[1m]`, so the table fix alone does not size alias-selected runs. Whether to resolve aliases is a consumer-audit decision, not implied by the table update.
- `worker_pool._run_with_continuation` and `write_sentinel` have no model to look up; they stay on env-var or floor behavior regardless of the table.

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Current resolver contracts (anchors).** `context_window.py`: `MODEL_CONTEXT_WINDOW` (line 19) holds 11 exact keys, all `200_000`; `_DEFAULT_CONTEXT_WINDOW` (35) and `_1M_CONTEXT_WINDOW` (36) are the private constants; `context_window_for(model: str | None, override: int | None = None) -> int` (39) resolves override (truthy only) → inline `LL_CONTEXT_LIMIT` read (the module's only env read; no helper exists) → `model is None` floor → `endswith("[1m]")` → exact `.get(model)` → floor. Shell `get_context_limit()` (`context-monitor.sh:179`) takes `$1` model and `$2` config override, tests the config override *before* `[1m]`, then uses prefix globs (`claude-opus-4*|claude-sonnet-4*|claude-haiku-4*` and `*`, both `200000`) rather than an exact table — so any new shell native-1M branch decides by prefix and Python by exact key; equivalent inputs only agree if the two key sets are kept deliberately aligned.
- **`MODEL_CONTEXT_WINDOW` is referenced nowhere outside `context_window.py`** (repo-wide search of py/sh/json/yaml/toml; zero test references), and no test relates its keys to `MODEL_PRICING`/`MODEL_ALIASES`/`MODEL_RANKS`. Dropping `claude-opus-3-7` or retaining `claude-sonnet-4-5` (priced nowhere in `pricing.py`) therefore trips no existing gate; the subset-free contract in the Proposed Solution has no test to update.
- **Other model tables already carry 5.x IDs the context table lacks.** `MODEL_PRICING` (`pricing.py`) has `claude-fable-5-1`, `claude-fable-5`, `claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5`; `host_runner.MODEL_ALIASES` maps `sonnet → claude-sonnet-5`, `opus → claude-opus-5-5`, `fable → claude-fable-5-1`, `haiku → claude-haiku-4-5`; `advisor.MODEL_RANKS["claude-code"]` ranks the same 5.x IDs. `claude-sonnet-5-5` (the ID the Steps to Reproduce uses) is absent from `MODEL_PRICING` (BUG-3696) and from the aliases. Consequence for the audit: `compress_action_text` receives the raw `--model` string (`executor.py` ~2560, `run_model`, ENH-3547 comment), so `--model sonnet` misses the table and `[1m]` and stays at the floor even after the table gains `claude-sonnet-5`; `resolve_model_alias()` is not applied on that path.
- **Compression threshold arithmetic.** `compress_action_text(text, *, model, context_window, trigger_pct=0.4, trigger_tokens=None, …)` (`compression/heuristic.py`) resolves `context_window_for(model)` only when `context_window is None`, then `_resolve_trigger()` takes the `min` of `int(trigger_pct × window)` and `trigger_tokens`: 80 000 at a 200k window, 400 000 at 1M. It returns the text byte-identical below the trigger, so a native-1M entry silently stops compression for those runs unless `trigger_tokens` is configured (`config/features.py`, default `None`).
- **Shell ordering detail for the reconciliation.** In `main()`, `check_compaction()` (`context-monitor.sh:230`, reset at 250) runs at 339 against the *pre-auto-upgrade* `CONTEXT_LIMIT`; the 200k→1M auto-upgrade (~408-414) and the `NEW_TOKENS > CONTEXT_LIMIT * 3` clamp (439) run later, and the upgraded value is what is persisted as state `.context_limit`. The post-compaction reset therefore uses a smaller denominator than the one written to state within the same invocation whenever the upgrade fires.
- **Env carriers.** `LL_CONTEXT_LIMIT` is written by `cli/auto.py`, `cli/parallel.py`, `cli/loop/run.py`, `cli/sprint/run.py` and scrubbed in `conftest.py` (~1195); the state file stores one `context_limit` number plus `detected_model` — nothing records a native-vs-effective split, so a host cap applied in only one of Python/shell cannot be observed from the other. `context-handoff-sentinel.sh` (lines 38-66) re-derives from state `.context_limit` → `LL_CONTEXT_LIMIT` → config → hard-coded `200000`.

## Impact

- **Priority**: P3 — current behavior is conservative but triggers early continuation and compression; an incorrect 1M correction could delay required handoffs
- **Effort**: Medium — effective-window contract and consumer audit, beyond a constants-only change
- **Risk**: Medium — a larger window changes handoff and compression thresholds

## Steps to Reproduce

1. Clear `LL_CONTEXT_LIMIT` and call `context_window_for('claude-sonnet-5-5')`.
2. Observe 200 000 despite the published native 1M window.
3. Compare `get_context_limit` with the same model and no config override; it also returns 200 000.

## Root Cause

`MODEL_CONTEXT_WINDOW` and the shell `get_context_limit()` mapping predate native 1M models. The generic Python helper is also used by API compression and compaction, so blindly applying Claude Code environment flags there could incorrectly change SDK behavior.

## Acceptance Criteria

- [ ] Exact changed model IDs cite official window sizes; fictitious `claude-opus-3-7` is removed and real legacy entries are retained independently of pricing coverage
- [ ] Consumer audit separates model capacity from effective CLI/API limits and records override/cap precedence
- [ ] Verified Sonnet 5/5.5 native windows resolve to 1M when unconstrained; a documented Claude Code 200k cap remains 200k on relevant host consumers
- [ ] Explicit LL overrides, `[1m]`, and unknown-model fallback retain their documented behavior; CLI-only environment flags do not change SDK compression
- [ ] An automated Python/shell parity test runs within pytest with environment isolation; it asserts agreement on equivalent inputs and pins the documented precedence differences between the layers (e.g. shell applies `LL_CONTEXT_LIMIT` verbatim, Python accepts positive ints only)
- [ ] Changed consumer handoff/compression thresholds have regression coverage and docs match the effective-window contract
- [ ] Current long-context pricing assumptions are source-cited
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3701 — alias/rank correction; independent of this context-window change
- BUG-3696 — exact Sonnet 5.5 pricing; independent of context-window coverage
- ENH-2282 — original shared context-window mapping, already done
- BUG-3541 — earlier alias correction explicitly left context windows out of scope, already done

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Existing context-window precedence and consumers |
| `docs/ARCHITECTURE.md` | Continuation and compression boundaries |

## Verification Notes

_`/ll:verify-issues --auto --from-evidence` — 2026-10-03_

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Integration Map (Dependent Files, Callers/Importers): the `context_limit: int = 200_000` default (`issue_manager.py:271`) and "default 200K" docstring (304) belong to `run_with_continuation` (def at 260), not `process_issue_inplace` (def at 720, which declares `context_limit: int | None = None` at 731; the `context_window_for(None, override=context_limit)` seam at 1336 is unchanged). Rewrote the bullet in place.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-02 (re-score after refine-issue gap analysis)_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Root cause re-verified against source (`context_window.py:19` has no 5.x entries; `context-monitor.sh:179` has a redundant `claude-*-4*` branch equal to the default; `LL_CONTEXT_LIMIT` precedence and the 200k→1M auto-upgrade at ~411-414 match the issue). Exact vendor window sizes for Opus 5.5, Fable 5.1, and Opus 4.7/4.8 are still to be confirmed during implementation.
- The consumer audit is now recorded, but the effective-window contract is still undecided: where a CLI-only cap (`CLAUDE_CODE_DISABLE_1M_CONTEXT`, read nowhere today) enters, and its precedence versus `LL_CONTEXT_LIMIT` and `[1m]`, must be fixed before coding.
- Python and shell already diverge in precedence (shell applies `LL_CONTEXT_LIMIT` verbatim; Python accepts positive ints only), and `context-handoff-sentinel.sh` is a third resolver.
- `ll-issues format-check` flags `unmarked_superseded_directive` on this file (advisory; not scored) — mark or remove superseded directive text before implementation.

### Outcome Risk Factors
- Deep per-site complexity: cross-layer (Python + two shell resolvers) precedence reconciliation, including the shell-only 200k→1M auto-upgrade at `context-monitor.sh:411-414`, which can silently override a lower host cap.
- Broad enumeration across ~10+ sites (code, hooks, schema, CLI help, 4 docs, configure skill + 3 mirrors) with no single mechanical substitution.
- Design decisions left open (wrapper vs. CLI-boundary injection, alias resolution for `compress_action_text`); resolve before coding to avoid rework.
- Test seam missing: `context-monitor.sh` has no source guard, so the parity test needs function extraction or an end-to-end hook run; consumer-threshold regression coverage does not exist today.
- Wide dependent surface: ~6 consumers plus both Stop/PostToolUse hooks; a larger denominator changes compression and handoff thresholds materially.


## Session Log
- `/ll:confidence-check` - 2026-10-03T02:03:38 - `fd5be2c0-43d8-4b54-8c03-b378cf03fcb4.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-03T02:01:44 - `26ae68ea-f6f3-459b-8b02-294e5cedb7ac.jsonl`
- `/ll:wire-issue` - 2026-10-03T01:58:07 - `bba5b006-d319-4fb3-b679-604cd3377912.jsonl`
- `/ll:confidence-check` - 2026-10-03T01:51:37 - `5c80f588-6917-4280-a0fd-deb893e83003.jsonl`
- `/ll:verify-issues` - 2026-10-03T01:50:16 - `d5c127c5-1093-4ed6-8c7f-cb02a5eb6377.jsonl`
- `/ll:verify-issues` - 2026-10-03T01:48:15 - `cff10cc1-7a74-4caa-bc06-44f535647ec7.jsonl`
- `/ll:reconcile-issue` - 2026-10-03T01:46:01 - `3346106e-8c53-48d3-b4ad-f3f86399089f.jsonl`
- `/ll:wire-issue` - 2026-10-03T01:43:28 - `71044aa4-4d2a-4fe3-a9fb-7049c7aa41c1.jsonl`
- `/ll:refine-issue` - 2026-10-03T01:36:19 - `b23974b4-ca6c-4d71-b9a2-1d4e04deffd6.jsonl`
- `/ll:capture-issue` - 2026-10-03T01:30:45 - `7cd57e8e-71e0-4299-a1a4-ccd6bda98ee6.jsonl`
