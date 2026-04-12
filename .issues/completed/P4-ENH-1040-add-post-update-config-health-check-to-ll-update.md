---
id: ENH-1040
type: ENH
priority: P4
status: backlog
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 72
---

# ENH-1040: Add post-update config health check to ll:update

## Summary

After running `/ll:update`, the skill should perform a lightweight validation of `.ll/ll-config.json` against the current schema and flag any unknown or invalid keys. This catches silent breakage from key renames or removals introduced in a new plugin version.

## Current Behavior

`/ll:update` upgrades the plugin and pip package but does nothing with the user's `.ll/ll-config.json`. If an update renames or removes a config key, the user's config silently stops having any effect — no warning is emitted.

## Expected Behavior

After updating, `/ll:update` runs a fast schema validation pass and reports:
- **Unknown keys**: keys present in the user's config that no longer exist in the schema (likely renamed/removed)
- **Invalid values**: keys whose values violate the schema type/enum (e.g., a string where a boolean is now expected)

It does **not** enumerate missing optional fields — those have defaults and their absence is intentional.

## Success Metrics

- **Unknown key detected**: `[WARN] Config issues detected` block is printed listing each key and the problem
- **Valid config**: `[OK] ll-config.json is valid` is printed with no false positives
- **Performance**: Validation completes in < 1s (non-blocking to the overall update flow)
- **No-op when absent**: Silently skips when `.ll/ll-config.json` is not present (non-ll projects unaffected)

## Motivation

A renamed config key is a silent footgun. The user ran an update, everything appears to succeed, but a feature they rely on (e.g., `commands.tdd_mode`, `sprints.default_max_workers`) is now ignored because the key was renamed. Without a post-update check, users only discover this when something stops working — and the cause isn't obvious. The check is low-effort to add (one `jsonschema` call) and high-value when it fires.

## Scope Boundaries

- **In scope**: Schema validation pass after plugin/package update in `ll:update`; reporting unknown/additional properties and type mismatches in `.ll/ll-config.json`
- **Out of scope**: Auto-migrating or repairing invalid config keys (read-only check only); validating config on every command run (post-update only); reporting missing optional fields (intentional absence is fine); generating a suggested migration diff

## Proposed Solution

Add a **Step 5: Config Health Check** to `skills/update/SKILL.md`, executed after the summary report if either plugin or package was updated (not skipped/failed):

1. Locate `.ll/ll-config.json` in the project root; skip silently if not found (non-ll-project).
2. Fetch the current schema via `python3 -c "import importlib.resources; ..."` or read from the installed package.
3. Run `python3 -m jsonschema --instance .ll/ll-config.json <schema>` (or equivalent programmatic call).
4. Filter results to **unknown/additional properties** and **type mismatches** only — suppress "missing required property" noise (almost nothing is required).
5. If violations found: print a `[WARN] Config issues detected` block listing each key and the problem.
6. If clean: print `[OK] ll-config.json is valid`.

