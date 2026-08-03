---
id: BUG-3012
title: BRConfig.to_dict() omits refine_status, extensions, and orchestration, breaking ll-config get
type: BUG
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
testable: true
labels:
- config
- cli
---

# BUG-3012: `BRConfig.to_dict()` omits `refine_status`, `extensions`, and `orchestration`, breaking `ll-config get`

## Summary

`refine_status`, `extensions`, and `orchestration` are all genuinely parsed by
`BRConfig` and actively consumed elsewhere in the codebase, but `to_dict()`
(`scripts/little_loops/config/core.py:648-922`) omits all three sections. Since
`ll-config get <dot.path>` resolves through `to_dict()`/`resolve_variable()`
(`core.py:924-946`), `ll-config get refine_status.columns`,
`ll-config get extensions`, and `ll-config get orchestration.host_cli` silently
return nothing even though the underlying features work correctly.

## Current Behavior

- `refine_status` is parsed and exposed as a `BRConfig` property at
  `core.py:270-272, 378-381`, and genuinely consumed by
  `scripts/little_loops/cli/issues/refine_status.py`.
- `extensions` is parsed as a raw-passthrough property at `core.py:428-431`,
  and consumed via the `EventBus`/extension loader.
- `orchestration` is parsed at `core.py:277-278` and exposed as a property at
  `core.py:399-401`, and is genuinely consumed — `orchestration.host_cli` is the
  documented override for `resolve_host()` (see `.claude/CLAUDE.md`'s "Host CLI
  Abstraction" section) and is actively set in this repo's own
  `.ll/ll-config.json`.
- None of the three keys appears in `to_dict()` (`core.py:648-922`), so
  `resolve_variable()` (used by `ll-config get`) can't find them — a lookup
  silently resolves to nothing rather than erroring, making the gap easy to
  miss.

## Steps to Reproduce

1. In a project with `refine_status` configured in `.ll/ll-config.json`, run
   `ll-config get refine_status.columns` (or any real configured sub-key).
2. Observe the command returns nothing, even though
   `scripts/little_loops/cli/issues/refine_status.py` reads and uses the same
   value correctly via `BRConfig.refine_status` directly.
3. Same result for `ll-config get extensions`.
4. Same result for `ll-config get orchestration.host_cli`, which returns nothing
   in this very repo despite `.ll/ll-config.json` setting it to `claude-code`.

## Expected Behavior

- `ll-config get refine_status.columns` / `refine_status.elide_order` should
  resolve to the configured values, matching every other parsed config section.
- `ll-config get extensions` should resolve to the configured extension list.
- `ll-config get orchestration.host_cli` should resolve to the configured host.

## Shape constraints (verified — do not assume otherwise)

Three details make the naive fix wrong:

1. **`RefineStatusConfig` has no `to_dict()`.** It is a plain dataclass
   (`scripts/little_loops/config/cli.py:151-163`) with only `from_dict`, fields
   `columns: list[str]` and `elide_order: list[str]`. The entry must be built
   inline, exactly like the `cache`/`deferred_tools` entries already do at
   `core.py:769-772`. (An earlier draft of this issue said to call
   `self.refine_status.to_dict()` — that method does not exist.)

2. **`extensions` is a `list`, not a dict** (`core.py:428-431` returns
   `self._raw_config.get("extensions", [])`). `resolve_variable()`
   (`core.py:924-946`) only descends into `dict` values, and space-joins a
   terminal list into a string. So `ll-config get extensions` will work and
   return the joined list, but `ll-config get extensions.<field>` is
   unreachable by design — the AC must not require it.

3. **`OrchestrationConfig` has no `to_dict()` either, and it nests two further
   dataclasses.** It is a dataclass (`scripts/little_loops/config/orchestration.py:60-101`)
   with `host_cli: str | None`, `request_path: str`, plus
   `composer: ComposerConfig` and `cluster: ClusterConfig` (each with their own
   `from_dict` only). The entry must be built inline and must descend into the
   nested objects, or `ll-config get orchestration.cluster.max_batch_size` stays
   unreachable while the top two scalars start working — a half-fix that is
   harder to notice than the current total absence.

## Suggested Fix Direction

In `to_dict()` (`core.py:648-922`), add alongside the existing `cache` /
`deferred_tools` entries:

```python
"refine_status": {
    "columns": self.refine_status.columns,
    "elide_order": self.refine_status.elide_order,
},
"extensions": self.extensions,
"orchestration": {
    "host_cli": self.orchestration.host_cli,
    "request_path": self.orchestration.request_path,
    "composer": {
        # fields per ComposerConfig / ComposerAdaptiveConfig at
        # config/orchestration.py:13-60 — read them at implementation time
        # rather than transcribing from this issue.
    },
    "cluster": {
        "max_batch_size": self.orchestration.cluster.max_batch_size,
        "enable_dedup": self.orchestration.cluster.enable_dedup,
        "propagate_context": self.orchestration.cluster.propagate_context,
    },
},
```

Add regression tests in `scripts/tests/` alongside the existing `to_dict()` /
`ll-config get` coverage.

## Also required: a parity guard so this stops recurring

All three omissions arrived the same way — a new config section was added with a
property and a `from_dict`, and `to_dict()` was never updated. Fixing only the
three known cases leaves the fourth to be discovered by the next audit. Add a
test that derives the expected key set instead of hardcoding it:

- Enumerate `BRConfig`'s public config properties by introspection (skip
  `get_*` helpers and the non-section properties `repo_path`,
  `legacy_issue_dirs`, `issue_categories`, `issue_priorities`).
