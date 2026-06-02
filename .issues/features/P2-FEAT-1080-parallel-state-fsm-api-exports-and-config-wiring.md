---
discovered_date: "2026-04-12"
discovered_by: issue-size-review

testable: false
confidence_score: 90
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 18
size: Very Large
parent: FEAT-1078
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1080: Parallel State FSM API Exports and Config Wiring

## Summary

Export `ParallelStateConfig` and `ParallelResult` from `scripts/little_loops/fsm/__init__.py`, add the `parallel` glyph field to `LoopsGlyphsConfig` in `config/features.py`, add the `parallel` key to `config-schema.json`, and update the affected test assertions.

## Parent Issue

Decomposed from FEAT-1078: Parallel State Wiring, Display, and Docs

## Use Case

**Who**: A developer building FSM loops with parallel state execution

**Context**: After `ParallelStateConfig` and `ParallelResult` are added to `fsm/schema.py` (FEAT-1074), a developer importing these types via `from little_loops.fsm import ...` needs them exposed in the public module API. Similarly, a user who sets `loops.glyphs.parallel` in `ll-config.json` expects the key to be accepted and applied.

**Goal**: Import `ParallelStateConfig` and `ParallelResult` from `little_loops.fsm` without resorting to internal module paths; configure the parallel state badge via the standard `loops.glyphs` config key.

**Outcome**: All parallel state types are available in the public FSM API; `loops.glyphs.parallel` in `ll-config.json` validates and takes effect.

## Motivation

This wiring step would:
- Expose `ParallelStateConfig` and `ParallelResult` in the public FSM API, directly unblocking FEAT-1081 (display) and FEAT-1082 (documentation) which depend on these types
- Allow users to configure the parallel state glyph via the established `LoopsGlyphsConfig` pattern — consistent with `sub_loop` and `route` badge config
- Prevent schema validation rejections for any `ll-config.json` that sets `loops.glyphs.parallel`
- Purely additive with no behavior changes — zero risk to existing functionality

## Current Behavior

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` raises `ImportError` — neither type is in `__init__.py`'s import block or `__all__`
- `LoopsGlyphsConfig` in `config/features.py:257-288` has no `parallel` field, so downstream code that reads `badges.get("parallel", ...)` will always fall back to its default regardless of user config
- `config-schema.json` `loops.glyphs` block at lines 760–772 has `"additionalProperties": false` at line 771 and no `"parallel"` property, so any `ll-config.json` with `loops.glyphs.parallel` is rejected by schema validation
- `test_config.py:1530` (`test_to_dict_returns_all_keys`) asserts `set(d.keys()) == {"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route"}` at lines 1533–1540 — will break if `to_dict()` gains `"parallel"`

## Expected Behavior

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` succeeds
- `LoopsGlyphsConfig.parallel` field defaults to `"\u2225"` and is included in `to_dict()` / `from_dict()`
- `config-schema.json` accepts `loops.glyphs.parallel` as a valid string property
- `test_config.py:1530` (`test_to_dict_returns_all_keys`) assertion includes `"parallel"` in the expected key set

## Proposed Solution

### `fsm/__init__.py` exports

- Extend the `from little_loops.fsm.schema import (...)` block at lines 120–127 to include `ParallelStateConfig` and `ParallelResult`
- Add both to `__all__` (lines 143–195); alphabetically sorted, "Par..." names come before `"PersistentExecutor"` at line 170. Insert `"ParallelResult"` then `"ParallelStateConfig"` immediately before line 170
- Add brief parallel state type description to module docstring (lines 1–68) under the `# Schema` comment block

### `config/features.py` — `LoopsGlyphsConfig`

- Add `parallel: str = field(default="\u2225")` to `LoopsGlyphsConfig` dataclass (lines 257–288). **Use bare inline default — NO `field()` wrapper** (matches existing style: `route: str = "⑃"`). Correct form: `parallel: str = "∥"`
- Add `"parallel": self.parallel` entry to `to_dict()` (body at lines 281–288) after the existing `"route"` entry at line 287
- Update `from_dict()` (body at lines 270–277) to read the `"parallel"` key: `parallel=data.get("parallel", "∥"),` after the `route=...` line at 276

