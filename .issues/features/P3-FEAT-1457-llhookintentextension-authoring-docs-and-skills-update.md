---
id: FEAT-1457
type: FEAT
priority: P3
status: open
parent: FEAT-1452
discovered_date: 2026-05-12
discovered_by: issue-size-review
decision_needed: false
---

# FEAT-1457: LLHookIntentExtension Authoring Docs and Skills Update

## Summary

After `LLHookIntentExtension` ships (FEAT-1456), update 9 skill/doc locations to reference the new Protocol plus 2 additional API/architecture doc entries. All edits are mechanical text changes — no code changes.

## Parent Issue

Decomposed from FEAT-1452: LLHookIntentExtension Protocol and Extension Registry Wiring

## Depends On

- FEAT-1456 (Protocol must exist before docs reference it)

## Scope

Covers FEAT-1452 / FEAT-1116 Implementation Step 17 — Authoring Docs and Skills, plus Integration Map documentation entries added by `/ll:wire-issue`.

## Files to Modify

1. `CONTRIBUTING.md` — "Authoring Extensions" > "2. Develop": add `LLHookIntentExtension` to the three-Protocol list
2. `CONTRIBUTING.md` — "Event Schema Maintenance": add `LLHookEvent` analogous documentation
3. `docs/reference/CLI.md` — `### ll-create-extension` "Generated file contents" code block: add `LLHookIntentExtension`
4. `scripts/little_loops/cli/create_extension.py:40-56` — update scaffold docstring/string
5. `skills/workflow-automation-proposer/SKILL.md` — Step 7 "For hooks" sketch: update from direct `hooks/hooks.json` edits to adapter model
6. `skills/configure/areas.md` — "Area: hooks" Current Values display table: update `session-start.sh` and `precompact-state.sh` paths to `hooks/adapters/claude-code/`
7. `skills/audit-claude-config/SKILL.md:41` — add `hooks/adapters/` to audit scope
8. `skills/init/SKILL.md` — Section 9.5: update `session-start.sh` warning and `pyyaml` dependency note
9. `.claude/CLAUDE.md` — `hooks/` directory entry: add `hooks/adapters/` and `hooks/core/` subdirectory breakdown
10. `docs/reference/API.md` — `### wire_extensions` description (line ~5944): add `LLHookIntentExtension` to the Protocol list
11. `docs/ARCHITECTURE.md` — Components table (lines ~484–487): add `LLHookIntentExtension` row (detected via `hasattr()`, populates `_HOOK_INTENT_REGISTRY` in `hooks/__init__.py`)

## Implementation Steps

1. Batch-edit `CONTRIBUTING.md` for both the Protocol list and Event Schema sections.
2. Update `docs/reference/CLI.md` scaffold code block.
3. Update `scripts/little_loops/cli/create_extension.py` scaffold string.
4. Update `skills/workflow-automation-proposer/SKILL.md` Step 7.
5. Update `skills/configure/areas.md` hooks area table.
6. Update `skills/audit-claude-config/SKILL.md` audit scope line.
7. Update `skills/init/SKILL.md` Section 9.5.
8. Update `.claude/CLAUDE.md` hooks directory entry.
9. Update `docs/reference/API.md` `wire_extensions` description.
10. Update `docs/ARCHITECTURE.md` components table.
11. Verify no missed locations: `grep -r "LLHookIntentExtension" CONTRIBUTING.md docs/ skills/ .claude/` — all 11 locations should appear.

## Acceptance Criteria

- All 9 skill/doc locations enumerated in FEAT-1452 Step 17 updated
- `docs/reference/API.md` `wire_extensions` description includes `LLHookIntentExtension`
- `docs/ARCHITECTURE.md` components table includes `LLHookIntentExtension` row
- Grep confirms no remaining references to old `session-start.sh` / `precompact-state.sh` paths in skills that should reference `hooks/adapters/claude-code/`

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b21eb7d-ba29-48d1-a82f-90d0bc6238a5.jsonl`