- Subtract the top-level keys `to_dict()` emits.
- Assert the difference is empty.

One alias is required and must be encoded explicitly, not special-cased loosely:
**`analytics_capture` is emitted under the `analytics` key** (`core.py:284-285`
parses from `raw["analytics"]["capture"]`; `core.py:789-796` emits it nested
under `"analytics"`). Use an explicit `{"analytics_capture": "analytics"}` alias
map so a future genuine omission can't hide behind a fuzzy match.

Verified today, this test fails with exactly
`{'extensions', 'orchestration', 'refine_status'}` — i.e. it reproduces this bug
and nothing else, so it is a valid pre-fix red test.

## Program Design

### Signatures

- `to_dict(self) -> dict` — existing, `scripts/little_loops/config/core.py:648-922`
- `resolve_variable(self, var_path: str) -> str | None` — existing, `core.py:924-946`
- `RefineStatusConfig(columns: list[str], elide_order: list[str])` — existing, `config/cli.py:151`
- `BRConfig.extensions -> list` — existing raw passthrough, `core.py:428-431`
- `OrchestrationConfig(host_cli, request_path, composer, cluster)` — existing,
  `config/orchestration.py:60-101`; property at `core.py:399-401`

### Call Path

`to_dict()` -> inline `"refine_status": {...}` dict + `"extensions": self.extensions`
+ nested `"orchestration": {...}` dict -> `resolve_variable()` (`core.py:924-946`)
-> `ll-config get`.

## Acceptance Criteria

- [ ] `ll-config get refine_status.columns` returns the configured columns for a
      project with `refine_status` set in `.ll/ll-config.json`.
- [ ] `ll-config get refine_status.elide_order` likewise.
- [ ] `ll-config get extensions` returns the configured extension list
      (space-joined per `resolve_variable`'s list handling).
- [ ] `ll-config get orchestration.host_cli` and
      `ll-config get orchestration.request_path` return the configured values.
- [ ] At least one nested orchestration lookup resolves (e.g.
      `orchestration.cluster.max_batch_size`), proving the entry descends into
      `ComposerConfig`/`ClusterConfig` rather than stopping at the scalars.
- [ ] All three keys are present in `to_dict()` output even when unset in config
      (default values), matching how sibling sections behave.
- [ ] No test asserts `extensions.<field>` resolves — that is unreachable given
      `extensions` is a list.
- [ ] A parity test derives `BRConfig`'s public config properties by
      introspection and asserts none are missing from `to_dict()`, using an
      explicit `{"analytics_capture": "analytics"}` alias map. Confirm it fails
      before the fix with exactly
      `{'extensions', 'orchestration', 'refine_status'}`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — silent CLI-tool gap, not a functional break of the
  underlying features (refine_status and extensions themselves work fine).
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.


## Session Log
- `/ll:verify-issues` - 2026-08-03T04:16:46 - `2184690f-4a99-44a3-bf23-ddded9adf45a.jsonl`
