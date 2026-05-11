---
id: ENH-1443
priority: P2
type: ENH
parent: ENH-1400
blocked_by:
- ENH-1442
confidence_score: 60
outcome_confidence: 68
score_complexity: 25
score_test_coverage: 0
score_ambiguity: 25
score_change_surface: 18
size: Very Large
---

# ENH-1443: Goals Discovery — Documentation Updates

## Summary

Soften four documentation files that currently describe `ll-goals.md` as a hard prerequisite for `scan-product`. After ENH-1442 ships the discovery fallback, these docs are inaccurate. Each update is a language change only — no behavioral code changes.

## Parent Issue

Decomposed from ENH-1400: Implement `goals_discovery` in product-analyzer

## Files to Modify

- `docs/reference/COMMANDS.md` — `### /ll:scan-product` and `### /ll:product-analyzer` prerequisite blocks list "Goals file exists (`.ll/ll-goals.md` by default)" as a hard requirement; change to reflect optional nature (file used if present, otherwise discovery runs)
- `docs/guides/GETTING_STARTED.md` — `### Goal-Oriented Scanning` paragraph states "Requires a product goals file (configured in `ll-config.json`)"; soften to "uses goals file if present, otherwise discovers goals from existing docs"
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — line ~167 instructs users to "create `ll-goals.md` by copying `templates/ll-goals-template.md`" as a prerequisite; change from hard instruction to a recommendation ("for best results, create…")
- `commands/help.md` — `/ll:scan-product` entry description implies goals file must exist; soften to reflect discovery fallback
- `docs/reference/CONFIGURATION.md` — two sections need updating:
  - `### product` reference table prose (~line 329): "To enable product scanning, set `product.enabled: true` and create a goals file…" — soften to mention that goals file is optional when discovery is configured
  - `### product.goals_discovery` section (~line 925): add a behavioral note explaining that these settings are now active (not just declared)

## Proposed Changes (per file)

### `docs/reference/COMMANDS.md`
Replace prerequisite wording in both `### /ll:scan-product` and `### /ll:product-analyzer`:
- Before: "Goals file exists (`.ll/ll-goals.md` by default)"
- After: "Goals file (`.ll/ll-goals.md`) if present; otherwise goals are discovered automatically from project docs"

### `docs/guides/GETTING_STARTED.md`
- Before: "Requires a product goals file (configured in `ll-config.json`)"
- After: "Uses product goals file if present (`.ll/ll-goals.md`), or discovers goals automatically from README and roadmap docs"

### `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- Before: Hard instruction to create `ll-goals.md` before running scan-product
- After: Recommendation ("For best results, create `ll-goals.md`…; if absent, scan-product discovers goals from existing docs")

### `commands/help.md`
Soften `/ll:scan-product` description to mention fallback discovery.

### `docs/reference/CONFIGURATION.md`

**Section 1 — `### product` reference table prose (~line 329):**
- Before: "To enable product scanning, set `product.enabled: true` and create a goals file with your product vision, personas, and strategic priorities."
- After: "To enable product scanning, set `product.enabled: true`. For best results, create a goals file (`.ll/ll-goals.md`) with your product vision; if absent, goals are discovered automatically from project docs."

**Section 2 — `### product.goals_discovery` section (~line 925):**
Add a note: "These settings are active when `ll-goals.md` is absent — `max_files` limits how many files are read; `required_files` entries trigger a warning if missing but never block analysis."

## Integration Map

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:329` — `### product` reference table prose; says "create a goals file" as a hard setup step; needs softening alongside the already-targeted `### product.goals_discovery` section at line ~925 [wiring gap — same file, different section]

### Notes from Wiring Research

- `skills/product-analyzer/SKILL.md` and `commands/scan-product.md` — both contain hard-stop prerequisite language for missing `ll-goals.md`; covered in full by ENH-1442 (core implementation), not this issue
- `hooks/scripts/session-start.sh` — warning for missing goals file; covered by ENH-1442
- `commands/create-sprint.md` — Goal-Aligned grouping skips when goals file absent; noted in ENH-1442 as a follow-up concern, not in scope for either ENH-1442 or ENH-1443
- `docs/guides/SPRINT_GUIDE.md` — already uses "if present" language; no change needed
- `docs/reference/API.md` — API docs for goals_parser; neutral language; no change needed
- `config-schema.json` — already correct; no changes needed

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Verify blocker is resolved** — confirm ENH-1442 is merged before touching these docs; the behavioral note in `CONFIGURATION.md:945` already references discovery semantics that ENH-1442 must ship.

