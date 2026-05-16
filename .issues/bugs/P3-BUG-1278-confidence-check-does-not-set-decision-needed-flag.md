---
id: BUG-1278
type: BUG
priority: P3
status: open
discovered_date: 2026-04-24
discovered_by: capture-issue
captured_at: "2026-04-24T21:18:45Z"
completed_at: "2026-04-24T23:11:47Z"

decision_needed: false
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
relates_to: ['BUG-1277']
---

# BUG-1278: `confidence-check` Does Not Set `decision_needed: true` When Unresolved Decisions Found

## Summary

`/ll:confidence-check` identifies unresolved design decisions and records them in the "Outcome Risk Factors" prose section, but does not set `decision_needed: true` in the issue frontmatter. The autodev loop's decision gate reads the frontmatter flag — not the notes — so the decision is never surfaced to the loop.

## Current Behavior

When `/ll:confidence-check` detects an unresolved decision (e.g., "whether `_throttle_counts` survives loop resume is flagged as an open decision — resolve before implementing"), it:
1. Records the risk in `## Confidence Check Notes` prose ✓
2. Leaves `decision_needed: false` in the frontmatter ✗

The autodev loop's `decide_current` state (autodev.yaml:184) checks `d.get('decision_needed') == 'true'`. It sees `false` and skips `run_decide`, proceeding directly to implementation or size review.

Observed in: ENH-1115 confidence check, which noted "Persistence decision unresolved" but left `decision_needed: false`.

## Expected Behavior

When `/ll:confidence-check` identifies an unresolved decision that it explicitly flags as needing resolution before implementation, it should set `decision_needed: true` in the issue frontmatter alongside the prose note.

Signal phrases that should trigger the flag:
- "open decision"
- "unresolved decision"
- "resolve before implementing"
- "decision point" (in the context of an unresolved choice)

## Steps to Reproduce

1. Run `/ll:confidence-check` on an issue where it identifies an unresolved design decision (e.g., one where `score_ambiguity ≤ 10` and Phase 4.5 fires, writing risk-factor prose containing "open decision", "unresolved decision", or "resolve before implementing")
2. After the skill completes, read the issue file's YAML frontmatter
3. Observe that `decision_needed` remains `false` despite the unresolved decision being recorded in `## Confidence Check Notes`
4. Run the autodev loop — observe that `decide_current` sees `decision_needed == 'false'` and skips the `/ll:decide-issue` gate, proceeding directly to implementation

## Root Cause

The `confidence-check` skill (`skills/confidence-check/SKILL.md`) documents how to compute readiness and outcome scores and write the risk prose, but has no instruction to update `decision_needed` in frontmatter when it surfaces a decision-class risk factor.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Phase 4** (`skills/confidence-check/SKILL.md:398-446`): updates `confidence_score`, `outcome_confidence`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface` via inline `---` block replacement — never touches `decision_needed`
- **Phase 4.5** (`skills/confidence-check/SKILL.md:448-495`): appends prose to `## Confidence Check Notes` when `outcome_confidence < 60` — no frontmatter write
- **Escalation output** (`skills/confidence-check/SKILL.md:563-566`): terminal output recommends `/ll:decide-issue` when `score_ambiguity ≤ 10` — prose only, no flag set
- **`score_ambiguity`** (`skills/confidence-check/SKILL.md:340-355`): Criterion C (0–25); score `≤ 10` = "Fundamental approach unclear, multiple competing options unresolved" — this is the existing ambiguity signal, never connected to `decision_needed`

## Proposed Solution

### Option A — Post-prose signal-phrase scan (matches issue spec)

> **Selected:** Option A — Post-prose signal-phrase scan — scans skill-generated risk-factor prose for explicit decision-class signal phrases; negligible over-trigger risk because Phase 4.5's `outcome_confidence < 60` gate provides natural scoping (if Phase 4.5 didn't fire, no unresolved decision was identified).

