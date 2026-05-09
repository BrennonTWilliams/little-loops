---
discovered_date: 2026-05-09
discovered_by: audit
---

# ENH-1401: Wire product setup into `init` — create goals template and config

## Summary

`/ll:init` strips the `product` section from generated config and never creates `.ll/ll-goals.md`, even when product analysis is a desired first-class feature. The `ll-goals-template.md` template exists at `templates/ll-goals-template.md` but is never deployed. As a result, users who want product analysis must manually create the goals file and edit config — there's no guided path.

## Motivation

This enhancement would:
- Eliminate the manual setup gap: users currently need 2 extra steps (create goals file, edit config) before `/ll:scan-product` is usable
- Deploy `templates/ll-goals-template.md` which exists but is never reached by normal init flow
- Make product analysis a first-class feature with a guided opt-in path during init

## Goal

After `/ll:init`, a user should have everything needed to run `/ll:scan-product` without additional manual setup. This means:

1. `product.enabled: true` is included in the generated config (opt-in by default during init)
2. `.ll/ll-goals.md` is created from the template if product is enabled
3. The completion message directs users to customize their goals file

## Implementation Steps

### `skills/init/SKILL.md`

**Step 4 (Generate Configuration)**: Remove the instruction to strip the `product` section. Include `product.enabled: true` and `product.goals_file: ".ll/ll-goals.md"` in the generated config for all project types.

**Step 8 (Write Configuration)**: After writing `ll-config.json`, if `product.enabled` is `true` and `.ll/ll-goals.md` does not already exist:
```
Copy templates/ll-goals-template.md → .ll/ll-goals.md
(Read plugin-relative template path, Write to project .ll/ll-goals.md)
```

**Step 12 (Completion Message)**: Always show:
```
Created: .ll/ll-goals.md  ← customize with your product vision
```
and add to Next Steps:
```
2. Customize product goals: .ll/ll-goals.md
3. Run product scan: /ll:scan-product
```

### `skills/init/interactive.md` — Add Round 4: Product Analysis

Insert a new mandatory round between Round 3b and Round 5. Update `TOTAL` to 7.

```yaml
# Round 4: Product Analysis
question: "Would you like to enable product analysis? (Scans your codebase against product goals to find feature gaps and UX improvements)"
options:
  - label: "Yes, enable product analysis (Recommended)"
    description: "Creates .ll/ll-goals.md template and enables /ll:scan-product"
  - label: "No, skip"
    description: "You can enable later with /ll:configure product"
```

If "Yes": include `product: { enabled: true }` in config and create goals template.
If "No": omit `product` section from config entirely.

### Config output (when enabled):

```json
"product": {
  "enabled": true
}
```
(goals_file defaults to `.ll/ll-goals.md` — omit from config since it matches schema default)

## Success Metrics

- Zero manual steps needed after `/ll:init --yes` before `/ll:scan-product` runs successfully
- Interactive init presents the product round and creates the goals file when opted in
- Existing `.ll/ll-goals.md` files are never overwritten

## Scope Boundaries

- **In scope**: `skills/init/SKILL.md` config generation logic, goals file deployment step, completion message, `skills/init/interactive.md` Round 4 addition
- **Out of scope**: Changes to `scan-product` behavior, product-analyzer skill internals, or the content of `ll-goals-template.md` itself

## Acceptance Criteria

- `/ll:init --yes` creates `.ll/ll-goals.md` and sets `product.enabled: true`
- `/ll:init --interactive` asks the product round and respects the answer
- If `.ll/ll-goals.md` already exists, init does not overwrite it
- Completion message shows the goals file and next-step guidance
- `/ll:init --dry-run` shows `[write] .ll/ll-goals.md` in the actions list

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 4 (remove product strip), Step 8 (add goals file deploy), Step 12 (update completion message)
- `skills/init/interactive.md` — add Round 4 between Round 3b and Round 5, update TOTAL to 7

### Dependent Files (Callers/Importers)
- `templates/ll-goals-template.md` — read-only source; copied to `.ll/ll-goals.md` during init

### Similar Patterns
- TBD - use grep: `grep -r "ll-goals" skills/` to find other references to the goals file

### Tests
- TBD - identify test files that exercise init flow

### Documentation
- TBD - docs referencing product setup steps that may need updating

### Configuration
- N/A

## Evidence

- `skills/init/SKILL.md:118` — "Strip the `_meta`, `$schema`, and `product` sections"
- `skills/init/SKILL.md:546` — completion message references goals file only conditionally, but step 8 never creates it
- `templates/ll-goals-template.md` — template exists but is never deployed


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32deefa2-352e-4fa9-a9df-ce9aad495a16.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): This issue's scope is specifically for new projects created via `/ll:init` going forward. ENH-1400 (implement goals discovery in product-analyzer) addresses the complementary case: existing/legacy projects that were initialized before this change and have no `ll-goals.md`. The two issues are not redundant — this issue prevents the missing-goals-file problem for future projects; ENH-1400 provides the retrofit fallback for projects already in place.
