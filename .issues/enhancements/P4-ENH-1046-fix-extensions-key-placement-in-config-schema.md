---
id: ENH-1046
type: ENH
priority: P4
status: backlog
discovered_date: 2026-04-11
discovered_by: issue-size-review
parent_issue: ENH-1040
confidence_score: 100
outcome_confidence: 100
---

# ENH-1046: Fix `extensions` key placement in `config-schema.json`

## Summary

The `extensions` key at `config-schema.json:903-908` appears placed *outside* the `properties` block (as a sibling rather than a member). This causes `jsonschema` validation to flag `extensions` as an `additionalProperties` violation even for valid configs that use it. Verify and fix the placement before any config validation feature is shipped.

## Parent Issue

Decomposed from ENH-1040: Add post-update config health check to ll:update

## Current Behavior

`config-schema.json` has `additionalProperties: false` at the top level (`config-schema.json:910`). If `extensions` is a sibling of `properties` rather than a key inside it, any `.ll/ll-config.json` that sets `extensions` would trigger a false-positive validation warning.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Bug confirmed (more severe than described)**: The schema at the time of this refinement was not just misplaced — it was **invalid JSON**. The `extensions` block was placed outside `properties` AND there was an extra `},` at line 909 that closed the root object prematurely, leaving `"additionalProperties": false` and `}` dangling outside the root. `python3 -c "json.load(open('config-schema.json'))"` produced `JSONDecodeError: Extra data: line 909 column 4`.

Brace depth trace at the affected lines (confirmed):
- `config-schema.json:901` — `}` closes `display` property object (depth 3→2)
- `config-schema.json:902` — `},` closes the root `properties` block (depth 2→1)
- `config-schema.json:903-908` — `"extensions": { ... }` at root level (wrong; depth 1→2→1)
- `config-schema.json:909` — `},` closed the root object (depth 1→0) — **premature root close**
- `config-schema.json:910-911` — `"additionalProperties": false` and `}` were **outside** root (extra data)

## Expected Behavior

`extensions` is correctly nested inside the `properties` block so that configs using it pass validation cleanly.

## Motivation

This enhancement would:
- Prevent false-positive `additionalProperties` validation warnings for valid configs that use `extensions`
- Unblock ENH-1047: the config health check feature depends on correct schema validation — shipping it without this fix would flag every config using `extensions` as invalid
- Technical debt: fixes a latent schema bug introduced when the `extensions` block was placed, with no observable symptoms until validation is enforced

## Success Metrics

- `json.loads(schema)["properties"]["extensions"]` resolves without `KeyError`
- A `.ll/ll-config.json` containing `{"extensions": {...}}` produces no validation warnings
- Regression test `scripts/tests/test_config_schema.py` exists and asserts `extensions` is in `properties`

## Scope Boundaries

- **In scope**: Verify and fix `extensions` key placement within the `properties` block of `config-schema.json`; add a regression test asserting correct placement
- **Out of scope**: Other schema property fixes, validation logic changes, changes to the `.ll/ll-config.json` format itself, broader config schema refactoring, or unrelated `additionalProperties` violations

## API/Interface

N/A — No public API changes

## Proposed Solution

1. Read `config-schema.json` and verify whether `extensions` is inside or outside `properties`
2. If misplaced: move the `extensions` definition inside the `properties` block
3. Create `scripts/tests/test_config_schema.py` asserting `json.loads(schema)["properties"]["extensions"]` exists; follow structural pattern from `scripts/tests/test_generate_schemas.py:63-89`
4. Run `python -m pytest scripts/tests/test_config_schema.py -v` to confirm

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 result — bug confirmed**: `extensions` IS outside `properties`. Step 1 (verify) can be skipped; proceed directly to Step 2.

**Exact fix**: In `config-schema.json`, move the `extensions` block (lines 903-908) to inside the `properties` block before line 902's closing `},`. After the move, adjust surrounding commas so `extensions` is a valid last entry in `properties`.

**Template for `scripts/tests/test_config_schema.py`** (following `test_generate_schemas.py:63-89` and `test_update_skill.py:13-19`):