After Phase 4.5 writes Outcome Risk Factors to `## Confidence Check Notes`, scan the generated risk-factor bullets for signal phrases:
- "open decision"
- "unresolved decision"
- "resolve before implementing"
- "decision point"

If any match: use the Edit tool to update `decision_needed: true` in the frontmatter `---` block (same inline replacement pattern as `skills/confidence-check/SKILL.md:398-446`). Include idempotency guard: skip write if already `true`. Skip entirely in CHECK_MODE.

**Trade-off**: More precise — only fires when the skill's own prose explicitly flags a decision. Requires a second Edit on the frontmatter (or pre-composition), after Phase 4.5.

### Option B — score_ambiguity threshold in Phase 4 (single Edit)

In Phase 4's existing frontmatter update, derive `decision_needed` from the already-computed `score_ambiguity`:
- `score_ambiguity ≤ 10` → include `decision_needed: true` in the `---` block write
- `score_ambiguity > 10` → include `decision_needed: false` (or omit if already `false`)

**Trade-off**: Single Edit operation — no second write needed. Consistent with existing escalation recommendation (`skills/confidence-check/SKILL.md:563-566`) that already routes `score_ambiguity ≤ 10` to `/ll:decide-issue`. May over-trigger on issues with low-but-non-zero ambiguity that don't strictly require a pre-implementation decision.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-24.

**Selected**: Option A — Post-prose signal-phrase scan

**Reasoning**: Option A's signal-phrase scan fires exactly when Phase 4.5 fires (both gated on `outcome_confidence < 60`), eliminating the coverage-hole concern — if Phase 4.5 doesn't write risk factors, no signal phrases exist to scan, and no unresolved decision was identified. Option B's `score_ambiguity ≤ 10` threshold is confirmed to over-trigger: ENH-1197 has `score_ambiguity: 10`, `decision_needed: false`, and no blocking decision — because the score-10 rubric tier ("Several design decisions left open, will require judgment calls during implementation") explicitly covers implementation-time judgment calls, not blocking pre-implementation option choices. The one structural novelty in Option A — scanning self-generated prose rather than user input — is minor given that all four building blocks (Edit tool `---` pattern, idempotency guard, CHECK_MODE guard, signal-phrase scan) are independently established in the codebase.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 2/3 | 3/3 | 3/3 | 10/12 |
| Option B | 2/3 | 3/3 | 3/3 | 1/3 | 9/12 |

**Key evidence**:
- **Option A**: Signal-phrase scan pattern established in `capture-issue/SKILL.md:236-241` and `format-issue/SKILL.md:163-175`; Phase 4.5 gate (`outcome_confidence < 60`) naturally scopes the scan to only cases where unresolved decisions were identified; no confirmed over-trigger risk.
- **Option B**: ENH-1197 (completed) has `score_ambiguity: 10`, `decision_needed: false`, correctly no blocking decision — confirmed over-triggering case for the `≤ 10` threshold; score-10 rubric tier explicitly covers implementation-time judgment calls, not blocking pre-implementation decisions.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — add `decision_needed` write step; placement depends on chosen option (Phase 4 or after Phase 4.5)

### Dependent Files (Consumers of `decision_needed`)
- `scripts/little_loops/loops/autodev.yaml:184` — `decide_current` state: `sys.exit(0 if d.get('decision_needed') == 'true' else 1)`
- `scripts/little_loops/loops/autodev.yaml:361-384` — `check_decision_before_size_review`: same flag check before size-review step
- `skills/manage-issue/SKILL.md:157-179` — Phase 2.3 Decision Gate: halts if `decision_needed: true` without `--force-implement`
- `skills/wire-issue/SKILL.md:443` — advisory warning in Next Steps output

