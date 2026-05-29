# FEAT-1743 Implementation Plan

## Summary
Wire `learning_tests.enabled` feature flag into config schema, config dataclass, `/ll:init`, and `/ll:configure`.

## Implementation Order

### Phase A: Config Schema + Dataclass (foundation)
1. **config-schema.json**: Add `enabled` (bool, default false) and `discoverability` (object with mode/skip_packages) to learning_tests. Remove `additionalProperties: false`.
2. **features.py**: Add `enabled: bool = False` and `DiscoverabilityConfig` sub-dataclass to `LearningTestsConfig`. Add `is_learning_tests_enabled()` helper.
3. **core.py**: Update `to_dict()` to export `enabled` and `discoverability`.

### Phase B: Init Skill (front-door opt-in)
4. **interactive.md**: Add new round (TOTAL=9), following Round 4 pattern with Yes/No AskUserQuestion.
5. **SKILL.md**: Add Step 6 summary entry, Step 8 scaffold handlers, Step 12 completion message. Step 10 already has `Bash(ll-learning-tests:*)`.

### Phase C: Configure Skill (post-init toggling)
6. **SKILL.md**: Add `learning-tests` to argument-hint, area mapping table, arguments list, interactive pagination.
7. **areas.md**: Add `## Area: learning_tests` handler.
8. **show-output.md**: Add `## learning_tests --show` section.

### Phase D: Tests
9. **test_config_schema.py**: Extend `test_learning_tests_in_schema` for enabled/discoverability.
10. **test_config.py**: Extend TestLearningTestsConfig + round-trip test.
11. **test_init_learning_tests.py**: New file - yes/no paths, re-prompt suppression, default-false.
12. **test_feat1743_init_wiring.py**: New doc-wiring test.
13. **test_feat1743_configure_wiring.py**: New/merged doc-wiring test.

### Phase E: Docs
14. **LEARNING_TESTS_GUIDE.md**: Add "Getting Started" section.
15. **CONFIGURATION.md**: Document new fields.

## Research Confirmed
- `feature_enabled()` at features.py:13 already exists - helper can go in features.py alongside it, avoiding the `learning_tests/` package shadowing issue.
- Step 10 already has `Bash(ll-learning-tests:*)` - only `Skill(ll:explore-api)` needs conditional addition.
- SyncConfig pattern (enabled: bool = False in from_dict) is the exact template for LearningTestsConfig.
