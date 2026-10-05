---
id: BUG-3701
type: BUG
title: 'Stale model tables: MODEL_ALIASES sonnet and MODEL_RANKS lack claude-sonnet-5-5'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:15Z'
parent: EPIC-3562
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-3701: Stale model tables: MODEL_ALIASES sonnet and MODEL_RANKS lack claude-sonnet-5-5

## Summary

Claude Code's built-in `sonnet` alias on the Anthropic API now resolves to `claude-sonnet-5-5`, but two little-loops model tables do not follow:

- `MODEL_ALIASES['sonnet']` in `scripts/little_loops/host_runner.py` still resolves to `claude-sonnet-5`.
- `MODEL_RANKS["claude-code"]` in `scripts/little_loops/advisor.py` has no `claude-sonnet-5-5`.

Evidence: this checkout's local settings select `sonnet`, and run `refine-to-ready-issue-20261002T111524` recorded `claude-sonnet-5-5` on all seven usage rows. The live [Claude Code model configuration](https://code.claude.com/docs/en/model-config) confirms the first-party default on 2026-10-02. It also documents provider-specific defaults and `ANTHROPIC_DEFAULT_SONNET_MODEL` overrides, so this is not a promise of CLI/SDK parity for every deployment.

**Scope revision (Opus review, 2026-10-02):** alias and ordinal rank only. All context-window cleanup/1M expansion is preserved in BUG-3704. That change affects handoff and compression thresholds and needs an effective-host-limit contract; it is not a regression caused by changing this alias.

## Current Behavior

- **Default-path divergence.** On the CLI request path, `sonnet` passes through verbatim and the host binary resolves it according to its provider/settings. With the first-party built-in default that is Sonnet 5.5. On the `sdk` / `batch` path, `resolve_model_alias("sonnet")` returns `claude-sonnet-5` (`host_runner.py:112`; used by hint resolution, API request construction, and `fsm/executor.py:_resolve_model`). The same declaration therefore selects an older model on the direct API path under the default configuration.
- **Undeclared SDK/batch states follow the same default.** `fsm.schema.DEFAULT_LLM_MODEL` is `"sonnet"` (`fsm/schema.py:24`) and is the final fallback in `_resolve_model` for an `sdk` action (state model-or-hint → run `--model` → `llm` model-or-hint, which defaults to `sonnet`). Every SDK/batch prompt state that declares no model therefore moves from Sonnet 5 to Sonnet 5.5 too, not only states that declare `sonnet` or `coding`. Evaluators always dispatch through the CLI host (`_resolve_model(..., "evaluator")`), which passes the alias verbatim, so they are unchanged by this alias edit. Other `DEFAULT_LLM_MODEL` consumers (the `ll-harness` semantic-judge model; `cli/artifact/discover.py`/`extract.py`, `cli/issues/link_epics.py`, `advisor.consult`) should be checked at implementation time for any direct API-path use.
- **Unranked model.** `advisor.rank_model("claude-code", "claude-sonnet-5-5")` returns `None`, so advisor capability-floor comparisons treat this current, observed model as unranked.
- **Floor behavior.** `check_floor('claude-code', 'opus', 'claude-code', 'claude-sonnet-5-5')` currently returns `unknown`, despite the existing ordinal Sonnet < Opus convention.

## Steps to Reproduce

1. `python -c "from little_loops.advisor import rank_model; print(rank_model('claude-code', 'claude-sonnet-5-5'))"`: prints `None`.
2. `python -c "from little_loops.host_runner import resolve_model_alias as r; print(r('sonnet'))"`: prints `claude-sonnet-5`.
3. `python -c "from little_loops.advisor import check_floor; print(check_floor('claude-code', 'opus', 'claude-code', 'claude-sonnet-5-5').status)"`: prints `unknown`.

## Expected Behavior

- `MODEL_ALIASES['sonnet']` is `claude-sonnet-5-5`, matching the current first-party built-in CLI default. SDK and batch requests using `sonnet` or the built-in `coding` hint send that concrete ID.
- `MODEL_RANKS["claude-code"]["claude-sonnet-5-5"] == 2`, the same tier as `claude-sonnet-5` (below Opus 3 and Fable 4, above Haiku 1).
- Explicit concrete IDs, including pinned `claude-sonnet-5`, remain unchanged. CLI aliases continue to pass through to the host; provider/settings override synchronization is outside scope.
- Capability-floor comparisons rank both literal Sonnet 5.5 and normalized `sonnet` aliases correctly; unrelated unknown models still remain unranked.