_Wiring pass added by `/ll:wire-issue`:_
- `commands/refine-issue.md:272` — contains a live line-range cross-reference to `skills/confidence-check/SKILL.md:398-446`; will become stale if Phase 4 is modified (Option B) or a new Phase 4.6 shifts line numbers (Option A) — must update after edit [Agent 1]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:106` — invokes `/ll:confidence-check` directly in the loop pipeline; no change needed but confirms this path exercises the new step [Agent 1]

### Similar Patterns (Reference Implementations)
- `skills/confidence-check/SKILL.md:398-446` — Phase 4: existing inline `---` block replacement; extend here for Option B
- `skills/decide-issue/SKILL.md:253-266` — Phase 7b: sets `decision_needed: false`; same Edit tool inline `---` block pattern
- `skills/format-issue/SKILL.md:163-175` — idempotency: skip write if field already has same value
- `skills/capture-issue/SKILL.md:236-241` — post-write signal-phrase scan pattern (for `testable: false`); analog for Option A's prose-scan step

### Tests
- `scripts/tests/test_confidence_check_skill.py` — existing structural tests (54 lines); add test for new step: assert phase text contains signal phrases or threshold value, idempotency guard, CHECK_MODE guard

_Wiring pass added by `/ll:wire-issue`:_
- Reference pattern: `scripts/tests/test_refine_issue_command.py:18-82` — closest analog; tests `decision_needed` write-back with phase boundary extraction (`content.index("### Phase ...")`), keyword assertions, idempotency guard, dry-run guard, `AskUserQuestion` absence [Agent 3]
- Reference pattern: `scripts/tests/test_decide_issue_skill.py:172-197` — tests `decision_needed: false` write-back in Phase 7; shows phase boundary slice + keyword assert structure [Agent 3]
- New test assertions needed (all in one new class in `test_confidence_check_skill.py`): (1) phase heading exists, (2) `decision_needed: true` in phase text, (3) signal phrases or `score_ambiguity` threshold documented, (4) idempotency guard documented, (5) `CHECK_MODE` guard present, (6) no `AskUserQuestion` [Agent 3]

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md:887` — `decision_needed` field description; may need a note that `confidence-check` can also set this flag

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:571` — inline comment on `IssueInfo.decision_needed` attributes it solely to `refine-issue`; extend to include `confidence-check` as a second setter [Agent 2]
- `docs/reference/COMMANDS.md:185,188,194` — all three mentions name only `refine-issue` as setter of `decision_needed: true`; update to include `confidence-check` [Agent 2]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:344-346` — describes `score_ambiguity ≤ 10` path as requiring manual `/ll:decide-issue` invocation; with the fix, `confidence-check` will have already set the flag that triggers `decide-issue` automatically in pipeline runs [Agent 2]

## Acceptance Criteria

- When confidence-check notes an unresolved design decision that must be resolved before implementation, it sets `decision_needed: true` in the issue frontmatter
- When no such decision is found, `decision_needed` remains unchanged
- Updated skill instructions tested against ENH-1115 (retrospectively produces `decision_needed: true`)

## Scope Boundaries

- **In scope**: `skills/confidence-check/SKILL.md` instructions; frontmatter update step
- **Out of scope**: How decisions are resolved (`/ll:decide-issue`); other frontmatter fields written by confidence-check

## Implementation Steps

