---
id: BUG-3051
title: 'confidence-check: no hard override for an unresolved blocked_by dependency'
type: BUG
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T02:01:17Z'
completed_at: '2026-08-05T03:05:22Z'
relates_to:
- ENH-3047
labels:
- skills
- issues
- gates
decision_needed: false
confidence_score: 95
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3051: confidence-check averages away a hard blocked_by dependency instead of forcing STOP

## Summary

`/ll:confidence-check ENH-3047` returned **75/100 → PROCEED WITH CAUTION** for an issue that
cannot be started at all: it is `blocked_by: [FEAT-3048]`, FEAT-3048 is `status: open`, and
ENH-3047's own body says "without it there is nothing to read." Criterion 5 (Dependencies
Satisfied) correctly scored 0/20, but with no hard override to back it, that 0 was simply
averaged against four near-perfect criteria (20+20+20+15+0=75) into a passing tier.

## Steps to Reproduce

1. Have an issue (e.g. ENH-3047) with `blocked_by: [FEAT-3048]` in frontmatter, where FEAT-3048
   is `status: open`.
2. Run `/ll:confidence-check ENH-3047`.
3. Observe Criterion 5 (Dependencies Satisfied) correctly scores 0/20, but the aggregate readiness
   score still sums to a passing tier (e.g. 75/100 → PROCEED WITH CAUTION) instead of being forced
   to `STOP — ADDRESS GAPS`, because no hard override exists for this criterion the way it does
   for the Learning Test and Program Design gates.

## Current Behavior

`skills/confidence-check/SKILL.md` Phase 3 ("Score and Recommend") defines exactly two hard
overrides that bypass the normal score-to-tier table and force `STOP — ADDRESS GAPS` regardless
of aggregate score:

- **Learning Test Hard Override** (`SKILL.md:302`) — any `missing`/`refuted` learning-test target
- **Program Design Hard Override** (`SKILL.md:304`) — `PD_FAIL` non-empty

Dependencies Satisfied (Criterion 5, `SKILL.md:220`, `rubric.md:245`) has no equivalent. It is
just one of five 0-20 criteria summed into the readiness total (`rubric.md` Phase 2 table), so a
critical unresolved `blocked_by` — scored 0 per the existing "Critical dependencies unresolved,
cannot proceed" row in that same table — is diluted rather than gating.

## Expected Behavior

An unresolved hard dependency should force `STOP — ADDRESS GAPS` (or `STOP — NOT READY`)
regardless of aggregate score, the same way the Learning Test and Program Design gates already
do — not get averaged into a passing tier that reads as "proceed, just be careful."

## Motivation

This readiness score is not just advisory prose — it is what `/ll:go-no-go`, `ll-auto`, and
sprint selection consume (per ENH-3047's own Motivation section, and per this repo's
`commands.confidence_gate` config gate). A misleadingly high score on a hard-blocked issue risks
that issue being auto-selected or greenlit by automation that trusts the aggregate number over
reading the per-criterion breakdown.

## Proposed Solution

Add a **Dependencies Hard Override** to `SKILL.md` Phase 3, following the exact shape of the two
existing overrides:

- Phase 1 (or a new lightweight Phase 1.x pre-fetch) resolves each ID in the issue's `blocked_by:`
  frontmatter list via `ll-issues show <ID> --json` and checks its `status`.
- If any `blocked_by` entry has a status other than `done`/`cancelled` (see `.claude/CLAUDE.md` §
  Issue File Format — `deferred` is explicitly non-terminal for `blocked_by`/`depends_on` edges),
  set a shell variable (e.g. `DEP_FAIL`) non-empty.
- In Phase 3, if `DEP_FAIL` is non-empty, output `STOP — ADDRESS GAPS` regardless of aggregate
  score, listing the unresolved blocker ID(s) and their status under **Gaps to Address** —
  mirroring the Program Design override's structure (`SKILL.md:304`).

This is additive to the existing Criterion 5 0-20 scoring (which stays as-is for the non-blocking
case — "Minor dependencies unresolved but non-blocking" still just scores 15, not a STOP).

