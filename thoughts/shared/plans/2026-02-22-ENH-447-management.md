# ENH-447: Confidence Score Blocking Gate for manage-issue

## Plan Summary

Add a `commands.confidence_gate` config block that enables `manage-issue` to halt before Phase 3 when an issue's `confidence_score` is below threshold. Gate defaults to disabled. New `--force-implement` flag bypasses the gate.

## Changes

### 1. config.py — Add ConfidenceGateConfig dataclass
- New `ConfidenceGateConfig` dataclass: `enabled: bool = False`, `threshold: int = 85`
- Add `confidence_gate: ConfidenceGateConfig` field to `CommandsConfig`
- Update `CommandsConfig.from_dict` to parse nested `confidence_gate` dict
- Update `BRConfig.to_dict()` to serialize `confidence_gate`
- Add to `__all__`

### 2. config-schema.json — Add confidence_gate schema
- Add `confidence_gate` object under `commands.properties`
- Properties: `enabled` (boolean, default false), `threshold` (integer, default 85, min 1, max 100)

### 3. manage-issue/SKILL.md — Gate check + --force-implement
- Insert gate check section between Phase 2 and Phase 3
- Add `--force-implement` to frontmatter flags description
- Add to Arguments flags list and Examples

### 4. init/interactive.md — Wizard question
- Add "Confidence gate" option to Round 3 features multi-select
- Add conditional follow-up threshold question in Round 5

### 5. configure/SKILL.md + areas.md — Commands area
- Add `commands` row to area mapping table
- Add `commands` to area selection menus
- Add `commands` area config flow in areas.md

### 6. Tests — test_config.py
- Add `TestConfidenceGateConfig` class
- Update `TestCommandsConfig` to cover `confidence_gate` field

### 7. Documentation — API.md, CONFIGURATION.md
- Document `ConfidenceGateConfig` and `confidence_gate` config block

## Success Criteria
- [ ] ConfidenceGateConfig dataclass with correct defaults
- [ ] Schema validates confidence_gate block
- [ ] manage-issue gate check logic between Phase 2→3
- [ ] --force-implement flag documented and wired
- [ ] Init wizard offers confidence gate config
- [ ] Configure skill exposes commands area
- [ ] All tests pass
- [ ] mypy/ruff clean
