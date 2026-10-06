---
id: BUG-3757
title: Confidence-check outcome threshold drifts in docs and set-flags configuration
type: BUG
priority: P2
status: open
testable: true
discovered_date: '2026-10-05'
parent: BUG-3754
labels:
- confidence-check
- docs
- scoring
- configuration
relates_to:
- BUG-3756
- BUG-3760
- ENH-3742
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3757: Confidence-check outcome threshold drifts in docs and set-flags configuration

## Summary

The configured outcome default is 65, but confidence-check documentation and `set-flags`' fallback still use 75. In addition, `set-flags` re-reads a fixed JSON path instead of using the loaded configuration, ignoring local threshold overrides and supported alternate config locations. Align the flag evaluator and documentation with the existing configuration contract; keep the default at 65 and the unproven-mechanism cap relative to the effective threshold. This includes runtime regression tests, so `testable: true` is explicit despite the documentation wording.

## Parent Issue

Decomposed from BUG-3754. BUG-3756 has shipped the rn-remediate score polarity and routing fix. This child owns threshold documentation, its remaining stale readiness comment/docstring, and set-flags configuration drift.

## Current Behavior

- `skills/confidence-check/SKILL.md`, **Phase 4.5: Findings Write-Back**, says the outcome-risk threshold defaults to 75. `skills/confidence-check/rubric.md`, **Outcome Confidence Cap (ENH-3350)**, documents default 75 / cap 74. Tracked `.gemini/`, `.kimi-code/`, `.qwen/` mirrors carry the same text.
- `scripts/little_loops/cli/issues/set_flags.py` sets `_DEFAULT_OUTCOME_THRESHOLD = 75`, constructs exported `FLAG_RULES` with it, and uses it in `_resolve_outcome_threshold()` when the config key/file cannot be read. A project omitting the key therefore has a loaded gate of 65 but a flag-evaluation threshold of 75.
- `_resolve_outcome_threshold()` reads `.ll/ll-config.json` directly. With base outcome 65 and `.ll/ll.local.md` overriding it to 75, `BRConfig` reports 75 while `set-flags` still resolves 65.
- Removing a base threshold of 75 with a local `outcome_threshold: null` restores the loaded default 65, but the flag resolver still reads 75. Root-level `ll-config.json` and host-selected configuration also reach `BRConfig` but are bypassed by the fixed `.ll` path.
- `docs/reference/CLI.md`, **ll-issues next-action / ll-issues na**, says `--outcome-threshold` defaults to 70; the CLI fallback is 65. The `check_complexity_pre_implement` comment in rn-remediate and `test_check_complexity_pre_implement_on_yes_routes_to_wire_check` docstring retain the old 85/75 pair after BUG-3756.
- `docs/reference/CLI.md`, **ll-loop edit-routes**, is a custom policy-table example using 75, not a default claim. The examples in the policy-router guide and library have the same status and should remain valid examples.

## Steps to Reproduce

1. In a temporary project, omit `commands.confidence_gate.outcome_threshold` from `.ll/ll-config.json`. Load `BRConfig` and compare its `commands.confidence_gate.outcome_threshold` with `set_flags._resolve_outcome_threshold(config)`: observe 65 versus 75.
2. Use a fresh issue with `outcome_confidence: 70` and an active decision signal in its current confidence notes. Run `ll-issues set-flags <ID> --dry-run`: the fallback 75 treats the issue as below threshold although the default gate is 65. <!-- ll-evidence-ok: `outcome_confidence: 70` is a hypothetical fresh-issue frontmatter value in a repro step, not a quote from `.ll/ll-config.json` -->
3. Set base outcome 65 and a local Markdown override of 75. Load configuration again: the gate reports 75 while the flag resolver returns 65. At outcome 70 an eligible finding is consequently missed.
4. Compare the skill's Phase 4.5 default and the rubric's cap prose with `ConfidenceGateConfig` and the schema; compare the CLI reference's 70 with `ll-issues next-action --help`.
5. Remove a base threshold of 75 with a local `outcome_threshold: null`: loaded threshold 65, flag threshold 75. Alternatively, use only a root or host-selected config with threshold 80: loaded threshold 80, flag threshold 75. An eligible finding at outcome 78 is missed in that alternate-location case. <!-- ll-evidence-ok: `outcome_threshold: null` is temporary `.ll/ll.local.md` reproduction setup verified by the review probe, not a quote from `.ll/ll-config.json`. -->

## Root Cause

The threshold change did not update every consumer. The static flag rules and a separately implemented JSON reader retain 75, while the canonical loaded configuration defaults to 65 and merges local overrides. Changing just the literal would fix omitted-key projects but leave override drift. The documentation also copied a default instead of being checked against the schema.

## Expected Behavior

