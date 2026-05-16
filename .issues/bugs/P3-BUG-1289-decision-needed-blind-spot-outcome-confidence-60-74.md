---
captured_at: "2026-04-25T19:07:05Z"
completed_at: "2026-04-25T19:48:04Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# BUG-1289: `decision_needed` blind spot for outcome_confidence 60–74

## Summary

`confidence-check` Phase 4.6 sets `decision_needed: true` only when `outcome_confidence < 60`, but autodev's `outcome_threshold` defaults to 75. Issues scoring 60–74 with genuine unresolved ambiguity (`score_ambiguity ≤ 10`) never get flagged, so autodev's `check_decision_before_size_review` gate never fires for them — they fall straight through to `run_size_review` and risk spurious decomposition.

## Current Behavior

Phase 4.6 of `confidence-check` (`skills/confidence-check/SKILL.md`, "Phase 4.6: Decision-Needed Flag") has this condition:

> "This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < 60`)"

The Phase 4.5 write-back that generates `Outcome Risk Factors` (which Phase 4.6 scans for signal phrases) is itself skipped when `outcome_confidence >= 60`. So the Phase 4.6 trigger cannot fire for any issue with `outcome_confidence` between 60 and 74, even if `score_ambiguity` is 0.

Meanwhile, `autodev.yaml` `context.outcome_threshold` defaults to 75. An issue with `outcome_confidence: 64` fails `check_passed`, but `decision_needed` is never set, so `check_decision_before_size_review` exits 1 → `run_size_review`.

## Expected Behavior

When `outcome_confidence` is below the project's `outcome_threshold` AND `score_ambiguity ≤ 10`, `decision_needed: true` should be set on the issue regardless of whether `outcome_confidence` is above or below 60. The current 60 threshold is an implementation artifact, not an intentional design boundary.

## Motivation

The `decision_needed` flag exists precisely to steer autodev away from size-review when the right intervention is `decide-issue`. The blind spot negates this protection for the 60–74 range — a realistic band where issues are "moderately risky" with ambiguity problems but not low enough to trigger the existing write-back path.

## Steps to Reproduce

1. Create an issue with `outcome_confidence: 64` and `score_ambiguity: 5` in frontmatter (unresolved design decision)
2. Set project `outcome_threshold: 75` in `.ll/ll-config.json`
3. Run `/ll:confidence-check [ID]`
4. Observe: Phase 4.5 generates no `Outcome Risk Factors` (because 64 ≥ 60)
5. Observe: Phase 4.6 never runs; `decision_needed` remains unset
6. Run autodev: `check_decision_before_size_review` exits 1 → `run_size_review` fires
7. Issue is incorrectly sent to size-review instead of `decide-issue`

## Root Cause

- **File**: `skills/confidence-check/SKILL.md`
- **Anchor**: Phase 4.5 (`HAS_FINDINGS` condition) and Phase 4.6 ("only has effect when... `outcome_confidence < 60`")
- **Cause**: The Phase 4.5 `HAS_FINDINGS` trigger for `Outcome Risk Factors` uses a hardcoded 60 threshold rather than the project-configurable `outcome_threshold`. Phase 4.6 depends on Phase 4.5 having fired, so it inherits the same gap.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `skills/confidence-check/SKILL.md:455` — `"Outcome Risk Factors" (present when outcome confidence < 60)` — the hardcoded `< 60` bucket in the `HAS_FINDINGS` definition
- `skills/confidence-check/SKILL.md:587` — `### Outcome Risk Factors (if outcome confidence < 60)` — the output format heading that confirms Phase 4.5 only writes this section at that threshold
- `skills/confidence-check/SKILL.md:501` — `"This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., \`HAS_FINDINGS\` is true and \`outcome_confidence < 60\`)"` — the Phase 4.6 guard that structurally depends on Phase 4.5 having emitted text
- `scripts/little_loops/loops/autodev.yaml:22–23` — `outcome_threshold: 75` in the loop `context:` block (canonical source: `commands.confidence_gate.outcome_threshold` in ll-config.json, but that key is absent from `.ll/ll-config.json`, so 75 is the effective default for the loop)
- `scripts/little_loops/config/automation.py:101` — `outcome_threshold: int = 70` in `ConfidenceGateConfig` — the Python-layer default is **70**, not 75; the loop context default (75) is tighter

## Proposed Solution

Two complementary options:

**Option A (preferred)**: In Phase 4.5, lower the `Outcome Risk Factors` trigger so it fires whenever `outcome_confidence < outcome_threshold` (read from `.ll/ll-config.json` `commands.confidence_gate.outcome_threshold`, defaulting to 75). Update Phase 4.5 trigger from hardcoded 60 to the project threshold.

