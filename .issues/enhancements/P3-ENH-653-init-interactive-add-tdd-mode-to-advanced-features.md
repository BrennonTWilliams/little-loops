---
id: ENH-653
type: enhancement
priority: P3
status: completed
discovered_date: 2026-03-08
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# ENH-653: Add TDD Mode to `--interactive` Advanced Features Selection

## Summary

The `/ll:init --interactive` wizard presents a "Which advanced features do you want to enable?" multi-select in Round 3a. `Test-Driven-Development (TDD) Mode` is not included there — it currently appears only in Round 8 (Project Advanced, gated behind the Extended Config Gate). Adding TDD Mode to Round 3a makes it discoverable alongside Parallel Processing, Context Monitoring, GitHub Sync, and Confidence Gate, and removes the need for users to navigate the optional advanced path to enable it.

## Current Behavior

TDD Mode (`commands.tdd_mode`) only appears in Round 8 (Project Advanced configuration), which is gated behind the Extended Config Gate. The Round 3a multi-select ("Which advanced features do you want to enable?") lists Parallel Processing, Context Monitoring, GitHub Sync, and Confidence Gate — but not TDD Mode. Users who do not enter the extended config path never see the TDD Mode option.

## Motivation

TDD Mode (`commands.tdd_mode` in `ll-config.json`) is a first-class workflow preference that directly affects every `manage-issue` run. Burying it in Round 8 means most users will never see it. Surfacing it in Round 3a — next to Confidence Gate, which is a similarly workflow-level toggle — matches its importance and improves discoverability.

## Expected Behavior

- [ ] Round 3a in `skills/init/interactive.md` includes a "Test-Driven Development (TDD)" option in the multi-select question
- [ ] Round 3a option description clearly explains the effect (write failing tests before implementation)
- [ ] When "TDD Mode" is selected in Round 3a, the final config includes `{ "commands": { "tdd_mode": true } }`
- [ ] When "TDD Mode" is NOT selected, `commands.tdd_mode` is omitted (defaults to `false`)
- [ ] The ACTIVE count calculation (post-Round 3b) is updated to account for TDD Mode if it requires a follow-up question in Round 5 (it likely does not — selection alone is sufficient)
- [ ] The existing TDD Mode question in Round 8 is removed entirely (not guarded) to avoid duplication
- [ ] Round 5 conditional logic table is updated to reflect any changes
- [ ] Manual verification: run `/ll:init --interactive`, confirm TDD appears in Round 3a multi-select and does NOT appear in Round 8

## Implementation Steps

1. **Add TDD option to Round 3a multi-select** in `skills/init/interactive.md`:
   - Label: `"Test-Driven Development (TDD)"`
   - Description: `"Write failing tests before implementation — manage-issue will create tests first, then implement to pass them"`

2. **Add mapping rule to Round 3a** (after the multi-select block):
   - `"Test-Driven Development (TDD)"` selected → `{ "commands": { "tdd_mode": true } }`
   - Not selected → omit (defaults to `false`)

3. **Update ACTIVE count logic** — TDD Mode selection in Round 3a does NOT trigger additional Round 5 questions (it's a simple boolean), so ACTIVE count does not change.

4. **Remove the Round 8 TDD question entirely** — delete the TDD Mode block from Round 8 (`skills/init/interactive.md` lines ~886–898). Do not guard it conditionally; the mapping is fully captured in Round 3a and a conditional guard adds complexity for no benefit.

5. **Update Round table** at the bottom of `interactive.md` if it references Round 8 TDD fields.

## Scope Boundaries

**In scope:**
- `skills/init/interactive.md` — Round 3a option addition + Round 8 TDD block removal
- Any inline help text or option descriptions within the wizard itself

**Out of scope:**
- `config-schema.json` — `commands.tdd_mode` already exists; no schema changes
- `ll-config.json` — schema default is `false`; no project config changes
- Changes to how `manage-issue` or other commands consume `tdd_mode` (behavior is unchanged)
- New CLI arguments or flags

## Files

- `skills/init/interactive.md` — primary change (Round 3a options + Round 8 TDD block)
- No schema changes needed — `commands.tdd_mode` already exists in `config-schema.json` (line ~278)
- No `ll-config.json` changes needed — schema default is `false`

## Impact

- **Priority**: P3 — Discoverability improvement; TDD Mode is functional today but hidden from most users who skip extended config
- **Effort**: Small — Single file change to `skills/init/interactive.md`, isolated to wizard UI with no schema or CLI changes
- **Risk**: Low — `config-schema.json` already supports `commands.tdd_mode`; change cannot affect non-init workflows
- **Breaking Change**: No

## Related Key Documentation

- `config-schema.json` — `commands.tdd_mode` boolean, default `false`
- ENH-613 — init interactive simplification (related: reducing unnecessary questions)

## Labels

`enhancement`, `init`, `ux`, `tdd`

---

**Completed** | Created: 2026-03-08 | Priority: P3

## Resolution

- Added "Test-Driven Development (TDD)" option to Round 3a multi-select in `skills/init/interactive.md`
- Added TDD config mapping (`{ "commands": { "tdd_mode": true } }`) in the Round 5 configuration section
- Removed the TDD Mode block (header, options, and mapping) from Round 8 entirely
- Updated the summary table to include `tdd_mode` in Round 3a's features list
- ACTIVE count logic unchanged — TDD selection requires no follow-up Round 5 question

## Session Log
- `/ll:capture-issue` - 2026-03-08T07:22:30Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81536658-b23f-4ba4-bcc6-0eb995bcf26f.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b384c54-14df-4e17-a051-5543cadfa726.jsonl`
- `/ll:confidence-check` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bbd9f44-2987-40e6-996f-adbad58e0bce.jsonl`
- `/ll:confidence-check` - 2026-03-08T08:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:ready-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b9858f3-eab7-4228-a05a-862f8e6117ba.jsonl`
- `/ll:manage-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