- `set-flags` uses `config.commands.confidence_gate.outcome_threshold`, including merged local overrides, key removal, supported config-location selection and the dataclass fallback. Exported default `FLAG_RULES` use the canonical default 65; custom thresholds still build rules for the effective value. The supplied loaded configuration governs even if its source file changes afterwards.
- Retain the existing `int()` coercion for numeric-string thresholds. If a loaded threshold cannot be converted, use the canonical default 65. Base JSON read/parse errors remain owned by `BRConfig` initialization, which already precedes flag evaluation; this fix adds no configuration validation policy.
- The skill states default 65. The rubric states default 65 / cap 64 and preserves `min(raw_sum, outcome_threshold − 1)`: an explicit threshold of 75 still has cap 74.
- The CLI reference states fallback 65 for `next-action`; custom policy examples retain their chosen 75.
- Existing true flags remain set under the current set-only contract. This fix changes new flag evaluation, without clearing previously recorded flags or changing signal phrases, suppressors, or scoring buckets.

## Proposed Solution

Normalize the already-loaded threshold in `_resolve_outcome_threshold()` instead of opening a config file again, retaining integer conversion and its conversion-error fallback. Derive the static default from `ConfidenceGateConfig`, then correct the source documentation and regenerate its tracked mirrors. Other readiness consumers have a distinct absence-sensitive caller-fallback contract and are follow-up work, rather than replacements with populated dataclass defaults.

## Program Design

### Types

- `ConfidenceGateConfig.outcome_threshold: int` — existing effective gate threshold, default 65.
- `FLAG_RULES: tuple[FlagRule, ...]` — existing exported rules for the canonical default.

### Signatures

- `_resolve_outcome_threshold(config: BRConfig) -> int` — retain the signature; return the loaded property's `int()` conversion, falling back to the canonical default on `TypeError`, `ValueError` or `OverflowError`. Do not add a second file reader.
- `_rules_for_threshold(threshold: int) -> tuple[FlagRule, ...]` — retain the existing dynamic rule builder and its strict below-threshold preconditions.

### Call Path

`BRConfig` loads defaults, base JSON and local overrides → `apply_flags_from_notes()` resolves the effective threshold → default or custom rules evaluate current findings → existing set-only persistence. Skill/rubric prose describes the same default and the relative cap formula.

## Implementation Steps

1. Replace the independent JSON reader in `_resolve_outcome_threshold()` with the loaded config property, retaining integer coercion and conversion-error fallback. Derive `_DEFAULT_OUTCOME_THRESHOLD` from `ConfidenceGateConfig().outcome_threshold` so static rules do not introduce another literal. Keep the default/custom rule-selection branch and all existing flag behavior.
2. Add parametrized behavioral cases to `scripts/tests/test_set_flags_cli.py` for each of the four rules: omitted config key with outcomes 64 / 65 / 70; explicit 75 with 74 / 75; both directions of local 65/75 overrides at outcome 70; local null removing base 75; no config file; root and host-selected config at threshold 80 / outcome 78. Isolate `LL_HOOK_HOST`/`LL_STATE_DIR` in location tests. Use fresh false flags and eligible current findings; retain spike gates/suppressors, direct-frontmatter trigger and missing-score controls. Check all four exported rule preconditions against the schema/dataclass boundary through their behavior, without closure introspection or fast-path identity assertions. Include numeric-string `"75"`, an unconvertible threshold falling back to 65, and one case rewriting the base file after `BRConfig` loads. Reuse existing true-flag and dry-run coverage where it already proves retention and unchanged bytes; do not duplicate it.
3. Edit the skill's Phase 4.5 default in place (499/500 lines; no net new lines) and the rubric's default/cap prose to 65 / 64. Tie the actual default and cap statements to `schema_default("commands.confidence_gate.outcome_threshold")` in `scripts/tests/test_confidence_check_skill.py`, using scoped Phase 4.5 and cap-section slices; checking for an unrelated `65` anywhere in the file is insufficient. Retain a text assertion for the relative cap formula so overrides are not turned into a fixed cap of 64.
4. Correct `docs/reference/CLI.md`'s `next-action` fallback 70 → 65, with a scoped check of that documented flag against the schema default in the existing skill test module. Leave the custom policy-table example at 75. Correct the residual readiness-gate comment and test docstring to refer to configured thresholds (default 85/65); BUG-3756 is done, but these leftovers still exist. Change no loop logic.
5. Regenerate tracked confidence-check mirrors using `ll-adapt --host gemini --apply`, and the corresponding kimi-code/qwen commands, with `CLAUDE_PLUGIN_ROOT` explicitly pointing to this checkout. `--only` filters agents, not skills. Inspect the generated diff and run the artifact/companion gates; stage only intended confidence-check mirror changes and preserve any unrelated working-tree work. Do not hand-edit mirrors or add unrelated host artifacts. Keep skill/doc text within the docs-audience rules.
6. Run `python -m pytest scripts/tests/test_confidence_check_skill.py scripts/tests/test_set_flags_cli.py scripts/tests/test_rn_remediate.py scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_docs_audience_gate.py -q`, then the full `python -m pytest scripts/tests/`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/set_flags.py` — canonical default and effective threshold resolution.
- `scripts/tests/test_set_flags_cli.py` — real configuration/boundary/flag behavior.
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md` — default/cap wording.
- `scripts/tests/test_confidence_check_skill.py` — scoped default/cap assertions.
- `docs/reference/CLI.md` — next-action default.
- `scripts/little_loops/loops/rn-remediate.yaml`, `scripts/tests/test_rn_remediate.py` — residual comment/docstring only after BUG-3756.
- `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` — regenerated tracked mirrors.