The check should be fast (< 1s), non-blocking (failures don't fail the update), and scoped to structural problems only.

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add new **Step 6: Config Health Check** after the current Summary Report (Step 5 at lines 152–172); the step is conditioned on `PLUGIN_RESULT` or `PACKAGE_RESULT` starting with "PASS"

### Dependent Files (Callers/Importers)
- `config-schema.json:910` — `additionalProperties: false` at top level; the schema to validate against; **not bundled in the pip package** — lives at the plugin source root only
- `.ll/ll-config.json` — the file being validated (user-owned, not in this repo)
- `scripts/pyproject.toml:37-40` — runtime dependencies (`pyyaml`, `wcwidth` only); **`jsonschema` is not currently a dependency** — `python3 -m jsonschema` won't work without adding it

_Wiring pass added by `/ll:wire-issue`:_
- `skills/audit-claude-config/SKILL.md:239-240` — instructs validation of `.ll/ll-config.json` against `config-schema.json` in its Task 3 subagent prompt; fixing `extensions` misplacement in Step 2 changes this skill's validation output for configs that use `extensions`
- `agents/consistency-checker.md:41,69` — includes a `ll-config.json` vs `config-schema.json` consistency check row; the schema fix makes its output accurate for `extensions`-using configs

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:484-493` — stdlib-only unknown-key detection via set subtraction (`unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS`); a viable no-dependency alternative to `jsonschema`
- `scripts/little_loops/doc_counts.py:110-157` — `verify_documentation()` structural model: scan → compare → return typed result with `all_match: bool`; silently skips missing files at line 136 (mirrors "no-op when absent" requirement)
- `scripts/little_loops/config/core.py:87-93` — `BRConfig._load_config()` — canonical pattern for reading `.ll/ll-config.json`; returns `{}` silently when absent
- `ll-verify-docs` validates documented counts against actual counts — same "lightweight post-op sanity check" pattern
- `P4-ENH-905` adds "skip if already current" to update — companion improvement to the same skill

### Tests
- `scripts/tests/test_update_skill.py` — model for skill content assertions (`assert "PASS" in content`, etc.); tests to add: assert Step 6 section exists, `[WARN]` and `[PASS]` tokens are present
- `scripts/tests/conftest.py:56-121` — `temp_project_dir` + `config_file` fixtures; use for mocking configs with unknown keys
- Integration: run against this repo's own `.ll/ll-config.json` and expect clean output

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_update_skill.py:72-79` — UPDATE `test_skill_has_summary_report`: add `assert "WARN" in content` alongside existing PASS/FAIL/SKIP/DRY-RUN assertions; Step 6 introduces `[WARN]` token not yet asserted (test does not assert `WARN` absence, so no break — but the assertion is needed for correctness)
- `TestUpdateSkillHealthCheck` class (new, in `test_update_skill.py`) — assert `"Step 6"`, `"Config Health Check"`, `"[PASS] ll-config.json is valid"`, and `"WARN"` in `SKILL_FILE.read_text()`; follow class + `read_text()` convention established at `test_update_skill.py:25`
- `scripts/tests/test_config_schema.py` (new) — assert `json.loads(config_schema)["properties"]["extensions"]` exists, guarding against regression of the Step 2 `extensions`-placement fix; follow structural pattern from `test_generate_schemas.py:63-89`

### Documentation
- N/A — no user-facing docs reference the update health check step

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:52-63` — existing `/ll:update` section documents current flags (`--plugin`, `--package`, `--all`, `--dry-run`); out of scope per issue boundaries (check adds no new flags), but listed here for completeness

### Configuration
- N/A — no configuration keys are added; the check is opt-out-by-absence (silently skips when `.ll/ll-config.json` is not present)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step numbering correction**: The issue says "Step 5" but the current `skills/update/SKILL.md:152` already defines Step 5 as the Summary Report. The new check should be **Step 6**, inserted after line 174 (`---` separator after the summary block).
- **`[OK]` vs `[PASS]` token**: The update skill uses `[PASS]`/`[FAIL]`/`[SKIP]`/`[DRY-RUN]` tokens throughout. Using `[OK]` would be inconsistent — use `[PASS] ll-config.json is valid` instead.
- **`jsonschema` dependency gap**: `python3 -m jsonschema` requires `jsonschema` to be installed, which it currently is not (`pyproject.toml:37-40`). Either add `jsonschema>=4.0` to `dependencies`, or use the stdlib-only set-subtraction approach from `fsm/validation.py:484-493` (no new dependency needed).
- **Schema location at runtime**: `config-schema.json` lives at the plugin source root, not bundled into the pip package. The skill can locate it via the plugin directory path (e.g., relative to `claude plugin path ll` output) rather than `importlib.resources`.
- **`extensions` false-positive risk**: The `extensions` key at `config-schema.json:903-908` appears placed *outside* the `properties` block (a sibling rather than a member). Validating `.ll/ll-config.json` with `jsonschema` against this schema would flag `extensions` as an additionalProperties violation even for valid configs that use it. Verify this before shipping — may require a schema fix or a key allowlist.
- **`python3 -c` pattern**: Already established in `skills/update/SKILL.md:68` and `skills/configure/SKILL.md:58-62` as `python3 -c "import importlib.metadata; ..."` — the same inline Python approach should be used for the validation check.

## API/Interface

N/A — No public API changes. The check is an internal step added to `skills/update/SKILL.md`; it has no new function signatures, CLI arguments, or data schemas exposed to callers.

## Implementation Steps

1. **Decision: dependency vs stdlib** — Choose between adding `jsonschema>=4.0` to `scripts/pyproject.toml:37-40` (enables full schema validation) or using the stdlib set-subtraction pattern from `scripts/little_loops/fsm/validation.py:484-493` (no new dep, catches unknown keys only, misses type violations)
2. **Fix `extensions` schema placement** (`config-schema.json:903-908`) — verify whether `extensions` is correctly nested inside `properties`; fix before adding validation to avoid false-positive WARNs for valid configs
3. **Add Step 6 to `skills/update/SKILL.md`** — insert after line 174 (the `---` separator after the Summary Report); condition on `PLUGIN_RESULT` or `PACKAGE_RESULT` starting with "PASS"; use `python3 -c` inline pattern (established at `SKILL.md:68`) to load `.ll/ll-config.json` and validate
4. **Output tokens** — use `[PASS] ll-config.json is valid` and `[WARN] Config issues detected` (not `[OK]`) to match existing token convention in the skill
5. **Add tests to `scripts/tests/test_update_skill.py`** — assert Step 6 section heading and `[WARN]`/`[PASS]` tokens are present in `SKILL.md` content; use `conftest.py:56-121` `temp_project_dir` fixture for any integration-level tests
6. **Verify no regressions** with `python -m pytest scripts/tests/test_update_skill.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_update_skill.py:72-79` — add `assert "WARN" in content` to `test_skill_has_summary_report` alongside existing PASS/FAIL/SKIP/DRY-RUN assertions
8. Add `TestUpdateSkillHealthCheck` class to `scripts/tests/test_update_skill.py` — assert `"Step 6"`, `"Config Health Check"`, `"[PASS] ll-config.json is valid"`, and `"WARN"` in `SKILL_FILE.read_text()`; follow class structure at line 25
9. Create `scripts/tests/test_config_schema.py` — assert `json.loads(schema)["properties"]["extensions"]` exists after Step 2 fix; follow `test_generate_schemas.py:63-89` structural assertion pattern

## Impact

- **Priority**: P4 — useful catch, but not blocking; users currently survive without it
- **Effort**: Small — adding a section to one skill file + a Python one-liner
- **Risk**: Low — read-only check, no mutations
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll:update`, `config`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- `skills/update/SKILL.md` exists ✓
- No "Step 5: Config Health Check" section in the update skill ✓
- Feature not yet implemented

## Session Log
- `/ll:confidence-check` - 2026-04-11T23:50:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8aa6ceaf-d9fb-4c1a-81d0-c2dba07ea652.jsonl`
- `/ll:wire-issue` - 2026-04-11T23:36:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c38386d1-6762-4fa8-bae4-7e6c7d87a79c.jsonl`
- `/ll:refine-issue` - 2026-04-11T23:30:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aae91033-bf21-4128-9943-0b0de35d7ab1.jsonl`
- `/ll:format-issue` - 2026-04-11T23:26:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc26f87f-4d80-4178-9160-efa8588edd13.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:capture-issue` - 2026-04-11T20:12:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6eeb90e-db91-4253-be84-397f6e9dfaa1.jsonl`
