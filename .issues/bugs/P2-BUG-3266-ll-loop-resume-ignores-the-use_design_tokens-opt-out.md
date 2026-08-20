---
id: BUG-3266
type: BUG
title: ll-loop resume ignores the use_design_tokens opt-out
priority: P2
status: open
relates_to:
- ENH-3264
- ENH-3267
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T21:10:34Z'
verify_verdict: VALID
labels:
- bug
- design-tokens
- loops
confidence_score: 100
outcome_confidence: 98
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3266: ll-loop resume ignores the use_design_tokens opt-out

## Summary

`ll-loop resume` ignores the per-loop `use_design_tokens: false` opt-out that ENH-3099 added. `cmd_resume` re-implements design-token context injection as a parallel copy of `cmd_run`'s block, but without the opt-out gate — so a loop that explicitly disables token injection still gets `design_tokens_context` populated when resumed.

Fix by extracting the gate into a shared helper called from both sites, so the two injection paths cannot diverge again.

## Current Behavior

Two independent injection blocks, structurally *similar* but not identical:

`scripts/little_loops/cli/loop/run.py:242-254` (`cmd_run`) computes the gate, including the string-coercion branch for `--context use_design_tokens=false`:

```python
_use_tokens = fsm.context.get("use_design_tokens", True)
if isinstance(_use_tokens, str):
    _use_tokens = _use_tokens.strip().lower() not in ("", "0", "false", "no", "off")
if _use_tokens and not fsm.context.get("design_tokens_context"):
    _tokens = load_design_tokens(_config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
else:
    fsm.context.setdefault("design_tokens_context", "")
```

`scripts/little_loops/cli/loop/lifecycle.py:715-717` (`cmd_resume`) has **no gate at all**:

```python
if not fsm.context.get("design_tokens_context"):
    _tokens = load_design_tokens(config)
    fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
```

So `use_design_tokens: false` is honored on `ll-loop run` and silently ignored on `ll-loop resume`.

## Expected Behavior

`use_design_tokens: false` suppresses `design_tokens_context` identically on both `ll-loop run` and `ll-loop resume`, including via `--context use_design_tokens=false` (string coercion). The key still exists as `""` in both paths so `${context.design_tokens_context}` interpolates without error.

## Motivation

A per-loop opt-out that works on one entry point and silently no-ops on another is worse than no opt-out: the loop author sets `use_design_tokens: false`, sees it honored on `ll-loop run`, and reasonably assumes it holds. Long-running loops are exactly the ones most likely to be resumed, so the path where the setting is ignored is the path where it matters most.

It also blocks the follow-on work in ENH-3267 (`design_guidance_context`, the DESIGN.md prose body): that variable needs to be injected under the same gate, and adding it to two divergent parallel blocks would double the defect rather than fix it. Extracting the shared helper here is what makes the follow-on safe. ENH-3264 (DESIGN.md as a token import source) is the upstream dependency of ENH-3267, not a direct consumer of this helper.

## Proposed Solution

Extract the gate + injection into a single shared helper — for example `inject_design_context(fsm, config)` in a module both call sites already import from — and call it from `cmd_run` and `cmd_resume`. Do not copy the block a second time; the parallel-maintenance pattern is what produced this defect.

The helper owns: reading `use_design_tokens` (bool or string form), the string coercion, the `load_design_tokens()` call, `render_as_prompt_context()`, and the `setdefault(..., "")` fallback.

**Implementation constraint — lazy import inside the helper body.** Both existing test classes patch the *source* module (`patch("little_loops.design_tokens.load_design_tokens", ...)`), which only works because `run.py` and `lifecycle.py` import `load_design_tokens` / `render_as_prompt_context` *inside* the function body rather than at module top-level. If the new helper in `_helpers.py` binds those names at module import time, every existing design-token test silently stops intercepting the call (`mock_load.assert_not_called()` passes vacuously, `assert_called_once()` fails). The helper must keep the `from little_loops.design_tokens import ...` inside its body — matching the lazy-`BRConfig` pattern already used by `seed_confidence_thresholds` (`_helpers.py:1385-1388`).

