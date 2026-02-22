---
discovered_date: 2026-02-22
discovered_by: capture-issue
---

# ENH-447: Add confidence-score blocking gate to manage-issue

## Summary

Enable `manage-issue` to treat the `confidence_score` frontmatter field as a blocking implementation gate. When enabled via `ll-config.json`, if an issue's `confidence_score` is below the configured threshold, `manage-issue` halts before proceeding to implementation and prompts the user to either run `/ll:confidence-check` first or override manually. The `/ll:init` wizard and `/ll:configure` skill both gain UI to configure the gate.

## Current Behavior

`manage-issue` invokes `confidence-check` as **advisory and non-blocking**: "Consider running the `confidence-check` skill to validate implementation readiness." If the issue has a `confidence_score` of 20/100 in its frontmatter, implementation proceeds anyway. There is no threshold check anywhere in the skill.

## Expected Behavior

A new `commands.confidence_gate` config block controls blocking behavior:

```json
{
  "commands": {
    "confidence_gate": {
      "enabled": true,
      "threshold": 85
    }
  }
}
```

When `enabled: true`, `manage-issue` checks the issue's `confidence_score` frontmatter before entering Phase 3 (Implementation):

- If `confidence_score >= threshold` → proceed normally
- If `confidence_score < threshold` → halt with message:
  ```
  ✗ Confidence gate: score 62/100 is below threshold 85.
    Run /ll:confidence-check [ID] to evaluate readiness, or use --force-implement to override.
  ```
- If `confidence_score` is absent → prompt user to run confidence-check first (or bypass with `--force-implement`)

When `enabled: false` (default) → advisory behavior unchanged; no gate applied.

## Motivation

The confidence check is designed to prevent wasted implementation effort on under-specified or risky issues. Without a gate, a low score is informational only and easily ignored. Making the gate opt-in (disabled by default) preserves existing behavior for all current users while giving teams that want enforced quality bars a proper mechanism.

The `--force-implement` override ensures the gate is never a hard blocker — it enforces intent, not obstruction.

## Use Case

A team sets `confidence_gate.enabled: true` and `threshold: 85` in their shared `ll-config.json`. When `ll-parallel` processes a batch of issues, any issue with `confidence_score: 72` is automatically blocked before implementation begins. The session reports the gate failure. The user runs `/ll:confidence-check` on that issue, the issue is refined, the score rises to 88, and the next run proceeds.

## Acceptance Criteria

- [ ] New `commands.confidence_gate` config block with `enabled: bool` (default `false`) and `threshold: int` (default `85`)
- [ ] `manage-issue` checks gate before Phase 3; halts with clear message if score < threshold
- [ ] `--force-implement` flag bypasses gate for one-off overrides
- [ ] Gate is silently skipped when `confidence_score` key is absent AND gate is disabled; when gate is enabled + score absent, user is prompted
- [ ] `/ll:init` wizard includes confidence gate question (options: 70, 85 (Recommended), 95, Disable)
- [ ] `/ll:configure` skill includes confidence gate setting
- [ ] `config-schema.json` validates `confidence_gate` block
- [ ] `scripts/tests/test_config.py` covers new config fields

## API/Interface

### Config Schema Addition

`confidence_gate` is added under the existing `commands` section:

```json
{
  "commands": {
    "confidence_gate": {
      "enabled": false,
      "threshold": 85
    }
  }
}
```

### manage-issue Gate Check (Phase 2 → Phase 3 transition)

```
IF config.commands.confidence_gate.enabled:
  READ confidence_score from issue frontmatter
  IF confidence_score is absent:
    WARN user: "No confidence_score on file. Run /ll:confidence-check [ID] first, or pass --force-implement to bypass."
    HALT unless --force-implement
  ELSE IF confidence_score < config.commands.confidence_gate.threshold:
    HALT with gate message unless --force-implement
```

### Init Wizard Question