```python
"""Tests for config-schema.json structure."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_SCHEMA = PROJECT_ROOT / "config-schema.json"


class TestConfigSchema:
    """Regression guards for config-schema.json structure."""

    def test_schema_file_exists(self) -> None:
        """config-schema.json must exist at project root."""
        assert CONFIG_SCHEMA.exists(), f"config-schema.json not found: {CONFIG_SCHEMA}"

    def test_extensions_in_properties(self) -> None:
        """extensions key must be inside the properties block."""
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "properties" in data, "config-schema.json missing top-level properties block"
        assert "extensions" in data["properties"], (
            "extensions key is outside the properties block — "
            "any config using extensions would trigger additionalProperties violation"
        )
```

## Integration Map

### Files to Modify
- `config-schema.json:903-910` — verify and fix `extensions` placement within `properties`

### Files to Create
- `scripts/tests/test_config_schema.py` — regression guard asserting `extensions` is inside `properties`

### Tests
- `scripts/tests/test_generate_schemas.py:63-89` — structural pattern to follow for the new test file

_Wiring pass added by `/ll:wire-issue` (pass 2):_
- `scripts/tests/test_config_schema.py` — (created as part of this issue) 2 tests passing; optional additional guards to consider:
  - `test_schema_is_valid_json()` — explicit `json.loads()` guard asserting no `JSONDecodeError` (current tests assume valid JSON implicitly)
  - `test_additional_properties_is_false()` — regression guard for `additionalProperties: false` at top level (prevents recurrence of the misplacement)
  - Meta-field assertions for `$schema`, `$id`, `title` following `test_generate_schemas.py:70-80` pattern
- `scripts/tests/test_config.py` — no existing coverage of `BRConfig.extensions` property; consider adding test that loads an `ll-config.json` with `extensions` key and asserts `BRConfig.extensions` returns it (follow pattern at `test_config.py:462-466` for other top-level keys)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

**Python code — confirmed NO file currently loads `config-schema.json` directly** (Agent 2 verified zero Python consumers). Schema is consumed only by skills and IDE tooling.

**Runtime callers of `config.extensions` (Python property — not directly affected by schema fix):**
- `scripts/little_loops/cli/loop/run.py` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/parallel.py` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/__init__.py` — re-exports `wire_extensions` and the `extensions` subpackage symbols

**Skills that reference `config-schema.json` (no changes needed — fix makes schema correct for them):**
- `skills/audit-claude-config/SKILL.md:239-240,483` — validates `ll-config.json` against `config-schema.json`; after fix will correctly accept `extensions` key
- `skills/configure/SKILL.md:31` — references `config-schema.json` for defaults and validation rules
- `skills/init/SKILL.md:262,291` — emits `$schema` URL pointing to `config-schema.json`

**Templates (IDE autocomplete only — no changes needed):**
- `templates/python-generic.json:2`, `templates/typescript.json:2`, `templates/go.json:2`, `templates/rust.json:2`, and 5 others — all reference `config-schema.json` via `"$schema"` pointer; after fix, IDEs will offer `extensions` as a valid autocomplete key

**Downstream blocked issue:**
- `.issues/enhancements/P4-ENH-1047-add-config-health-check-step-to-ll-update-skill.md` — depends on ENH-1046; its health check reads `config-schema.json["properties"]` to find known keys

_Wiring pass added by `/ll:wire-issue` (pass 2):_
- `scripts/little_loops/extensions/__init__.py` — re-exports `ReferenceInterceptorExtension`; part of extensions sub-package gated by `extensions` config key (no changes needed)
- `scripts/little_loops/extensions/reference_interceptor.py` — reference interceptor class that users list under `extensions` in `ll-config.json` (no changes needed)
- `scripts/little_loops/fsm/executor.py:154` — calls `wire_extensions()` hook registry; indirectly part of extension loading path (no changes needed)
- `scripts/tests/test_config.py` — tests `config/core.py` which owns `LLConfig.extensions:178-180`; no coverage of the `extensions` property itself
- `scripts/tests/test_hooks_integration.py` — exercises lifecycle hooks that use extension wiring (no changes needed)
- `agents/consistency-checker.md:41,69` — validates `ll-config.json` against `config-schema.json`; after fix, correctly accepts `extensions` key without false-positive violations

