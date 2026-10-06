---
id: BUG-3757
title: 'Confidence-check outcome threshold drifts in docs and set-flags configuration'
type: BUG
priority: P2
status: open
discovered_date: '2026-10-05'
parent: BUG-3754
labels:
- confidence-check
- docs
- scoring
- configuration
relates_to:
- BUG-3756
- ENH-3742
---

# BUG-3757: Confidence-check outcome threshold drifts in docs and set-flags configuration

## Summary

The confidence gate defaults to outcome 65, but confidence-check documentation and `set-flags`' fallback still use 75. In addition, `set-flags` re-reads the base JSON instead of using the loaded configuration, so local threshold overrides are ignored. Align the flag evaluator and the documentation with the existing configuration contract; keep the gate's default at 65 and the unproven-mechanism cap relative to the effective threshold.

## Parent Issue

Decomposed from BUG-3754. BUG-3756 owns rn-remediate score polarity and routing. This child owns threshold documentation and the related runtime configuration drift; it is no longer a docs-only change.

## Current Behavior

- `skills/confidence-check/SKILL.md:424` says the Phase 4.5 outcome-risk threshold defaults to 75. `skills/confidence-check/rubric.md:360` documents default 75 / cap 74. Tracked `.gemini/`, `.kimi-code/`, `.qwen/` mirrors carry the same text.
- `scripts/little_loops/cli/issues/set_flags.py` sets `_DEFAULT_OUTCOME_THRESHOLD = 75`, constructs exported `FLAG_RULES` with it, and uses it in `_resolve_outcome_threshold()` when the config key/file cannot be read. A project omitting the key therefore has a loaded gate of 65 but a flag-evaluation threshold of 75.
- `_resolve_outcome_threshold()` reads `.ll/ll-config.json` directly. With base outcome 65 and `.ll/ll.local.md` overriding it to 75, `BRConfig` reports 75 while `set-flags` still resolves 65.
- `docs/reference/CLI.md:1844` says `next-action --outcome-threshold` defaults to 70; the CLI fallback is 65. The rn-remediate readiness comment and an associated test docstring also retain the old 85/75 pair.
- `docs/reference/CLI.md:1587` is a custom policy-table example using 75, not a default claim. The examples in the policy-router guide and library have the same status and should remain valid examples.

## Steps to Reproduce

1. In a temporary project, omit `commands.confidence_gate.outcome_threshold` from `.ll/ll-config.json`. Load `BRConfig` and compare its `commands.confidence_gate.outcome_threshold` with `set_flags._resolve_outcome_threshold(config)`: observe 65 versus 75.
2. Use a fresh issue with `outcome_confidence: 70` and an active decision signal in its current confidence notes. Run `ll-issues set-flags <ID> --dry-run`: the fallback 75 treats the issue as below threshold although the default gate is 65.
3. Set base outcome 65 and a local Markdown override of 75. Load configuration again: the gate reports 75 while the flag resolver returns 65. At outcome 70 an eligible finding is consequently missed.
4. Compare the skill's Phase 4.5 default and the rubric's cap prose with `ConfidenceGateConfig` and the schema; compare the CLI reference's 70 with `ll-issues next-action --help`.

## Root Cause

The threshold change did not update every consumer. The static flag rules and a separately implemented JSON reader retain 75, while the canonical loaded configuration defaults to 65 and merges local overrides. Changing just the literal would fix omitted-key projects but leave override drift. The documentation also copied a default instead of being checked against the schema.

## Expected Behavior

- `set-flags` uses `config.commands.confidence_gate.outcome_threshold`, including merged local overrides and the dataclass fallback. Exported default `FLAG_RULES` use the canonical default 65; custom thresholds still build rules for the effective value.
- The skill states default 65. The rubric states default 65 / cap 64 and preserves `min(raw_sum, outcome_threshold − 1)`: an explicit threshold of 75 still has cap 74.
- The CLI reference states fallback 65 for `next-action`; custom policy examples retain their chosen 75.
- Existing true flags remain set under the current set-only contract. This fix changes new flag evaluation, without clearing previously recorded flags or changing signal phrases, suppressors, or scoring buckets.

## Program Design

### Types

- `ConfidenceGateConfig.outcome_threshold: int` — existing effective gate threshold, default 65.
- `FLAG_RULES: tuple[FlagRule, ...]` — existing exported rules for the canonical default.

### Signatures

- `_resolve_outcome_threshold(config: BRConfig) -> int` — retain the existing signature and read the loaded configuration rather than opening JSON again.
- `_rules_for_threshold(threshold: int) -> tuple[FlagRule, ...]` — retain the existing dynamic rule builder and its strict below-threshold preconditions.

### Call Path

`BRConfig` loads defaults, base JSON and local overrides → `apply_flags_from_notes()` resolves the effective threshold → default or custom rules evaluate current findings → existing set-only persistence. Skill/rubric prose describes the same default and the relative cap formula.

