---
id: ENH-2158
title: Add rubric-refine, cua-agent-desktop, and oracle sub-loops to LOOPS_REFERENCE.md
type: ENH
priority: P3
status: done
created: 2026-06-14
affects:
- docs/guides/LOOPS_REFERENCE.md
confidence_score: 98
outcome_confidence: 80
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 20
completed_at: '2026-06-15T15:09:29Z'
---

## Problem

Four loops exist in the codebase but are not documented in `docs/guides/LOOPS_REFERENCE.md`:

1. **`rubric-refine`** — added in commit `aa38dc03`; has its own YAML at `scripts/little_loops/loops/rubric-refine.yaml`. Referenced only in the internal `loops/README.md`.
2. **`cua-agent-desktop`** — listed in CHANGELOG v1.124.0 as a new built-in loop; not in LOOPS_REFERENCE.md.
3. **`oracles/enumerate-and-prove`** — oracle sub-loop; not in the oracle sub-loops table.
4. **`oracles/verify-confidence-scores`** — oracle sub-loop; not in the oracle sub-loops table.

## Acceptance Criteria

- [ ] Add `rubric-refine` entry to the appropriate LOOPS_REFERENCE.md section (harness/rubric category) with: description, primary use case, key states
- [ ] Add `cua-agent-desktop` entry with: description, primary use case, key states
- [ ] Add `oracles/enumerate-and-prove` and `oracles/verify-confidence-scores` rows to the oracle sub-loops table
- [ ] `ll-loop list` output matches all entries added (spot-check that loop names are correct)

## Notes

Source of truth for each loop's description is the `description:` field at the top of its YAML file. Key states can be derived from the `states:` block.

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_REFERENCE.md` — add four new rows to existing category tables

### Exact Insertion Points in LOOPS_REFERENCE.md

| Loop | Target Section | Insert After Row |
|------|---------------|-----------------|
| `rubric-refine` | `### Code Quality` | `incremental-refactor` |
| `cua-agent-desktop` | `### Harness Examples` | `loop-specialist-eval` (before `adversarial-redesign`) |
| `oracles/enumerate-and-prove` | `### API Adoption` | `integrate-sdk` |
| `oracles/verify-confidence-scores` | `### General-Purpose` | `refine-to-ready-issue` |

### Source YAML Files (Read-Only)
- `scripts/little_loops/loops/rubric-refine.yaml` — `description:` + `states:` fields
- `scripts/little_loops/loops/cua-agent-desktop.yaml` — `description:` + `states:` fields
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — `description:` + `parameters:` + `states:`
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — `description:` + `parameters:` + `states:`

### Oracle Row Pattern
The oracle sub-loops table format follows the inline pattern established by `oracles/plan-research-iteration` in the Research & Knowledge section — oracle entries appear as rows in their parent loop's category table, not a separate oracle table. Each description names: (1) which parent loops invoke it, (2) what it does per-iteration, (3) any key parameters, (4) invocation form (`loop: oracles/<name>` with `with:` context passthrough).

### Verification
- `ll-loop list` — public loops only (rubric-refine, cua-agent-desktop should appear)
- `ll-loop list --all` — includes oracle sub-loops with `visibility: internal`

## Implementation Steps

1. Read each YAML's `description:` field (source of truth per Notes)
2. Add `rubric-refine` row to Code Quality table after `incremental-refactor` row
3. Add `cua-agent-desktop` row to Harness Examples table before `adversarial-redesign` row
4. Add `oracles/enumerate-and-prove` row to API Adoption table after `integrate-sdk` row
5. Add `oracles/verify-confidence-scores` row to General-Purpose table after `refine-to-ready-issue` row
6. Run `ll-loop list` to spot-check that rubric-refine and cua-agent-desktop appear

## Session Log
- `/ll:ready-issue` - 2026-06-15T15:09:10 - `8417bb7e-796a-43e5-bfb3-21e47c3fa0c3.jsonl`
- `/ll:refine-issue` - 2026-06-15T15:02:39 - `bfb46a9b-5490-47c1-9e5a-da36f7acc9d5.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/715daee3-a8ee-4638-8ef8-07da70cc80cc.jsonl`
- `/ll:refine-issue` - 2026-06-15T15:02:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-06-15T16:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27852c7a-21ba-4f1e-900e-98795bd95fd9.jsonl`


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-06-15
- **Reason**: already_fixed
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
