---
id: ENH-3257
type: ENH
title: confidence-check fetches format-check JSON but reads only four of its gap keys
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:37Z'
parent: EPIC-2856
testable: true
relates_to:
- BUG-3249
- ENH-3256
- ENH-3248
- ENH-3247
- ENH-3047
- ENH-2852
confidence_score: 98
outcome_confidence: 85
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 20
---

# ENH-3257: confidence-check fetches format-check JSON but reads only four of its gap keys

## Summary

`/ll:confidence-check` Phase 1.6 fetches the complete `format-check` JSON payload
once (`skills/confidence-check/SKILL.md:138`) and reuses it in Phase 1.8 rather
than re-invoking the CLI. Between the two phases it extracts exactly four keys:

| Phase | Key | Effect |
|---|---|---|
| 1.6 | `program_design_nonspecific` | `PD_GAP` display detail |
| 1.6 | (`ll-issues check-design` exit) | `PD_FAIL` — can force STOP |
| 1.8 | `missing_behavior_parity` | `PARITY_GAP` |
| 1.8 | `stale_symbol_ref` + `stale_cli_flag` | `CLAIM_GAP` — advisory only, explicitly cannot escalate to STOP (`:204-207`) |

`template_placeholders`, `boilerplate`, and `missing` are never read — grep
across the whole `skills/confidence-check/` directory returns no hits. The
payload containing them is already in `$FC_JSON`; the data is fetched and
discarded.

Observed on BUG-3249, which scored `confidence_score: 100` /
`outcome_confidence: 99` while `ll-issues format-check BUG-3249` reported:

```
  missing: Steps to Reproduce
  boilerplate: Impact
  template_placeholders: Motivation: [Why this issue matters - business value, ...]
  template_placeholders: Impact: [P0-P5]
  template_placeholders: Impact: [Justification]
  template_placeholders: Impact: [Small/Medium/Large]
  template_placeholders: Impact: [Low/Medium/High]
  template_placeholders: Impact: [Yes/No]
```

The sibling loop already treats one of these as routable: ENH-3248 added a
`check_placeholders` state (`scripts/little_loops/loops/refine-to-ready-issue.yaml:371-396`)
that reads `template_placeholders` via `--format json` and forces a refine. That
signal is gated in the *loop* but not in the *skill*, so a standalone
`/ll:confidence-check` sails past debris the loop would bounce.

Proposed direction: extract `template_placeholders` / `boilerplate` / `missing`
from the already-captured `$FC_JSON` in Phase 1.6 and feed them as a cap on
Criterion 4, mirroring exactly how `CLAIM_GAP` works today (advisory cap, not a
STOP escalation). No new CLI call and no re-derived predicate — `format-check`
stays the single source of truth.

Related: BUG-3249 (the instance), ENH-3248 (`check_placeholders`, the loop-side
precedent), ENH-3247 (`format-check --fix` repairing structural debris),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends), ENH-3047 (added the
Phase 1.8 keys, the pattern to follow).


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Mirror the existing `CLAIM_GAP` idiom exactly (`skills/confidence-check/SKILL.md:187-207`,
`rubric.md:241-256`): extract `template_placeholders`, `boilerplate`, and
`missing` from the already-captured `$FC_JSON` in Phase 1.6 (no second
`format-check` call), combine them into one joined advisory variable the
same way `CLAIM_GAP` concatenates `stale_symbol_ref` + `stale_cli_flag`, and
feed it into the Criterion 4 cap in `rubric.md` alongside `PARITY_GAP`/
`CLAIM_GAP` — a ceiling on Criterion 4, never a Phase 3 `STOP` escalation.