### `config-schema.json`

- Add `"parallel"` property to the `loops.glyphs` object schema (block at lines 760–772, insert before `"additionalProperties": false` at line 771):
  ```json
  "parallel": {
    "type": "string",
    "default": "\u2225",
    "description": "Badge for parallel states (default: \u2225)"
  }
  ```
  Mirrors the `"sub_loop"` and `"route"` entries already present.

### Tests

- `scripts/tests/test_config.py:1530` — update `test_to_dict_returns_all_keys` (set assertion at lines 1533–1540) to include `"parallel"`; add `assert d["parallel"] == "\u2225"` below it
- `scripts/tests/test_config.py:1510` — update `TestLoopsGlyphsConfig.test_defaults` to add `assert config.parallel == "\u2225"`
- `scripts/tests/test_config.py:1558` — update `TestBRConfigLoopsGlyphs.test_loops_glyphs_defaults_when_absent` to assert `config.loops.glyphs.parallel == "\u2225"`
- `scripts/tests/test_fsm_schema.py` — add a public-API import smoke test using `from little_loops.fsm import ParallelStateConfig, ParallelResult` (NOTE: existing tests in this file import from `little_loops.fsm.schema` directly — the new test should validate the public `__init__` re-export specifically)

## API/Interface

New public exports added to `little_loops/fsm/__init__.py`:

```python
from little_loops.fsm import ParallelStateConfig, ParallelResult
```

New field on `LoopsGlyphsConfig` (config/features.py):

```python
@dataclass
class LoopsGlyphsConfig:
    # ... existing fields (prompt, slash_command, shell, mcp_tool, sub_loop, route) ...
    parallel: str = "\u2225"  # ∥  — bare default, no field() wrapper (matches existing field style)
```

New property in `config-schema.json` under `loops.glyphs`:

```json
"parallel": {
  "type": "string",
  "default": "\u2225",
  "description": "Badge for parallel states (default: \u2225)"
}
```

## Implementation Steps

1. Export `ParallelStateConfig` and `ParallelResult` from `fsm/__init__.py` (import block + `__all__` + module docstring)
2. Add `parallel: str` field to `LoopsGlyphsConfig`, `to_dict()`, and `from_dict()` in `config/features.py`
3. Add `"parallel"` property to `loops.glyphs` in `config-schema.json`
4. Update `test_config.py:1530` (`test_to_dict_returns_all_keys`) assertion to include `"parallel"` key and value
5. Add `test_fsm_schema.py` import smoke test for the new exports

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `run.py:100`, `info.py:728`, `core.py:430` — confirm no breakage from the new `"parallel"` key appearing in `to_dict()` output (no code changes needed; smoke-check via test run)
7. Update `test_config.py:1519` (`test_from_dict_empty`) — add `assert config.parallel == "\u2225"` to cover `parallel` default when key is absent from input dict
8. Update `test_config.py:1524` (`test_from_dict_partial_override`) — add override case: `from_dict({"parallel": "P"})` → `config.parallel == "P"`
9. Update `test_config.py:1564-1573` (`test_loops_glyphs_override_from_config`) — include `"parallel"` in sample config; assert default and override round-trip through `BRConfig`
10. Add `test_config_schema.py::test_loops_glyphs_parallel_in_schema` — navigate `data["properties"]["loops"]["properties"]["glyphs"]["properties"]` and assert `"parallel"` key present with `"type": "string"`; mirrors existing `test_commands_rate_limits_block` pattern (line 56)
11. Write `scripts/tests/test_ll_auto.py` (new file) — assert no warning is emitted when a loop containing a `parallel:` state runs under ll-auto; use `capsys` pattern from `test_ll_loop_state.py:332`; validates the "no warning under ll-auto" acceptance criterion

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/__init__.py` — Add `ParallelStateConfig`, `ParallelResult` to import block, `__all__`, docstring
- `scripts/little_loops/config/features.py` — Add `parallel` field to `LoopsGlyphsConfig` dataclass, `to_dict()`, `from_dict()`
- `config-schema.json` — Add `"parallel"` to `loops.glyphs` schema
- `scripts/tests/test_config.py` — Update `test_to_dict_returns_all_keys` assertion
- `scripts/tests/test_fsm_schema.py` — Add import smoke test

### Read-only Dependencies

- `scripts/little_loops/fsm/schema.py` — source of `ParallelStateConfig` and `ParallelResult` (FEAT-1074 must be complete)

### Similar Patterns

- `from little_loops.fsm.schema import (...)` grouped import block in `fsm/__init__.py:120-127`
- `sub_loop: str` and `route: str` fields in `LoopsGlyphsConfig` — naming and wiring pattern
- `"sub_loop"` and `"route"` entries in `config-schema.json` `loops.glyphs` block

### Dependent Files (Callers/Importers)

- FEAT-1081 (parallel state CLI display) — will import `ParallelResult` to render parallel execution output
- FEAT-1082 (parallel state documentation) — references `ParallelStateConfig` in API docs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:100` — calls `_config.loops.glyphs.to_dict()` and passes the result as `badges=_badges`; new `"parallel"` key flows through silently — no change needed, verify no breakage
- `scripts/little_loops/cli/loop/info.py:728` — same pattern: `badges = BRConfig(Path.cwd()).loops.glyphs.to_dict()`; no change needed
- `scripts/little_loops/config/core.py:430` — embeds `self._loops.glyphs.to_dict()` inside `BRConfig.to_dict()` output (`"loops"."glyphs"` sub-dict); gains `"parallel"` after FEAT-1080, no change needed
- `scripts/little_loops/cli/loop/layout.py:119-123` — `_get_state_badge()` (declared line 119) receives the badges dict and at line 123 uses `{**_ACTION_TYPE_BADGES, **(badges or {})}` merge (`_ACTION_TYPE_BADGES` at line 102); the new `"parallel"` key will be present but not consumed until FEAT-1081 adds a lookup branch — no change needed, no breakage