> **Selected:** Option A — exact precedent in `manage-issue/SKILL.md:202`; all config infrastructure already exists; text-only change with no false-positive risk

**Option B** (additional safety net): In Phase 4.6, add a second trigger that sets `decision_needed: true` when `score_ambiguity ≤ 10` regardless of `outcome_confidence` — because low ambiguity score is a direct and unambiguous signal of a decision bottleneck.

Recommend implementing Option A first (closes the gap fully), then evaluate Option B separately.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-25.

**Selected**: Option A — Fix Phase 4.5 threshold

**Reasoning**: Option A is a text-only substitution in `skills/confidence-check/SKILL.md` replacing the hardcoded `< 60` with `config.commands.confidence_gate.outcome_threshold` (default 75), following the established pattern from `skills/manage-issue/SKILL.md:202`. All backing infrastructure (config-schema.json, `ConfidenceGateConfig`, autodev.yaml, configure skill) already exists. Option B was explicitly evaluated and rejected in BUG-1278 due to a confirmed over-trigger case (ENH-1197: `score_ambiguity: 10`, `decision_needed: false`, correctly no blocking decision) and would fire unconditionally on passing issues whose consumers are not designed to receive `decision_needed: true`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (fix Phase 4.5 threshold) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (second Phase 4.6 trigger) | 1/3 | 2/3 | 3/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: `skills/manage-issue/SKILL.md:202` uses `config.commands.confidence_gate.readiness_threshold` as direct precedent; `config-schema.json:367-373` and `automation.py:101` already define the field; `autodev.yaml:23` uses `outcome_threshold: 75` as effective default
- Option B: `BUG-1278` decided against identical `≤ 10` approach with confirmed over-trigger case (ENH-1197); fires without Phase 4.5 having written any prose — no existing pattern has this shape; ENH-1288 (P2 open) will handle the same routing concern at the loop level

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 4.5 `HAS_FINDINGS` condition and Phase 4.6 guard

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — reads `decision_needed` field via `ll-issues show --json`; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml` — reads `decision_needed` frontmatter; additional consumer of the flag Phase 4.6 sets; no change needed
- `scripts/little_loops/issue_manager.py:563-565` — `if info.decision_needed is True` routes issue to decide-issue in Python CLI; fix correctly causes more issues to hit this branch; no change needed
- `scripts/little_loops/parallel/worker_pool.py:373` — `if issue.decision_needed is True` in `_process_issue()`; same downstream consumer; no change needed

### Similar Patterns
- `manage-issue` Phase 2.3 Decision Gate — also reads `decision_needed`; unaffected
- `skills/manage-issue/SKILL.md:183–202` — canonical notation for config reads in SKILL.md prose: `config.commands.confidence_gate.readiness_threshold`; the BUG-1289 fix introduces `config.commands.confidence_gate.outcome_threshold` following this precedent
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:150–165` — canonical Python snippet for reading `outcome_threshold` in a YAML loop action: `cg.get('outcome_threshold', ${context.outcome_threshold})`; same pattern in `autodev.yaml:134–158`

