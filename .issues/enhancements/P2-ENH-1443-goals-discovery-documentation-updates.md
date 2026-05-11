---
id: ENH-1443
status: done
priority: P2
type: ENH
parent: ENH-1400
blocked_by:
- ENH-1442
confidence_score: 100
outcome_confidence: 85
completed_at: 2026-05-11T20:15:46Z
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
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
- `skills/init/interactive.md:245` — **Round 4: Product Analysis** option description reads `"Creates .ll/ll-goals.md from the template and enables /ll:scan-product"`; implies `ll-goals.md` is what enables `scan-product` (no longer true — scan-product works without it); soften to `"Creates .ll/ll-goals.md for richer analysis (scan-product works without it)"` [second wiring pass — 2026-05-11]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1443_doc_wiring.py` — **new test file needed**; every prior ENH in this family (1401, 1402, 1403, 1404, 1421, 1428, 1442) has a `test_enh*_doc_wiring.py`; follow the pattern in `scripts/tests/test_enh1442_doc_wiring.py`; assert softened language is present in each of the 5 target files and old hard-prerequisite strings are absent [second wiring pass — 2026-05-11]

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

2. ~~**Update `docs/reference/CONFIGURATION.md:327`**~~ — **Already done.** Line 327 now reads: "`ll-goals.md` is optional — if absent, goals are auto-discovered from existing project documentation (README, CHANGELOG, architecture docs). Create a hand-authored goals file only when you want precise control…" — conditional framing, not imperative.

3. **Confirm all 5 files need no further changes** — codebase research (2026-05-11) confirms all 5 target locations are already softened (see Current State section below).

4. **Run spot-check grep to verify no hard-prerequisite strings remain** across all 5 target files:
   ```bash
   grep -n "Goals file exists\|Requires a product goals file\|create a goals file" \
     docs/reference/COMMANDS.md docs/guides/GETTING_STARTED.md \
     docs/guides/ISSUE_MANAGEMENT_GUIDE.md commands/help.md \
     docs/reference/CONFIGURATION.md
   ```
   Expected: **zero matches** — confirmed 2026-05-11.

### Wiring Phase (added by `/ll:wire-issue` — second pass, 2026-05-11)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `skills/init/interactive.md:245` — change `"Creates .ll/ll-goals.md from the template and enables /ll:scan-product"` to `"Creates .ll/ll-goals.md for richer analysis (scan-product works without it)"` in the Round 4: Product Analysis option description
6. Create `scripts/tests/test_enh1443_doc_wiring.py` — follow the pattern in `scripts/tests/test_enh1442_doc_wiring.py`; assert softened language is present in each of the 5 target files (positive assertions) and old hard-prerequisite phrases are absent (negative assertions)

### Codebase Research Findings (2026-05-11)

_Added by `/ll:refine-issue` — all 5 documentation targets verified already softened:_

- `docs/reference/CONFIGURATION.md:327` — "optional — if absent, goals are auto-discovered" ✓
- `docs/reference/COMMANDS.md:131,243` — "if present; otherwise goals are discovered automatically from project docs" ✓
- `docs/guides/GETTING_STARTED.md:238` — "if present… or discovers goals automatically from README and roadmap docs" ✓
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:167` — "if absent, scan-product discovers goals from existing docs" ✓
- `commands/help.md:32` — "using goals file if present, or auto-discovering goals" ✓

Verification grep (`grep -n "Goals file exists\|Requires a product goals file\|create a goals file"` across all 5 files) returned zero matches. ENH-1442 blocker is also confirmed completed (`.issues/completed/P2-ENH-1442-goals-discovery-core-implementation.md`). All acceptance criteria are met — this issue is ready to close.

### Current State of Target Files (from codebase research)

| File | Location | Status |
|------|----------|--------|
| `docs/reference/COMMANDS.md` | `### /ll:scan-product` + `### /ll:product-analyzer` | **Already softened** — "if present; otherwise goals are discovered automatically" |
| `docs/guides/GETTING_STARTED.md` | `### Goal-Oriented Scanning` | **Already softened** — "Uses product goals file if present… or discovers goals automatically" |
| `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` | Line 167, `### Scanning the Codebase` | **Already softened** — "for best results, create…; if absent, scan-product discovers goals" |
| `commands/help.md` | `/ll:scan-product` entry | **Already softened** — "using goals file if present, or auto-discovering goals" |
| `docs/reference/CONFIGURATION.md` | Line 327, `### product` table prose | **Already softened** — "`ll-goals.md` is optional — if absent, goals are auto-discovered from existing project documentation" |
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

**Done** | Created: 2026-05-11 | Priority: P2

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
- `/ll:manage-issue` - 2026-05-11T20:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-11T20:13:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/445a93c8-05ff-4bfc-bf41-6d7b2a7cf592.jsonl`
- `/ll:confidence-check` - 2026-05-11T20:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/373f6a58-c552-4de7-a881-0d71318a6873.jsonl`
- `/ll:wire-issue` - 2026-05-11T20:09:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/364a3eba-8e8d-4e02-9004-4d6306fcaefe.jsonl`
- `/ll:refine-issue` - 2026-05-11T20:04:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/743e1871-ec24-486c-9536-5de729f828d4.jsonl`
- `/ll:issue-size-review` - 2026-05-11T10:13:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8da1efd7-3aca-49c4-9873-ccde11dae506.jsonl`
- `/ll:issue-size-review` - 2026-05-11T10:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5787b1a3-847a-4d77-ae60-8f0638e3429d.jsonl`
- `/ll:confidence-check` - 2026-05-11T09:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d76d8938-e809-494e-92bb-545bcd5d8b26.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:40:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbc33c0c-5e48-4db2-b24b-3ce0d476b92c.jsonl`
- `/ll:wire-issue` - 2026-05-11T08:34:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50399d9-8071-4239-8ddd-576bec12c255.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:28:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/738a9c42-7028-4bea-9dfa-7e9c727b4b87.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a400556-76fe-4ad7-9557-40b6a1c32a72.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be1e58ed-bc9d-4da3-8129-97d5e6621836.jsonl`
