---
id: ENH-2661
title: Add learning state badge glyph to _ACTION_TYPE_BADGES
status: done
priority: P3
type: ENH
discovered_by: capture-issue
discovered_date: 2026-07-16
captured_at: 2026-07-16 00:00:00+00:00
completed_at: '2026-07-17T01:58:41Z'
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 19
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2661: Add learning state badge glyph to _ACTION_TYPE_BADGES

## Summary

`_ACTION_TYPE_BADGES` in `scripts/little_loops/cli/loop/layout.py:108` currently maps four FSM state `action_type` values to Unicode glyphs: `prompt` (✦), `slash_command` (/━►), `shell` (❯_), and `mcp_tool` (⚡). The FSM engine already supports a `type: learning` state kind (FEAT-1283) which executes the `ll:explore-api` skill to prove API assumptions before progressing, but learning states share no badge of their own — they fall through to the `shell` fallback glyph (❯_) because no `action_type` matches and no `loop:` field is set.

Add a fifth entry, `"learning": "⚗"`, mapping to U+2697 ALEMBIC. The alembic glyph evokes distillation/proof-of-substance, which fits the learning state's purpose (prove the substance of an external behavior before relying on it).

## Current Behavior

A learning state (`type: learning` per `scripts/little_loops/loops/lib/common.yaml:84`, owned by FEAT-1283) renders with the shell fallback glyph ❯_ in `ll-loop show` diagrams and FSM visualizations because:
1. `_get_state_badge()` (`layout.py`) keys off `state.action_type` and `state.loop`
2. Learning states set `type: learning`, not `action_type: learning` or `loop: ...`
3. Neither `_ACTION_TYPE_BADGES` nor any other lookup recognizes `learning`

The mismatch means learning states are visually indistinguishable from ordinary shell states in clean preset diagrams.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of `_get_state_badge()` (`layout.py:295–310`) and `_box_kind_color()` (`layout.py:136–158`):_

The Current Behavior section overstates the present-day rendering. The exact behavior of `_get_state_badge()` for a canonical `type: learning` state (e.g. the `prove:` state in `scripts/little_loops/loops/ready-to-implement-gate.yaml` — `type: learning`, no `action_type`, no `action`, no `loop`, no `route`) is:

1. `state is not None` → continue past line 297
2. `state.loop is None` → fall through line 302
3. `state.action_type` is `None` (falsy) → fall through line 304
4. `state.action is None` (falsy) → fall through line 306
5. `state.route is None` → fall through line 308
6. Return `""` (line 310) — **empty string, no badge**

The shell-glyph (❯_) fallback at line 306–307 only fires when the learning state ALSO has `action:` set, which is uncommon. The dominant visual symptom is therefore **no badge at all** in the diagram, not a shell-looking badge — operators see a `type: learning` box with no glyph at all and no kind color (the parallel `_box_kind_color()` returns `None` at line 158 for the same state shape).

Only a small subset of learning states that mix in `action:` (uncommon; the FEAT-1283 design separates learning from action execution) actually render with the ❯_ shell glyph today.

The FSM loader does NOT copy `type: learning` into `action_type: "learning"` at parse time — confirmed by full search of `scripts/little_loops/fsm/` (schema.py, executor.py, fragments.py, validation.py). The two fields are independent on `StateConfig` (`schema.py:534` for `action_type`, `schema.py:568` for `type`).

## Expected Behavior

- `type: learning` states render with ⚗ (U+2697 ALEMBIC) in the FSM diagram's top border, alongside the existing prompt/slash_command/shell/mcp_tool badges.
- The lookup resolution for learning states goes through the badge helper so existing `_get_state_badge()` precedence rules (sub-loop wins over action_type) continue to apply if a learning state ever embeds a sub-loop.
- `_get_state_badge()` for a learning state returns the alembic glyph (or a state-shape-equivalent fallback if a future refactor moves the lookup onto `state.type` instead of `state.action_type`).

## Motivation

Diagrams are the primary navigation surface for `ll-loop show` and the iterative loop-tuning workflow. Operators tuning a multi-state harness need to *spot* learning states at a glance — a state that proves an assumption is semantically distinct from a state that executes a shell command, even when both look the same on screen. A dedicated glyph:

- Makes harness structure self-documenting (a glance at the diagram conveys "this state will probe an external API")
- Distinguishes learning states from ordinary shell commands so reviewers don't second-guess why a `type: learning` block has a shell-looking badge
- Follows the established glyph-per-action-type pattern that already gives prompt/slash_command/shell/mcp_tool distinct visual identities

The alembic glyph is semantically apt: alchemy's alembic distills raw material into proven substance, mirroring the learning state's "prove the API behaves as claimed" role.

## Proposed Solution

In `scripts/little_loops/cli/loop/layout.py:108`, extend the dict:

```python
_ACTION_TYPE_BADGES: dict[str, str] = {
    "prompt": "✦",         # ✦
    "slash_command": "/━►",  # /━►
    "shell": "❯_",         # ❯_
    "mcp_tool": "⚡",       # ⚡
    "learning": "⚗",       # ⚗ — alembic (U+2697)
}
```

This requires plumbing `type: learning` through to the badge lookup. Current `_get_state_badge()` resolves via `state.action_type`; the helper must also consult `state.type == "learning"` (or the FSM loader must copy `type: learning` into `action_type: "learning"` at parse time — the latter keeps the renderer ignorant of state kinds).

**Recommended approach**: extend `_get_state_badge()` to fall through to `_ACTION_TYPE_BADGES["learning"]` when `state.type == "learning"` and no action/loop is set. Keeps the badge dict as the single source of visual mapping and avoids coupling the renderer to FSM-loader internals.

`_ACTION_TYPE_KIND_COLORS` (`layout.py:125`) should also gain a `"learning"` entry so the diagram color-codes learning states distinctly from shell (gray) and prompt (magenta). A muted cyan (`36`) would match the "distillation/proof" theme without competing with the active-state highlight.

### Codebase Research Findings — Implementation Approach Alternatives

_Added by `/ll:refine-issue` — formatted as discrete Option blocks to enable decision-point detection:_

The original prose above already identifies two viable resolutions; this addendum formats them as bold-label blocks for decision routing.

**Option A**: Extend `_get_state_badge()` (and the parallel `_box_kind_color()`) to consult `state.type` as a new branch after the sub-loop check. The renderer gains awareness of one more shape dimension (`state.type`) but keeps the dict as the single source of visual mapping. No FSM-loader changes; no schema changes. Future kind-scoped glyphs (e.g. a hypothetical `type: convergence`) can plug in the same way by adding to the dict and the helper branch.

> **Selected:** Option A — established codebase pattern (`fsm/executor.py:1218`, `fsm/validation.py:710` already consume `state.type == "learning"` directly); `_box_kind_color()`'s docstring explicitly requires mirroring `_get_state_badge()`'s chain, so the type-branch is added to both helpers in lockstep. Reuse score 3/3; no new infrastructure; no schema or loader changes.

**Option B**: Have the FSM loader (`scripts/little_loops/fsm/schema.py:from_dict`) copy `type: learning` into `action_type: "learning"` at parse time. Keeps `_get_state_badge()` ignorant of `state.type` — the existing `effective.get(state.action_type, ...)` lookup at `layout.py:305` resolves naturally. Couples loader logic to a specific renderer's key set; future kinds would each need loader-side copy logic. The kind-color helper would need the same change unless it also reads `action_type`.

**Recommended**: Option A — `_get_state_badge()` already has precedence semantics for `state.loop` and `state.action_type`; consulting `state.type` next to those is a natural extension and avoids spreading key-copy logic across the loader/renderer boundary. Sibling precedent: `fsm/executor.py:_execute_state()` (`scripts/little_loops/fsm/executor.py:1206–1219`) already reads `state.type == "learning"` alongside `state.loop is not None` to dispatch — extending the same pattern into the diagram layer is consistent with the executor's design.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-16.

**Selected**: Option A — Extend `_get_state_badge()` (and the parallel `_box_kind_color()`) to consult `state.type` as a new branch after the sub-loop check.