### Documentation

- N/A — no existing documentation references these types yet; FEAT-1082 covers new doc additions

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — contains a literal table enumerating the six existing `glyphs.*` keys with defaults and descriptions; has no `glyphs.parallel` row; will be out of date after this issue lands. NOTE: FEAT-1082 completed — but verify whether the docs have been updated to include `parallel`. If FEAT-1082's doc update already landed, the row may now be stale-referencing a type that didn't exist yet. Re-verify during implementation.

### Configuration

- `config-schema.json` — listed in Files to Modify above

### Tests

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py:56` — existing test `test_commands_rate_limits_block` guards `commands.rate_limits` inside `additionalProperties: false`; no equivalent test guards `loops.glyphs.parallel`; new test `test_loops_glyphs_parallel_in_schema` needed, navigating `data["properties"]["loops"]["properties"]["glyphs"]["properties"]` and asserting `"parallel"` key present with `"type": "string"` — prevents silent schema regression where the property is accidentally dropped
- `scripts/tests/test_ll_auto.py` (new file) — acceptance criterion "No warning under ll-auto" has zero test coverage; assert no warning is emitted when a loop containing a `parallel:` state runs under ll-auto (mirrors `capsys` pattern from `test_ll_loop_state.py:332`)

## Dependencies

- FEAT-1074 must be complete (`ParallelStateConfig` and `ParallelResult` must exist in `schema.py`)

## Acceptance Criteria

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` works without error
- `LoopsGlyphsConfig.parallel` field exists, defaults to `"\u2225"`, and round-trips through `to_dict()` / `from_dict()`
- `config-schema.json` validates `ll-config.json` files with `loops.glyphs.parallel`
- All existing tests pass; `test_to_dict_returns_all_keys` updated assertion passes

## Outer-CLI awareness (ll-auto, ll-parallel, ll-sprint)

The three orchestrator CLIs each invoke FSM loops through `PersistentExecutor.run()`. When a loop containing a `parallel:` state runs under one of these CLIs, the outer scheduler's concurrency must NOT compose with the inner `parallel:` state's `max_workers` — that would multiply worker counts and blow out thread/worktree limits silently.

