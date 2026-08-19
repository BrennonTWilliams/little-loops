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

Phase 1.6 captures the full `format-check` payload into `$FC_JSON` and Phase 1.8
reuses it, but between them only four keys are read
(`program_design_nonspecific`, `missing_behavior_parity`, `stale_symbol_ref`,
`stale_cli_flag`). `template_placeholders`, `boilerplate`, and `missing` are
fetched and discarded, so an issue full of unfilled template debris can score
`confidence_score: 100`.

## Expected Behavior

Phase 1.8 extracts the structural-debris keys from the same `$FC_JSON` into a
`STRUCT_GAP` variable and `rubric.md` Criterion 4 caps at 10 when it is
non-empty — a ceiling, never a floor, never a Phase 3 `STOP` escalation. Only
directive-section `missing` entries participate (see Proposed Solution ›
Narrowing).

## Motivation

The data is already in memory; not reading it is a pure miss. `/ll:confidence-check`
is the gate before implementation, and an issue whose Acceptance Criteria section
does not exist should not be able to score full marks on "Issue Well-Specified."
The loop already bounces one of these signals (ENH-3248's `check_placeholders`),
so a standalone skill run is currently weaker than the same check inside a loop.

## Proposed Solution

Mirror the existing `CLAIM_GAP` idiom exactly (`skills/confidence-check/SKILL.md:187-207`,
`rubric.md:241-256`): extract the structural-debris keys from the already-captured
`$FC_JSON` in Phase 1.8 (no second `format-check` call), combine them into one
joined advisory variable — **named `STRUCT_GAP`** — the same way `CLAIM_GAP`
concatenates `stale_symbol_ref` + `stale_cli_flag`, and feed it into the
Criterion 4 cap in `rubric.md` alongside `PARITY_GAP`/`CLAIM_GAP` — a ceiling on
Criterion 4, never a Phase 3 `STOP` escalation.

### Narrowing: `missing` is filtered, not taken raw

Measured across all 173 open issues in this repo (via `check_format_gaps()`):

| key | issues firing |
|---|---|
| `template_placeholders` | 6 (3%) |
| `boilerplate` | 4 (2%) |
| `missing` (raw) | **102 (58%)** |
| any of the three | 106 (61%) |

Raw `missing` is dominated by ceremonial sections whose absence says nothing
about how well-specified an issue is — `Status` (63), `Current Behavior` (55),
`Impact` (39), `Scope Boundaries` (33), `Expected Behavior` (33), `Use Case` (23)
— versus the directive sections that actually gate implementation:
`Program Design` (10), `Acceptance Criteria` (5), `Summary` (5).

Taking `missing` raw would pin Criterion 4 at 10 for ~58% of the backlog because
an `## Impact` heading is absent, making the cap near-permanently on and
therefore uninformative. So `missing` is filtered to a directive allowlist:

```
_CRITERION4_DIRECTIVE_SECTIONS = {"Summary", "Acceptance Criteria",
                                  "Program Design", "Implementation Steps"}
```

`template_placeholders` and `boilerplate` are taken unfiltered — at 3% and 2%
they are already rare and unambiguously mean "template debris left in place."

### Remedy differs per key

`ll-issues format-check --fix` (ENH-3247, completed) repairs `boilerplate` and
can insert `missing` sections structurally, but `template_placeholders` is
explicitly not auto-fixable — the CLI itself annotates those entries
`(literal template debris; no --fix, needs content)`. The `STRUCT_GAP` advisory
text under **Gaps to Address** should therefore say which entries `--fix`
resolves and which need authored content, rather than recommending `--fix`
uniformly.

All three fields are `list[str]` (`FormatGaps.to_dict()`,
`scripts/little_loops/issue_parser.py:546-573`), matching the shape the
existing `python -c "... '; '.join(...)"` extraction idiom already handles,
so no new parsing shape is needed.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md:187-207` (Phase 1.8) — add the `STRUCT_GAP` extraction one-liner off the already-captured `$FC_JSON`, using the same `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom -->`-annotated convention used for `PARITY_GAP`/`CLAIM_GAP`; the `missing` allowlist filter lives inside this one-liner as a set intersection, so no `issue_parser.py` change is needed
- `skills/confidence-check/rubric.md:241-256` — extend the Criterion 4 "Parity/Claim Cap" row and its prose note to also apply when `STRUCT_GAP` is non-empty; rename the row to cover all three signals (e.g. "Parity/Claim/Structure Cap")

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
- `scripts/tests/test_confidence_check_skill.py:502-550` `TestConfidenceCheckClaimParityPrefetch` — the exact test class to extend: `test_phase_1_8_names_all_three_gap_keys` (add `STRUCT_GAP`'s three source keys), `test_phase_1_8_does_not_reissue_format_check`, `test_phase_1_8_marks_claim_gap_advisory`, `test_phase_3_does_not_name_claim_gap` (mirror as `test_phase_3_does_not_name_struct_gap`), plus a new `test_phase_1_8_filters_missing_to_directive_sections` asserting the allowlist appears — all pure text-slice assertions against `SKILL.md`, no fixtures or subprocess calls
- `scripts/tests/test_confidence_check_skill.py:553-578` `TestConfidenceCheckRubricClaimParityCap` — parallel rubric.md test class to extend the same way (`test_cap_row_present`, `test_cap_documented_as_ceiling`, `test_cap_documented_as_not_a_hard_override`)
- Note: `test_feat3048_symbol_cli_claim_gaps.py` tests `check_format_gaps()` in `issue_parser.py` directly (a different layer — the gap-population sites, not the skill prose); confirmed out of scope since Program Design states no `issue_parser.py` changes are needed

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Host skill mirrors `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` (both `SKILL.md` and `rubric.md`) are git-tracked verbatim copies enforced by `scripts/tests/test_wiring_skills_and_commands.py:413-443` (`test_skill_mirrors_carry_companions`, generic over `SKILL_MIRROR_ROOTS`). After editing `skills/confidence-check/SKILL.md`/`rubric.md`, run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply` or the mirror-companion test fails on drift. Same finding as ENH-3256 — if both issues land in the same change, one `ll-adapt` pass covers both.

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Phase 3's hard-override list (`skills/confidence-check/SKILL.md:357-365`) must NOT gain an entry for `STRUCT_GAP` — confirmed only Learning Test, Program Design (`PD_FAIL`), and Dependencies (`DEP_FAIL`) are named there; `CLAIM_GAP`/`PARITY_GAP` are deliberately absent, and `STRUCT_GAP` follows the same cap-only discipline

## Program Design

### Signatures
- `FormatGaps.to_dict()` — already serializes `template_placeholders`, `boilerplate`, `missing` as `list[str]` (`scripts/little_loops/issue_parser.py:546`); no signature change needed

### Call Path
`cmd_format_check` produces the JSON payload via `FormatGaps.to_dict` (both defined above) -> captured once into `$FC_JSON` (`skills/confidence-check/SKILL.md:138`) -> Phase 1.8 extraction one-liners extend to add the new combined variable (`SKILL.md:187-207`) -> Criterion 4 cap row extends (`rubric.md:241-256`) -> Criterion 4 score only, never Phase 3 STOP overrides (`SKILL.md:357-365`)

### Decision Rules

**Variable name:** `STRUCT_GAP` (the earlier draft left it unnamed as
`<new_var>`, which made its Implementation Steps and prescribed tests
unwriteable).

**Composition:**
```
STRUCT_GAP = '; '.join(
    d.get('template_placeholders', [])
    + d.get('boilerplate', [])
    + [m for m in d.get('missing', []) if m in _CRITERION4_DIRECTIVE_SECTIONS]
)
```
where `_CRITERION4_DIRECTIVE_SECTIONS = {"Summary", "Acceptance Criteria",
"Program Design", "Implementation Steps"}`. The filter is inlined in the skill's
`python3 -c` one-liner (the `CLAIM_GAP` named-dict variant, `SKILL.md:196`), not
added to `issue_parser.py` — the allowlist is a confidence-check scoring policy,
not a property of the gap key itself, and `format-check` must keep reporting all
`missing` sections to its other consumers.

**Cap semantics:** non-empty `STRUCT_GAP` caps Criterion 4 at 10 regardless of
which other row would otherwise apply — a ceiling, never a floor. It is
cap-only: no Phase 3 hard-override paragraph, matching `PARITY_GAP`/`CLAIM_GAP`.

**Interaction with the sibling cap:** ENH-3256's `DECISION_GAP` caps Criterion C
(Ambiguity); `STRUCT_GAP` caps Criterion 4 (Well-Specified). Different criteria,
so the caps compose additively with no ordering dependency. If both land
together, `rubric.md` gains one cap row per criterion, not a merged row.

**Inert cases:** all three keys empty, or only non-directive `missing` entries
present (e.g. just `Status`/`Impact`) — `STRUCT_GAP` is the empty string and
Criterion 4 scoring is untouched.

## Implementation Steps

1. Add the `STRUCT_GAP` extraction to Phase 1.8 in
   `skills/confidence-check/SKILL.md` per Decision Rules above, off the
   already-captured `$FC_JSON` — no second `format-check` invocation, matching
   the explicit "do not issue a second format-check call" comment already
   present for `PARITY_GAP`/`CLAIM_GAP` (`SKILL.md:189-190`).
2. Add the prose paragraph describing `STRUCT_GAP` beside the existing
   `PARITY_GAP`/`CLAIM_GAP` paragraph, stating the directive-section allowlist,
   the cap-not-STOP discipline, and the per-key remedy split (`--fix` repairs
   `boilerplate`/`missing`; `template_placeholders` needs authored content).
3. Extend `rubric.md`'s Criterion 4 cap row and prose note to cover
   `STRUCT_GAP`, staying a cap — consistent with `SKILL.md:204-207`'s statement
   that `CLAIM_GAP` "must not be escalated to a STOP verdict."
4. Confirm Phase 3's hard-override list (`SKILL.md:357-365`) gains no
   `STRUCT_GAP` entry.
5. Run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply &&
   ll-adapt --host qwen --apply` to refresh the three verbatim skill mirrors.

## Acceptance Criteria

- [ ] Phase 1.8 of `skills/confidence-check/SKILL.md` names `STRUCT_GAP` and all
      three source keys (`template_placeholders`, `boilerplate`, `missing`).
- [ ] Phase 1.8 issues no second `format-check` call — `$FC_JSON` is still
      fetched exactly once, in Phase 1.6.
- [ ] The `missing` contribution is filtered to the directive allowlist; an issue
      whose only `missing` entries are `Status` and `Impact` leaves `STRUCT_GAP`
      empty.
- [ ] An issue with a non-empty `template_placeholders` list caps Criterion 4 at
      10 and does **not** produce a `STOP — ADDRESS GAPS` verdict.
- [ ] `rubric.md`'s Criterion 4 cap row names `STRUCT_GAP` and is documented as a
      ceiling and explicitly not a hard override.
- [ ] `STRUCT_GAP` does not appear in Phase 3's hard-override paragraphs
      (`test_phase_3_does_not_name_struct_gap`).
- [ ] The three host skill mirrors match `skills/confidence-check/` byte-for-byte.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Weakens the pre-implementation gate, but the loop-side `check_placeholders` already covers the highest-value signal in automated runs.
- **Effort**: Small - Two prose files, one extraction one-liner and one rubric row; no Python change.
- **Risk**: Low - Cap-only semantics with a measured allowlist; the narrowing keeps the trigger rate at ~3-5% of open issues rather than 58%.
- **Breaking Change**: No - Scores can drop for issues carrying real debris, which is the intent; no interface changes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-18 | Priority: P2

## Success Metrics

- A re-run of `/ll:confidence-check` on ENH-3256/ENH-3257 in their pre-cleanup
  state (10 `template_placeholders`, 4 `boilerplate`) caps Criterion 4 at 10.
- `STRUCT_GAP` fires on ≤ 10% of open issues, not the 58% raw `missing` would
  produce — verifiable by re-running the measurement in Proposed Solution ›
  Narrowing after implementation.

## Scope Boundaries

**In scope:** reading three already-fetched keys in Phase 1.8 and the Criterion 4
cap row in `rubric.md`.

**Out of scope:**
- Any change to `scripts/little_loops/issue_parser.py` or
  `cli/issues/format_check.py` — all three keys already exist and serialize
  correctly; the allowlist is a scoring policy local to confidence-check.
- `refine-to-ready-issue.yaml`'s `check_placeholders` state (ENH-3248). It
  re-invokes `format-check` independently and gates on a count rather than a
  joined string — a separate consumer, deliberately not unified here.
- Auto-remediation. `STRUCT_GAP` is advisory; running `format-check --fix` or
  authoring the missing content stays the user's action.
- Criterion C (Ambiguity), which ENH-3256 covers.

## Backwards Compatibility

No interface change. `$FC_JSON` is already fetched; this reads three more keys
from it. Issues carrying real structural debris will score up to 10 points lower
on Criterion 4 than before, which is the intended correction — previously scored
issues keep their frontmatter until re-run. The cap cannot lower an issue below
its existing row (ceiling, never floor) and cannot produce a `STOP` verdict.

## API/Interface

```bash
# skills/confidence-check/SKILL.md Phase 1.8 — reuses $FC_JSON from Phase 1.6
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) -->
STRUCT_GAP=$(echo "$FC_JSON" | python3 -c "
import json,sys
d = json.load(sys.stdin)
DIRECTIVE = {'Summary', 'Acceptance Criteria', 'Program Design', 'Implementation Steps'}
print('; '.join(
    d.get('template_placeholders', [])
    + d.get('boilerplate', [])
    + [m for m in d.get('missing', []) if m in DIRECTIVE]
))" 2>/dev/null || true)
```


## Session Log
- `/ll:verify-issues` - 2026-08-18T23:42:05 - `5babd785-d270-4764-90c8-5811c9188fb7.jsonl`
- `/ll:confidence-check` - 2026-08-18T22:04:27 - `bb66018c-ab8d-4e0a-a8d9-81ae552f7d58.jsonl`
- `/ll:wire-issue` - 2026-08-18T22:00:40 - `b37bf726-239f-4f1a-b2e3-9f5b456cd984.jsonl`
- `/ll:refine-issue` - 2026-08-18T21:39:54 - `1598a616-9bb3-45c4-9fb9-f9f87bed73c9.jsonl`
- `/ll:capture-issue` - 2026-08-18T20:48:47 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