**Reasoning**: The codebase is already designed for this shape of dispatch — `StateConfig.type` is exposed at `fsm/schema.py:568`, consumed directly by `fsm/executor.py:1218` and `fsm/validation.py:710`, and the `_box_kind_color()` docstring (`layout.py:139-147`) explicitly requires mirroring `_get_state_badge()`'s precedence chain. Adding `state.type == "learning"` as a fifth tier in both helpers plugs into an existing field without restructuring. Option B would have required new loader-side normalization (`StateConfig.from_dict` has no precedent for cross-field copy; `test_fsm_schema.py:2868` asserts `type` and `action_type` are independent), and would silently change behavior at executor dispatch (`executor.py:1905-1911` interprets unknown action_types as prompts), validator gates (`validation.py:1594,1672,1776`), and `to_dict()` roundtrip output (the loader-injected `action_type: "learning"` would emit a fabricated key on the source-of-truth loop file).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Renderer consults `state.type` | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B — Loader copies `type` → `action_type` | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: Reuses `state.type` (`schema.py:568`) and the existing precedence chain in `_get_state_badge()` (`layout.py:295-310`) and `_box_kind_color()` (`layout.py:136-158`). Test infrastructure ready: `_state()` helper in `test_cli_loop_layout.py:100-147` already passes `type=None` and `learning=None` defaults; the `_ACTION_TYPE_BADGES.items()` loop in `test_ll_loop_display.py:2988` auto-covers a new key. Precedent for the same shape: `executor.py:1218` and `validation.py:710`. Reuse score 3/3.
- **Option B**: No precedent for loader-side cross-field copy in `scripts/little_loops/fsm/`; `StateConfig.from_dict` (`schema.py:701-732`) does direct passthrough only. Existing test `test_fsm_schema.py:2868-2870` asserts `type` and `action_type` are independent fields — Option B would silently break this invariant. Roundtrip via `to_dict()` (`schema.py:580-581`) would emit a fabricated `action_type: "learning"` key into the loop YAML source. Reuse score 0/3.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — add `"learning": "⚗"` to `_ACTION_TYPE_BADGES`; add a matching entry to `_ACTION_TYPE_KIND_COLORS`; extend `_get_state_badge()` to consult `state.type` for the learning fallback.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/layout.py:299` — `{**_ACTION_TYPE_BADGES, **(badges or {})}` merge site; the new key flows through unchanged.
- Any renderer that iterates `_ACTION_TYPE_BADGES.items()` for legend output (if present) gains the new entry automatically.

### Similar Patterns
- The four existing keys are all action-type-scoped (`state.action_type` lookup). The learning state is the first kind-scoped lookup (resolved via `state.type` rather than `state.action_type`). This sets the pattern for future kind-scoped glyphs (e.g., a hypothetical `type: convergence` state).

### Tests
- `scripts/tests/test_ll_loop_display.py:2970` (`test_badge_constants_match_spec`) — add `assert _ACTION_TYPE_BADGES["learning"] == "⚗"  # ⚗`.
- `scripts/tests/test_ll_loop_display.py:2986` (`test_get_state_badge_action_types`) — extend the loop to assert a `StateConfig(type="learning")` (or whichever field the new lookup consults) returns the alembic glyph.
- Consider a dedicated `test_get_state_badge_learning_state` to document the type-vs-action_type resolution rule.

### Documentation
- `docs/reference/API.md` — if it documents `_ACTION_TYPE_BADGES` directly, add the new entry.
- `thoughts/` notes on the clean preset diagram aesthetic — mention the new glyph if it shows example diagrams.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — additional integration points and the kind-color/config surface that the original map did not surface:_

**Additional Files to Modify** (above and beyond the single-file claim):

- `scripts/little_loops/cli/loop/layout.py` — also extend `_box_kind_color()` (`layout.py:136–158`) to consult `state.type == "learning"` so the kind-color lookup mirrors the badge lookup. The two helpers currently share an identical precedence chain (`loop` → `action_type` → `action` → `terminal`); adding `type` to one without the other produces mismatched visual signals (badge ⚗, no kind color). This is required for consistency, not optional.
- `scripts/little_loops/config/features.py` — `LoopsGlyphsConfig` (line 562) currently exposes only `prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route`, `parallel` fields. Adding a `learning: str | None = None` field to the dataclass plus a corresponding entry in `to_dict()` (line 586) allows user override via `loops.glyphs.learning` in `.ll/ll-config.json`. Without this, the new constant is hard-coded — inconsistent with the precedent set by `glyphs.parallel`.
- `config-schema.json` — the `glyphs` block (around line 941) declares the existing keys with `additionalProperties: false`. A `learning` property must be added so user overrides validate; otherwise the JSON schema rejects `loops.glyphs.learning` even though the runtime would silently ignore it.
- `docs/reference/CONFIGURATION.md` — lines 859–865 list each `glyphs.*` config key with description. Add a row for `glyphs.learning`. The override-example JSON at lines 891–899 should also gain a `learning` line for parity with the other examples.
- `scripts/tests/test_config_schema.py` — `test_loops_glyphs_parallel_in_schema` (line 173) is the pattern to copy for a new `test_loops_glyphs_learning_in_schema` asserting the `learning` property is declared.
- `scripts/tests/test_config.py` — `TestLoopsGlyphsConfig` (line 2483) has per-field defaults tests at lines 2543–2563; add a parallel test for the new `learning` default and the override-from-config path.

