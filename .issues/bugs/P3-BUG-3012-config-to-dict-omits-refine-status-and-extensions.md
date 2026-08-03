---
id: BUG-3012
title: BRConfig.to_dict() omits refine_status and extensions, breaking ll-config get
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

# BUG-3012: `BRConfig.to_dict()` omits `refine_status` and `extensions`, breaking `ll-config get`

## Summary

`refine_status` and `extensions` are both genuinely parsed by `BRConfig` and
actively consumed elsewhere in the codebase, but `to_dict()`
(`scripts/little_loops/config/core.py:648-922`) omits both sections. Since
`ll-config get <dot.path>` resolves through `to_dict()`/`resolve_variable()`
(`core.py:924-946`), `ll-config get refine_status.columns` and
`ll-config get extensions` silently return nothing even though the underlying
features work correctly.

## Current Behavior

- `refine_status` is parsed and exposed as a `BRConfig` property at
  `core.py:270-272, 378-381`, and genuinely consumed by
  `scripts/little_loops/cli/issues/refine_status.py`.
- `extensions` is parsed as a raw-passthrough property at `core.py:428-431`,
  and consumed via the `EventBus`/extension loader.
- Neither key appears in `to_dict()` (`core.py:648-922`), so
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

## Expected Behavior

- `ll-config get refine_status.columns` / `refine_status.elide_order` should
  resolve to the configured values, matching every other parsed config section.
- `ll-config get extensions` should resolve to the configured extension list.

## Shape constraints (verified — do not assume otherwise)

Two details make the naive fix wrong:

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

## Suggested Fix Direction

In `to_dict()` (`core.py:648-922`), add alongside the existing `cache` /
`deferred_tools` entries:

```python
"refine_status": {
    "columns": self.refine_status.columns,
    "elide_order": self.refine_status.elide_order,
},
"extensions": self.extensions,
```

Add regression tests in `scripts/tests/` alongside the existing `to_dict()` /
`ll-config get` coverage.

## Program Design

### Signatures

- `to_dict(self) -> dict` — existing, `scripts/little_loops/config/core.py:648-922`
- `resolve_variable(self, var_path: str) -> str | None` — existing, `core.py:924-946`
- `RefineStatusConfig(columns: list[str], elide_order: list[str])` — existing, `config/cli.py:151`
- `BRConfig.extensions -> list` — existing raw passthrough, `core.py:428-431`

### Call Path

`to_dict()` -> inline `"refine_status": {...}` dict + `"extensions": self.extensions`
-> `resolve_variable()` (`core.py:924-946`) -> `ll-config get`.

## Acceptance Criteria

- [ ] `ll-config get refine_status.columns` returns the configured columns for a
      project with `refine_status` set in `.ll/ll-config.json`.
- [ ] `ll-config get refine_status.elide_order` likewise.
- [ ] `ll-config get extensions` returns the configured extension list
      (space-joined per `resolve_variable`'s list handling).
- [ ] Both keys are present in `to_dict()` output even when unset in config
      (empty list defaults), matching how sibling sections behave.
- [ ] No test asserts `extensions.<field>` resolves — that is unreachable given
      `extensions` is a list.
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