**Config argument.** In `cmd_run` a `BRConfig` is already in hand (`run.py:231`, `_config`). In `cmd_resume` the `BRConfig` is constructed at `lifecycle.py:713`, *after* the `seed_confidence_thresholds(fsm.context)` call at `:677` — so the helper call belongs at the existing `:715` block position with `config` passed explicitly, and the `config: BRConfig | None = None` lazy-load path exists only for parity with the precedent.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py:242-254` — replace the inline block with a call to the shared helper
- `scripts/little_loops/cli/loop/lifecycle.py:707-717` — replace the ungated block with the same call

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` (`test_design_tokens_context_injected_via_cmd_resume`) — existing coverage of the resume injection path
- `scripts/tests/test_cli_loop_lifecycle.py:1396-1485` (`TestCmdRunDesignTokensOptOut`, ENH-3099) — currently exercises `cmd_run` only (`test_default_loads_design_tokens`, `test_use_design_tokens_false_skips_loading`, `test_use_design_tokens_string_falsy_values_skip_loading` parametrized over `["false", "False", "no", "off", "0", ""]`); add the `cmd_resume` counterparts, which fail before the fix
- Prefer parametrizing the opt-out assertions over both entry points (`cmd_run` / `cmd_resume`) in one class rather than duplicating a second class — a duplicated test file mirrors the duplicated source block this issue exists to delete, and would let the two paths drift again silently.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:26` — top-level import of `little_loops.cli.loop._helpers` (already imports `seed_confidence_thresholds` from the module that is the natural home for the new shared helper)
- `scripts/little_loops/cli/loop/lifecycle.py:20` — same top-level import from `_helpers.py`
- `scripts/little_loops/cli/artifact.py:66-69` — separate, unrelated caller of `load_design_tokens` (for CSS-variable export via `render_as_css_vars_themed`); not affected by this fix, do not modify

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- Corrected block boundaries: `run.py:228-254` (not just 242-254) — the block starts with the local imports of `BRConfig`, `load_design_tokens`, `render_as_prompt_context` and includes the `seed_confidence_thresholds(fsm.context, _config)` call at line 240. `lifecycle.py:707-717` similarly opens with local imports of `BRConfig`, `load_design_tokens`, `render_as_prompt_context`, `wire_extensions`, `RateLimitCircuit`, `wire_transports`.
- Natural home for the shared helper: `scripts/little_loops/cli/loop/_helpers.py` ("Shared helpers for ll-loop CLI subcommands", module docstring at line 1). Both `run.py` and `lifecycle.py` already import from it at module top-level (`run.py:26`, `lifecycle.py:20`). Existing precedent of the identical shape (gate + mutate `fsm.context` in place, optional pre-built config): `seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None` (`_helpers.py:1367`), called as `seed_confidence_thresholds(fsm.context, _config)` in `run.py:240` and `seed_confidence_thresholds(fsm.context)` in `lifecycle.py:677`.
- `load_design_tokens`/`render_as_prompt_context` are also called from `scripts/little_loops/cli/artifact.py:66-69`, but for CSS-variable export via a different renderer (`render_as_css_vars_themed`) — an unrelated, non-FSM-context code path with no `use_design_tokens` opt-out semantics. Not a candidate for the new helper; do not touch.
- Test class naming correction: the actual class on disk is `TestCmdRunDesignTokensOptOut` (`test_cli_loop_lifecycle.py:1396`), not `TestUseDesignTokensOptOut` as currently written elsewhere in this issue.
- Existing `cmd_resume`-side design-token coverage is a single test, `test_design_tokens_context_injected_via_cmd_resume` (`:921-948`), living inside the general `TestCmdResume` class (`:609`) — there is no dedicated `TestCmdResumeDesignTokensOptOut` class today; a new opt-out test can either extend `TestCmdResume` or start a new sibling class, matching this file's existing mixed convention (both styles coexist for `seed_confidence_thresholds` vs `derive_input_hash` imports).

## Program Design

### Types
- No new data shape introduced; the fix operates on the existing `fsm.context: dict[str, Any]` field of `FSMLoop` (`@dataclass` at `scripts/little_loops/fsm/schema.py:1279`, `context` field at line 1305).

### Signatures
- New shared helper (name/placement is the implementer's call), mirroring the existing precedent `seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None` (`scripts/little_loops/cli/loop/_helpers.py:1367`), which both `cmd_run` (`run.py:240`) and `cmd_resume` (`lifecycle.py:677`) already call in this exact shape:
- `inject_design_context(context: dict[str, Any], config: BRConfig | None = None) -> None`
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` — defined at `scripts/little_loops/design_tokens.py:160`
- `render_as_prompt_context(tokens: DesignTokens) -> str` — defined at `scripts/little_loops/design_tokens.py:225`

### Call Path
`cmd_run` (`run.py:92`) / `cmd_resume` (`lifecycle.py:553`) -> shared helper in `little_loops.cli.loop._helpers` -> `load_design_tokens()` -> `render_as_prompt_context()` -> `fsm.context["design_tokens_context"]`

