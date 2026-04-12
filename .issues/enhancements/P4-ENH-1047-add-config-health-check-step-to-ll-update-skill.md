---
id: ENH-1047
type: ENH
priority: P4
status: backlog
discovered_date: 2026-04-11
discovered_by: issue-size-review
parent_issue: ENH-1040
depends_on: ENH-1046
confidence_score: 90
outcome_confidence: 100
---

# ENH-1047: Add Config Health Check step to `ll:update` skill

## Summary

Add a **Step 6: Config Health Check** to `skills/update/SKILL.md` that runs after a successful update and validates `.ll/ll-config.json` against `config-schema.json`. Reports unknown/additional keys and type mismatches; prints `[PASS] ll-config.json is valid` or `[WARN] Config issues detected`.

## Parent Issue

Decomposed from ENH-1040: Add post-update config health check to ll:update

## Depends On

ENH-1046 — `extensions` schema placement must be fixed first to avoid false-positive `[WARN]` for valid configs using `extensions`

## Current Behavior

`/ll:update` upgrades the plugin and pip package but never validates the user's `.ll/ll-config.json`. If a key is renamed in a new version, it silently stops having any effect.

## Expected Behavior

After updating (when `PLUGIN_RESULT` or `PACKAGE_RESULT` starts with "PASS"), Step 6 runs:
1. Locates `.ll/ll-config.json`; silently skips if not present
2. Validates using stdlib set-subtraction (no new dependency): `unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS` pattern from `scripts/little_loops/fsm/validation.py:484-493`
3. Prints `[WARN] Config issues detected` with each unknown key, or `[PASS] ll-config.json is valid`
4. Non-blocking — check failure does not fail the overall update

## Motivation

This enhancement would:
- **Silent config rot prevention**: When `ll:update` renames config keys between versions, users' existing `.ll/ll-config.json` silently stops having any effect — no error, no warning, just unexpected behavior with no clear cause.
- **Immediate feedback loop**: A post-update health check catches the mismatch at the moment it's introduced, before the next usage session, reducing debugging time.
- **Low-risk instrumentation**: The check is read-only and non-blocking — it cannot fail the update or change any state.

## Success Metrics

- `[WARN] Config issues detected` is printed when `.ll/ll-config.json` has unknown keys
- `[PASS] ll-config.json is valid` is printed with no false positives for a valid config
- Validation completes in < 1s
- Silently skips when `.ll/ll-config.json` is not present

## Scope Boundaries

- **In scope**: Validating top-level keys in `.ll/ll-config.json` against `config-schema.json["properties"]`; printing `[PASS]` or `[WARN]` output tokens; silently skipping when `.ll/ll-config.json` is absent
- **Out of scope**: Deep/nested property validation; automatic config migration or key renaming; validating config _before_ the update runs; reporting type mismatches (beyond unknown-key detection); supporting configs other than `.ll/ll-config.json`

## Proposed Solution

### Step 6 implementation in `skills/update/SKILL.md`

Insert after line 174 (the `---` separator after Step 5 Summary Report), conditioned on either `PLUGIN_RESULT` or `PACKAGE_RESULT` starting with "PASS":

```markdown
## Step 6: Config Health Check

If either `PLUGIN_RESULT` or `PACKAGE_RESULT` starts with "PASS":

1. Check whether `.ll/ll-config.json` exists; if not, print nothing and skip.
2. Read `.ll/ll-config.json` (use `scripts/little_loops/config/core.py:87-93` pattern).
3. Extract top-level keys from `config-schema.json["properties"]` as the known key set.
4. Compute unknown keys: `unknown = set(user_config.keys()) - known_keys`.
5. If `unknown` is non-empty: print `[WARN] Config issues detected` followed by each unknown key.
6. If `unknown` is empty: print `[PASS] ll-config.json is valid`.

Use `python3 -c` inline pattern (established at `SKILL.md:68`). Non-blocking — do not raise on errors.
```

### Actual `python3 -c` command for Step 6

`config-schema.json` is **not** bundled in the `little_loops` Python package (wheel contains only `fsm-loop-schema.json`). It lives in the Claude Code plugin install cache. Locate it via `~/.claude/plugins/installed_plugins.json`:

```bash
python3 -c "
import json, pathlib, sys

config_path = pathlib.Path('.ll/ll-config.json')
if not config_path.exists():
    sys.exit(0)

# Locate config-schema.json via plugin installation registry
plugins_file = pathlib.Path.home() / '.claude' / 'plugins' / 'installed_plugins.json'
if not plugins_file.exists():
    sys.exit(0)
plugins = json.loads(plugins_file.read_text()).get('plugins', {})
entry = plugins.get('ll@little-loops', [])
if not entry:
    sys.exit(0)
schema_path = pathlib.Path(entry[0]['installPath']) / 'config-schema.json'
if not schema_path.exists():
    sys.exit(0)

config = json.loads(config_path.read_text())
schema = json.loads(schema_path.read_text())
known = set(schema.get('properties', {}).keys())
unknown = sorted(set(config.keys()) - known)
if unknown:
    print('[WARN] Config issues detected: unknown keys: ' + ', '.join(unknown))
else:
    print('[PASS] ll-config.json is valid')
" 2>/dev/null || true
```

All `sys.exit(0)` guards are intentional — non-blocking, silent skips on missing files.

### Output tokens

