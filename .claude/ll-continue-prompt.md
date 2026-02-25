# Continue: ENH-447 — Confidence Score Blocking Gate for manage-issue

## Context
Implementing ENH-447: Add `commands.confidence_gate` config block that enables `manage-issue` to halt before Phase 3 when an issue's `confidence_score` is below threshold.

Issue file: `.issues/enhancements/P3-ENH-447-confidence-score-blocking-gate-for-manage-issue.md`
Plan: `thoughts/shared/plans/2026-02-22-ENH-447-management.md`

## Completed

1. **config.py** — Added `ConfidenceGateConfig` dataclass (`enabled: bool = False`, `threshold: int = 85`) before `CommandsConfig`. Wired into `CommandsConfig` with `confidence_gate` field, `from_dict`, and `to_dict`. Added to `__all__`.

2. **config-schema.json** — Added `confidence_gate` object under `commands.properties` with `enabled` (boolean, default false), `threshold` (integer, default 85, min 1, max 100), `additionalProperties: false`.

3. **manage-issue/SKILL.md** — Added Phase 2.5 confidence gate check between Phase 2 and Phase 3 with full pseudocode logic. Added `--force-implement` flag to frontmatter args description, flags documentation list, and examples section.

4. **test_config.py** — Added `TestConfidenceGateConfig` class with `test_from_dict_with_all_fields` and `test_from_dict_with_defaults`. Updated `TestCommandsConfig` tests to include `confidence_gate` in both all-fields and defaults tests. Added `ConfidenceGateConfig` to imports.

## Remaining Tasks

5. **Init wizard** (`skills/init/interactive.md`):
   - Add "Confidence gate" option to Round 3 features multi-select (line 132-143)
   - Add conditional threshold question in Round 5 dynamic section (follow pattern of "Context monitoring" → threshold at line 324-334)
   - Add config mapping note after Round 5 for confidence gate settings

6. **Configure skill** — Two files:
   - `skills/configure/SKILL.md`: Add `| commands | commands | Command hooks, confidence gate |` to area mapping table (lines 47-58). Add `commands` to area selection AskUserQuestion menus (lines 138-188).
   - `skills/configure/areas.md`: Add `## Area: commands` section at end. Follow `## Area: context` pattern (line 409). Show current values for `confidence_gate.enabled` and `confidence_gate.threshold`. Add AskUserQuestion with enable + threshold questions.

7. **Documentation**:
   - `docs/API.md` line 88: Update `CommandsConfig` row or add note about `confidence_gate` sub-config
   - `docs/CONFIGURATION.md` lines 64-68: Update `commands` JSON example to include `"confidence_gate": {"enabled": false, "threshold": 85}`

8. **Run verification**: `python -m pytest scripts/tests/`, `python -m mypy scripts/little_loops/`, `ruff check scripts/`, `ruff format scripts/`

9. **Complete issue lifecycle**: Update issue frontmatter with resolution, move to `.issues/completed/`, commit all changes with conventional commit.

## Resume Command
```
/ll:manage-issue enhancement implement ENH-447 --resume
```
