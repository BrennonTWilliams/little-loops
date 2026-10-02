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

The host CLI now resolves the `sonnet` alias to `claude-sonnet-5-5`, but three little-loops model tables do not follow:

- `MODEL_ALIASES['sonnet']` in `scripts/little_loops/host_runner.py` still resolves to `claude-sonnet-5`.
- `MODEL_RANKS["claude-code"]` in `scripts/little_loops/advisor.py` has no `claude-sonnet-5-5`.
- `MODEL_CONTEXT_WINDOW` in `scripts/little_loops/context_window.py` has no Claude 5.x entries, and it holds `claude-opus-3-7`, which is not a real model.

Evidence: this checkout's local Claude Code settings (gitignored `settings.local.json`) set `"model": "sonnet"`, and run `refine-to-ready-issue-20261002T111524` recorded `claude-sonnet-5-5` on all 7 `usage.jsonl` rows. So the host's own `sonnet` alias already means 5.5.

## Current Behavior

- **Path divergence.** On the CLI request path, `sonnet` passes through verbatim and the host binary resolves it to `claude-sonnet-5-5`. On the `sdk` / `batch` request path, `resolve_model_alias("sonnet")` returns `claude-sonnet-5` (`host_runner.py:112`; used at `host_runner.py:195`, `:198`, `:3333` and `fsm/executor.py:3692`). The same loop YAML `model: sonnet` therefore runs a different model depending on `orchestration.request_path`.
- **Unranked model.** `advisor.rank_model("claude-code", "claude-sonnet-5-5")` returns `None`, so advisor capability-floor comparisons treat the model that most runs actually use as unranked.
- **Context window.** No `claude-*-5*` key exists in `MODEL_CONTEXT_WINDOW`, so every 5.x model uses the 200 000-token floor in `context_window_for()`. `hooks/scripts/context-monitor.sh:get_context_limit()` (~L179) duplicates this logic with a `case` on `claude-opus-4*|claude-sonnet-4*|claude-haiku-4*`; it carries a "keep in sync with `context_window.py`" comment.
- `MODEL_CONTEXT_WINDOW` contains `claude-opus-3-7` (no such model) and `claude-sonnet-4-5`; neither has a `MODEL_PRICING` entry.

## Steps to Reproduce

1. `python -c "from little_loops.advisor import rank_model; print(rank_model('claude-code', 'claude-sonnet-5-5'))"`: prints `None`.
2. `python -c "from little_loops.host_runner import resolve_model_alias as r; print(r('sonnet'))"`: prints `claude-sonnet-5`.
3. `python -c "from little_loops.context_window import MODEL_CONTEXT_WINDOW as m; print([k for k in m if '-5' in k])"`: prints `[]`.

## Expected Behavior

- `MODEL_ALIASES['sonnet']` is `claude-sonnet-5-5`, matching what the host CLI resolves. The CLI and SDK paths then run the same model for `model: sonnet`.
- `MODEL_RANKS["claude-code"]["claude-sonnet-5-5"] == 2`, the same tier as `claude-sonnet-5` (below Opus 3 and Fable 4, above Haiku 1).
- `MODEL_CONTEXT_WINDOW` has no fictitious entries (`claude-opus-3-7` removed). It covers the 5.x models only where the published context window is confirmed externally. Otherwise the issue records that 5.x stays on the 200 000 floor and why.
- `context-monitor.sh:get_context_limit()` changes in the same commit as any `MODEL_CONTEXT_WINDOW` change.

## Motivation

The SDK path silently runs an older model than the CLI path for the same YAML, and the advisor floor cannot rank the most-used model. Split out of BUG-3696 (advisor review, 2026-10-02): this is an alias and ranking defect, not a pricing defect.

## Proposed Solution

