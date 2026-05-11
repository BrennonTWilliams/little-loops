---
discovered_date: 2026-05-09
discovered_by: audit
confidence_score: 95
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
completed_at: 2026-05-11T09:06:29Z
---

# ENH-1401: Wire product setup into `init` — create goals template and config

## Summary

`/ll:init` strips the `product` section from generated config and never creates `.ll/ll-goals.md`, even when product analysis is a desired first-class feature. The `ll-goals-template.md` template exists at `templates/ll-goals-template.md` but is never deployed. As a result, users who want product analysis must manually create the goals file and edit config — there's no guided path.

## Current Behavior

`/ll:init` (both `--yes` and `--interactive` modes) strips the `product` section entirely from the generated `ll-config.json`. The `templates/ll-goals-template.md` file exists but is never copied to `.ll/ll-goals.md`. Users who want to run `/ll:scan-product` must manually: (1) edit `ll-config.json` to add `product.enabled: true`, and (2) copy the goals template to `.ll/ll-goals.md`.

## Expected Behavior

After `/ll:init --yes`, the generated config includes `product.enabled: true` and `.ll/ll-goals.md` is created from the template automatically. After `/ll:init --interactive`, a new Round 4 asks whether to enable product analysis and creates the goals file if the user opts in. The completion message directs users to customize their goals file. Existing `.ll/ll-goals.md` files are never overwritten.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Write `scripts/tests/test_enh1401_doc_wiring.py` — new doc-wiring test file with `TestInitSkillProductSetup` and `TestInitInteractiveProductRound` classes (follow pattern in `scripts/tests/test_enh1421_doc_wiring.py`)
5. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:167` — remove or qualify the manual `ll-goals.md` copy instruction; note that `/ll:init` now handles this for new projects
6. Update `docs/reference/CONFIGURATION.md` — locate the `### Manual Configuration` section and remove `product` from the "not exposed through `/ll:init`" list

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
- `hooks/scripts/session-start.sh` — `validate_enabled_features()` (lines 134–143): checks `product.enabled` + file existence, warns if absent; ENH-1401 ensures fresh `--yes` init never triggers this warning [Wiring pass]
- `commands/scan-product.md` — `### Step 1: Validate Prerequisites`: gates on `product.enabled` (Step 1.1) and physical file existence (Step 1.2); both conditions now satisfied for new installs — behavioral unlock, no text change [Wiring pass]
- `skills/product-analyzer/SKILL.md` — `## Guardrails`: hard-stop when `ll-goals.md` absent; upstream path to this stop is removed for new installs — behavioral unlock, no text change [Wiring pass]

### Similar Patterns
- `skills/init/SKILL.md:308-329` (Step 9: Update .gitignore) — existence guard pattern: check if file exists, skip if already present, otherwise create/append; use this same guard for `.ll/ll-goals.md`
- `skills/init/SKILL.md:477-509` (Step 11: Update CLAUDE.md) — more explicit duplicate guard: read file, search for marker string, skip if found, write otherwise
- `skills/init/interactive.md` (Round 6: Document Tracking) — nearest structural analog for Round 4; mandatory single-question round with binary opt-in, recommended first option, conditional config injection, and "Skip" option omits section entirely
- `skills/init/SKILL.md:294-301` (Step 8: Write Configuration) — `Omit product section if user selected "No, skip"` is already in the conditional omit list; the `--yes` path must be updated to default to *including* product rather than omitting it
- Template copy mechanism: Claude reads plugin-relative `templates/ll-goals-template.md` with the Read tool and writes content to project-relative `.ll/ll-goals.md` with the Write tool — no shell `cp` command (confirmed by `thoughts/shared/plans/2026-01-22-FEAT-020-management.md:299-302`)