**Dependent Files — extended**:

- `scripts/little_loops/cli/loop/info.py:26` — re-exports badge constants from `layout.py`; the new `learning` key flows through unchanged.
- `scripts/little_loops/config/core.py:653` — `BRConfig` reads `loops.glyphs.to_dict()`; the new key flows into `_get_state_badge(badges=...)` automatically once `LoopsGlyphsConfig` exposes it.
- `scripts/little_loops/issues/clusters.py:451` — out-of-package but imports `_draw_box` from `layout.py`; not affected by the badge dict change.

**Tests — extended** (in addition to the existing list):

- `scripts/tests/test_cli_loop_layout.py` — `TestBoxKindColor` class (lines 92–208) has the per-kind-color test pattern (`test_<kind>_maps_to_<color>`); add `test_learning_maps_to_<chosen_color>` matching the `_ACTION_TYPE_KIND_COLORS["learning"]` value (suggested `"36"` muted cyan per issue). Construct a learning state via `self._state(type="learning")` — the `_state` helper already includes `"type"` and `"learning"` keys in its defaults (lines 100–147 of the test file).
- `scripts/tests/test_snapshot_loop_layout.py` — if any existing snapshot uses a `type: learning` state, the rendered diagram will change (from no badge to ⚗). Snapshot files will need regeneration. Confirm during implementation whether any snapshot fixture exercises the learning-state shape.
- `scripts/tests/test_ll_loop_display.py:3002–3005` (`test_sub_loop_badge_takes_precedence_over_action_type`) — no change required, but the inverse precedence test for learning (`type="learning"` loses to `action_type="shell"`? wins? — depends on chosen implementation) is worth adding if Option A's branch order matters.

**Similar Patterns — extended**:

- The `_PARALLEL_BADGE` addition (FEAT-1225, sibling issue `.issues/features/P2-FEAT-1225-parallel-display-badge-test.md`) is the closest precedent: it added a `parallel` key to `_ACTION_TYPE_BADGES`, extended both `_get_state_badge()` and `_box_kind_color()`, added the `_PARALLEL_KIND_COLOR` to `_ACTION_TYPE_KIND_COLORS`, plumbed the new field through `LoopsGlyphsConfig` (`features.py`), updated `config-schema.json`, added `CONFIGURATION.md` documentation, and added per-key tests to both `test_ll_loop_display.py` and `test_cli_loop_layout.py`. **ENH-2661 should mirror this exact pattern** (modulo the kind-color and config-schema edits, which FEAT-1225 already established as standard for badge additions).
- The `_ACTION_TYPE_KIND_COLORS` lookup already has `additionalProperties: false`-equivalent semantics: an unknown key returns `None` (line 153), so adding a new key with no consumers is harmless.

**Configuration — corrected** (the original `N/A` was incomplete):

- This is NOT configuration-free if user override parity with `glyphs.parallel` is desired. To match the established ENH-904 / FEAT-1225 precedent, add `learning: str | None = None` to `LoopsGlyphsConfig` (`features.py:562`), an entry in `to_dict()` (line 586), a `learning` property in `config-schema.json`, a row in `docs/reference/CONFIGURATION.md:859–865`, and corresponding tests in `test_config.py` / `test_config_schema.py`. Skipping this leaves the new badge hard-coded — acceptable for an XS-effort change but inconsistent with the glyphs override surface.

### Wiring Pass Findings

_Wiring pass added by `/ll:wire-issue` (3-agent trace + direct grep confirmation). All items below are net-new relative to the refine pass above._