```
"What confidence score threshold should gate implementation? (gate disabled = no blocking)"
Options:
  - 70    → allows most issues through
  - 85    → (Recommended) enforces solid readiness
  - 95    → strict; only near-perfect issues proceed
  - Disable confidence gate (default)
```

## Proposed Solution

1. Add `ConfidenceGateConfig` dataclass to `config.py` with `enabled: bool = False` and `threshold: int = 85`; wire into `CommandsConfig`
2. Add `confidence_gate` schema block to `config-schema.json` under `commands`
3. Update `skills/manage-issue/SKILL.md`: after Phase 2 planning, insert gate check block; add `--force-implement` to accepted flags
4. Update `skills/init/SKILL.md`: add AskUserQuestion for confidence gate with the four options listed above
5. Update `skills/configure/SKILL.md`: add confidence gate section to the settings menu
6. Add tests for `ConfidenceGateConfig` parsing and default values in `scripts/tests/test_config.py`
7. Update `README.md` and `docs/API.md` to document the new config block

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — add gate check at Phase 2→3 transition; add `--force-implement` flag
- `scripts/little_loops/config.py` — add `ConfidenceGateConfig` dataclass; add to `CommandsConfig`
- `config-schema.json` — add `confidence_gate` block under `commands` properties
- `skills/init/SKILL.md` — add confidence gate question to wizard
- `skills/configure/SKILL.md` — add confidence gate setting

### Dependent Files (No Changes Required)
- `scripts/little_loops/cli/auto.py` — invokes manage-issue; gate logic is inside the skill
- `scripts/little_loops/cli/parallel.py` — same; no changes needed
- `scripts/little_loops/cli/sprint.py` — same

### Similar Patterns
- `commands.pre_implement` / `commands.post_implement` in `CommandsConfig` — existing hook fields
- `--gates` flag in manage-issue — existing phase gate mechanism
- `confidence_score` frontmatter field — set by `/ll:confidence-check` Phase 4

### Tests
- `scripts/tests/test_config.py` — add tests for `ConfidenceGateConfig` fields, defaults, and from_dict parsing

### Documentation
- `README.md` — document `commands.confidence_gate` config option
- `docs/API.md` — update config reference with `ConfidenceGateConfig`

### Configuration
- `config-schema.json` — `confidence_gate.enabled` (boolean, default false), `confidence_gate.threshold` (integer, default 85)

## Implementation Steps

1. Add `ConfidenceGateConfig` dataclass to `scripts/little_loops/config.py` (`enabled: bool = False`, `threshold: int = 85`); add `confidence_gate: ConfidenceGateConfig` field to `CommandsConfig`; update `from_dict` and serialization
2. Add `confidence_gate` schema block to `config-schema.json` under `commands.properties` with `additionalProperties: false`
3. Update `skills/manage-issue/SKILL.md` Phase 2→3 section to check `config.commands.confidence_gate.enabled`; add `--force-implement` to flags list and description
4. Update `skills/init/SKILL.md` to add AskUserQuestion for confidence gate threshold with options 70 / 85 (Recommended) / 95 / Disable
5. Update `skills/configure/SKILL.md` to expose `commands.confidence_gate.enabled` and `threshold` as configurable settings
6. Add `test_confidence_gate_config_defaults` and `test_confidence_gate_config_from_dict` to `scripts/tests/test_config.py`
7. Update `README.md` config section and `docs/API.md` to document `confidence_gate`

## Impact

- **Priority**: P3 — Useful quality enforcement but not blocking anything
- **Effort**: Medium — Config dataclass + schema + skill update + wizard integration
- **Risk**: Low — Gate defaults to disabled; existing behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/API.md` | Config reference — `CommandsConfig` and schema documentation |
| `docs/ARCHITECTURE.md` | System design — manage-issue phase structure |

## Labels

`enhancement`, `captured`, `manage-issue`, `confidence-check`, `config`, `workflow`

## Session Log
- `/ll:capture-issue` - 2026-02-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88e50ae7-8f86-442f-bc39-9214f39f18c1.jsonl`

---

**Open** | Created: 2026-02-22 | Priority: P3
