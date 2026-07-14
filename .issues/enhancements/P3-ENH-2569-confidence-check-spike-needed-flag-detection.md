---
id: ENH-2569
title: "confidence-check Phase 4.x \u2014 set spike_needed flag from Outcome Risk\
  \ Factors"
type: ENH
priority: P3
status: done
labels:
- skills
- confidence
- frontmatter-flags
- risk-reduction
- captured
captured_at: '2026-07-10T01:34:59Z'
completed_at: '2026-07-14T20:41:48Z'
discovered_date: '2026-07-10'
discovered_by: capture-issue
parent: EPIC-2570
confidence_score: 96
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2569: confidence-check Phase 4.x — set spike_needed flag from Outcome Risk Factors

## Summary

Add a new signal-phrase flag phase to the existing `/ll:confidence-check` skill that sets `spike_needed: true` in issue frontmatter when the Phase 4.5 Outcome Risk Factors describe an unproven **internal** mechanism — the failure mode where the correct remedy is a code spike (FEAT-2567), not decide/wire/decompose. This converts the coding agent's ad-hoc "you should spike this" advice into a machine-readable routing signal, and doubles as a base-rate measurement: how often the spike failure mode actually occurs across the backlog, before autodev routing complexity (ENH-2568) is committed.

## Current Behavior

`skills/confidence-check/SKILL.md` Phase 4.5 writes Outcome Risk Factors when outcome confidence falls below `commands.confidence_gate.outcome_threshold` (default 75). Three follow-on phases scan that content for signal phrases and set frontmatter flags:

- Phase 4.6 — `decision_needed` ("open decision", "Option A/B", …)
- Phase 4.7 — `missing_artifacts` ("does not exist", "needs wiring", …) with co-deliverable suppression
- Phase 4.9 — `implementation_order_risk` ("implement tests first", …)
- Phase 4.8 — `mechanical_fanout_suppressed` (Pattern B suppression)

No phase recognizes the unproven-mechanism failure mode. ENH-2565 scored outcome-confidence 66/100 explicitly because "(a) the flock-guarded readiness-gated pop has zero precedent in any loop YAML, and (b) no existing test exercises N-worker FSM fan-out with a real barrier" — and no flag was set, so nothing downstream (autodev `triage_outcome_failure`, a human scanning frontmatter) can route it to the spike remedy. The spike was instead suggested ad-hoc by the coding agent during manual refinement.

## Expected Behavior

Running `/ll:confidence-check ENH-2565` (or any issue with equivalent risk factors) sets `spike_needed: true` in frontmatter and logs:

```
✓ spike_needed set to true — unproven internal mechanism detected in Outcome Risk Factors
```

Issues whose risk factors concern a third-party API are NOT flagged (that is `/ll:explore-api` + `learning_tests_required` territory). Issues already carrying `spike_attempted: true` or `spike_completed: true` are never re-flagged. `--check` mode makes no writes, as with all Phase 4.x flags.

## Motivation

- Closes the last outcome-confidence diagnosis with no machine-readable flag: ambiguity, missing artifacts, and ordering risk all have one; concentrated novel-mechanism risk does not.
- Prerequisite signal for ENH-2568 (autodev `check_spike_needed` routing and `spike-gate.yaml` both read this flag).
- Measurement before mechanism: landing the flag alone and running the backlog through `/ll:confidence-check --all` yields the `spike_needed` fire rate, which decides whether ENH-2568's routing investment is justified beyond the single ENH-2565 datum.

## Proposed Solution

New **Phase 4.10** (or next free 4.x number) in `skills/confidence-check/SKILL.md`, placed after Phase 4.9 and mirroring the Phase 4.6/4.7 structure exactly.

**Skip this phase if**: `CHECK_MODE` is true; or `spike_attempted`/`spike_completed` already true in frontmatter. Only has effect when Phase 4.5 produced Outcome Risk Factors.

**Signal phrases** (any match triggers the candidate check):
- "no precedent"
- "zero precedent"
- "unprecedented"
- "no existing test exercises"
- "untested mechanism"
- "novel mechanism"
- "unproven approach"
- "no test coverage of the"

**Score condition** (candidate must also satisfy at least one, to avoid flagging rhetorical uses of the phrases):
- `score_test_coverage` (Criterion B) <= 10, OR
- Criterion A Depth judged Moderate/Deep in the Phase 2b assessment

**External-API suppression**: if the matched risk-factor sentence names a third-party package, SDK, or external API surface (same exclusion heuristic as `/ll:refine-issue` Step 7.5 learning-target extraction — exclude project-internal code and contract-stable stdlib), do NOT set `spike_needed`. Instead emit an advisory line pointing to `/ll:explore-api`, and leave `learning_tests_required` handling to the existing machinery. This prevents double-remediation of the same risk.

**Write**: `spike_needed: true` via the inline `---` block Edit pattern of Phase 4.6/4.7 (or `ll-issues set-flag` if a CLI verb exists/is added — follow whatever Phase 4.6 does at implementation time). Idempotency: skip the write if already `true`. Log the ✓ line on write.

