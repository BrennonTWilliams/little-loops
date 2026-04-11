---
id: ENH-1040
type: ENH
priority: P4
status: backlog
discovered_date: 2026-04-11
discovered_by: capture-issue
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

## Motivation

A renamed config key is a silent footgun. The user ran an update, everything appears to succeed, but a feature they rely on (e.g., `commands.tdd_mode`, `sprints.default_max_workers`) is now ignored because the key was renamed. Without a post-update check, users only discover this when something stops working — and the cause isn't obvious. The check is low-effort to add (one `jsonschema` call) and high-value when it fires.

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
- `skills/update/SKILL.md` — add Step 5 section after the summary report

### Dependent Files (Callers/Importers)
- `config-schema.json` — the schema the check validates against
- `.ll/ll-config.json` — the file being validated (user-owned, not in this repo)

### Similar Patterns
- `ll-verify-docs` validates documented counts against actual counts — same "lightweight post-op sanity check" pattern
- `P4-ENH-905` adds "skip if already current" to update — companion improvement to the same skill

### Tests
- Unit: mock a config with an unknown key, verify the check emits a WARN
- Unit: mock a valid config, verify the check emits OK
- Integration: run against this repo's own `.ll/ll-config.json` and expect clean output

## Implementation Steps

1. Add `jsonschema` validation logic (Python one-liner or small helper) to the update skill's Step 5 section
2. Filter output to additionalProperties violations and type errors only
3. Wire into the skill: run after summary, only when at least one component was updated
4. Test against this repo's config and a synthetic config with a bad key

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
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:capture-issue` - 2026-04-11T20:12:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6eeb90e-db91-4253-be84-397f6e9dfaa1.jsonl`