### Files to Modify
- `skills/confidence-check/SKILL.md` — new Dependencies pre-fetch step, Phase 3 hard override
- `skills/confidence-check/rubric.md` — document the override alongside the existing two, if the
  reference table there needs updating

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Dependent Files (Consumers of the readiness score)
- `skills/go-no-go/SKILL.md` — consumes confidence-check's readiness score/tier to make its go/no-go call
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — FSM loop gated by `commands.confidence_gate` (`readiness_threshold`/`outcome_threshold` in `.ll/ll-config.json`)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml`, `scripts/little_loops/loops/sprint-build-and-validate.yaml` — sprint loops consuming the same gate
- `scripts/little_loops/sprint.py`, `scripts/little_loops/cli/sprint/run.py` — sprint issue selection integrates readiness scores

### Tests
- `scripts/tests/test_confidence_check_skill.py` — the existing test file for this skill; already covers Phase 4/4.5/4.6, the Learning Test and Program Design hard overrides, Criterion D, Criterion A, and `VERDICT_JSON`. A Dependencies Hard Override test class belongs here, following the same shape as the existing `PD_FAIL`-override tests in this file.

### Existing Prefetch Pattern to Extend
- `skills/confidence-check/rubric.md:113-117` (Phase 1.5) and `SKILL.md:136-140` (Phase 1.6) both set their gate variable by shelling out to `ll-issues show/format-check ... --json` and parsing with an inline `python3 -c` script (no `jq` anywhere in this skill) — the same idiom this issue's Proposed Solution specifies for `DEP_FAIL` via `ll-issues show <ID> --json`.

## Program Design

### Types

- `DEP_FAIL: str` — shell variable, empty or non-empty, mirroring `PD_FAIL`'s shape
  (`skills/confidence-check/SKILL.md:132-150`)

### Signatures

- Reuse `ll-issues show <ID> --json` (already used by Phase 1.5's learning-test pre-fetch,
  `rubric.md:113`) to resolve each `blocked_by` ID's `status` field.

### Call Path

`skills/confidence-check/SKILL.md` Phase 1.x pre-fetch -> `ll-issues show <blocked_by ID> --json`
-> `cmd_show()` (`scripts/little_loops/cli/issues/show.py:852`, JSON branch at `:871-872`) emits
the issue's `status` field -> status extracted via inline `python -c` -> `DEP_FAIL` shell variable
-> `SKILL.md` Phase 3 hard-override paragraph (same slot as `PD_FAIL`, `SKILL.md:304`)

## Impact

- **Priority**: P2 — the score feeds automation (`/ll:go-no-go`, `ll-auto`, sprint selection)
  that trusts the aggregate number
- **Effort**: Low — mirrors an existing, well-established override pattern
- **Risk**: Low — additive gate; does not change scoring for issues without unresolved
  `blocked_by` dependencies

## Related Key Documentation

- `.claude/CLAUDE.md` — Issue File Format, `blocked_by`/`depends_on` deferral discriminator
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Completed** | Created: 2026-08-05 | Completed: 2026-08-05 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-05T03:04:22 - `4535f4d4-f14b-460b-89bd-b88362861660.jsonl`
- `/ll:ready-issue` - 2026-08-05T02:47:14 - `d359d751-fc31-4860-a2ab-1331fcb490fc.jsonl`
- `/ll:confidence-check` - 2026-08-05T02:36:55 - `b31d828d-efcd-47ab-bb1e-e15aa1cfb7d9.jsonl`
- `/ll:refine-issue` - 2026-08-05T02:32:29 - `aa24e5e7-0f72-4dfd-ae25-e8166d71faf6.jsonl`
- `/ll:capture-issue` - 2026-08-05T02:02:02 - `78b80840-5577-4179-95d0-0f368e10d2bb.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **File**: `skills/confidence-check/SKILL.md`
- **Anchor**: `### Phase 3: Score and Recommend` (SKILL.md:300), between the Learning Test Hard Override (SKILL.md:302) and Program Design Hard Override (SKILL.md:304)
- **Cause**: Phase 3 defines exactly two hard-override paragraphs (Learning Test at SKILL.md:302, Program Design/`PD_FAIL` at SKILL.md:304) and no third one for dependencies. A grep across `skills/confidence-check/SKILL.md`, `rubric.md`, and `reference.md` for `blocked_by|depends_on` returns zero matches — the skill never reads that frontmatter structurally. Criterion 5's detection method (`SKILL.md:220-230`) only inspects issue-body prose ("Blocked By"/"Dependencies" sections) and a `{{config.issues.base_dir}}/completed/` directory check, not the `blocked_by`/`depends_on` fields. So the "Critical dependencies unresolved, cannot proceed" row (`rubric.md:247-252`, scores 0) is just one term in the SKILL.md:306 aggregate sum — there is no gate comparable to `PD_FAIL` that intercepts it before the score-to-tier table.

## Resolution

- **Action**: fix
- **Completed**: 2026-08-05
- **Status**: Completed

### Changes Made

- `skills/confidence-check/SKILL.md`: Added `### Phase 1.7: Pre-Fetch Dependencies Gate` — resolves each `blocked_by` frontmatter ID via `ll-issues show --json`, lowercases `status`, and sets `DEP_FAIL`/`DEP_ROWS` when any entry is not `done`/`cancelled` (`deferred` treated as non-terminal per `.claude/CLAUDE.md`). Added a **Dependencies Hard Override** paragraph to Phase 3 (alongside the existing Learning Test and Program Design overrides) that forces `STOP — ADDRESS GAPS` when `DEP_FAIL` is set. Added `Bash(ll-issues:*)` to the skill's `allowed-tools` frontmatter (it was already invoked by the pre-existing Program Design pre-fetch but missing from the allowlist).
- `skills/confidence-check/rubric.md`: Documented the Dependencies Hard Override directly under the Criterion 5 scoring table.
- `scripts/tests/test_confidence_check_skill.py`: Added `TestConfidenceCheckDependenciesPrefetch` and `TestConfidenceCheckRubricDependenciesOverride` covering the new Phase 1.7 heading, `blocked_by` read, `ll-issues show` usage, the deferred-non-terminal note, the Phase 3 override text, and the allowed-tools entry.

### Verification Results
- Tests: PASS (18280 passed, 42 skipped; 1 pre-existing unrelated failure — `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`, confirmed present on `main` before this change via `git stash`)
- Lint: PASS (`ruff check`)
- The new inline `python3 -c` calls in Phase 1.7 are suppressed from the `ll-verify-skill-prose` algorithm-as-prose baseline gate via `<!-- ll-prose-ok: ... -->` comments, matching the pre-existing PD_GAP idiom in Phase 1.6