**Path correction (blocking factual error):**
- The config schema is at **`scripts/little_loops/config-schema.json`**, NOT bare `config-schema.json` at the repo root — that path does not exist (`find` confirms only `scripts/little_loops/config-schema.json`). The CLAUDE.md "Config schema" pointer and all references in this issue (Files to Modify, step 9) should use the fully-qualified path. The `glyphs` block is at `scripts/little_loops/config-schema.json:941` with `additionalProperties: false` (verified) — so a `learning` property MUST be added there or the schema rejects `loops.glyphs.learning`.

**Test that WILL BREAK (not previously flagged by line):**
- `scripts/tests/test_config.py:2513–2527` (`TestLoopsGlyphsConfig.test_to_dict_returns_all_keys`) — asserts `set(d.keys()) == {"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route", "parallel"}` (a 7-key **set-equality**, not a subset). Adding `"learning"` to `LoopsGlyphsConfig.to_dict()` breaks this test unless the set literal is updated to include `"learning"`. The refine pass references `TestLoopsGlyphsConfig` (line 2483) generically but never called out this specific breaking assertion — FEAT-1227 (the parallel-glyph precedent) explicitly listed the analogous set-literal as a "will break" line. [Agent 2 + Agent 3 finding — both converged]

**Test class missing from the map entirely:**
- `scripts/tests/test_config.py:2540` (`TestBRConfigLoopsGlyphs`) — separate from `TestLoopsGlyphsConfig` (2483), this class exercises the full-`BRConfig` override path: `test_loops_glyphs_defaults_when_absent` (2543) and `test_loops_glyphs_override_from_config` (2550). Extend both to cover `learning` (default `assert config.loops.glyphs.learning == "⚗"`; add a `learning` key to the override sample). The refine pass listed only the sibling `TestLoopsGlyphsConfig`; this class was omitted. [Agent 3 finding]

**Render-level (integration) color test missing:**
- `scripts/tests/test_cli_loop_layout.py:262` (`TestDiagramKindColors`) — the issue lists the *unit*-level `TestBoxKindColor` but not this *integration*-level class that asserts kind colors appear in the rendered `_render_fsm_diagram()` output. Add a `test_learning_state_color_in_diagram` mirroring the shell-kind assertion (~line 304) so the ⚗ kind-color is validated end-to-end, not just in the `_box_kind_color()` unit. [Agent 3 finding]

**Correctness sharpening on an existing test item:**
- The issue's item to "extend the `_ACTION_TYPE_BADGES.items()` loop in `test_get_state_badge_action_types` (`test_ll_loop_display.py:2986`)" is INSUFFICIENT on its own under the selected Option A. That loop constructs `StateConfig(action_type=<key>)`, but Option A dispatches learning via `state.type == "learning"`, not `state.action_type`. So the iteration will not exercise the learning branch. A **dedicated** `test_get_state_badge_learning` constructing `StateConfig(type="learning")` (modeled after `test_get_state_badge_sub_loop`, ~line 2997) is REQUIRED, not merely "consider"-optional as line 133 currently phrases it. [Agent 3 finding — resolves the type-vs-action_type dispatch gap]

**De-risked (open question in step 12 now answered):**
- No snapshot fixture uses a `type: learning` state — `scripts/tests/__snapshots__/test_snapshot_loop_layout.ambr` has 0 matches for `learning`/`⚗`, and the four snapshot tests build FSMs inline (no `type: learning`). The existing `scripts/tests/fixtures/fsm/learning-state-loop.yaml` is consumed only by `test_learning_state.py` (executor behavior), not by any layout snapshot. **Step 12's "regenerate if fixtures use `type: learning`" resolves to: no regeneration needed.** An opportunistic new snapshot test using that fixture is available if desired but not required. [Agent 2 + Agent 3 finding]

**Verified flows-through-unchanged (checked, no edit needed — do not chase these):**
- `docs/reference/API.md:536` documents `glyphs: LoopsGlyphsConfig` as an opaque field; it does NOT enumerate glyph keys (0 matches for `_ACTION_TYPE_KIND_COLORS` or per-key glyphs), so no doc edit there.
- `scripts/little_loops/config/core.py:653` (`BRConfig.to_dict()`) reads `self._loops.glyphs.to_dict()` wholesale — the new key flows through once `LoopsGlyphsConfig.to_dict()` includes it.
- `scripts/little_loops/config/__init__.py:60,100` re-exports `LoopsGlyphsConfig` (class-level `__all__`) — transparent, no per-field change.
- `scripts/little_loops/fsm/executor.py:1169,1218` and `fsm/validation.py:710` read `state.type == "learning"` but assert no badge/color strings — no coupling.
- No legend/help-text renderer iterates `_ACTION_TYPE_BADGES.items()` for user output; no `ll-verify-*` script enumerates glyph fields.