1. In `skills/confidence-check/SKILL.md`, add a post-scoring step: after writing Outcome Risk Factors, scan for decision-class risks; if any are flagged as requiring resolution before implementation, update `decision_needed: true` in frontmatter using `sed` or a Python snippet
2. Document the signal phrases that qualify as decision-class risks
3. Add a note to the skill output indicating when `decision_needed` was flipped

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. After editing `skills/confidence-check/SKILL.md`, update the line-range cross-reference in `commands/refine-issue.md:272` to point to the new location (line numbers will shift if Phase 4 is modified or Phase 4.6 is inserted)
5. Update `docs/reference/API.md:571` — extend the `decision_needed` inline comment to include `confidence-check` as a second setter alongside `refine-issue`
6. Update `docs/reference/COMMANDS.md:185,188,194` — update attribution mentions from `refine-issue`-only to include `confidence-check`
7. Add a new test class to `scripts/tests/test_confidence_check_skill.py` following `test_refine_issue_command.py:18-82` pattern: assert on (1) new phase heading existence, (2) `decision_needed: true` in phase text, (3) signal phrases or `score_ambiguity` threshold, (4) idempotency guard, (5) `CHECK_MODE` guard, (6) no `AskUserQuestion`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Edit tool pattern**: Use the same inline `---` block replacement as Phase 4 — do NOT use `sed` or a Python snippet; the Edit tool instruction approach is standard across all skills (pattern at `skills/confidence-check/SKILL.md:398-446`)
- **Option A placement** (post-prose scan): Add as a new Phase 4.6 step after Phase 4.5 (`skills/confidence-check/SKILL.md:495`); scan the just-written `## Confidence Check Notes` content for signal phrases; if matched, do a targeted Edit on the frontmatter `---` block
- **Option B placement** (score threshold): Extend Phase 4's existing Edit block at `skills/confidence-check/SKILL.md:398-446` to include `decision_needed: true/false` derived from `score_ambiguity` — keeps all frontmatter writes in one Edit call
- **Idempotency**: Check existing `decision_needed` value before writing; skip if already the target value (pattern from `skills/format-issue/SKILL.md:163-175`)
- **CHECK_MODE guard**: Phase 4.5 is skipped when `CHECK_MODE=true`; the new step must carry the same guard (no writes in check mode)
- **Test**: Follow structural test approach in `scripts/tests/test_confidence_check_skill.py` — locate new phase heading, extract text, assert required keywords (decision_needed, threshold or signal phrases, idempotency guard, CHECK_MODE)
- **Serialization compatibility**: `autodev.yaml:184` checks `d.get('decision_needed') == 'true'` against the string output of `ll-issues show --json`; YAML boolean `true` is serialized to string `"true"` by `scripts/little_loops/cli/issues/show.py:248-250` — no extra handling needed

## Impact

- **Priority**: P3 — causes autodev to skip the decision gate for issues that genuinely need it
- **Risk**: Low — only changes frontmatter; no behavioral change to the rest of the skill

## Labels

`bug`, `confidence-check`, `decision-needed`, `skills`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

## Resolution

Fixed by adding **Phase 4.6: Decision-Needed Flag** to `skills/confidence-check/SKILL.md` immediately after Phase 4.5. The new phase scans the Outcome Risk Factors content written by Phase 4.5 for signal phrases ("open decision", "unresolved decision", "resolve before implementing", "decision point") and sets `decision_needed: true` in the issue frontmatter when any are found. Guards: CHECK_MODE skip, idempotency (no-op if already `true`). Documentation updated in `docs/reference/API.md`, `docs/reference/COMMANDS.md`, and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`. Six structural tests added to `scripts/tests/test_confidence_check_skill.py`.

## Session Log
- `/ll:manage-issue` - 2026-04-24T23:11:47Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a59f955d-1476-46b6-86c4-9ebfbfd80b60.jsonl`
- `/ll:ready-issue` - 2026-04-24T23:05:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8aef0887-aa9d-46f7-97dd-71ef2dc9ab95.jsonl`
- `/ll:decide-issue` - 2026-04-24T23:02:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c07b93f-0220-43db-b622-3f5b2c40f07a.jsonl`
- `/ll:confidence-check` - 2026-04-24T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0515c411-1a42-422d-8af5-9d3a19f5d03c.jsonl`
- `/ll:wire-issue` - 2026-04-24T22:55:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27c8ab24-3531-40ba-b883-80ca4b272ff6.jsonl`
- `/ll:refine-issue` - 2026-04-24T22:50:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27826087-82cc-4bce-924a-d8383ccdcf0e.jsonl`
- `/ll:capture-issue` - 2026-04-24T21:18:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82f88b14-6ac1-4d64-a028-6d67f78c0498.jsonl`