Use `[PASS]` and `[WARN]`. Note: `[WARN]` is a **new** token — it does not exist in the current skill. `[PASS]` already appears at `SKILL.md:102` and `:142`; `[FAIL]` and `[DRY-RUN]` also exist. `[WARN]` must be added to the Step 5 status key table as well (after the `DRY-RUN` row at `SKILL.md:169`).

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add Step 6 after line 174
- `scripts/tests/test_update_skill.py:72-79` — add `assert "WARN" in content` to `test_skill_has_summary_report`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md:209` — lists `/ll:update [flags]` in the help command registry; no modification needed (Step 6 is internal behavior, not a new flag)

### Files to Create
- *(none — ENH-1046 creates `test_config_schema.py`)*

### New Test Class
Add `TestUpdateSkillHealthCheck` to `scripts/tests/test_update_skill.py`:
```python
class TestUpdateSkillHealthCheck:
    def test_has_health_check_step(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Step 6" in content
        assert "Config Health Check" in content
        assert "[PASS] ll-config.json is valid" in content
        assert "WARN" in content
```
No fixture parameter — use module-level `SKILL_FILE` constant directly (defined at `test_update_skill.py:15`; class convention starts at `:22`). There is no `skill_file` fixture in this test file.

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:484-493` — stdlib-only unknown-key detection (set subtraction)
- `scripts/little_loops/doc_counts.py:110-157` — scan → compare → return typed result with `all_match: bool`
- `scripts/little_loops/config/core.py:87-93` — canonical `.ll/ll-config.json` reader

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `config-schema.json` is **not** in the `little_loops` Python package (wheel only bundles `little_loops/fsm/fsm-loop-schema.json`); it is installed at `~/.claude/plugins/cache/little-loops/ll/<version>/config-schema.json`
- Plugin install path is discoverable at runtime via `~/.claude/plugins/installed_plugins.json` → `plugins['ll@little-loops'][0]['installPath']`
- `SKILL_FILE` module constant at `test_update_skill.py:15`; `TestUpdateSkillExists` class at `:22`; no `skill_file` pytest fixture exists — all tests call `SKILL_FILE.read_text()` directly
- `PLUGIN_RESULT` and `PACKAGE_RESULT` initialized to `"SKIP"` at `skills/update/SKILL.md:60-61`; set to `"PASS (...)"`, `"FAIL"`, or `"DRY-RUN"` in Steps 3–4; the `[[ "$VAR" == PASS* ]]` bash pattern matches the `"PASS (...)"` format
- `[WARN]` token is absent from `skills/update/SKILL.md` entirely — it is a net-new addition; Step 5 status key table at `SKILL.md:165-169` must gain a `WARN` row alongside PASS/SKIP/FAIL/DRY-RUN
- **`config-schema.json` is currently invalid JSON** (not just a misplaced key): line 909 has a stray `  }` that prematurely closes the root object, leaving `,"additionalProperties": false\n}` as orphaned "Extra data". `json.loads(schema_path.read_text())` will raise `JSONDecodeError` until ENH-1046 moves `extensions` back inside `properties` and removes the extra `}`. The `2>/dev/null || true` pattern in the proposed command handles this silently (no output, no crash) — but the health check will produce **no output at all** until ENH-1046 is implemented. To test Step 6 locally before ENH-1046 is done, manually fix the schema first.
- Known top-level `properties` keys in the schema (once ENH-1046 is fixed): `$schema`, `project`, `issues`, `automation`, `parallel`, `commands`, `scan`, `prompt_optimization`, `continuation`, `context_monitor`, `scratch_pad`, `documents`, `product`, `sprints`, `loops`, `refine_status`, `dependency_mapping`, `sync`, `cli`, `extensions` — the `$schema` key in `.ll/ll-config.json` is covered and will NOT trigger a false-positive `[WARN]`

## Implementation Steps

1. **Add Step 6** to `skills/update/SKILL.md` after the `---` separator at line 174 using the `python3 -c` inline script from the Proposed Solution
2. **Locate schema via `installed_plugins.json`**: `~/.claude/plugins/installed_plugins.json` → `plugins['ll@little-loops'][0]['installPath']` → append `/config-schema.json`; silently skip if any path is missing
3. **Condition on success**: Step 6 only runs when `PLUGIN_RESULT` or `PACKAGE_RESULT` starts with `"PASS"` (use `[[ "$PLUGIN_RESULT" == PASS* ]] || [[ "$PACKAGE_RESULT" == PASS* ]]`)
4. **Output tokens**: `[PASS] ll-config.json is valid` or `[WARN] Config issues detected: unknown keys: <key1>, <key2>`
5. **Update Step 5 status key table** at `SKILL.md:165-169`: add `WARN      — Config has unknown keys (check ll-config.json)` row
6. **Update `test_skill_has_summary_report`** at `test_update_skill.py:72-79`: add `assert "WARN" in content`
7. **Add `TestUpdateSkillHealthCheck`** class to `test_update_skill.py` (no fixture — use `SKILL_FILE.read_text()` directly per `:15` constant)
8. **Run tests**: `python -m pytest scripts/tests/test_update_skill.py -v`

## Impact

- **Priority**: P4 — useful catch; not blocking
- **Effort**: Small — one skill file edit + test additions
- **Risk**: Low — read-only check, non-blocking
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `config`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:wire-issue` - 2026-04-12T00:23:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22a916dd-1ac5-463a-a702-32213f1fb106.jsonl`
- `/ll:refine-issue` - 2026-04-12T00:17:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4b327ba3-7c3e-4006-abb7-60e05970f5fd.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8100eaa2-e0c8-468c-9fe0-101f7a401771.jsonl`
- `/ll:wire-issue` - 2026-04-12T00:03:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cc6387c-e0c6-4503-a1a8-88e95b78d4a0.jsonl`
- `/ll:refine-issue` - 2026-04-11T23:59:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a29d508-c296-40fa-a3fe-f13e68603d46.jsonl`
- `/ll:format-issue` - 2026-04-11T23:53:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/724f1c58-106c-47fd-98d9-4c658e8ddec9.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1c66be5-a6d5-41db-b207-85921b3e11c7.jsonl`
