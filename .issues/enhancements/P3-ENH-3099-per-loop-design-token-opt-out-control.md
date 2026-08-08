---
id: ENH-3099
title: "Add per-loop design-token opt-out control"
type: ENH
priority: P3
status: done
captured_at: '2026-08-07T22:53:54Z'
completed_at: '2026-08-07T22:53:54Z'
discovered_date: 2026-08-07
discovered_by: manual
labels:
- fsm
- loops
- design-tokens
relates_to:
- ENH-1768
confidence_score: 90
outcome_confidence: 90
decision_needed: false
testable: true
---

# ENH-3099: Add per-loop design-token opt-out control

## Summary

`ll-loop run` unconditionally injected the resolved design-token set into
`context.design_tokens_context` for every FSM loop whenever design tokens
were enabled project-wide (`CONFIGURATION.md` → `design_tokens`). Non-visual
loops (code refactors, issue-management
automations, text-only generators) had no way to skip this injection short
of disabling design tokens project-wide, which would also strip them from
the artifact-generating loops that actually need them.

## Current Behavior

The project's `design_tokens` config (see `CONFIGURATION.md` → `design_tokens`) has a single project-wide on/off setting.
A project running both UI-artifact loops (e.g. `generative-art`, `vega-viz`)
and non-visual loops (e.g. issue-refinement, code-quality loops) had no
per-loop control: tokens were either injected into every loop's context or
none of them.

## Expected Behavior

A loop opts out by setting `use_design_tokens: false` in its YAML `context:`
block, or by passing `--context use_design_tokens=false` at run time, while
other loops in the same project keep receiving injected tokens. String
values from `--context` are parsed case-insensitively; `false`, `no`, `off`,
`0`, and empty string are all falsy; anything else (including the key being
absent) defaults to `true` for backward compatibility.
`context.design_tokens_context` is always present (`""` when opted out) so
prompts that reference `${context.design_tokens_context}` unconditionally
never fail to interpolate.

## Change

Gated the injection in `cmd_run` (`scripts/little_loops/cli/loop/run.py`)
behind a per-loop `context.use_design_tokens` flag, defaulting to `true` for
backward compatibility:

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

A loop opts out by setting `use_design_tokens: false` in its YAML `context:`
block, or by passing `--context use_design_tokens=false` at run time. String
values from `--context` are parsed case-insensitively; `false`, `no`, `off`,
`0`, and empty string are all falsy. `context.design_tokens_context` is
always present (`""` when opted out) so prompts that reference
`${context.design_tokens_context}` unconditionally never fail to interpolate.

`cmd_resume` (`scripts/little_loops/cli/loop/lifecycle.py`) does not carry
the same opt-out branch — it only backfills `design_tokens_context` when
absent from the restored checkpoint context, so a resumed run continues
whatever choice `cmd_run` made when the run was first started. No change was
needed there.

## Files Changed

- `scripts/little_loops/cli/loop/run.py` — added the `use_design_tokens` gate
  in `cmd_run` (12 lines).
- `docs/reference/CONFIGURATION.md` — documented the opt-out under the
  `design_tokens` config section.
- `docs/generalized-fsm-loop.md` — documented `use_design_tokens` alongside
  the `design_tokens_context` runner-injected context variable.
- `scripts/tests/test_cli_loop_lifecycle.py` — added
  `TestCmdRunDesignTokensOptOut`: default-loads-tokens case, YAML
  `use_design_tokens: false` case, and a parametrized case covering all
  accepted falsy string values from `--context`.

## Program Design

### Types

- N/A — no new dataclass or schema field; `use_design_tokens` is a plain
  `fsm.context` entry (`str | bool`), like `max_steps` or `input_hash`.

### Signatures

No new functions. The gate is inline in `cmd_run` in
`scripts/little_loops/cli/loop/run.py`, reading and coercing an existing
dict entry:

- `fsm.context.get(key: str, default: bool) -> bool | str`
  - `_use_tokens = fsm.context.get("use_design_tokens", True)`; if the
    result is a `str` (from `--context use_design_tokens=VALUE`), coerce via
    `_use_tokens.strip().lower() not in ("", "0", "false", "no", "off")`.

### Call Path

`cmd_run` → (existing) `--context` / YAML `context:` merge into
`fsm.context` → new `use_design_tokens` read/coerce → conditionally calls
existing `load_design_tokens(_config)` / `render_as_prompt_context(_tokens)`
→ sets `fsm.context["design_tokens_context"]`.

Read the flag straight out of `fsm.context` (already merged from YAML
`context:` and `--context` overrides by the time this line runs) rather than
adding a new schema field — `use_design_tokens` is a plain context variable,
not a structural loop-config knob, so it needs no `FSMLoop`/JSON-schema
changes, no validation entry, and no CLI flag parity work. Truthy/falsy
string coercion mirrors the convention already used for other context
booleans passed via `--context KEY=VALUE` (raw strings).

## Scope Boundaries

- **In scope**: the opt-out gate in `cmd_run`, docs, and a regression test.
- **Out of scope**: mirroring the gate into `cmd_resume` (a resumed run
  inherits whatever choice `cmd_run` made when the run started — see above);
  a project-level default other than the existing project-wide
  `design_tokens` on/off setting; per-state (as opposed to per-loop) opt-out
  granularity.

## Impact

- **Priority**: P3 — unblocks running non-visual loops in a project that also
  has design tokens enabled project-wide, without a global toggle-off.
- **Effort**: Small — 12-line gate, no schema/validation changes.
- **Risk**: Low — additive, defaults preserve existing behavior for every
  loop that doesn't set `use_design_tokens`.
- **Breaking Change**: No.

## Acceptance Criteria

- [x] A loop with no `use_design_tokens` key continues to get
      `design_tokens_context` injected when design tokens are enabled
      project-wide (backward compatible) [hard]
- [x] `context.use_design_tokens: false` (YAML) skips `load_design_tokens`
      entirely [hard]
- [x] `--context use_design_tokens=<falsy string>` (case-insensitive
      `false`/`no`/`off`/`0`/empty) is honored the same as the YAML boolean
      [hard]
- [x] `context.design_tokens_context` is always set (`""` when opted out) so
      prompts referencing it unconditionally never fail to interpolate [hard]
- [x] `python -m pytest scripts/tests/` exits 0 [hard]
- [x] Documented in `CONFIGURATION.md` and `generalized-fsm-loop.md`

## Resolution

Implemented directly in `scripts/little_loops/cli/loop/run.py`
(commit `c55614ed`, "feat(loops): add per-loop design-token opt-out
control"). This issue backfills the completed-issue record, tests, and docs
for that change.

## Session Log
- `hook:posttooluse-status-done` - 2026-08-08T04:13:20 - `f9fbc2bf-6078-4046-9c09-ebcd58791fed.jsonl`
- manual - 2026-08-07T22:53:54Z

---

## Status

**Current Status**: done