## Motivation

Under first-party built-in defaults, the SDK path silently runs an older model than the CLI path for the same declaration, and the advisor floor cannot rank Sonnet 5.5. Split out of BUG-3696 (advisor review, 2026-10-02): this issue owns alias selection and ordinal ranking.

## Proposed Solution

1. `host_runner.py`: change `MODEL_ALIASES["sonnet"]` to `"claude-sonnet-5-5"`. Keep the BUG-2828 rationale and clarify that the table tracks first-party built-in defaults, not every provider or `ANTHROPIC_DEFAULT_*_MODEL` setting.
2. `advisor.py`: add `"claude-sonnet-5-5": 2` to `MODEL_RANKS["claude-code"]`. Keep `claude-sonnet-5` (rank 2) for runs that pin it explicitly.
3. Update the alias-resolution and SDK/batch boundary tests. Add explicit hint, pin-preservation, alias-normalization, and floor-result regressions; assertions derived only from `MODEL_ALIASES` cannot catch a stale alias value.
4. Update API/event documentation (required: the `MODEL_RANKS` order sentence, the `model_resolved` example and the CLI `coding →` example) and record a release note at release prep (not under `[Unreleased]`): `sonnet`, built-in `coding` **and any SDK/batch state with no declared model (the `DEFAULT_LLM_MODEL` fallback)** now select Sonnet 5.5 on the direct API paths. [Live pricing](https://platform.claude.com/docs/en/about-claude/pricing), verified 2026-10-02, gives Sonnet 5 and 5.5 identical per-token rates; task token usage, behavior, and total cost can still change. Users can pin `claude-sonnet-5` to retain their current model.
5. Keep selection/rank pricing coverage from BUG-3696 (it extends the existing `test_every_alias_target_is_ranked_and_priced`; do not add a second copy here). Do not extend it to context-window keys: context sizing and price support are independent, and deleting a real legacy model to satisfy a price-subset assertion would be wrong.

## Verified Non-Issues (2026-10-04)

Checked against the code so nobody re-investigates:

- `hooks/scripts/context-monitor.sh:187` and `context_window.py` have no `claude-sonnet-5` entry either; both fall to the 200k floor. That is BUG-3704's scope and is unchanged by this alias edit.
- The remaining literal `claude-sonnet-5` hits outside tables, tests and docs are docstring/comment examples only (`cli/loop/header.py:123`, `issue_manager.py:172`, the `pricing.py` header); no behavior depends on them.
- `adapters/core.py:242` treats any `MODEL_ALIASES` key or `claude-` prefix as a Claude model; no change needed.
- `build_anthropic_request` sends no sampling, thinking or forced tool-choice parameters, so no request rewrite is needed for Sonnet 5.5.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py:112`: `MODEL_ALIASES["sonnet"]`
- `scripts/little_loops/advisor.py:~55`: `MODEL_RANKS["claude-code"]`
- `scripts/tests/test_host_runner_dispatch.py`, `scripts/tests/test_model_hints.py`, `scripts/tests/test_advisor.py`: boundary and floor regressions
- `docs/reference/API.md:~12494` (`### MODEL_RANKS`): the description's ordering sentence (`claude-haiku-4-5` < `claude-sonnet-5` < ...) must add `claude-sonnet-5-5` as equal to `claude-sonnet-5`. **Required edit.**
- `docs/reference/API.md`: `MODEL_ALIASES` / `resolve_model_alias` description, if it names the `sonnet` target
- `docs/reference/EVENT-SCHEMA.md:230`: `model_resolved` example names `claude-sonnet-5` for the SDK path; update the example
- `docs/reference/CLI.md:~977`: the `coding → claude-sonnet-5 (claude-code)` example; refresh to `claude-sonnet-5-5` (**required**, it shows the observed model for the default alias)
- `docs/reference/API.md:9904` (cache-oracle section): states "The `sonnet` alias currently resolves to `claude-sonnet-5`, so the 512-token floor applies only to requests that name `claude-sonnet-5-5` explicitly." **This sentence becomes false** after the alias flip and was missing from the doc list. Rewrite it to say the `sonnet` alias on `sdk`/`batch` now gets the 512 floor via alias resolution, while a direct `decide_cache_marking(model="sonnet")` call is not alias-resolved and keeps 1024 (**required**; same cache-floor side effect as the CONFIGURATION/ARCHITECTURE edits below)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/header.py:122-123` (`format_model_selection` docstring): states "the SDK path resolves a literal `sonnet` to `claude-sonnet-5`"; a direct alias-target claim that goes stale. Update the docstring in the same change (comment-only; the non-issues note above covers the line-123 literal as behavior-free, not as accurate) [Agent 2 finding]
- `docs/reference/API.md:12542` (`### MODEL_RANKS` prose): the ordering sentence is at line 12542 (the `~12494` anchor above is stale); same required edit as listed above [Agent 1 finding]
- `docs/reference/CONFIGURATION.md:1972` (`cache` section, `require_repeat` paragraph) and `docs/ARCHITECTURE.md:801` (`cache_marking_oracle.decide_cache_marking()` row): both state "1024 tokens for Sonnet / 4096 for Opus". After this change `sonnet` on the SDK/batch path resolves to `claude-sonnet-5-5`, which has a 512-token override (see Dependent Files). Add the Sonnet 5.5 exception or qualify as "family default" [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:195`, `:198` (`resolve_model_hint`: the `coding` hint maps to `sonnet`, so on `anthropic-api` it now resolves to `claude-sonnet-5-5`), `:3333` (SDK request builder)
- `scripts/little_loops/fsm/executor.py:3692`: SDK-path `ModelSelection` (`_resolve_model(..., "sdk")` falls back to `llm.model`, default `DEFAULT_LLM_MODEL = "sonnet"`)
- `scripts/little_loops/fsm/schema.py:24` and `:1050`: `DEFAULT_LLM_MODEL = "sonnet"` and the `llm` config default; unchanged, but its resolved SDK-path target changes
- `scripts/little_loops/advisor.py:117`: `rank_model` normalizes through `resolve_model_alias`, so `rank_model("claude-code", "sonnet")` now looks up `claude-sonnet-5-5` (still rank 2)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py:3333` (`build_anthropic_request`) → `scripts/little_loops/cache_marking_oracle.py` (`_prefix_minimum_for`, `_MODEL_PREFIX_MINIMUMS["claude-sonnet-5-5"] = 512`, `CACHEABLE_PREFIX_MINIMUMS["sonnet"] = 1024`): **an unlisted runtime side effect.** The builder resolves the alias before `decide_cache_marking(model=...)`, so a `sonnet` request on `sdk`/`batch` moves from the 1024-token family floor to the 512-token Sonnet 5.5 floor. Prompts of 512–1023 tokens become cache-markable on the direct API paths. Not a defect (512 is the verified vendor value), but the release note should name it alongside the model change. `decide_cache_marking(model="sonnet")` called directly is not alias-resolved and stays 1024 [Agent 2 finding]
- `scripts/little_loops/cli/doctor.py:1147-1160` (`_advisor_data`): `main_model = DEFAULT_LLM_MODEL` (`"sonnet"`), then the real `check_floor(advisor_host, advisor_model, main_host, main_model)` feeds the `advisor_floor` row (`ok` → `full`, otherwise `partial`). `check_floor` normalizes through `rank_model` → `resolve_model_alias`, so once the alias moves, `ll-doctor` reports `unknown`/`partial` for every configured advisor unless the rank row lands in the same change. Rank row and alias flip must ship together [Agent 1 + Agent 3 finding]
- `scripts/little_loops/advisor.py:271`, `:287`, `:289` (`consult` / `consult_for_trigger`): `resolved_main_model = main_model or DEFAULT_LLM_MODEL`, passed to `check_floor`. Same coupling as `doctor.py`: an unranked `claude-sonnet-5-5` yields `unknown` here, and `consult_with_budget` (~`:588-599`) turns `violation` into `skipped_reason="floor_violation"` [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py:3697-3716` (`_resolve_model`): `:3699`/`:3701`/`:3716` are the `resolve_model_alias`/`resolve_model_hint` uses; callers `:2587` (`sdk`/`batch` vs `cli` selection), `:3243`/`:3293` (`"evaluator"`, CLI host, unchanged), `:3752`, `:3844`/`:3871`/`:3893` (`dispatch_anthropic_request`/`dispatch_batch_request`/`poll_batch_result`) [Agent 1 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py:541` and `scripts/little_loops/adapters/core.py:262`, `:293`: `resolve_model_hint` callers on the hint path; for `claude-code` they return the alias string (`sonnet`), so unaffected [Agent 1 + Agent 2 finding]
- `scripts/little_loops/host_runner.py:138` (`_HINT_ALIASES`, `"coding": "sonnet"`): the table feeding the `resolve_model_hint` call at `:198`; unchanged [Agent 1 finding]
- Other `DEFAULT_LLM_MODEL` consumers to confirm at implementation time (this issue already asks for the check): `fsm/evaluators.py:1187`, `:1302`, `:1478`, `:2193` (evaluators; CLI host, alias passes verbatim), `cli/artifact/extract.py:78`, `cli/artifact/discover.py:418`, `cli/issues/link_epics.py:336`, `cli/harness.py:29`, `cli/loop/info.py:1528` (`llm.model != DEFAULT_LLM_MODEL` display check), `cli/issues/decisions.py:912` (`model="sonnet"` via `build_blocking_json`, host-CLI path). None is an `sdk`-path caller by static reading [Agent 1 finding]

### Tests
- `scripts/tests/test_host_runner_dispatch.py:382`, `:386`, `:410`, `:427`: update alias and SDK/batch request assertions to `claude-sonnet-5-5`. **Do not update line 396:** it is the literal-ID pass-through case for pinned Sonnet 5, which must remain unchanged. Retain/add lower/capitalized/whitespace alias cases and full-ID/unknown-ID pass-through coverage
- `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced` (extended by BUG-3696 to cover all rank keys): passes only if `claude-sonnet-5-5` is both ranked and priced. The `claude-sonnet-5-5` price was added by BUG-3696 (now `done`), so the gate can pass. This is the single shared gate; add no duplicate here
- **Undeclared SDK state regression** (`test_model_hints.py` or alongside the SDK-path tests in `test_fsm_executor.py`): an `sdk`/`batch` action whose state, run `--model` and `llm` all declare nothing resolves through `DEFAULT_LLM_MODEL` to `claude-sonnet-5-5` in `ModelSelection`, while the same state on the CLI path stays host-resolved (`sonnet` verbatim) and an evaluator keeps the CLI path. Extend `test_default_fsm_model_is_a_resolvable_alias` (`test_host_runner_dispatch.py`) only if it needs the concrete value
- `scripts/tests/test_advisor.py:64`: `test_claude_code_covers_haiku_sonnet_opus_fable` asserts the exact rank key set; add `claude-sonnet-5-5`. Add a rank-ordering assertion (`haiku < sonnet-5-5 < opus-5-5`)
- `scripts/tests/test_advisor.py`: `rank_model('claude-code', 'sonnet') == rank_model('claude-code', 'claude-sonnet-5-5') == 2`; pinned Sonnet 5 stays rank 2. `check_floor` returns `ok` for Opus advising literal Sonnet 5.5, `violation` for Haiku advising it, and `ok` for same-tier Sonnet 5/5.5; unrelated unknown IDs still return `unknown`
- `scripts/tests/test_model_hints.py`: explicitly assert `coding` on `anthropic-api` resolves to Sonnet 5.5, `coding` on `claude-code` remains `sonnet`, and an explicit `anthropic-api.coding: claude-sonnet-5` override stays pinned. Verify `_resolve_model`/`ModelSelection` carries the new concrete ID for SDK/batch telemetry while preserving the original declaration
- `scripts/tests/test_fsm_executor.py:~4039–4145`: SDK-path tests that pass `model="claude-sonnet-5"` explicitly are unaffected. Re-check any that pass `sonnet` and assert the resolved ID
- Literal `claude-sonnet-5` in unrelated fixtures (`test_feat3182_evidence_bundle.py`, `test_issue_history_agent_quality.py`, `test_history_reader_events.py`) is data, not an alias assertion; leave it unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution::test_aliases_map_to_concrete_ids` (`:382`, `:386`), `::test_dispatch_sends_resolved_model_to_sdk` (`:410`), `::test_batch_submission_sends_resolved_model_to_sdk` (`:427`): the only three tests that pin the old literal as the alias *result*; confirmed by Agent 3 that no other test hardcodes it. `::test_non_aliases_pass_through_unchanged` (`:396`) must stay as is [Agent 2 + Agent 3 finding]
- `scripts/tests/test_advisor.py::TestModelRanks::test_claude_code_covers_haiku_sonnet_opus_fable` (`:64-73`): will fail on the exact key-set assertion once the rank row is added (already listed above; confirmed). `test_advisor.py` has **no** sonnet case today: model the alias-equals-concrete rank test on `TestRankModel::test_alias_and_concrete_id_return_same_rank`, and the floor cases on `TestCheckFloor::test_pinned_same_host_violation`, `::test_unknown_model_returns_unknown_not_silent_pass`, `::test_equal_rank_same_host_is_ok`, `::test_advisor_ranked_above_main_same_host_is_ok` [Agent 3 finding]
- `scripts/tests/test_host_runner_dispatch.py::test_every_alias_target_is_ranked_and_priced` (`:444-457`): couples the two table edits. The alias flip alone fails it (`rank_model("claude-code", "claude-sonnet-5-5")` is `None`) and the rank row alone does not; land both together [Agent 2 + Agent 3 finding]
- **New (write): `build_anthropic_request(model="sonnet")` end to end** in `scripts/tests/test_cache_control.py` (reuse `TestSonnet55RequestShape._kwargs`, a 2048-char `system_prompt` is 512 tokens): call with `"sonnet"` twice; assert the request carries `model == "claude-sonnet-5-5"`, the first call is unmarked and the repeat is marked at the 512 floor. Today no test sends the alias through the builder with a prompt in the 512–1023 token band. `TestModelSpecificPrefixMinimum::test_older_sonnet_keeps_1024_floor` (`:361-364`; calls `decide_cache_marking` directly, no alias resolution) stays valid [Agent 2 + Agent 3 finding]
- **New (write): real-`check_floor` doctor test** in `scripts/tests/test_cli_doctor_install_checks.py::TestAdvisor`: advisor `opus` vs main `DEFAULT_LLM_MODEL` (`sonnet`) asserts `floor_status == "ok"`; advisor `claude-haiku-4-5` asserts `violation`. The existing tests (`:773`, `:793-796`, `:888-911`) monkeypatch `little_loops.advisor.check_floor` or never reach it, so none would catch an unranked `sonnet` [Agent 3 finding]
- **New (write, optional): `--main-model sonnet` case** in `scripts/tests/test_cli_advise.py` next to `test_capability_floor_violation_exits_nonzero_no_consult` (`:126`, covers only `--model haiku --main-model opus`) [Agent 3 finding]
- **Undeclared-SDK-state literal pin**, anchored: `scripts/tests/test_fsm_executor.py::TestRequestPathDispatchWiring` (`test_request_path_sdk_calls_dispatch_not_cli` `:12822`, `test_state_level_request_path_overrides_orchestration_default` `:12869`, batch test `~:12933`) assert `kwargs["model"] == resolve_model_alias(fsm.llm.model)`, which is table-derived and cannot detect a wrong target; add a literal `"claude-sonnet-5-5"` assertion (extend one of these or the `test_model_hints.py::TestSdkDispatch::test_precedence_and_payload_match_client` row `({}, None, LLMConfig(model="haiku"), "haiku")` pattern, adding an undeclared row). `ModelSelection` has no direct unit tests (constructed only in `executor.py` `_resolve_model`, `:3703`/`:3706`/`:3717`); assert it via the `model_requested` / `model_resolved` / `model_backend` event fields as `TestSdkDispatch` does [Agent 3 finding]
- `scripts/tests/test_model_hints.py::TestEvaluatorDispatch::test_precedence` (`:631-652`) and `::test_llm_structured_event_carries_fields` (`:654-665`): assert the bare alias `"sonnet"` on `claude-code`; unaffected, and they are the regression that evaluators stay host-resolved [Agent 3 finding]
- `scripts/tests/test_loop_model_display.py::TestFormatModelSelection::test_sdk_literal_alias_is_not_a_hint` (`:51-54`) and `::TestLiveUpdate::test_selection_fields_observed_model_wins` (`:130-139`): pure-formatter tests fed literal `claude-sonnet-5`; will not fail, but stale as documentation of the default. Optional refresh to `claude-sonnet-5-5` alongside the `header.py` docstring [Agent 1 + Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py:216-217` (requires `check_floor` and `rank_model` to appear in `docs/reference/API.md`) and `scripts/tests/test_wiring_skills_and_commands.py::test_generated_mirrors_do_not_ship_claude_model_aliases` (`:929-944`): gates on the files this issue edits; they key on names/aliases, not target values, so should stay green [Agent 1 + Agent 2 finding]

### Documentation
- `docs/reference/CLI.md:~977–992`: the `coding` example reflects the default behavior changed by this issue; update it to `claude-sonnet-5-5` as a required documentation edit
- `docs/guides/SESSION_HANDOFF.md:384`: `detected_model` example; illustrative, optional

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:10796` (a long line matching `claude-sonnet-5`): not in the issue's literal-site list; inspect while editing and decide alias-default vs pin [Agent 1 finding]
- `docs/reference/CONFIGURATION.md:1972` and `docs/ARCHITECTURE.md:801`: cache-floor prose, see Files to Modify above [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:519`, `:598-599` and `docs/guides/LOOPS_GUIDE.md:655`: describe hints and aliases by name only (`coding` → `sonnet`), no literal ID; no edit needed [Agent 2 finding]
- `docs/observability/realized-savings-verification.md:42`, `:50`, `:54`, `:146`: historical trace-model narrative; leave unchanged [Agent 1 + Agent 2 finding]
- `site/` HTML mirrors `docs/reference/API.md` and is build output; do not hand-edit [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Conventions in force — model tables** (from codebase-pattern-finder, anchors verified 2026-10-04):
  - `MODEL_ALIASES` (`host_runner.py:109`–`112`) holds only current targets, while `MODEL_RANKS["claude-code"]` (`advisor.py:54`–`57`) and `MODEL_PRICING` (`pricing.py:75`–`76`) keep superseded and current IDs side by side (e.g. `claude-sonnet-5-5` and `claude-sonnet-5` both priced via shared `_SONNET_5`; `claude-opus-5`/`claude-opus-5-5` both rank 3). A rank row is added; the old `claude-sonnet-5` row is not removed.
  - Earlier bumps (BUG-3541: opus 5 → 5-5, fable 5 → 5-1) changed aliases, ranks, pricing, tests and `API.md` together; model-ID doc examples are prose and track the tables in the same change.
  - **Test-style split, by file.** `test_host_runner_dispatch.py` (`TestModelAliasResolution`) and `test_advisor.py` assert literal IDs, so a stale alias fails there. `test_model_hints.py` asserts `== MODEL_ALIASES[...]` (lines 70, 107, 704, 725, 761), so it cannot detect a stale alias value and passes unchanged after the edit. The explicit `coding`-on-`anthropic-api` → `claude-sonnet-5-5` assertion therefore needs a literal ID, not a table lookup.
  - **Single cross-table gate:** `test_host_runner_dispatch.py::test_every_alias_target_is_ranked_and_priced` (~line 444) is the only test relating aliases, ranks and pricing. `MODEL_CONTEXT_WINDOW` (`context_window.py`) has no lockstep test; it is BUG-3704's scope.
  - Already literal `claude-sonnet-5-5` and unaffected: `cache_marking_oracle.py:62`, `test_adapters_model_hint.py:89`, `test_batch_request_path.py:88`, `test_pricing.py`.
  - Additional literal `claude-sonnet-5` doc sites, **decided 2026-10-05** (re-grepped with a word-boundary match): `CLI.md:983`, `:987`, `:998` show the observed model for the default alias, so update to `claude-sonnet-5-5` with the required `:~977` example; `API.md:9904` is a required rewrite (false after the flip, see Files to Modify); `API.md:9885` and `:12686` already describe 5.5 correctly, no edit; `API.md:3011` (`TokenUsage.model` example) is illustrative, update to `claude-sonnet-5-5` for consistency; `API.md:89` and `:10796` contain no bare `claude-sonnet-5` (earlier hits were `-5-5` substrings), drop from scope; `SESSION_HANDOFF.md:384` stays optional.

## Program Design

### Types

- `MODEL_ALIASES: dict[str, str]` (existing, `little_loops.host_runner`) — `"sonnet"` target changes to `"claude-sonnet-5-5"`
- `MODEL_RANKS: dict[str, dict[str, int]]` (existing, `little_loops.advisor`) — gains `"claude-sonnet-5-5": 2` under `"claude-code"`

### Signatures

- `resolve_model_alias(model: str) -> str` — existing, unchanged; returns the new `sonnet` target
- `rank_model(host: str, model: str) -> int | None` — existing, unchanged; now ranks `claude-sonnet-5-5`

### Call Path

`resolve_model_hint` / SDK request builder (`little_loops.host_runner`) -> `resolve_model_alias` -> `MODEL_ALIASES`; `rank_model` (`little_loops.advisor`) -> `resolve_model_alias` -> `MODEL_RANKS`.

`build_batch_request` reuses `build_anthropic_request`, so the alias must be asserted at both API boundaries. `_resolve_model` builds the corresponding SDK-path `ModelSelection` and telemetry. Current requests use a fresh user message and no explicit disabled thinking, forced tool-choice, or sampling settings; the [Sonnet 5.5 migration requirements](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) do not require a request-parameter rewrite for this alias correction.

## Implementation Steps

1. Sonnet 5.5 pricing and the coverage gate are available (BUG-3696 is `done`); confirm `MODEL_PRICING` still prices `claude-sonnet-5-5` before editing the tables.
2. Update the Sonnet alias and add rank 2 while retaining explicitly pinned Sonnet 5.
3. Update/add the boundary, hint, normalization, pin, and floor tests above; refresh required docs.
4. Completeness check (no wiring test covers the ~17 sites): `grep -rnE 'claude-sonnet-5([^-0-9]|$)' docs scripts/little_loops --include='*.md' --include='*.py' --exclude-dir=node_modules`; every remaining hit must be a deliberate pin, a `MODEL_RANKS`/`MODEL_PRICING` row, or the optional `SESSION_HANDOFF.md` example.
5. Run `python -m pytest scripts/tests/`; record the behavioral model change for release prep.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Land the alias flip (`host_runner.py:112`) and the rank row (`advisor.py:57`) in the same commit; `test_every_alias_target_is_ranked_and_priced` and the `ll-doctor` `advisor_floor` row (`cli/doctor.py:_advisor_data`) both go `unknown`/red if only the alias moves
- Update `scripts/little_loops/cli/loop/header.py:122-123` (`format_model_selection` docstring) to name `claude-sonnet-5-5`
- Update `docs/reference/CONFIGURATION.md:1972` and `docs/ARCHITECTURE.md:801`: cache floor is now 512 tokens for `claude-sonnet-5-5` (the resolved `sonnet` target) vs the 1024 Sonnet family default
- Add to the release note: `sonnet` requests on `sdk`/`batch` now also use the 512-token Sonnet 5.5 cache-prefix floor (`cache_marking_oracle._MODEL_PREFIX_MINIMUMS`), a side effect of resolving the alias before `decide_cache_marking`
- Add `scripts/tests/test_cache_control.py` test: `build_anthropic_request(model="sonnet")` sends `claude-sonnet-5-5` and applies the 512 floor (reuse `TestSonnet55RequestShape._kwargs`)
- Add `scripts/tests/test_cli_doctor_install_checks.py::TestAdvisor` real-`check_floor` case against `DEFAULT_LLM_MODEL` (`sonnet`) so an unranked alias target is caught
- Add a literal `"claude-sonnet-5-5"` assertion for the undeclared-SDK-state path in `test_fsm_executor.py::TestRequestPathDispatchWiring` (existing assertions use `resolve_model_alias(...)` and cannot detect a stale target)
- Update `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution` lines `:382`, `:386`, `:410`, `:427` (not `:396`) and `scripts/tests/test_advisor.py:64-73` key set

## Impact

- **Priority**: P3 - the SDK path runs an older model for `sonnet`, and the advisor floor cannot rank Sonnet 5.5. The CLI dispatch behavior is unaffected
- **Effort**: Small - two model tables, targeted regression tests, doc examples
- **Risk**: Low-Medium - model behavior and task token usage change for SDK/batch consumers using `sonnet`, built-in `coding` or no declared model (the `DEFAULT_LLM_MODEL` fallback); verified per-token rates are identical
- **Breaking Change**: Behavioral, for `request_path: sdk|batch` consumers using `sonnet` / `coding` / the undeclared default (changelog note); no API or schema change

## Acceptance Criteria

- [ ] `resolve_model_alias("sonnet") == "claude-sonnet-5-5"`, and `resolve_model_hint("coding", backend="anthropic-api")` returns `claude-sonnet-5-5`
- [ ] Mocked SDK and batch boundaries both send Sonnet 5.5 for `sonnet`; SDK-path `ModelSelection` records the new resolved ID and original declaration
- [ ] An undeclared `sdk`/`batch` state resolves to `claude-sonnet-5-5` via `DEFAULT_LLM_MODEL`; the same state on the CLI path and evaluators remain host-resolved; the release note names this default-path change
- [ ] Alias case/whitespace normalization still works; concrete Sonnet 5 pins and hint overrides remain unchanged; CLI `coding` remains the host-resolved `sonnet` alias
- [ ] `MODEL_RANKS["claude-code"]["claude-sonnet-5-5"] == 2`; `test_advisor.py` asserts the key set and the haiku < sonnet-5-5 < opus-5-5 ordering
- [ ] Alias/literal Sonnet 5.5 floor checks return the expected `ok`/`violation` outcomes; same-tier Sonnet 5 remains compatible and unrelated unknown models remain unranked
- [ ] `test_every_alias_target_is_ranked_and_priced` passes (needs the `claude-sonnet-5-5` price already added under BUG-3696)
- [ ] Docs (`API.md` `MODEL_RANKS` order sentence, `EVENT-SCHEMA.md` `model_resolved` example, `CLI.md` `coding →` example) match the new tables and qualify CLI parity to first-party built-in defaults
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3696: pricing-only after the 2026-10-04 split; adds the `claude-sonnet-5-5` price and extends `test_every_alias_target_is_ranked_and_priced`. That test fails without the price; the price landed when BUG-3696 went `done`, so the dependency is resolved.
- ENH-3719: unpriced-model footer split from BUG-3696; independent of this issue.

- BUG-3704: owns all context-window cleanup and native-1M sizing with host caps and automated Python/shell parity; independent of this alias/rank correction

- ENH-3703: optional pricing fallback (unrelated to this issue's tables)

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Host alias and advisor rank contracts |
| `docs/reference/EVENT-SCHEMA.md` | Requested/resolved model telemetry |

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~17 change sites (2 source tables, `header.py` docstring, 5+ test files incl. 3 new tests, 5 doc files); each site is mechanical, but completeness has no verification grep or wiring test
- Moderate blast radius: ~6-10 `resolve_model_alias` dependents (`resolve_model_hint`, `_resolve_model`, `rank_model`, `check_floor`, `doctor._advisor_data`, `build_anthropic_request`) shift behavior with the alias flip; alias and rank rows must land in one commit
- Minor open per-site judgment calls: alias default vs. pin for the extra `claude-sonnet-5` doc literals, and the `DEFAULT_LLM_MODEL` consumer check deferred to implementation time

## Session Log
- `/ll:confidence-check` - 2026-10-05T03:00:49 - `2c448ab4-cf8f-4ac4-a172-efb98c1f6296.jsonl`
- `/ll:confidence-check` - 2026-10-05T02:50:20 - `3e4f6f99-a73d-41bc-a00b-29febd7074d9.jsonl`
- `/ll:wire-issue` - 2026-10-05T02:47:28 - `5a869ba8-fe04-48d9-8bed-d3413a6faae0.jsonl`
- `/ll:refine-issue` - 2026-10-05T02:40:31 - `2aefc2a8-3cc7-463c-8fe9-e07529945488.jsonl`
- Pre-implementation review 3 - 2026-10-05 - direct review, no consult: found `API.md:9904` asserts the `sonnet` alias resolves to Sonnet 5 (false after the flip; added as required edit); resolved the per-site doc pin-vs-default calls; dropped two non-sites (`API.md:89`, `:10796`); added a residual-literal grep as the completeness check; removed stale `blocked_by: BUG-3696` (done).
- Pre-implementation review 2 - 2026-10-04 - `/ll:advise` with Opus (confidence 0.78): widened the behavior-change note to the `DEFAULT_LLM_MODEL` SDK/batch fallback (evaluators verified CLI-path, unchanged); added undeclared-SDK-state regression; made API.md `MODEL_RANKS` and CLI.md `coding` example required edits with corrected line anchors; recorded verified non-issues; dependency now targets pricing-only BUG-3696; shared coverage test is extended, not duplicated.
- Pre-implementation review - 2026-10-02 - `/ll:advise` with Opus (confidence 0.80): narrowed to alias/rank, qualified provider/override claims, corrected the pinned-ID test instruction, added floor and request-boundary regressions, and moved context-window work to BUG-3704
- Pre-implementation review (2026-10-02, `/ll:advise` with Fable): reframed from a raw capture. The `sonnet` alias is stale because the host's own `sonnet` already resolves to 5.5; added the context-window cleanup and the `context-monitor.sh` lockstep