1. `host_runner.py`: change `MODEL_ALIASES["sonnet"]` to `"claude-sonnet-5-5"`. Keep the BUG-2828 comment ("Keep this table in sync with the current model lineup") and add a note that the target must match the host CLI's own alias.
2. `advisor.py`: add `"claude-sonnet-5-5": 2` to `MODEL_RANKS["claude-code"]`. Keep `claude-sonnet-5` (rank 2) for runs that pin it explicitly.
3. `context_window.py`: remove `claude-opus-3-7`. Decide `claude-sonnet-4-5`: keep it only if it is priced, or document why the table is broader than `MODEL_PRICING`. Add 5.x entries only with externally confirmed window sizes. Mirror every change in `context-monitor.sh:get_context_limit()`.
4. Changelog note at release prep (not under `[Unreleased]`): the `sonnet` alias on the `sdk` / `batch` request path now resolves to `claude-sonnet-5-5`, which changes the model and the cost for consumers on that path.
5. After this lands, extend BUG-3696's price-coverage test to include `MODEL_CONTEXT_WINDOW` keys, if the cleaned table is a subset of `MODEL_PRICING`.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py:112`: `MODEL_ALIASES["sonnet"]`
- `scripts/little_loops/advisor.py:~55`: `MODEL_RANKS["claude-code"]`
- `scripts/little_loops/context_window.py:19`: `MODEL_CONTEXT_WINDOW`
- `hooks/scripts/context-monitor.sh:~179`: `get_context_limit()` (lockstep with `context_window.py`)
- `docs/reference/API.md:~12483`: `MODEL_RANKS` description lists the ranked IDs
- `docs/reference/API.md`: `MODEL_ALIASES` / `resolve_model_alias` description, if it names the `sonnet` target
- `docs/reference/EVENT-SCHEMA.md:~230`: `model_resolved` example names `claude-sonnet-5` for the SDK path; update the example

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:195`, `:198` (`resolve_model_hint`: the `coding` hint maps to `sonnet`, so on `anthropic-api` it now resolves to `claude-sonnet-5-5`), `:3333` (SDK request builder)
- `scripts/little_loops/fsm/executor.py:3692`: SDK-path `ModelSelection`
- `scripts/little_loops/advisor.py:117`: `rank_model` normalizes through `resolve_model_alias`, so `rank_model("claude-code", "sonnet")` now looks up `claude-sonnet-5-5` (still rank 2)

### Tests
- `scripts/tests/test_host_runner_dispatch.py:382`, `:386`, `:396`, `:410`, `:427`: pin `("sonnet", "claude-sonnet-5")`; update to `claude-sonnet-5-5`
- `scripts/tests/test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced`: passes only if `claude-sonnet-5-5` is both ranked and priced. Pricing comes from BUG-3696, which is why this issue is `blocked_by` it
- `scripts/tests/test_advisor.py:64`: `test_claude_code_covers_haiku_sonnet_opus_fable` asserts the exact rank key set; add `claude-sonnet-5-5`. Add a rank-ordering assertion (`haiku < sonnet-5-5 < opus-5-5`)
- `scripts/tests/test_fsm_executor.py:~4039–4145`: SDK-path tests that pass `model="claude-sonnet-5"` explicitly are unaffected. Re-check any that pass `sonnet` and assert the resolved ID
- Context-window tests (grep `context_window_for` / `MODEL_CONTEXT_WINDOW` in `scripts/tests/`) and any `context-monitor.sh` shell test covering `get_context_limit`
- Literal `claude-sonnet-5` in unrelated fixtures (`test_feat3182_evidence_bundle.py`, `test_issue_history_agent_quality.py`, `test_history_reader_events.py`) is data, not an alias assertion; leave it unchanged

### Documentation
- `docs/reference/CLI.md:~977–992`: the example `coding → claude-sonnet-5 (claude-code)` shows the CLI path's observed model; optionally refresh it to `claude-sonnet-5-5`
- `docs/guides/SESSION_HANDOFF.md:384`: `detected_model` example; illustrative, optional

## Program Design

### Types

- `MODEL_ALIASES: dict[str, str]` (existing, `little_loops.host_runner`) — `"sonnet"` target changes to `"claude-sonnet-5-5"`
- `MODEL_RANKS: dict[str, dict[str, int]]` (existing, `little_loops.advisor`) — gains `"claude-sonnet-5-5": 2` under `"claude-code"`
- `MODEL_CONTEXT_WINDOW: dict[str, int]` (existing, `little_loops.context_window`) — drops `claude-opus-3-7`; 5.x entries only if externally confirmed

### Signatures

- `resolve_model_alias(model: str) -> str` — existing, unchanged; returns the new `sonnet` target
- `rank_model(host: str, model: str) -> int | None` — existing, unchanged; now ranks `claude-sonnet-5-5`
- `context_window_for(model: str | None, override: int | None = None) -> int` — existing, unchanged

### Call Path

`resolve_model_hint` / SDK request builder (`little_loops.host_runner`) -> `resolve_model_alias` -> `MODEL_ALIASES`; `rank_model` (`little_loops.advisor`) -> `resolve_model_alias` -> `MODEL_RANKS`.

## Impact

- **Priority**: P3 - the SDK path runs an older model for `sonnet`, and the advisor floor cannot rank the most-used model. The default CLI path is unaffected
- **Effort**: Small - three constant tables, one shell `case`, pinned-test updates, doc examples
- **Risk**: Low-Medium - the alias change alters which model, and so what cost, SDK/batch consumers get for `sonnet` and the `coding` hint
- **Breaking Change**: Behavioral, for `request_path: sdk|batch` consumers using `sonnet` / `coding` (changelog note); no API or schema change

## Acceptance Criteria

- [ ] `resolve_model_alias("sonnet") == "claude-sonnet-5-5"`, and `resolve_model_hint("coding", backend="anthropic-api")` returns `claude-sonnet-5-5`
- [ ] `MODEL_RANKS["claude-code"]["claude-sonnet-5-5"] == 2`; `test_advisor.py` asserts the key set and the haiku < sonnet-5-5 < opus-5-5 ordering
- [ ] `claude-opus-3-7` is removed from `MODEL_CONTEXT_WINDOW`. Each 5.x context-window entry cites an externally confirmed size, or the issue records that 5.x stays on the 200 000 floor and why
- [ ] `context-monitor.sh:get_context_limit()` agrees with `context_window_for()` for every model in `MODEL_CONTEXT_WINDOW` (a test compares them, or the commit records a manual comparison)
- [ ] `test_every_alias_target_is_ranked_and_priced` passes (requires BUG-3696's `claude-sonnet-5-5` price)
- [ ] Docs (`API.md` `MODEL_RANKS`, `EVENT-SCHEMA.md` `model_resolved` example) match the new tables
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3696: adds the `claude-sonnet-5-5` price and the alias/rank price-coverage test. Hard dependency: `test_every_alias_target_is_ranked_and_priced` fails without that price.

- ENH-3703: optional pricing fallback (unrelated to this issue's tables)

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log
- Pre-implementation review (2026-10-02, `/ll:advise` with Fable): reframed from a raw capture. The `sonnet` alias is stale because the host's own `sonnet` already resolves to 5.5; added the context-window cleanup and the `context-monitor.sh` lockstep
