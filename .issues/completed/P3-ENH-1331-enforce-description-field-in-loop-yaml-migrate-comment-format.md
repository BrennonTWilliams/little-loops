---
captured_at: "2026-05-02T19:50:27Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
---

# ENH-1331: Enforce description: field in loop YAML; migrate comment-based descriptions

## Summary

The `/ll:analyze-loop` skill's Step 3b-1 reads the loop's declared goal from
`ll-loop show <name> --json`, expecting a top-level `description` key in the
JSON output. `cmd_show --json` delegates to `fsm.to_dict()`, which only emits
`description` when `FSMLoop.description is not None` — and that field is
populated solely from the parsed YAML value `data.get("description")`. A
comment such as `# Description: my goal` at the top of a loop YAML file is
invisible to the YAML parser, so the field is always `None` and the skill
reports "(no description provided)" even when intent text exists in the file.

The fix is two-pronged:

1. **Enforce the `description:` field** as a required YAML field in new loops.
   `ll:create-loop` already emits it; templates and docs should make it
   explicit.
2. **Migrate existing violations** — scan built-in and project loops for files
   that lack a `description:` key (or use `# Description:` comments) and
   normalize them to use the proper YAML field.

Optionally add comment-parsing as a fallback in `_load_loop_meta` /
`load_loop_with_spec` to handle user-written loops in external projects that
can't be migrated here.

## Current Behavior

When a built-in loop YAML file uses a comment (`# Description: my goal`) instead
of a YAML key, the YAML parser ignores it. `FSMLoop.description` is always `None`
in this case. `ll-loop show <name> --json` omits the `"description"` key entirely,
and `/ll:analyze-loop` reports "(no description provided)" in Step 3b-1 even though
intent text exists in the file.

## Expected Behavior

All built-in loop YAML files have a top-level `description:` key. `ll-loop show
<name> --json` always includes `"description"` for built-in loops. `/ll:analyze-loop`
reads a non-empty goal in Step 3b-1 for every built-in loop. `ll-loop validate`
emits a warning when a loop file is missing the `description:` field.

## Motivation

Without a machine-readable description, `analyze-loop` cannot perform goal
alignment assessment (Step 3b-3), which is one of the skill's most valuable
outputs. All built-in loops should serve as a reference implementation, so
they must all carry a proper `description:` field.

## Scope Boundaries

- **In scope**: Auditing all built-in loop YAML files for missing `description:` keys; migrating `# Description:` comments to proper `description: |` YAML fields; adding a missing-description warning to `ll-loop validate`; optional comment-parsing fallback in `_load_loop_meta` / `load_loop_with_spec` for externally-managed loops.
- **Out of scope**: Changing the storage format or schema of user-managed project loop files; modifying FSM evaluation logic; enforcing the field in existing third-party extensions that cannot be migrated here.

## Implementation Steps

1. **Audit**: run `grep -rL "^description:" scripts/little_loops/loops/*.yaml`
   to find built-in loops missing the field.
2. **Migrate built-in loops**: add or promote `# Description:` comments to
   proper `description: |` YAML fields for any flagged files.
3. **Optional fallback**: in `_load_loop_meta` (and `load_loop_with_spec` if
   appropriate), scan raw YAML text for a `^# Description:` comment and inject
   it into the spec dict before `yaml.safe_load` — so externally-managed
   project loops still work.
4. **Validation in `ll-loop validate`**: emit a warning when a loop file has no
   `description:` key.
5. **`ll:create-loop` template check**: confirm all wizard-generated templates
   include the `description:` field (already true as of writing; add a test).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/*.yaml` — built-in loops (audit + migrate)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop_with_spec` (optional fallback)
- `scripts/little_loops/cli/loop/info.py` — `_load_loop_meta` (optional fallback)
- `scripts/little_loops/fsm/validation.py` — add missing-description warning
- `skills/create-loop/SKILL.md` — confirm template includes field (doc note)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` imports `_load_loop_meta` (same file)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop_with_spec` called by `ll-loop run`, `ll-loop show`
- Skills that call `ll-loop show --json`: `skills/analyze-loop/SKILL.md`

### Similar Patterns
- TBD - check other YAML loaders in `scripts/little_loops/` for comment-parsing patterns

### Tests
- TBD - add/update tests for `ll-loop show <name> --json` to assert `"description"` present
- TBD - add test for `ll-loop validate` warning when `description:` absent
- TBD - add test for `ll:analyze-loop` Step 3b-1 goal reading

### Documentation
- `skills/create-loop/SKILL.md` — confirm template section already includes `description:` field

### Configuration
- N/A

## Acceptance Criteria

- [ ] All built-in loop YAML files have a `description:` field (no comment-only descriptions)
- [ ] `ll-loop show <name> --json` always includes `"description"` for built-in loops
- [ ] `/ll:analyze-loop` Step 3b-1 reads a non-empty goal for all built-in loops
- [ ] `ll-loop validate <name>` emits a warning when `description:` is absent
- [ ] (Optional) `_load_loop_meta` falls back to `# Description:` comment for externally-managed loops

## API/Interface

N/A - No public API changes. The optional comment-parsing fallback in `_load_loop_meta` is internal to the CLI and backward compatible (additive behavior only).

## Impact

- **Priority**: P3 - Quality improvement; doesn't block core loop functionality but degrades `analyze-loop` goal alignment for all built-in loops
- **Effort**: Small - YAML field additions are mechanical; validation check and optional fallback are isolated
- **Risk**: Low - Additive changes; promoting a comment to a YAML key is non-breaking for all consumers
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-05-02T19:54:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c7505b5-ede1-476a-a6b7-a18e3c4c8571.jsonl`
