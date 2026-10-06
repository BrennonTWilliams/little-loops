---
id: BUG-3757
title: 'Confidence-check docs state a stale 75 outcome_threshold default (real default is 65)'
type: BUG
priority: P2
status: open
discovered_date: '2026-10-05'
parent: BUG-3754
labels:
- confidence-check
- docs
- scoring
---

# BUG-3757: Confidence-check docs state a stale 75 outcome_threshold default (real default is 65)

## Summary

`skills/confidence-check/SKILL.md` (~`:424`) and `rubric.md` (~`:360-361`) say `outcome_threshold` defaults to 75, so the unproven-mechanism hard cap reads as 74. The real default is 65 (`config/automation.py:160`, `config-schema.json:534-539`), so the cap is 64. The 65 gate stays where it is; only the text (and sibling stale defaults) change, and a test ties the documented number to the schema.

## Parent Issue

Decomposed from BUG-3754: Confidence-check score contract drift: rn-remediate reads score polarity inverted, skill text states a stale 75 outcome threshold. The polarity half lives in the sibling child (BUG-3756).

## Current Behavior

- `SKILL.md:424` and `rubric.md:360-361` document default 75 / cap 74, and the `.gemini/`, `.kimi-code/`, `.qwen/` skill mirrors carry the same text.
- Sibling stale values: `scripts/little_loops/cli/issues/set_flags.py` (`_DEFAULT_OUTCOME_THRESHOLD = 75` at `:34`, `FLAG_RULES` `:239`, `_resolve_outcome_threshold` docstring/fallbacks `:243`, `:252`, `:255`, `apply_flags_from_notes` branch `:297`); comment `rn-remediate.yaml:206` ("outcome >= 75"); `test_rn_remediate.py:661` docstring; `docs/reference/CLI.md:1587` (75) and `:1844` (`70`).
- No test compares a number in `skills/**/*.md` or `docs/` to the schema.

## Expected Behavior

- `SKILL.md` and `rubric.md` state default 65 and cap 64; mirrors regenerate cleanly.
- A test ties the documented default to `config-schema.json`.
- Sibling stale defaults are fixed or explicitly left (rule-syntax examples at `policy-router.yaml:184`, `POLICY_ROUTER_GUIDE.md:4,73` are not default claims and stay).

## Implementation Steps

1. Edit `SKILL.md:424` in place (file is 499/500 lines — no net added line) and `rubric.md:360-361` to 65 / 64. Regenerate mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply` (`test_skill_mirrors_carry_companions` requires byte-identical mirror `rubric.md`). Avoid `scripts/tests/…` / `scripts/little_loops/…` citations in skill/doc text (`test_docs_audience_gate.py`).
2. Add `test_documented_outcome_threshold_matches_schema` to `scripts/tests/test_confidence_check_skill.py` using `little_loops.init.core.schema_default("commands.confidence_gate.outcome_threshold")` and the existing `_cap_section_text` section slice; keep the existing Phase 2b/4.5 cap-text assertions green.
3. Decide `set_flags.py` scope (code default, not docs). If in: move `:34`, `:239`, `:243`, `:252`, `:255`, `:297` together, add a 65–74 boundary case (e.g. `outcome_confidence=70`) to `test_set_flags_cli.py` and a `_DEFAULT_OUTCOME_THRESHOLD == schema_default(...)` assertion.
4. Fix the `rn-remediate.yaml:206` comment and `test_rn_remediate.py:661` docstring (prose only; coordinate with BUG-3756 if both edit the YAML). Decide `docs/reference/CLI.md:1587` and fix `:1844` (`70` → 65).
5. Run `python -m pytest scripts/tests/test_confidence_check_skill.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_docs_audience_gate.py scripts/tests/test_set_flags_cli.py -v`, then the full `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 - documentation drift (the actual gate is already 65); split from P0 parent because it has no runtime effect
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Acceptance Criteria

SKILL.md and rubric.md state default 65 and cap 64, a test ties the documented default to `config-schema.json`, mirror and docs-audience gates pass, and the `set_flags.py` / `CLI.md` scope decisions are recorded.

## Status

**Open** | Created: 2026-10-06 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-10-06T06:49:39 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