### Tests
- `scripts/tests/test_goals_parser.py:445` — reads `templates/ll-goals-template.md` directly to verify it parses cleanly; ensure template content remains valid after any template changes
- `scripts/tests/test_hooks_integration.py:1650-1667` (`test_warns_product_without_goals`) — tests that `session-start.sh` emits a warning when `product.enabled: true` but goals file is absent; after ENH-1401 a fresh `--yes` init should never trigger this warning
- `scripts/tests/test_hooks_integration.py:1671` (`test_no_warnings_when_properly_configured`) — asserts no warning when `product.enabled: true` AND goals file exists; this is the post-ENH-1401 steady state for fresh inits; no change needed but confirms acceptance
- No dedicated init skill unit tests found; acceptance criteria should be verified manually or via a new integration test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1401_doc_wiring.py` — **new test file to write** following the pattern in `scripts/tests/test_enh1421_doc_wiring.py`; two test classes: `TestInitSkillProductSetup` (asserts strip instruction removed, `product.enabled: true` present, goals deploy step present, dry-run display, completion message) and `TestInitInteractiveProductRound` (asserts `TOTAL = 7`, Round 4 present, Yes/No options present) [Wiring pass]

### Documentation
- `docs/guides/GETTING_STARTED.md` — may reference manual product setup steps that become obsolete after this change
- `docs/reference/CONFIGURATION.md:97,321,327,914,945` — canonical config docs for `product.goals_file` and `product.enabled`; verify the init-path description matches new behavior
- `docs/reference/COMMANDS.md` — documents `/ll:scan-product`; may reference prerequisites that init now satisfies automatically
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:167` — instructs users to manually copy `ll-goals-template.md` to `.ll/ll-goals.md` as a prerequisite; this step becomes obsolete for projects initialized after ENH-1401 [Wiring pass]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### Manual Configuration` section states product is "not exposed through `/ll:init`"; becomes inaccurate after this change — update the section to reflect product as a first-class init output [Wiring pass]

### Configuration
- N/A

## Impact

- **Priority**: P2 - Improves first-time user experience for product analysis; currently requires 2 manual steps that block the feature
- **Effort**: Small - Changes limited to `skills/init/SKILL.md` (Steps 4, 8, 12), `skills/init/interactive.md` (new Round 4), and three documentation updates
- **Risk**: Low - Only affects init flow for new projects; existence guard prevents overwriting existing `.ll/ll-goals.md`; `--yes` path change is additive (opt-in included by default, opt-out remains possible in interactive mode)
- **Breaking Change**: No

## Labels

`init`, `product-analysis`, `enhancement`, `ux`

## Evidence

- `skills/init/SKILL.md:114-118` (Step 4) — exact strip instruction: "Strip the `_meta`, `$schema`, and `product` sections (product is configured separately in interactive mode)." — remove `and 'product'` from this list
- `skills/init/SKILL.md:294-301` (Step 8) — `Omit product section if user selected "No, skip"` already present in the conditional omit list; Step 8 has no template-copy step at all
- `skills/init/SKILL.md:545-556` (Step 12) — `Created: .ll/ll-goals.md (product goals template) # Only show if product enabled` already stubbed; just needs the condition to activate
- `skills/init/interactive.md:13` — `TOTAL = 6` (mandatory rounds: 1, 2, 3a, 6, 11, 12); adding mandatory Round 4 raises this to `TOTAL = 7`
- `templates/ll-goals-template.md` — template exists but is never deployed
- `hooks/scripts/session-start.sh:134-143` (`validate_enabled_features`) — already warns at session start when `product.enabled: true` but goals file missing; ENH-1401 prevents this warning from ever firing for fresh inits


## Status

**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-11T09:06:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-11T09:00:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8610438d-cea0-44b4-b2b2-1529be41efbc.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c10d07e-eeb6-4ce4-99da-db233fc76bc1.jsonl`
- `/ll:wire-issue` - 2026-05-11T08:54:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ef22b16-036e-4cd5-88ab-741d528e880a.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:49:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbd60305-2081-4e7f-be4d-5257ff65febb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T21:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32deefa2-352e-4fa9-a9df-ce9aad495a16.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): This issue's scope is specifically for new projects created via `/ll:init` going forward. ENH-1400 (implement goals discovery in product-analyzer) addresses the complementary case: existing/legacy projects that were initialized before this change and have no `ll-goals.md`. The two issues are not redundant — this issue prevents the missing-goals-file problem for future projects; ENH-1400 provides the retrofit fallback for projects already in place.