## Implementation Steps

1. Replace the independent JSON reader in `_resolve_outcome_threshold()` with the loaded config property. Derive `_DEFAULT_OUTCOME_THRESHOLD` from `ConfidenceGateConfig().outcome_threshold` so static rules do not introduce another literal. Keep the default/custom rule-selection branch and all existing flag behavior.
2. Add meaningful cases to `scripts/tests/test_set_flags_cli.py`: omitted config key with outcomes 64 / 65 / 70; explicit 75 with 74 / 75; base 65 overridden locally to 75 at outcome 70; base 75 overridden locally to 65 at outcome 70. Use fresh false flags and eligible current findings, with the existing per-rule spike gate/suppressor prerequisites. Test already-true flags remain true, dry-run does not mutate, and all four exported rules use the same default as the schema/dataclass. Also test a project with no config file.
3. Edit the skill's Phase 4.5 default in place (499/500 lines; no net new lines) and the rubric's default/cap prose to 65 / 64. Tie the actual default and cap statements to `schema_default("commands.confidence_gate.outcome_threshold")` in `scripts/tests/test_confidence_check_skill.py`, using scoped Phase 4.5 and cap-section slices; checking for an unrelated `65` anywhere in the file is insufficient. Retain a text assertion for the relative cap formula so overrides are not turned into a fixed cap of 64.
4. Correct `docs/reference/CLI.md`'s `next-action` default 70 → 65. Leave the custom policy-table example at 75. Correct the stale readiness-gate comment/test docstring in rn-remediate, or verify BUG-3756 already did so; avoid concurrent edits to the shared YAML.
5. Regenerate tracked confidence-check mirrors using `ll-adapt --host gemini --apply`, and the corresponding kimi-code/qwen commands. Inspect the generated diff and run the artifact/companion gates; do not hand-edit mirrors or add unrelated host artifacts. Keep skill/doc text within the docs-audience rules.
6. Run `python -m pytest scripts/tests/test_confidence_check_skill.py scripts/tests/test_set_flags_cli.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_docs_audience_gate.py -q`, then the full `python -m pytest scripts/tests/`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/set_flags.py` — canonical default and effective threshold resolution.
- `scripts/tests/test_set_flags_cli.py` — real configuration/boundary/flag behavior.
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md` — default/cap wording.
- `scripts/tests/test_confidence_check_skill.py` — scoped default/cap assertions.
- `docs/reference/CLI.md` — next-action default.
- `scripts/little_loops/loops/rn-remediate.yaml`, `scripts/tests/test_rn_remediate.py` — stale comment/docstring only, coordinated with BUG-3756.
- `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` — regenerated tracked mirrors.

### Dependent Files

- `scripts/little_loops/config/automation.py` and `scripts/little_loops/config-schema.json` already default to 65; reuse them without changing the gate.
- `scripts/little_loops/config/core.py` already merges local overrides; this fix consumes that result.
- ENH-3742 also edits the skill/rubric and `set_flags.py`. Coordinate shared-file changes; neither fix requires the other to land first.

### Tests and Documentation

The existing flag/skill suites and mirror/docs-audience gates remain required. The custom policy examples in `docs/guides/POLICY_ROUTER_GUIDE.md`, `scripts/little_loops/loops/lib/policy-router.yaml`, and the CLI reference are examples, so their 75 values are not part of the default correction.

## Impact

- **Priority**: P2 - runtime flag drift affects omitted defaults and local overrides; the canonical gate is already correct
- **Effort**: Small to Medium
- **Risk**: Low to Medium - changes newly evaluated flags in affected projects; existing flags remain set
- **Breaking Change**: No

## Acceptance Criteria

- The loaded gate and flag evaluator agree for absent configuration, omitted keys, explicit thresholds and both directions of local override.
- At default 65, eligible findings can fire at 64 and do not newly fire at 65 or 70; custom 75 gives the corresponding 74 / 75 boundary. Existing true flags are retained.
- Skill/rubric prose states default 65 / cap 64 and keeps the relative cap formula; scoped tests tie the documented values and exported flag-rule default to the schema/dataclass.
- CLI default documentation is corrected; policy examples remain valid. Mirror, docs-audience, targeted and full local test gates pass.

## Review Notes

Reviewed on 2026-10-06. Temporary-project probes reproduced 65 versus 75 with an omitted key and 75 versus 65 with a local override. The pre-change rn-remediate, confidence-check and set-flags suites passed together (287 tests); their current coverage does not catch these cases. An Opus `/ll:advise` consult supported including the runtime resolver and canonical default (confidence 0.75). P2 is retained because omitted keys/local overrides are affected rather than all configured projects, although incorrect flags can feed DECIDE/WIRE routing. Coordinate shared-file edits with ENH-3742; the fixes have no hard dependency. No implementation changes were made during this review.

## Status

**Open** | Created: 2026-10-06 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-10-06T06:49:39 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
