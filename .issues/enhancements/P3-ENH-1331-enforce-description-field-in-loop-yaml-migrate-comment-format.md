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

## Motivation

Without a machine-readable description, `analyze-loop` cannot perform goal
alignment assessment (Step 3b-3), which is one of the skill's most valuable
outputs. All built-in loops should serve as a reference implementation, so
they must all carry a proper `description:` field.

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

## Affected Files

- `scripts/little_loops/loops/*.yaml` — built-in loops (audit + migrate)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop_with_spec` (optional fallback)
- `scripts/little_loops/cli/loop/info.py` — `_load_loop_meta` (optional fallback)
- `scripts/little_loops/fsm/validation.py` — add missing-description warning
- `skills/create-loop/SKILL.md` — confirm template includes field (doc note)

## Acceptance Criteria

- [ ] All built-in loop YAML files have a `description:` field (no comment-only descriptions)
- [ ] `ll-loop show <name> --json` always includes `"description"` for built-in loops
- [ ] `/ll:analyze-loop` Step 3b-1 reads a non-empty goal for all built-in loops
- [ ] `ll-loop validate <name>` emits a warning when `description:` is absent
- [ ] (Optional) `_load_loop_meta` falls back to `# Description:` comment for externally-managed loops

## Labels

`enhancement`, `loops`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3
