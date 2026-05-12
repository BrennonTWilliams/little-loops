---
id: FEAT-1457
type: FEAT
priority: P3
status: done
parent: FEAT-1452
discovered_date: 2026-05-12
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-12T04:10:19Z
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
12. `docs/development/TROUBLESHOOTING.md` — "Hook Not Triggering" chmod block: fix stale `hooks/scripts/precompact-state.sh` path to `hooks/adapters/claude-code/precompact.sh` (same stale-path pattern as item 6)

## Integration Map

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1457_doc_wiring.py` — new test file needed; follows convention from `scripts/tests/test_feat1407_doc_wiring.py`; one class per primary file, asserting each expected new string is present post-edit (e.g., `"LLHookIntentExtension" in ARCHITECTURE.read_text()`)
- `scripts/tests/test_create_extension.py` — update `TestMainCreateExtensionApply`: add assertion that `"LLHookIntentExtension" in ext_content` for the generated `extension.py` scaffold (no existing assertion covers the Protocol list string content)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — becomes the cross-link target of the new `CONTRIBUTING.md` "Event Schema Maintenance" paragraph (item 2); optionally add a forward pointer to `LLHookIntentExtension` in `extension.py` as the mechanism for contributing hook intent handlers [Agent 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. Fix stale path in `docs/development/TROUBLESHOOTING.md` "Hook Not Triggering" chmod block: `hooks/scripts/precompact-state.sh` → `hooks/adapters/claude-code/precompact.sh`
13. Create `scripts/tests/test_feat1457_doc_wiring.py` — doc wiring tests asserting each of the 12 primary files contains the expected new strings; follow pattern from `scripts/tests/test_feat1407_doc_wiring.py`
14. Add assertion to `scripts/tests/test_create_extension.py` (`TestMainCreateExtensionApply`) that the generated `extension.py` scaffold contains `"LLHookIntentExtension"`

## Acceptance Criteria

- All 9 skill/doc locations enumerated in FEAT-1452 Step 17 updated
- `docs/reference/API.md` `wire_extensions` description includes `LLHookIntentExtension`
- `docs/ARCHITECTURE.md` components table includes `LLHookIntentExtension` row
- Grep confirms no remaining references to old `session-start.sh` / `precompact-state.sh` paths in skills **and** `docs/development/TROUBLESHOOTING.md` that should reference `hooks/adapters/claude-code/`
- `scripts/tests/test_feat1457_doc_wiring.py` exists and passes

## Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current tree (parent `LLHookIntentExtension` Protocol shipped in commit `89c7f656`)._

### Protocol Definition (Source of Truth)

`scripts/little_loops/extension.py:103-111` — `LLHookIntentExtension` is a `@runtime_checkable` Protocol with a single method:

```python
def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

Detected via `hasattr()` in `wire_extensions()`; returned handlers are merged into `_HOOK_INTENT_REGISTRY` (`scripts/little_loops/hooks/__init__.py:44`) and consumed by `little_loops.hooks.main_hooks()`.

Already exported from `scripts/little_loops/__init__.py:15,67`. Companion types `LLHookEvent` / `LLHookResult` live at `scripts/little_loops/hooks/types.py`.

### Corrections to "Files to Modify" Entries

**Item 1 — `CONTRIBUTING.md` "three-Protocol list" is a misnomer.**
- The "2. Develop" section (`CONTRIBUTING.md:545-557`) only shows the base `LLExtension` example. There is no enumeration of Protocols there to extend.
- The three optional Protocols (`InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`) are actually listed in the **scaffold docstring** rendered by `_render_extension()` (`scripts/little_loops/cli/create_extension.py:82-83`) and mirrored in the CLI.md scaffold preview (`docs/reference/CLI.md:1344-1345`).
- **Recommended interpretation**: extend the "2. Develop" prose to mention `LLHookIntentExtension` alongside the base `LLExtension`, and add it to the scaffold docstring + CLI.md preview (which already covers items 3 and 4).

**Item 4 — wrong line range in `scripts/little_loops/cli/create_extension.py`.**
- Lines `40-56` are `_render_pyproject()` and contain no Protocol references.
- The actual scaffold docstring listing the optional mixin Protocols is at lines `82-83` inside `_render_extension()`. Update there:
  ```python
  "    Optional mixin Protocols (InterceptorExtension, ActionProviderExtension,",
  "    EvaluatorProviderExtension) are opt-in — implement their methods to activate.",
  ```