### Tests
- `scripts/tests/test_confidence_check_skill.py:56–97` — `TestDecisionNeededFlagWriteBack` class; existing tests for Phase 4.6 heading and `decision_needed: true` documentation; add new test method here asserting Phase 4.5 text contains `outcome_threshold` (not hardcoded `60`)
- `scripts/tests/test_confidence_check_skill.py:59` — `_phase_text()` helper slices SKILL.md by phase heading via `content.find("\n###", start + 1)`; use same pattern to slice Phase 4.5 for new tests
- `scripts/tests/test_frontmatter.py:283–293` — inline fixture pattern: `content = """---\noutcome_confidence: 64\nscore_ambiguity: 5\n---\n# Fixture\n"""` (no temp files needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1550-1555` — `test_context_thresholds_defined` asserts `"outcome_threshold" in ctx` for autodev loop; safe, no change needed (key presence only, not value)
- `scripts/tests/test_config.py:403` — `assert config.outcome_threshold == 70`; will break **only if** `ConfidenceGateConfig` Python default is changed to 75; this fix targets SKILL.md prose only — do NOT change `automation.py:101` or this test will fail

### Documentation
- N/A — Phase 4.6 behavior not separately documented

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md:370-376` — configure wizard lists `70 (default)` as an option for `outcome_threshold`; no change needed (accurate schema default), but note: the SKILL.md prose will default to 75 while the schema/Python default remains 70
- `skills/init/interactive.md:254,328,352` — documents `outcome_threshold = 70` as the schema default to omit; no change needed — the schema default stays 70

### Configuration
- `.ll/ll-config.json` `commands.confidence_gate.outcome_threshold` — used to parameterize the trigger; **this key is not currently present** in `.ll/ll-config.json` (only `enabled` and `readiness_threshold` are set)
- Default value is **70** in `scripts/little_loops/config/automation.py:101` (`ConfidenceGateConfig`) and `config-schema.json`; the autodev loop context uses **75** (`autodev.yaml:23`) — the skill should default to 75 to match loop behavior, not 70

## Implementation Steps

1. Read `commands.confidence_gate.outcome_threshold` from `.ll/ll-config.json` in confidence-check Phase 4.5 (default 75)
2. Change Phase 4.5 `Outcome Risk Factors` condition from `outcome_confidence < 60` to `outcome_confidence < outcome_threshold`
3. Phase 4.6 inherits the fix automatically since it depends on Phase 4.5 having produced Risk Factors
4. Add test fixture to verify `decision_needed` is set for issues in the 60–74 range with `score_ambiguity ≤ 10`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Step 2 target lines: `skills/confidence-check/SKILL.md:455` (bucket definition) and `:587` (output heading) — both contain the hardcoded `< 60` string; update both to `< outcome_threshold`
- Step 2 notation: use `config.commands.confidence_gate.outcome_threshold` (with `default: 75`) following the `manage-issue` SKILL.md prose convention at `skills/manage-issue/SKILL.md:183–202`
- Step 4 test file: add to `scripts/tests/test_confidence_check_skill.py` in `TestDecisionNeededFlagWriteBack` class (line 56); reuse `_phase_text()` pattern (line 59) but target Phase 4.5 instead of Phase 4.6; assert `"60"` does NOT appear as a standalone threshold and `"outcome_threshold"` DOES appear
- Default value to use: **75** (matching autodev loop context), NOT 70 (Python/schema default is more permissive and would widen the gap slightly)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Do NOT modify** `scripts/little_loops/config/automation.py:101` — the Python dataclass default stays `outcome_threshold: int = 70`; changing it to 75 would break `test_config.py:402` and misalign with `config-schema.json:370`; the SKILL.md prose default of 75 is independent of the Python class default
6. Verify `scripts/tests/test_config.py:402` still passes (`assert config.outcome_threshold == 70`) — it will if `automation.py` is untouched
7. Verify `scripts/tests/test_builtin_loops.py:1550-1555` still passes — it checks `"outcome_threshold" in ctx` for autodev context; unaffected by SKILL.md changes

## Impact

- **Priority**: P3 — affects projects with `outcome_threshold > 60` (the default); fixes a systematic miss in the decision gate
- **Effort**: Small — single condition change in SKILL.md; no new logic
- **Risk**: Low — only affects Phase 4.5/4.6 write-back; does not change scoring or readiness gate behavior
- **Breaking Change**: No — adds write-back for issues that previously got no write-back; additive

## Labels

`bug`, `confidence-check`, `decision-needed`, `autodev`, `captured`

## Resolution

Fixed by replacing the hardcoded `outcome_confidence < 60` threshold in Phase 4.5 and Phase 4.6 of `skills/confidence-check/SKILL.md` with `config.commands.confidence_gate.outcome_threshold` (default: 75). Phase 4.6 inherits the fix automatically since it depends on Phase 4.5 having emitted Outcome Risk Factors. Added `TestPhase45OutcomeThreshold` test class with 3 new tests to `scripts/tests/test_confidence_check_skill.py` to prevent regression.

## Session Log
- `/ll:manage-issue` - 2026-04-25T19:48:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/108d4a10-0e89-4c33-b67d-c715cd39fd6e.jsonl`
- `/ll:ready-issue` - 2026-04-25T19:38:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8773f369-1b55-4807-a306-62c43b644158.jsonl`
- `/ll:decide-issue` - 2026-04-25T19:33:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4da1c7d0-ca07-471f-a273-72684f564dab.jsonl`
- `/ll:confidence-check` - 2026-04-25T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/678ce4e2-2d4a-4e51-9c09-4bc6e9dc83cd.jsonl`
- `/ll:wire-issue` - 2026-04-25T19:27:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e062038-fdf7-4d52-8f99-e3db06cb9745.jsonl`
- `/ll:refine-issue` - 2026-04-25T19:22:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e01f4663-cf90-46a5-9bf2-707bcff9ccec.jsonl`
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