If no signal phrase matches, or the score condition fails, or suppression applies: leave `spike_needed` unchanged (never write `false` — absence is the negative, matching the other flags except decision_needed's option-count special case).

## Scope Boundaries

- **Not** the `/ll:spike` skill itself (FEAT-2567) and **not** the autodev/gate-loop routing that consumes the flag (ENH-2568). This issue is deliberately the smallest, measurement-first slice.
- No rubric.md scoring changes — Criteria A-D scoring is untouched; this phase only reads scores already computed.
- No changes to Phases 4.6-4.9 beyond adding the new phase alongside them.
- Not blocked by FEAT-2567: the flag can land and accumulate base-rate data before the skill exists.

## API/Interface

- New frontmatter flag `spike_needed: true` (absent = false). Consumed later by ENH-2568 (`ll-issues check-flag <ID> spike_needed`), FEAT-2567 (skill clears/supersedes via `spike_completed`).
- New log line contract: `✓ spike_needed set to true — unproven internal mechanism detected in Outcome Risk Factors`.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — new Phase 4.10; update the Phase 4.5 "determine whether there are findings" cross-references if they enumerate the flag phases.
- `skills/confidence-check/rubric.md` — only if the phase list / output-format template enumerates flags there.

### Dependent Files
- `scripts/little_loops/loops/autodev.yaml` `triage_outcome_failure` — future consumer (ENH-2568); no change here.
- `ll-issues check-flag` — verify it reads arbitrary boolean frontmatter flags generically (precedent: `decision_needed`, `missing_artifacts`).

### Similar Patterns
- Phase 4.7 (missing_artifacts) — closest structural twin: signal phrases + a suppression rule + idempotent write + log line.
- Phase 4.6 (decision_needed) — the original signal-phrase flag phase.
- `/ll:refine-issue` Step 7.5 — the external-dependency identification heuristic to reuse for suppression.

### Tests
- Structural tests **do exist** — `scripts/tests/test_confidence_check_skill.py` has one class per flag phase: `TestDecisionNeededFlagWriteBack` (~line 87), `TestMissingArtifactsFlagWriteBack` (~line 135), `TestImplementationOrderRiskFlagWriteBack` (~line 185). Each asserts, by string-searching `SKILL.md`: (1) phase heading exists, (2) correct frontmatter field name written, (3) signal phrases documented, (4) idempotency guard present, (5) CHECK_MODE skip guard present, (6) no `AskUserQuestion` (unconditional write); 4.7 adds a co-deliverable-suppression assertion.
- **New test class to add**: `TestSpikeNeededFlagWriteBack` mirroring the above, plus an assertion that the external-API suppression rule and the score-condition are documented in Phase 4.10.
- Manual AC: run against ENH-2565 (must flag), a doc-only issue (must not flag), and an external-API issue (must suppress + advise explore-api).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — the `DOC_STRINGS_PRESENT` parametrized list (~line 20) holds one `(doc_path, expected_string, issue_id)` tuple per documented issue-template field (repo convention, ENH-1963). When the `spike_needed` row lands in `ISSUE_TEMPLATE.md` (Step 3), add a tuple `("docs/reference/ISSUE_TEMPLATE.md", "spike_needed", "ENH-2569")` so the new field's doc presence is CI-asserted. Presence-check only; adding a row does not break existing cases. [Agent 3 finding]
- Confirmed **no change needed**: `cmd_check_flag` is field-agnostic (exercised generically by `scripts/tests/test_autodev_decision_gate.py` and `scripts/tests/test_rn_remediate.py`, not a dedicated test); the `learning_tests/extractor.py` exclusion list is stdlib/builtins-scoped, so the external-API suppression heuristic is authored fresh in Phase 4.10 rather than imported. [Agent 3 finding]

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — the **Frontmatter Field Reference Table** (~lines 886–888) already enumerates `decision_needed`, `missing_artifacts`, `implementation_order_risk`, `mechanical_fanout_suppressed`; add a `spike_needed` (bool) row there.
- CHANGELOG entry.

### Configuration
- None. Threshold reuse: fires only when Phase 4.5 ran (outcome < `commands.confidence_gate.outcome_threshold`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact write mechanism (resolves the "or CLI verb" ambiguity in Proposed Solution):**
- Phases 4.6/4.7/4.9 write their flag via the **Edit tool**, inline `---` block replacement — `skills/confidence-check/SKILL.md:373` (4.6), `:399` (4.7), `:421` (4.9). This is explicitly *distinct* from Phase 4's `ll-issues set-scores` CLI path.
- **No `ll-issues set-flag` verb exists** (`scripts/little_loops/cli/issues/__init__.py` dispatcher, confirmed). Do NOT plan around adding one; mirror the Edit-tool pattern. (Generic programmatic writes go through `frontmatter.py:update_frontmatter()` at lines 243–266, but the sibling phases use the Edit tool, not a CLI, so Phase 4.10 should too.)
- `ll-issues check-flag <ID> <field>` **is** confirmed generic — `scripts/little_loops/cli/issues/check_flag.py:cmd_check_flag()` (lines 13–33) reads any boolean frontmatter field, exit 0 if `'true'`. ENH-2568's `check-flag ... spike_needed` consumer needs no CLI change.

**Score-condition caveat (affects Implementation Step 2):**
- `score_test_coverage` IS a persisted frontmatter field (written by Phase 4 via `--score-test-coverage`, `SKILL.md:297`), so the `score_test_coverage <= 10` condition can read frontmatter directly.
- **Criterion A Depth is NOT persisted** — only the combined `score_complexity` total is written (`SKILL.md:296`); the Breadth/Depth sub-split from Phase 2b (`SKILL.md:222–225`, levels Mechanical/Local/Moderate/Deep) exists only in the in-session assessment reasoning. Phase 4.10 must **re-derive** "Depth Moderate/Deep" from the Phase 2b assessment text produced earlier in the same run, not from a `score_complexity_depth` field (none exists).

**External-API suppression heuristic (Implementation Step 2) — concrete source:**
- The exclusion logic to reuse lives in `scripts/little_loops/learning_tests/extractor.py:_EXTRACTION_PROMPT` (lines 33–61); the canonical exclusion list is at lines 42–46 (project-internal code; Python builtins; contract-stable stdlib `os, sys, pathlib, json, re, datetime`). Entry points: `extract_learning_targets()` (149–194), `resolve_learning_targets()` (197–218).

**Phase ordering note:** In file order Phase 4.8 (`SKILL.md:427`) actually follows Phase 4.9 (`:405`). Place the new phase after both; "next free 4.x number" ⇒ **Phase 4.10**.

**Flag-enumeration touch-points:** `skills/confidence-check/rubric.md` does NOT enumerate flag names (grep-confirmed zero matches) — no change needed there. Only `docs/reference/ISSUE_TEMPLATE.md` needs the new row.

## Implementation Steps

1. Draft Phase 4.10 text after Phase 4.8 (`SKILL.md:427`), mirroring Phase 4.7's structure (skip conditions, signal phrases, suppression, Edit-tool inline `---` write, log line). Use the Edit-tool pattern — **not** a `set-flag` CLI (none exists).
2. Add the score-condition (read `score_test_coverage` from frontmatter for the `<= 10` check; re-derive Criterion A Depth from the in-session Phase 2b assessment — no persisted Depth field) and the external-API-suppression rule (reuse the exclusion list from `learning_tests/extractor.py:_EXTRACTION_PROMPT`).
3. Add a `spike_needed` (bool) row to the Frontmatter Field Reference Table in `docs/reference/ISSUE_TEMPLATE.md` (~line 886). No `rubric.md` change (it does not enumerate flags).
4. Add `TestSpikeNeededFlagWriteBack` to `scripts/tests/test_confidence_check_skill.py`, mirroring `TestMissingArtifactsFlagWriteBack` (7-assertion shape: heading, field name, signal phrases, idempotency guard, CHECK_MODE guard, no-`AskUserQuestion`, plus the suppression-rule check). Also add the tuple `("docs/reference/ISSUE_TEMPLATE.md", "spike_needed", "ENH-2569")` to `DOC_STRINGS_PRESENT` in `scripts/tests/test_wiring_reference_docs.py` so the new template row is CI-asserted (wiring pass).
5. Validate against the three manual AC issues (ENH-2565, doc-only, external-API) and run `python -m pytest scripts/tests/test_confidence_check_skill.py -v`.
6. Run `/ll:confidence-check --all` (or `--sprint`) once post-merge and record the `spike_needed` fire rate in ENH-2568 before starting its routing work.

## Impact

- **Priority**: P3 — small, additive, and the cheapest piece of the spike lattice; unblocks measurement for ENH-2568.
- **Effort**: Small — one markdown phase + doc touches; no engine or loop changes.
- **Risk**: Low — worst case is a spurious frontmatter flag that nothing consumes yet.
- **Breaking Change**: No.

## Related Issues

- **FEAT-2567** — `/ll:spike` skill that acts on the flag (not a blocker for this issue).
- **ENH-2568** — autodev triage routing + spike-gate loop; consumes this flag and is blocked by it.
- **ENH-2565** — motivating instance and first manual AC case.
- **ENH-2209** — learning-target extraction heuristic reused for external-API suppression.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-07-10T01:34:59Z - `manual capture via Claude Cowork session`
- `/ll:refine-issue` - 2026-07-14T15:18:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260714-151757-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/bbfcda80-6904-47b7-b170-561c9dc789f0.jsonl`
- `/ll:wire-issue` - 2026-07-14T15:33:00 - `session JSONL unresolved`
- `/ll:manage-issue` - 2026-07-14T20:41:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260714-151757-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/8e05480c-967d-46bc-838f-48bac77dd30c.jsonl`