**Side-effect note (informational):**
- `.issues/features/P5-FEAT-918-...md:162,354,452,576` — has stale line number references after this fix (`additionalProperties: false` moved from line 903 to 909; `extensions` block now at lines 902-907 not 896-901); does not affect correctness of the structural instruction

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional consumers identified:**
- `scripts/little_loops/config/core.py:178-180` — `LLConfig.extensions` property reads from `ll-config.json`; affected by false-positive validation at runtime when schema is wrong
- `scripts/little_loops/extension.py` — loads extension modules using the `extensions` config value
- `scripts/tests/test_extension.py` — extension loading tests (functional, not schema-level)
- `scripts/tests/test_interceptor_extension.py` — reference interceptor extension tests

**Test file conventions** (from `scripts/tests/test_update_skill.py:13` and `scripts/tests/test_generate_schemas.py:63-89`):
- Path resolution: `PROJECT_ROOT = Path(__file__).parent.parent.parent`
- Schema load: `json.loads((PROJECT_ROOT / "config-schema.json").read_text())`
- Assertion pattern: `assert "extensions" in data["properties"], "extensions outside properties block"`
- Grouping: class `TestConfigSchema` with one-line docstrings per method

### Similar Patterns
- `scripts/tests/test_generate_schemas.py:63-89` — existing schema structure assertion pattern to follow for new test

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue` (pass 2):_
- `docs/reference/CONFIGURATION.md:11,210,614-657` — documents `extensions` as valid top-level config key with full entry-point behavior reference; no text changes needed (docs already describe correct behavior, fix makes schema consistent with them)
- `docs/ARCHITECTURE.md:31,67` — references `config-schema.json` in mermaid diagram and directory tree; no changes needed
- `docs/reference/API.md` — documents `wire_extensions()` and `LLConfig.extensions`; no changes needed

### Configuration
- N/A — fix is to the schema definition file itself; no config format changes

## Implementation Steps

1. Read `config-schema.json` around lines 900-912 to confirm whether `extensions` is inside or outside `properties`
2. If misplaced: move the `extensions` block inside `properties` (before `additionalProperties: false`)
3. Create `scripts/tests/test_config_schema.py` with a single assertion: `assert "extensions" in json.loads(Path("config-schema.json").read_text())["properties"]`
4. Run tests to confirm pass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete steps (no "if" needed — bug confirmed):

1. **Confirmed**: `extensions` at `config-schema.json:903-908` is outside `properties` (which closes at line 902) — skip verify, go straight to fix
2. **Fix**: Move lines 903-908 into the `properties` block — insert before line 902's `},`; adjust surrounding commas
3. **Create** `scripts/tests/test_config_schema.py` — use template in Proposed Solution; `Path(__file__).parent.parent.parent / "config-schema.json"` resolves correctly from within `scripts/tests/`
4. **Run**: `python -m pytest scripts/tests/test_config_schema.py -v`

## Impact

- **Priority**: P4 — prerequisite to ENH-1047; low urgency on its own
- **Effort**: Small — read the schema, fix placement if needed, add one test
- **Risk**: Low — no behavior changes; fixes a latent schema bug
- **Breaking Change**: No

## Labels

`enhancement`, `config-schema`, `backlog`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22a916dd-1ac5-463a-a702-32213f1fb106.jsonl`
- `/ll:wire-issue` - 2026-04-12T00:22:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4b327ba3-7c3e-4006-abb7-60e05970f5fd.jsonl`
- `/ll:refine-issue` - 2026-04-12T00:17:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f87a1d1a-2de3-4399-b636-a019a11df0d3.jsonl`
- `/ll:format-issue` - 2026-04-12T00:14:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a319c6f4-5f29-42a5-823f-710649229b66.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b1168be-9a31-47c9-b0ae-3addb8ed046e.jsonl`
- `/ll:wire-issue` - 2026-04-11T23:50:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e91ec87-845e-4bd2-a082-d56e1f8290b5.jsonl`
- `/ll:refine-issue` - 2026-04-11T23:45:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0ada111-a97b-4fba-a14c-7991ffb760e0.jsonl`
- `/ll:format-issue` - 2026-04-11T23:42:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62a07b09-9beb-4aa9-bef0-579a2ca4ceb7.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1c66be5-a6d5-41db-b207-85921b3e11c7.jsonl`