2. **Update `docs/reference/CONFIGURATION.md:327`** — the one remaining hard-language location:
   - Current: `"To enable product scanning, set \`product.enabled: true\` and create a goals file with your product vision, personas, and strategic priorities."`
   - Target: `"To enable product scanning, set \`product.enabled: true\`. For best results, create a goals file (\`.ll/ll-goals.md\`) with your product vision, personas, and strategic priorities; if absent, goals are discovered automatically from project docs."`

3. **Confirm the other 4 files need no further changes** — codebase research shows they are already softened (see Current State section below).

4. **Run spot-check grep to verify no hard-prerequisite strings remain** across all 5 target files:
   ```bash
   grep -n "Goals file exists\|Requires a product goals file\|create a goals file" \
     docs/reference/COMMANDS.md docs/guides/GETTING_STARTED.md \
     docs/guides/ISSUE_MANAGEMENT_GUIDE.md commands/help.md \
     docs/reference/CONFIGURATION.md
   ```
   Expected: only `CONFIGURATION.md` (before step 2) or zero matches (after).

### Current State of Target Files (from codebase research)

| File | Location | Status |
|------|----------|--------|
| `docs/reference/COMMANDS.md` | `### /ll:scan-product` + `### /ll:product-analyzer` | **Already softened** — "if present; otherwise goals are discovered automatically" |
| `docs/guides/GETTING_STARTED.md` | `### Goal-Oriented Scanning` | **Already softened** — "Uses product goals file if present… or discovers goals automatically" |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | Line 167, `### Scanning the Codebase` | **Already softened** — "for best results, create…; if absent, scan-product discovers goals" |
| `commands/help.md` | `/ll:scan-product` entry | **Already softened** — "using goals file if present, or auto-discovering goals" |
| `docs/reference/CONFIGURATION.md` | Line 327, `### product` table prose | **Needs update** — still says "create a goals file" as a flat setup imperative |
| `docs/reference/CONFIGURATION.md` | Line ~945, `### product.goals_discovery` behavioral note | **Already present** — "active when `ll-goals.md` is absent… never block analysis" |

## Acceptance Criteria

- All five files updated with softened prerequisite language
- No file implies `ll-goals.md` is required for `scan-product` to function
- Behavioral note in `CONFIGURATION.md` accurately describes `goals_discovery` field semantics
- No functional code changes (markdown instruction files only)

## Scope Boundaries

- **In scope**: Language softening in the 5 listed doc/command files
- **Out of scope**: Core implementation (covered in ENH-1442); config schema (already correct); any test changes

## Dependencies

Must ship after ENH-1442 (docs describe behavior introduced by that child).

## Labels

`enhancement`, `documentation`, `product-analyzer`

## Status

**Open** | Created: 2026-05-11 | Priority: P2

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 68/100 → MODERATE (↑ from 57 — verification grep now present; scope narrowed to 1 site)

### Concerns
- ENH-1442 (core implementation blocker) is still open; ENH-1442 is itself blocked by ENH-1402 (also open). ENH-1443 docs describe behavior introduced by ENH-1442 — both upstream issues must ship first.

### Gaps to Address
- Resolve ENH-1402 → ENH-1442 dependency chain before implementing ENH-1443. The remaining change (one sentence in CONFIGURATION.md:327) is trivial once the blocker chain clears.

### Outcome Risk Factors
- Test coverage structural gap: no automated tests for markdown docs — by design for a docs-only change, not a real implementation risk.
- Pattern B verification chain incomplete: 5 sites enumerated + spot-check grep specified (step 4), but no automated wiring test asserting completeness.

## Session Log
- `/ll:issue-size-review` - 2026-05-11T10:13:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8da1efd7-3aca-49c4-9873-ccde11dae506.jsonl`
- `/ll:issue-size-review` - 2026-05-11T10:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5787b1a3-847a-4d77-ae60-8f0638e3429d.jsonl`
- `/ll:confidence-check` - 2026-05-11T09:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d76d8938-e809-494e-92bb-545bcd5d8b26.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:40:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc33c0c-5e48-4db2-b24b-3ce0d476b92c.jsonl`
- `/ll:wire-issue` - 2026-05-11T08:34:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50399d9-8071-4239-8ddd-576bec12c255.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:28:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/738a9c42-7028-4bea-9dfa-7e9c727b4b87.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a400556-76fe-4ad7-9557-40b6a1c32a72.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be1e58ed-bc9d-4da3-8129-97d5e6621836.jsonl`