### Decision Rules
N/A — no new decision logic. This fix extracts existing gate logic verbatim; it does not add a new gap kind, threshold, or keyword list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- Types/Signatures/Call Path above are derived from `codebase-analyzer` findings: `fsm.context` type from `scripts/little_loops/fsm/schema.py:1279-1305`; `load_design_tokens`/`render_as_prompt_context` signatures from `scripts/little_loops/design_tokens.py:160,225`; the `inject_design_context` name is illustrative only (matches Proposed Solution's example) — the implementer may choose a different name.

## Implementation Steps

1. Add the `cmd_resume` opt-out tests to `TestCmdRunDesignTokensOptOut` (`test_cli_loop_lifecycle.py:1396-1485`, renaming it to drop the `CmdRun` prefix once it covers both paths) and confirm they fail against current `main` — this is the regression proof. Cover both the YAML-boolean form and the persisted-string form.
2. Extract `run.py:242-254`'s gate + injection wholesale into a shared helper in `_helpers.py`, preserving the string-coercion branch and the `setdefault(..., "")` fallback exactly, and keeping the `little_loops.design_tokens` import *inside* the helper body (see § Proposed Solution — Implementation constraint).
3. Call the helper from `cmd_run` (`run.py:242-254`, passing `_config`) and `cmd_resume` (`lifecycle.py:715-717`, passing `config`), deleting both inline blocks.
4. Verify: the new tests pass, `test_design_tokens_context_injected_via_cmd_resume` (`:921-948`) and all three existing `cmd_run` opt-out tests still pass, and `python -m pytest scripts/tests/` exits 0.

## Impact

- **Scope**: two call sites plus one new helper. ~30 LOC net.
- **Compatibility**: behavior change only for loops that set `use_design_tokens: false` *and* are resumed — currently a silent no-op, which is the bug.
- **Risk**: low. Isolated, fully covered by existing test classes once the resume counterpart is added.

## Scope Boundaries

**In scope**
- The shared-helper extraction and the `cmd_resume` gate fix, for the existing `design_tokens_context` variable only.

**Out of scope**
- Any new context variable. `design_guidance_context` is ENH-3264's follow-on and consumes this helper once it exists.
- Any change to `load_design_tokens()` or the design-token model.
- Documentation updates. `docs/reference/CONFIGURATION.md:755` and `docs/generalized-fsm-loop.md:1099-1103` already describe the opt-out as applying to both `cmd_run` and `cmd_resume` — they document the *intended* behavior, so this fix makes the docs true rather than requiring an edit. (The per-loop tables in `docs/guides/LOOPS_REFERENCE.md` omit the opt-out entirely; that is pre-existing ENH-3099 doc debt, not this bug's.)
- `scripts/little_loops/cli/artifact.py:66-69` — confirmed by grep to be the only other `load_design_tokens` caller, and it renders CSS variables rather than FSM prompt context. No third injection site exists.

## Acceptance Criteria

1. `use_design_tokens: false` on a loop suppresses `design_tokens_context` on `ll-loop resume`, not just `ll-loop run`. *(Fails on current `main`.)*
2. `--context use_design_tokens=false` (string form) is honored on both paths — the string-coercion branch lives in the shared helper. On `resume` this covers both the re-passed `--context` flag and the value restored from the original run's persisted state (see § Root Cause for why the restored value is a *string*, not a bool).
3. When suppressed, `design_tokens_context` is still present as `""` on both paths, so `${context.design_tokens_context}` never hard-fails interpolation.
4. Exactly one implementation of the gate exists; `cmd_run` and `cmd_resume` both call it.
5. `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of ENH-3264, where it was pulled into scope because that issue's acceptance criteria could not pass against current `main` without it. It is an independent defect that exists today and does not depend on any DESIGN.md work, so it ships on its own.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `cmd_resume()` (signature at line 553), injection block at lines 707-717
- **Precondition that makes the fix work**: the gate is only meaningful on resume because `use_design_tokens` actually survives into the resumed context. `cmd_resume` restores the full persisted FSM context as its base at `lifecycle.py:651-655` (BUG-2485) before applying any `--context` overrides, so a `use_design_tokens` set in the loop YAML *or* passed as `--context` on the original run is present in `fsm.context` by the time the injection block runs. Note the two forms differ in type: a YAML `use_design_tokens: false` restores as a bool, while a `--context use_design_tokens=false` restores as the string `"false"` (the `--context` parser at `lifecycle.py:657-662` / `run.py` stores raw strings, and JSON state round-trips them as strings). Both must pass through the coercion branch — this is why the string handling cannot be dropped from the shared helper.
- **Cause**: `cmd_resume`'s only guard is `not fsm.context.get("design_tokens_context")` (`lifecycle.py:715`) — it never reads `fsm.context.get("use_design_tokens", ...)`. On an opted-out original run, `design_tokens_context` was persisted as `""` (falsy), so on resume `not ""` evaluates `True` and `load_design_tokens(config)` / `render_as_prompt_context(...)` fire again, overwriting the empty placeholder with real token content. `cmd_run`'s parallel block (`run.py:242-254`) reads and coerces `use_design_tokens` before that same falsy-check — the gate `cmd_resume` lacks entirely.


## Session Log
- `/ll:confidence-check` - 2026-08-20T21:40:55 - `d6d6772b-3466-4177-b443-81b8082d8c60.jsonl`
- `/ll:confidence-check` - 2026-08-20T21:34:25 - `ff90fea6-905c-4a3b-9ca3-a82cdf5d6ffd.jsonl`
- `/ll:verify-issues` - 2026-08-20T21:32:15 - `8801f712-ba12-4901-ad8c-405f7261e477.jsonl`
- `/ll:refine-issue` - 2026-08-20T21:22:46 - `d45eb280-8788-4b5e-9748-16d4c132c1ab.jsonl`