- Add `LLHookIntentExtension` to the same list (it is also a mixin Protocol opt-in).

**Item 6 — `skills/configure/areas.md` already partially updated.**
- Line `861` already shows `adapters/claude-code/session-start.sh` ✅ — no change needed.
- Line `868` still shows bare `precompact-state.sh` — update to `adapters/claude-code/precompact-state.sh`.

**Item 8 — `skills/init/SKILL.md` Section 9.5 partially current.**
- Line `367` already references `little_loops.hooks.session_start` (the Python module path), so the pyyaml note is correct.
- Line `354` warning still uses `session-start.sh` shell-script verbiage in the example warning text — update to reflect the Python-handler model.

### Current Text Snippets (for find-and-replace)

**`docs/ARCHITECTURE.md:484-487`** — Components table tail. Insert new row after the three existing `*ProviderExtension` / `InterceptorExtension` rows and before the `ReferenceInterceptorExtension` row:
```markdown
| `LLHookIntentExtension` | `extension.py` | Protocol for plugins contributing hook intent handlers (`provided_hook_intents()`); detected via `hasattr()` in `wire_extensions`, merged into `_HOOK_INTENT_REGISTRY` in `hooks/__init__.py` |
```

**`docs/reference/API.md` ~line 5942-5944** — currently describes the second-pass population of `_contributed_actions` / `_contributed_evaluators` / `_interceptors`. Append a parallel sentence about `_HOOK_INTENT_REGISTRY` for `LLHookIntentExtension`.

**`.claude/CLAUDE.md:39`** — current entry is a single line:
```
hooks/          # Lifecycle hooks and prompts
```
Replace with a subdirectory breakdown showing `hooks/core/` (host-agnostic Python handlers), `hooks/adapters/<host>/` (host translation layer), and `hooks/prompts/`.

**`skills/audit-claude-config/SKILL.md:41`** — current entry:
```markdown
- **Hooks**: `hooks/hooks.json` + `hooks/prompts/*.md` - Lifecycle hooks
```
Extend to include `hooks/adapters/` and `hooks/core/`.

**`CONTRIBUTING.md:605-619` "Event Schema Maintenance"** — currently scoped to `LLEvent` only. Add a clarifying paragraph that `LLHookEvent` / `LLHookResult` are a sibling request/response wire format (not pub/sub) and do **not** participate in the JSON Schema regeneration flow described above; point readers to `docs/reference/EVENT-SCHEMA.md:39` and `scripts/little_loops/hooks/types.py`.

### Verification Greps (post-edit)

```bash
# All 11 doc/skill locations should mention the new Protocol
grep -rn "LLHookIntentExtension" CONTRIBUTING.md docs/ skills/ .claude/CLAUDE.md scripts/little_loops/cli/create_extension.py

# No bare precompact-state.sh references should remain in user-facing docs
grep -rn "precompact-state\.sh" skills/ | grep -v "adapters/claude-code/"
```

## Resolution

Completed 2026-05-12. All 12 doc/skill/source locations updated to reference `LLHookIntentExtension` (or the corresponding `hooks/adapters/<host>/` path correction). New doc-wiring test `scripts/tests/test_feat1457_doc_wiring.py` covers all 12 locations (30 assertions, all passing). `TestMainCreateExtensionApply.test_extension_py_lists_hook_intent_protocol` added to `scripts/tests/test_create_extension.py` to guard the scaffold docstring contents. Verification greps confirm no remaining bare `precompact-state.sh` references in `skills/` or `docs/development/`.

Pre-existing test failures on `main` (`test_generate_schemas.py`, `test_update_skill.py::TestMarketplaceVersionSync`) are unrelated to this change — confirmed via `git stash` comparison.

## Session Log
- `/ll:manage-issue` - 2026-05-12T04:10:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cba4ea4-18a2-41ce-a895-b0396b466ef3.jsonl`
- `/ll:ready-issue` - 2026-05-12T04:04:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fcb76f03-a51f-4e9c-82e4-acc7d900e197.jsonl`
- `/ll:wire-issue` - 2026-05-12T04:01:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87381695-a823-4020-9ce9-37ec468aefab.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d5c46ae-96e4-467e-8fd3-f9f3cfc2ae88.jsonl`
- `/ll:refine-issue` - 2026-05-12T03:53:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/967b791f-d483-49a1-b837-4ae3f38b184b.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b21eb7d-ba29-48d1-a82f-90d0bc6238a5.jsonl`