## Implementation Steps

1. Add `"learning": "⚗"` to `_ACTION_TYPE_BADGES` in `layout.py`.
2. Add `"learning"` to `_ACTION_TYPE_KIND_COLORS` (suggested: `"36"` muted cyan).
3. Extend `_get_state_badge()` to resolve a learning state via `state.type` when no `action_type`/`action`/`loop` matches.
4. Add the three test assertions in `test_ll_loop_display.py` listed above.
5. Run `python -m pytest scripts/tests/test_ll_loop_display.py -k badge` and visually confirm `ll-loop show` on a learning-state-bearing loop renders ⚗.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps for the kind-color mirror, config wiring, and additional test files that the original 5-step list omitted:_

6. **Mirror in `_box_kind_color()`** (`layout.py:136–158`) — add a parallel `state.type == "learning"` branch that returns `_ACTION_TYPE_KIND_COLORS["learning"]`. Place it after the `state.loop` check (sub-loop wins) and before the `state.action_type` lookup, mirroring `_get_state_badge()`'s precedence.
7. **Add a kind-color test in `test_cli_loop_layout.py:TestBoxKindColor`** — model after `test_mcp_tool_maps_to_yellow` (line ~190). Use `self._state(type="learning")` (the helper already exposes `type` in its defaults, lines 100–147).
8. **Wire `LoopsGlyphsConfig.learning`** (`features.py:562`) — add `learning: str | None = None` to the dataclass and an entry in `to_dict()` (line 586). Default is `None` so existing `to_dict()` callers that read keys by name remain unaffected; `layout.py:_get_state_badge()` falls back to the built-in constant when the override is `None`.
9. **Update `config-schema.json`** — declare a `learning` property under the `glyphs` block (around line 941) so user overrides validate. Mirror the structure of the existing `parallel` property (added by FEAT-1227).
10. **Update `docs/reference/CONFIGURATION.md:859–865`** — add a row for `glyphs.learning` and extend the example JSON at lines 891–899 to include a `learning` line.
11. **Add config tests** — `test_loops_glyphs_learning_in_schema` (mirror `test_loops_glyphs_parallel_in_schema` at `test_config_schema.py:173`) and a per-field test in `TestLoopsGlyphsConfig` (`test_config.py:2483`) for the default and override-from-config paths.
12. **Visual / snapshot verification** — run `python -m pytest scripts/tests/test_snapshot_loop_layout.py` to confirm no existing snapshots regress. If `test_snapshot_loop_layout.py` fixtures use `type: learning`, regenerate via `pytest --snapshot-update`.
13. **End-to-end verification on `ready-to-implement-gate`** — run `ll-loop show scripts/little_loops/loops/ready-to-implement-gate.yaml` and confirm the `prove:` state renders with ⚗ in the top border (matches the integration in `loops/ready-to-implement-gate.yaml`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. **Use the correct schema path** — all edits to the JSON schema target `scripts/little_loops/config-schema.json` (line 941 `glyphs` block, `additionalProperties: false`), NOT a bare root-level `config-schema.json` (which does not exist).
15. **Update the breaking set-literal** — in `scripts/tests/test_config.py:2513–2527` (`test_to_dict_returns_all_keys`), add `"learning"` to the `set(d.keys()) == {...}` assertion. This test WILL FAIL otherwise (set-equality, not subset).
16. **Extend `TestBRConfigLoopsGlyphs`** (`test_config.py:2540`) — add `learning` coverage to `test_loops_glyphs_defaults_when_absent` (2543, assert default `"⚗"`) and `test_loops_glyphs_override_from_config` (2550, add a `learning` override key).
17. **Add a dedicated type-dispatch badge test** — in `test_ll_loop_display.py`, write `test_get_state_badge_learning` constructing `StateConfig(type="learning")` and asserting the ⚗ glyph (model after `test_get_state_badge_sub_loop`, ~line 2997). The existing `_ACTION_TYPE_BADGES.items()` loop (step 4) dispatches by `action_type` and will NOT exercise the `state.type` branch — this dedicated test is required, not optional.
18. **Add a render-level kind-color test** — in `test_cli_loop_layout.py:262` (`TestDiagramKindColors`), add `test_learning_state_color_in_diagram` asserting the learning kind-color appears in `_render_fsm_diagram()` output (mirror the shell-kind assertion ~line 304), complementing the unit-level `TestBoxKindColor` test.
19. **Skip snapshot regeneration** — wiring confirmed no snapshot fixture uses `type: learning` (0 matches in `test_snapshot_loop_layout.ambr`); step 12's conditional regeneration is a no-op. Optionally add a new snapshot test using `scripts/tests/fixtures/fsm/learning-state-loop.yaml`.

## Impact

- **Priority**: P3. Visual polish; doesn't affect correctness or correctness-related debugging. Doesn't block any other feature.
- **Effort**: XS. ~5 lines of code, ~10 lines of test additions. Single-file change plus the lookup-helper extension.
- **Risk**: Low. The new key is additive; existing renderers ignore unknown keys or fall through to their existing default. The kind-color addition follows the same fallback semantics already established for `mcp_tool`.
- **Backwards compatibility**: Fully backwards compatible. Existing diagrams that don't use learning states are byte-identical; diagrams that *do* use learning states currently display ❯_ and will switch to ⚗ — a visible-but-intentional change for the states that warranted their own kind in the first place.

## Resolution

Implemented via Option A (renderer consults `state.type`), mirroring the FEAT-1225
parallel-glyph precedent exactly:

- `layout.py` — added `"learning": "⚗"` (U+2697 ALEMBIC) to `_ACTION_TYPE_BADGES` and
  `"learning": "36"` (muted cyan) to `_ACTION_TYPE_KIND_COLORS`; added a
  `state.type == "learning"` tier to both `_get_state_badge()` and `_box_kind_color()`,
  placed after the sub-loop check so a learning state that embeds a sub-loop still
  shows the sub-loop badge/color. Updated the `_box_kind_color()` docstring precedence list.
- `config/features.py` — added `learning: str = "⚗"` to `LoopsGlyphsConfig` with
  matching `from_dict`/`to_dict` entries for `loops.glyphs.learning` overrides.
- `config-schema.json` — declared the `learning` glyph property (the block is
  `additionalProperties: false`).
- `docs/reference/CONFIGURATION.md` — added the `glyphs.learning` row.
- Tests: dedicated `test_get_state_badge_learning` + precedence test in
  `test_ll_loop_display.py`; `test_learning_maps_to_cyan` / `test_learning_yields_to_sub_loop`
  in `TestBoxKindColor` and `test_learning_state_color_in_diagram` in `TestDiagramKindColors`
  (`test_cli_loop_layout.py`); updated the `to_dict` set-literal and default/override
  assertions in `test_config.py`; `test_loops_glyphs_learning_in_schema` in
  `test_config_schema.py`.

Verified end-to-end: `ll-loop show scripts/little_loops/loops/ready-to-implement-gate.yaml`
renders the `prove:` learning state with a muted-cyan `⚗` badge. Full suite: 15115 passed,
36 skipped. No snapshot regeneration needed (no fixture uses `type: learning`).

## Session Log
- `/ll:manage-issue` - 2026-07-17T01:58:02Z - `c2510e44-fcba-45e4-8ed1-398080b6f309.jsonl`
- `/ll:ready-issue` - 2026-07-17T01:49:30 - `b9cc31f0-c0c6-4354-9691-ce16b94a8abd.jsonl`
- `/ll:confidence-check` - 2026-07-16T23:40:00 - `7e729572-5a2d-4041-9bd6-09fdc31243af.jsonl`
- `/ll:wire-issue` - 2026-07-16T23:28:31 - `662c2d02-abef-4d10-9ba7-e1ae1ed1edc9.jsonl`
- `/ll:decide-issue` - 2026-07-16T23:12:42 - `2b0ca1df-7c62-41b3-bca6-f14f3a99fe12.jsonl`
- `/ll:refine-issue` - 2026-07-16T23:09:37 - `6d26c8e2-beb5-4509-b48c-5e42b98eb8bd.jsonl`
- `/ll:capture-issue` - 2026-07-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49310899-7033-4907-9485-79b5c5414ca0.jsonl`

## Status

Done.