Decision and contract (documented here; enforced by this issue's wiring):

- **`ll-auto`** — runs issues sequentially by design. A `parallel:` state inside the loop fans out normally using its own `max_workers`. No composition concern. **No code change needed**, but add an inline comment in `ll-auto`'s main loop explaining that the inner parallel state is free to use its full `max_workers` budget.
- **`ll-parallel`** — runs N issues in N parallel worktrees, each running the full loop. If the loop contains `parallel:` state with `max_workers=4`, the system could spawn `N * 4` threads. This issue adds a **soft-cap warning** emitted once per `ll-parallel` run when the loop definition contains any `parallel:` state: `WARNING: loop 'X' contains parallel state(s); ll-parallel concurrency (N) multiplies inner parallel concurrency (M). Cumulative worker budget: N*M=<product>. Consider reducing inner max_workers or running under ll-auto.` No hard limit in v1 — authors are responsible. Tracked as a hard-limit candidate under ENH-1176 (resource limits).
- **`ll-sprint`** — runs a curated ordered list of issues, typically sequentially (unless `--parallel` is passed, in which case it delegates to `ll-parallel` behavior). Apply the same soft-cap warning as `ll-parallel` when `--parallel` is in effect.

### Files that must be touched to deliver the warning

- `scripts/little_loops/cli/ll_auto.py` — comment only
- `scripts/little_loops/cli/ll_parallel.py` — scan loaded FSMLoop for any `state.parallel is not None`; emit warning once before fan-out
- `scripts/little_loops/cli/ll_sprint.py` — same scan when `--parallel` is active

### Modules that MUST NOT be touched in this issue

- `scripts/little_loops/fsm/executor.py` — parallel dispatch is FEAT-1076's territory
- `scripts/little_loops/fsm/parallel_runner.py` — FEAT-1075's territory
- `scripts/little_loops/parallel/worker_pool.py` — keep the ll-parallel worker pool unaware of FSM parallel states; the warning is at the CLI layer by design

### Outer-CLI awareness acceptance criteria

- Loading a loop with any `parallel:` state under `ll-parallel` emits exactly one WARNING to stderr naming the cumulative worker budget
- Same under `ll-sprint --parallel`; no warning under `ll-sprint` without `--parallel`
- No warning under `ll-auto` (sequential by design); comment present in the CLI module explaining why
- A test in `test_ll_parallel.py` (new) and `test_ll_sprint.py` (extend) asserts the warning fires exactly once per run and includes the computed `N*M` product

## Impact

- **Priority**: P2
- **Effort**: Very Small — Additive-only: import extension, dataclass field, schema property, test assertion update
- **Risk**: Low — No existing behavior modified
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `wiring`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`fsm/__init__.py` exact `__all__` state** (`scripts/little_loops/fsm/__init__.py:136-184`):
- `"PersistentExecutor"` is at line 160; `"ParallelResult"` and `"ParallelStateConfig"` (alphabetically "Par" < "Per") both insert immediately before it
- Schema types currently exported: `DEFAULT_LLM_MODEL` (139), `EvaluateConfig` (146), `FSMLoop` (150), `LLMConfig` (157), `RouteConfig` (161), `StateConfig` (168)

**`LoopsGlyphsConfig` field declaration style** (`scripts/little_loops/config/features.py:193-198`):
- All fields use bare inline defaults, e.g. `route: str = "\u2443"  # ⑃` — no `field()` wrapper
- `from_dict()` spans lines 200–210; `to_dict()` spans lines 212–221

**`config-schema.json` exact glyphs block** (lines 658–670):
- `"additionalProperties": false` is at line 669 on the `glyphs` object; adding `"parallel"` to `properties` before that line is sufficient to unblock schema validation
- Outer `loops` object also has `"additionalProperties": false` at line 672 (no change needed there)

**Test assertions needing `parallel` additions** (`scripts/tests/test_config.py`):
- `TestLoopsGlyphsConfig.test_defaults` (line 1428): asserts each field value individually — add `assert config.parallel == "\u2225"`
- `TestLoopsGlyphsConfig.test_to_dict_returns_all_keys` (line 1448): set assertion at line 1451–1458 — add `"parallel"` to set; add `assert d["parallel"] == "\u2225"`
- `TestBRConfigLoopsGlyphs.test_loops_glyphs_defaults_when_absent` (line 1473): integration test asserting defaults — add `assert config.loops.glyphs.parallel == "\u2225"`

**`test_parallel_types.py` is unrelated** (`scripts/tests/test_parallel_types.py`, 1024 lines):
- Covers `little_loops/parallel/types.py` worker types (QueuedIssue, WorkerResult, etc.) — not FSM schema types; no overlap with this issue

**`test_fsm_schema.py` import pattern**:
- All existing tests import from `little_loops.fsm.schema` (internal module path)
- The new smoke test should explicitly import from `little_loops.fsm` (public `__init__`) to validate the re-export wiring introduced by this issue
- Follow the pattern from `scripts/tests/test_extension.py:469-497` (`test_smoke_import_interceptor_extension`): one-liner import with `# noqa: F401`, then `assert Symbol is not None`

**Additional `test_config.py` assertions needed** (wiring pass added by `/ll:wire-issue`):
- `test_config.py:1437` (`test_from_dict_empty`) — currently asserts `prompt` and `sub_loop` only; add `assert config.parallel == "\u2225"` to cover default when not passed
- `test_config.py:1442` (`test_from_dict_partial_override`) — add a case passing `{"parallel": "P"}` and asserting `config.parallel == "P"` with unset fields defaulted
- `test_config.py:1482-1491` (`test_loops_glyphs_override_from_config`) — add `"parallel"` to the sample config dict and assert `config.loops.glyphs.parallel == "\u2225"` when absent, and the override value when present

**FEAT-1074 dependency STILL ACTIVE as of 2026-04-21**:
- Re-verified: `ParallelStateConfig` and `ParallelResult` remain absent from `scripts/little_loops/fsm/schema.py` (670 lines; grepped — zero matches). FEAT-1074 is still under `.issues/features/` (not in `completed/`).
- Steps 1 and 5 still blocked on FEAT-1074. Steps 2-4 and 6-9 still actionable immediately.

**FEAT-1074 dependency confirmed still active** (verified 2026-04-12):
- `ParallelStateConfig` and `ParallelResult` are absent from `scripts/little_loops/fsm/schema.py` — FEAT-1074 is in `.issues/features/` (not completed). Steps 1 and 5 (`fsm/__init__.py` exports + `test_fsm_schema.py` smoke test) must wait for FEAT-1074 to merge.

**Line number correction**:
- Issue step 9 references `test_loops_glyphs_defaults_when_absent` at line 1473; actual current location is **lines 1476–1480** (3-line drift from earlier edits).

**Line-number refresh (2026-04-21)** — codebase has drifted further since the 2026-04-12 research pass; authoritative current locations:
- `fsm/__init__.py` (195 lines) — schema import block: lines 120–127; `__all__`: lines 143–195; `"PersistentExecutor"`: line 170 (insertion point for new Par-prefixed entries)
- `config/features.py` (352 lines) — `LoopsGlyphsConfig`: lines 257–288; `from_dict()`: 267–277 (route entry at 276); `to_dict()`: 279–288 (route entry at 287); **style confirmed**: all fields use bare inline defaults (no `field()` wrapper) — e.g. `route: str = "⑃"  # ⑃`
- `config-schema.json` (1013 lines) — `loops.glyphs` block: lines 760–772; existing props on lines 764–769; `"additionalProperties": false`: line 771 (insertion point for `"parallel"` property)
- `scripts/tests/test_config.py` (1573 lines):
  - `TestLoopsGlyphsConfig`: class starts line 1507
  - `test_defaults`: line 1510 (add `assert config.parallel == "∥"`)
  - `test_from_dict_empty`: line 1519 (add `assert config.parallel == "∥"`)
  - `test_from_dict_partial_override`: line 1524 (add override case)
  - `test_to_dict_returns_all_keys`: line 1530 (set assertion at lines 1533–1540; add `"parallel"` to set and `assert d["parallel"] == "∥"` after line 1542)
  - `TestBRConfigLoopsGlyphs`: class starts line 1555
  - `test_loops_glyphs_defaults_when_absent`: line 1558
  - `test_loops_glyphs_override_from_config`: lines 1564–1573 (end of file)
- `scripts/tests/test_fsm_schema.py` (2104 lines) — last class is `TestAgentToolsStateConfig` at **line 2019** (not 1875 as earlier research stated). New `TestParallelStatePublicExports` class appends at end of file
- CLI wiring touchpoints:
  - `cli/loop/run.py:100` (was `:97`) — `_config.loops.glyphs.to_dict()`
  - `cli/loop/info.py:728` — unchanged
  - `config/core.py:430` (was `:424`) — `"glyphs": self._loops.glyphs.to_dict(),`
  - `cli/loop/layout.py` — `_ACTION_TYPE_BADGES` dict at line 102; `_get_state_badge()` declared line 119; merge expression at line 123; badge consumers at lines 527 and 1513

**Note on `_PARALLEL_BADGE` reference**:
- The original issue text referenced `(badges or {}).get("parallel", _PARALLEL_BADGE)` — this symbol does NOT exist in the codebase today. It was a forward reference to FEAT-1081's eventual integration. Implementers should treat this as descriptive of post-FEAT-1081 behavior, not a current code path to verify.

**Smoke test class placement** — `test_fsm_schema.py` currently has 13 test classes; the last is `TestAgentToolsStateConfig` starting at line 1875. Add a new `TestParallelStatePublicExports` class at end of file:

```python
class TestParallelStatePublicExports:
    """Verify ParallelStateConfig and ParallelResult are re-exported from public FSM API."""

    def test_smoke_import_parallel_state_config(self) -> None:
        """Importing ParallelStateConfig from public FSM API succeeds."""
        from little_loops.fsm import ParallelStateConfig  # noqa: F401 — import is the test

        assert ParallelStateConfig is not None

    def test_smoke_import_parallel_result(self) -> None:
        """Importing ParallelResult from public FSM API succeeds."""
        from little_loops.fsm import ParallelResult  # noqa: F401 — import is the test

        assert ParallelResult is not None
```

---

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-12_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 partial blocker**: `ParallelStateConfig` and `ParallelResult` do not yet exist in `scripts/little_loops/fsm/schema.py`. Steps 1 (fsm/__init__.py exports) and 5 (smoke test) must wait for FEAT-1074 to ship. Steps 2-4 and 6-9 (config/features.py, config-schema.json, all test_config.py assertions) are fully actionable now — 7 of 9 implementation steps can proceed immediately.

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `c25b41ad-2e86-4d04-bea4-6daf251405e7.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `bb241b55-1d34-432c-a106-7784678fa9e9.jsonl`
- `/ll:wire-issue` - 2026-04-21T15:39:13 - `33fbf0c9-abd5-4804-acea-7186e27543a1.jsonl`
- `/ll:refine-issue` - 2026-04-21T15:33:13 - `40d82980-5a40-467a-afca-9b5a6c642dff.jsonl`
- `/ll:refine-issue` - 2026-04-12T23:18:12 - `b9548464-43de-4404-b392-5f02350675b4.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `2fff07e3-8175-409d-b80a-4696f20cca93.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `b9548464-43de-4404-b392-5f02350675b4.jsonl`
- `/ll:wire-issue` - 2026-04-12T23:14:05 - `cfd74bef-7777-40b8-b2c3-4a5efe2d48f4.jsonl`
- `/ll:refine-issue` - 2026-04-12T23:07:55 - `1c3ebdf4-689c-484d-8bd7-e5f4bbfe93b1.jsonl`
- `/ll:format-issue` - 2026-04-12T23:04:14 - `95ca3cc7-a17d-4286-82ee-08e5166f6ce9.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `77a4f6c6-909a-4d66-84d7-1e952b12aed8.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score 11/11); outer-CLI awareness scope added via wiring pass created a clear second concern

### Decomposed Into
- FEAT-1227: Parallel State Core API Exports and Config Wiring
- FEAT-1228: Parallel State Outer-CLI Awareness and Warnings

---

**Open** | Created: 2026-04-12 | Priority: P2