All three fields are `list[str]` (`FormatGaps.to_dict()`,
`scripts/little_loops/issue_parser.py:546-573`), matching the shape the
existing `python -c "... '; '.join(...)"` extraction idiom already handles,
so no new parsing shape is needed.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md:187-207` (Phase 1.8) — add extraction of `template_placeholders`, `boilerplate`, `missing` from the already-captured `$FC_JSON`, using the same `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom -->`-annotated one-liner convention used for `PARITY_GAP`/`CLAIM_GAP`
- `skills/confidence-check/rubric.md:241-256` — extend the Criterion 4 "Parity/Claim Cap" row and its prose note to also apply when the new combined variable is non-empty

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` already produces all three keys; no changes needed, confirmed no schema gap
- `scripts/little_loops/issue_parser.py:863` (`missing`), `:883-893` (`boilerplate`), `:1449-1500` `_template_placeholders()` (`template_placeholders`) — the three population sites; all already serialize into `FormatGaps.to_dict()` (`:546-573`) and require no changes for this issue
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:371-396` `check_placeholders` state — the ENH-3248 loop-side precedent; it re-invokes `format-check --format json` independently rather than sharing a cached `$FC_JSON` the way skill phases do, and gates on `len(d.get('template_placeholders', [])) == 0` rather than joining strings — a different consumer of the same field, not a shared implementation to touch

### Conventions in Force
- `$FC_JSON` is fetched exactly once (Phase 1.6, `SKILL.md:138`); every later phase reuses it via `python -c "import json,sys; ... '; '.join(...)"` one-liners, each preceded by the identical `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) ... -->` comment marker — evidence: `SKILL.md:162,170,193,195`
- Two micro-variants of the extraction idiom coexist: inline single-key (`PD_GAP`, `PARITY_GAP`, using bare `python`) vs. named-dict multi-key combination (`CLAIM_GAP`, using `python3` with `d = json.load(sys.stdin)` then combining fields) — evidence: `SKILL.md:139-140,194,196`. Combining three keys (`template_placeholders`+`boilerplate`+`missing`) matches the `CLAIM_GAP` variant's shape.
- Advisory-cap vs. hard-override is a documented binary in this file: gap keys that get a named "`X Hard Override`" paragraph in Phase 3 force `STOP — ADDRESS GAPS` regardless of score (Learning Test, Program Design, Dependencies — `SKILL.md:359,361,363`); gap keys with no such Phase 3 paragraph are cap-only, confined to a rubric.md table row (`PARITY_GAP`/`CLAIM_GAP` — `rubric.md:245-256`). No other criterion besides Criterion 4 has a documented cap mechanic.

### Tests
- `scripts/tests/test_confidence_check_skill.py` — structural tests for Phase 1.6/1.8 layout
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` — tests the Phase 1.8 `CLAIM_GAP`/`PARITY_GAP` pattern this issue mirrors
- `scripts/tests/test_ll_issues_format_check.py` — tests the JSON payload shape for all gap keys including the three currently unread ones

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py:502-550` `TestConfidenceCheckClaimParityPrefetch` — the exact test class to extend: `test_phase_1_8_names_all_three_gap_keys` (add the new combined key), `test_phase_1_8_does_not_reissue_format_check`, `test_phase_1_8_marks_claim_gap_advisory`, `test_phase_3_does_not_name_claim_gap` (mirror as `test_phase_3_does_not_name_<new_var>`) — all pure text-slice assertions against `SKILL.md`, no fixtures or subprocess calls
- `scripts/tests/test_confidence_check_skill.py:553-578` `TestConfidenceCheckRubricClaimParityCap` — parallel rubric.md test class to extend the same way (`test_cap_row_present`, `test_cap_documented_as_ceiling`, `test_cap_documented_as_not_a_hard_override`)
- Note: `test_feat3048_symbol_cli_claim_gaps.py` tests `check_format_gaps()` in `issue_parser.py` directly (a different layer — the gap-population sites, not the skill prose); confirmed out of scope since Program Design states no `issue_parser.py` changes are needed

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Host skill mirrors `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` (both `SKILL.md` and `rubric.md`) are git-tracked verbatim copies enforced by `scripts/tests/test_wiring_skills_and_commands.py:413-443` (`test_skill_mirrors_carry_companions`, generic over `SKILL_MIRROR_ROOTS`). After editing `skills/confidence-check/SKILL.md`/`rubric.md`, run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply` or the mirror-companion test fails on drift. Same finding as ENH-3256 — if both issues land in the same change, one `ll-adapt` pass covers both.

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Phase 3's hard-override list (`skills/confidence-check/SKILL.md:357-365`) must NOT gain an entry for the new combined variable — confirmed only Learning Test, Program Design (`PD_FAIL`), and Dependencies (`DEP_FAIL`) are named there; `CLAIM_GAP`/`PARITY_GAP` are deliberately absent, and the new variable follows the same cap-only discipline

## Program Design

### Signatures
- `FormatGaps.to_dict()` — already serializes `template_placeholders`, `boilerplate`, `missing` as `list[str]` (`scripts/little_loops/issue_parser.py:546`); no signature change needed

### Call Path
`cmd_format_check` produces the JSON payload via `FormatGaps.to_dict` (both defined above) -> captured once into `$FC_JSON` (`skills/confidence-check/SKILL.md:138`) -> Phase 1.8 extraction one-liners extend to add the new combined variable (`SKILL.md:187-207`) -> Criterion 4 cap row extends (`rubric.md:241-256`) -> Criterion 4 score only, never Phase 3 STOP overrides (`SKILL.md:357-365`)

### Decision Rules
N/A — no new gap kind or threshold; this issue extends an existing cap
mechanism (Criterion 4's Parity/Claim Cap) to three additional pre-existing
gap keys using the identical mechanism already in place for `PARITY_GAP`/
`CLAIM_GAP`.

## Implementation Steps

1. Phase 1.8 in `skills/confidence-check/SKILL.md` extracts `template_placeholders`, `boilerplate`, and `missing` from the already-captured `$FC_JSON` — no second `format-check` invocation, matching the explicit "do not issue a second format-check call" comment already present for `PARITY_GAP`/`CLAIM_GAP` (`SKILL.md:189-190`).
2. `rubric.md`'s Criterion 4 "Parity/Claim Cap" row and prose note extend to cover the new combined signal, staying a cap (never a Phase 3 STOP escalation) — consistent with `SKILL.md:204-207`'s explicit statement that `CLAIM_GAP` "must not be escalated to a STOP verdict."
3. `python -m pytest scripts/tests/test_confidence_check_skill.py scripts/tests/test_feat3048_symbol_cli_claim_gaps.py -v` passes, and a new test exercises an issue with a non-empty `template_placeholders`/`boilerplate`/`missing` gap to confirm Criterion 4 is capped without triggering a STOP verdict.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:confidence-check` - 2026-08-18T22:04:27 - `bb66018c-ab8d-4e0a-a8d9-81ae552f7d58.jsonl`
- `/ll:wire-issue` - 2026-08-18T22:00:40 - `b37bf726-239f-4f1a-b2e3-9f5b456cd984.jsonl`
- `/ll:refine-issue` - 2026-08-18T21:39:54 - `1598a616-9bb3-45c4-9fb9-f9f87bed73c9.jsonl`
- `/ll:capture-issue` - 2026-08-18T20:48:47 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