### Dependent Files

- `scripts/little_loops/config/automation.py` and `scripts/little_loops/config-schema.json` already default to 65; reuse them without changing the gate.
- `scripts/little_loops/config/core.py` already merges local overrides; this fix consumes that result.
- ENH-3742 also edits the skill/rubric and `set_flags.py`. Prefer this small threshold fix before ENH-3742, then rebase its shared-file work. Keep this skill edit line-neutral so it fits the current 499/500-line limit; no semantic hard dependency or cycle is needed.

### Tests and Documentation

The existing flag/skill suites and mirror/docs-audience gates remain required. The custom policy examples in `docs/guides/POLICY_ROUTER_GUIDE.md`, `scripts/little_loops/loops/lib/policy-router.yaml`, and the CLI reference are examples, so their 75 values are not part of the default correction.

## Impact

- **Priority**: P2 - runtime flag drift affects omitted defaults, local overrides and alternate config locations; schema/dataclass defaults are already correct
- **Effort**: Small to Medium
- **Risk**: Low to Medium - changes newly evaluated flags in affected projects; existing flags remain set
- **Breaking Change**: No

## Acceptance Criteria

- The loaded configuration and flag evaluator agree for absent configuration, omitted keys, explicit thresholds, both directions of local override, local null removal and supported root/host config locations. A post-load file change does not alter that evaluation.
- At default 65, eligible findings can fire at 64 and do not newly fire at 65 or 70; custom 75 gives the corresponding 74 / 75 boundary. Existing true flags are retained.
- Numeric-string thresholds retain integer coercion; conversion failures use 65. Existing spike suppression, numeric/direct triggers, missing-score and dry-run behavior are preserved.
- Skill/rubric prose states default 65 / cap 64 and keeps the relative cap formula; scoped tests tie the documented values and exported flag-rule default to the schema/dataclass.
- CLI default documentation is corrected; policy examples remain valid. The main skill edit adds no net lines, and generated diffs contain only intended source/mirror changes. Mirror, docs-audience, targeted and full local test gates pass.

## Scope Boundaries

This issue fixes set-flags runtime threshold resolution and default documentation. The shared `resolve_confidence_thresholds()` used by readiness checks and next-action also bypasses local/alternate configuration, but must preserve explicit override and per-key caller-fallback semantics. BUG-3760 tracks that separately without a blocking dependency; completing this issue alone does not establish threshold parity with those readers. Do not replace their absence-sensitive read with `ConfidenceGateConfig` defaults here.

## Review Notes

Reviewed on 2026-10-06. Temporary-project probes reproduced 65 versus 75 with an omitted key and 75 versus 65 with a local override. The pre-change rn-remediate, confidence-check and set-flags suites passed together (287 tests); their current coverage does not catch these cases. An Opus `/ll:advise` consult supported including the runtime resolver and canonical default (confidence 0.75). P2 is retained because omitted keys/local overrides are affected rather than all configured projects, although incorrect flags can feed DECIDE/WIRE routing. Coordinate shared-file edits with ENH-3742; the fixes have no hard dependency. Follow-up review on 2026-10-06 reconfirmed both cases in fresh temporary projects (65/75 for an omitted key, 75/65 for a local override). The merged telemetry work does not affect this bug. Prefer landing this small fix before ENH-3742 and rebase shared skill/rubric/flag edits; its skill changes must remain line-neutral. The broader 338-test baseline passed with one optional skip. No implementation changes were made during this review.

Further review on 2026-10-06 inspected `main` at `77faacc66`. Probes confirmed null-removal, root/host-location and post-load re-read drift, plus existing numeric-string coercion. BUG-3756 is now done; its two stale readiness annotations remain. The focused six-file baseline passed **947 tests**. Opus via `/ll:advise` (`claude-opus-5-5`, confidence 0.85) supported a separate non-blocking readiness-reader follow-up and retaining integer coercion. Its dissent favored combining the user-visible consistency fixes; separate plans preserve their different fallback contracts. Accepted behavioral regression checks rather than brittle source/closure/identity scans. Retained the scoped CLI default check because next-action's documented 70 is a verified defect, despite the advisor's suggestion to omit it. No implementation changes were made.

## Status

**Open** | Created: 2026-10-06 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-06T18:21:47 - `225d913b-150f-4f37-9e25-fcb3cb3d0b0e.jsonl`
- `/ll:ready-issue` - 2026-10-06T18:16:35 - `471d3a7a-54d3-4495-af46-a12400a91738.jsonl`
- `/ll:issue-size-review` - 2026-10-06T06:49:39 - `cede7154-079d-47b6-bd61-dd96bcbe90b1.jsonl`
