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
blocked_by:
- BUG-3696
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
- **Unranked model.** `advisor.rank_model("claude-code", "claude-sonnet-5-5")` returns `None`, so advisor capability-floor comparisons treat the model that most runs actually use as unranked.
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

The SDK path silently runs an older model than the CLI path for the same YAML, and the advisor floor cannot rank the most-used model. Split out of BUG-3696 (advisor review, 2026-10-02): this is an alias and ranking defect, not a pricing defect.

## Proposed Solution

1. `host_runner.py`: change `MODEL_ALIASES["sonnet"]` to `"claude-sonnet-5-5"`. Keep the BUG-2828 rationale and clarify that the table tracks first-party built-in defaults, not every provider or `ANTHROPIC_DEFAULT_*_MODEL` setting.
2. `advisor.py`: add `"claude-sonnet-5-5": 2` to `MODEL_RANKS["claude-code"]`. Keep `claude-sonnet-5` (rank 2) for runs that pin it explicitly.
3. Update the alias-resolution and SDK/batch boundary tests. Add explicit hint, pin-preservation, alias-normalization, and floor-result regressions; assertions derived only from `MODEL_ALIASES` cannot catch a stale alias value.
4. Update API/event documentation and record a release note at release prep (not under `[Unreleased]`): `sonnet` / built-in `coding` now select Sonnet 5.5 on the direct API paths. [Live pricing](https://platform.claude.com/docs/en/about-claude/pricing), verified 2026-10-02, gives Sonnet 5 and 5.5 identical per-token rates; task token usage, behavior, and total cost can still change. Users can pin `claude-sonnet-5` to retain their current model.
5. Keep selection/rank pricing coverage from BUG-3696. Do not extend it to context-window keys: context sizing and price support are independent, and deleting a real legacy model to satisfy a price-subset assertion would be wrong.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py:112`: `MODEL_ALIASES["sonnet"]`
- `scripts/little_loops/advisor.py:~55`: `MODEL_RANKS["claude-code"]`
- `scripts/tests/test_host_runner_dispatch.py`, `scripts/tests/test_model_hints.py`, `scripts/tests/test_advisor.py`: boundary and floor regressions
- `docs/reference/API.md:~12483`: `MODEL_RANKS` description lists the ranked IDs
- `docs/reference/API.md`: `MODEL_ALIASES` / `resolve_model_alias` description, if it names the `sonnet` target
- `docs/reference/EVENT-SCHEMA.md:~230`: `model_resolved` example names `claude-sonnet-5` for the SDK path; update the example

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:195`, `:198` (`resolve_model_hint`: the `coding` hint maps to `sonnet`, so on `anthropic-api` it now resolves to `claude-sonnet-5-5`), `:3333` (SDK request builder)
- `scripts/little_loops/fsm/executor.py:3692`: SDK-path `ModelSelection`
- `scripts/little_loops/advisor.py:117`: `rank_model` normalizes through `resolve_model_alias`, so `rank_model("claude-code", "sonnet")` now looks up `claude-sonnet-5-5` (still rank 2)

### Tests
- `scripts/tests/test_host_runner_dispatch.py:382`, `:386`, `:410`, `:427`: update alias and SDK/batch request assertions to `claude-sonnet-5-5`. **Do not update line 396:** it is the literal-ID pass-through case for pinned Sonnet 5, which must remain unchanged. Retain/add lower/capitalized/whitespace alias cases and full-ID/unknown-ID pass-through coverage
- `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced`: passes only if `claude-sonnet-5-5` is both ranked and priced. Pricing comes from BUG-3696, which is why this issue is `blocked_by` it
- `scripts/tests/test_advisor.py:64`: `test_claude_code_covers_haiku_sonnet_opus_fable` asserts the exact rank key set; add `claude-sonnet-5-5`. Add a rank-ordering assertion (`haiku < sonnet-5-5 < opus-5-5`)
- `scripts/tests/test_advisor.py`: `rank_model('claude-code', 'sonnet') == rank_model('claude-code', 'claude-sonnet-5-5') == 2`; pinned Sonnet 5 stays rank 2. `check_floor` returns `ok` for Opus advising literal Sonnet 5.5, `violation` for Haiku advising it, and `ok` for same-tier Sonnet 5/5.5; unrelated unknown IDs still return `unknown`
- `scripts/tests/test_model_hints.py`: explicitly assert `coding` on `anthropic-api` resolves to Sonnet 5.5, `coding` on `claude-code` remains `sonnet`, and an explicit `anthropic-api.coding: claude-sonnet-5` override stays pinned. Verify `_resolve_model`/`ModelSelection` carries the new concrete ID for SDK/batch telemetry while preserving the original declaration
- `scripts/tests/test_fsm_executor.py:~4039–4145`: SDK-path tests that pass `model="claude-sonnet-5"` explicitly are unaffected. Re-check any that pass `sonnet` and assert the resolved ID
- Literal `claude-sonnet-5` in unrelated fixtures (`test_feat3182_evidence_bundle.py`, `test_issue_history_agent_quality.py`, `test_history_reader_events.py`) is data, not an alias assertion; leave it unchanged

### Documentation
- `docs/reference/CLI.md:~977–992`: the example `coding → claude-sonnet-5 (claude-code)` shows the CLI path's observed model; optionally refresh it to `claude-sonnet-5-5`
- `docs/guides/SESSION_HANDOFF.md:384`: `detected_model` example; illustrative, optional

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

1. Land BUG-3696 so Sonnet 5.5 has exact pricing and the coverage gate is available.
2. Update the Sonnet alias and add rank 2 while retaining explicitly pinned Sonnet 5.
3. Update/add the boundary, hint, normalization, pin, and floor tests above; refresh required docs.
4. Run `python -m pytest scripts/tests/`; record the behavioral model change for release prep.

## Impact

- **Priority**: P3 - the SDK path runs an older model for `sonnet`, and the advisor floor cannot rank the most-used model. The default CLI path is unaffected
- **Effort**: Small - two model tables, targeted regression tests, doc examples
- **Risk**: Low-Medium - model behavior and task token usage change for SDK/batch consumers using `sonnet` / built-in `coding`; verified per-token rates are identical
- **Breaking Change**: Behavioral, for `request_path: sdk|batch` consumers using `sonnet` / `coding` (changelog note); no API or schema change

## Acceptance Criteria

- [ ] `resolve_model_alias("sonnet") == "claude-sonnet-5-5"`, and `resolve_model_hint("coding", backend="anthropic-api")` returns `claude-sonnet-5-5`
- [ ] Mocked SDK and batch boundaries both send Sonnet 5.5 for `sonnet`; SDK-path `ModelSelection` records the new resolved ID and original declaration
- [ ] Alias case/whitespace normalization still works; concrete Sonnet 5 pins and hint overrides remain unchanged; CLI `coding` remains the host-resolved `sonnet` alias
- [ ] `MODEL_RANKS["claude-code"]["claude-sonnet-5-5"] == 2`; `test_advisor.py` asserts the key set and the haiku < sonnet-5-5 < opus-5-5 ordering
- [ ] Alias/literal Sonnet 5.5 floor checks return the expected `ok`/`violation` outcomes; same-tier Sonnet 5 remains compatible and unrelated unknown models remain unranked
- [ ] `test_every_alias_target_is_ranked_and_priced` passes (requires BUG-3696's `claude-sonnet-5-5` price)
- [ ] Docs (`API.md` `MODEL_RANKS`, `EVENT-SCHEMA.md` `model_resolved` example) match the new tables and qualify CLI parity to first-party built-in defaults
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3696: adds the `claude-sonnet-5-5` price and the alias/rank price-coverage test. Hard dependency: `test_every_alias_target_is_ranked_and_priced` fails without that price.
- BUG-3704: owns all context-window cleanup and native-1M sizing with host caps and automated Python/shell parity; independent of this alias/rank correction
- ENH-3703: optional pricing fallback (unrelated to this issue's tables)

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Host alias and advisor rank contracts |
| `docs/reference/EVENT-SCHEMA.md` | Requested/resolved model telemetry |

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log
- Pre-implementation review - 2026-10-02 - `/ll:advise` with Opus (confidence 0.80): narrowed to alias/rank, qualified provider/override claims, corrected the pinned-ID test instruction, added floor and request-boundary regressions, and moved context-window work to BUG-3704
- Pre-implementation review (2026-10-02, `/ll:advise` with Fable): reframed from a raw capture. The `sonnet` alias is stale because the host's own `sonnet` already resolves to 5.5; added the context-window cleanup and the `context-monitor.sh` lockstep
