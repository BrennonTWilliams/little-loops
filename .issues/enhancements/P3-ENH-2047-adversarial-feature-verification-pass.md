---
id: ENH-2047
title: Adversarial feature-verification pass (try-to-break, distinct from confirmatory
  verify)
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T00:00:00Z'
completed_at: '2026-06-14T13:47:00Z'
discovered_date: '2026-06-09'
discovered_by: capture-issue
relates_to:
- ENH-216
- FEAT-808
labels:
- verification
- testing
- adversarial
- harness
- eval
decision_needed: false
confidence_score: 97
outcome_confidence: 80
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2047: Adversarial feature-verification pass

## Summary

Add a verification mode that deliberately tries to *break* an implemented feature
— boundary values, malformed/hostile inputs, failure modes — rather than
confirming it works. This is squid's adversarial-QA framing: failing to attempt a
few genuine break-paths is itself a FAIL, not a pass.

Today every feature-level verification path in little-loops is **confirmatory** or
**user-perspective**; the only adversarial framing that exists is for issue
*prioritization*, not for stress-testing a built feature.

## Current Behavior

| Path | Framing | Adversarial? |
|---|---|---|
| `run-tests` | Executes configured `test_cmd` | No — execution only |
| eval harness `execute` state (`create-eval-from-issues`) | "Use it as a real user would" | No — quality-of-experience |
| `verify-issue-loop` | "Does criterion N *hold*?" per acceptance criterion | No — confirmatory |
| `verify-issues` | Issue accuracy / regression vs. code | No — consistency check |
| `go-no-go` | Adversarial debate on *whether to build* | Adversarial, but prioritization |

Existing fuzz/adversarial issues are narrower: ENH-216 (fuzz critical *parsers*)
and the parallel-state fuzz suite (FEAT-1200/1214/1219/1222) target specific
modules, not "attack this implemented feature/criterion." Nothing generates
boundary/hostile/failure-mode probes against a feature and treats "no break-paths
attempted" as failure.

## Expected Behavior

A new adversarial verification pass that, for a given feature or acceptance
criterion, generates and exercises deliberate break-paths:

- Boundary / extreme values (empty, max, off-by-one, unicode, very large).
- Malformed / hostile inputs (wrong types, injection-shaped strings, partial
  state, concurrent/duplicate invocation).
- Known failure modes (missing config, absent files, interrupted runs).
- **Verdict rule (squid-derived): attempting fewer than N genuine break-paths is
  itself a FAIL**, even if everything attempted passed.

### Hard constraint

This MUST be a *distinct* pass — a sibling to `verify-issue-loop` or a new mode —
and MUST NOT alter the eval harness `execute` state. The `execute` state's
"as a real user would" framing is load-bearing and protected by a standing
correction (eval `execute` = exercise as a user, not break-it, not implement).
Polluting it with adversarial framing would regress that design.

Placement options for refinement to decide:
- A sibling skill that emits an adversarial verification loop YAML (mirrors
  `verify-issue-loop`'s structure: one state per probe class, `llm_structured`
  evaluator, fail-fast), OR
- An `--adversarial` mode on `verify-issue-loop` that adds a break-path state
  per criterion alongside the existing "does it hold" state.

Recommendation: lean toward a sibling skill so the confirmatory and adversarial
loops stay independently runnable and composable.

## Acceptance Criteria

- [ ] A verification path exists that, given a feature/issue, produces deliberate
      break-path probes across at least boundary, malformed/hostile, and
      failure-mode categories.
- [ ] The pass FAILs when fewer than a configured minimum number of distinct
      break-paths are genuinely attempted (not just when a probe finds a bug).
- [ ] The eval harness `execute` state is unchanged (verified by test/diff).
- [ ] Output integrates with existing FSM verification tooling (runnable via
      `ll-loop`, fail-fast routing consistent with `verify-issue-loop`).
- [ ] Tests cover: a feature that survives all probes (pass), a feature with a
      reproducible break (fail-with-finding), and the "too few break-paths
      attempted" self-FAIL.

## Out of Scope

- Replacing or modifying `run-tests` (stays execution-only).
- Parser-level fuzzing already tracked by ENH-216 and the parallel fuzz suite.
- Adversarial *prioritization* (owned by `go-no-go` / FEAT-808).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify / Create
- `skills/adversarial-verify-loop/SKILL.md` *(new)* — new sibling skill (Option A); mirrors `skills/verify-issue-loop/SKILL.md` synthesis steps
- `skills/verify-issue-loop/SKILL.md` — extend with `--adversarial` flag (Option B); currently 259 lines

#### Reference Files (Patterns to Follow)
- `skills/verify-issue-loop/SKILL.md` — sibling pattern: generates loop YAML with one `verify-criterion-N` state per criterion using `action_type: prompt` + `evaluate.type: llm_structured`; Step 3–5 define the synthesis logic to mirror
- `skills/create-eval-from-issues/SKILL.md` — protected `execute` state ("as a real user would"); MUST NOT be altered; hard constraint source

#### FSM Evaluator Infrastructure
- `scripts/little_loops/fsm/evaluators.py:158` — `evaluate_output_numeric()`: parses stdout as float and applies comparison operator; satisfies MR-1 as member of `NON_LLM_EVALUATOR_TYPES`
- `scripts/little_loops/fsm/evaluators.py:255` — `evaluate_output_json()`: parses JSON stdout, extracts value at dot-path, applies comparison; enables `.count >= min_probes` gate against a structured artifact file
- `scripts/little_loops/fsm/validation.py:81` — `NON_LLM_EVALUATOR_TYPES` frozenset: `{exit_code, output_numeric, output_json, output_contains, convergence, diff_stall, action_stall, mcp_result, harbor_scorer}` — any of these satisfies MR-1 structural check

#### Tests
- `scripts/tests/test_verify_issue_loop.py` — test pattern to follow: inline YAML fixture (`VERIFY_YAML_3_CRITERIA`), validates routing + terminal states + `load_and_validate` pass
- `scripts/tests/test_create_eval_from_issues.py` — regression guard: confirms `execute` state framing unchanged; run after any implementation

#### Similar Patterns (Shell-Count Gate)
- `scripts/little_loops/loops/apply-research.yaml` `validate_scores` state — canonical `output_numeric` shell-count pattern: shell computes count, echoes scalar; comment "Output ONLY the count — required by output_numeric evaluator"
- `scripts/little_loops/loops/general-task.yaml` `check_done_criteria` state — `output_json` pattern extracting `.count` field from a JSON artifact file written by a prior state

#### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 rule rationale; rule MR-4 (`on_no`/`on_partial` dead-end warning)
- `docs/guides/LOOPS_GUIDE.md` — evaluator types, routing, terminal state reference

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `skills/adversarial-verify-loop/agents/openai.yaml` *(new)* — Codex Skills API frontmatter; must be generated via `ll-adapt-skills-for-codex --apply` after `SKILL.md` is created; `test_all_real_skills_have_openai_yaml` in `scripts/tests/test_adapt_skills_for_codex.py` will fail in CI without it

### Documentation Updates

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — update `"64 skills"` → `"65 skills"` (CI-enforced by `test_wiring_guides_and_meta.py` `DOC_STRINGS_PRESENT`)
- `CONTRIBUTING.md` — update `"64 skill definitions"` → `"65 skill definitions"` (two occurrences: directory tree + section header); optionally add `adversarial-verify-loop/` to directory listing alongside `verify-issue-loop/`
- `docs/ARCHITECTURE.md` — update `"64 composable skills"` in mermaid node and `"# 64 skill definitions"` in directory tree → 65 (CI-enforced)
- `commands/help.md` — add `/ll:adversarial-verify-loop` entry in `AUTOMATION & LOOPS` block and Quick Reference Table (mirrors `/ll:verify-issue-loop` entry)
- `docs/reference/COMMANDS.md` — add `### /ll:adversarial-verify-loop` section and Quick Reference table row (mirrors `### /ll:verify-issue-loop`)
- `docs/reference/CLI.md` — add skill table row (mirrors `verify-issue-loop` row)
- `.claude/CLAUDE.md` — add `adversarial-verify-loop`^ to `## Commands & Skills` Automation & Loops list
- `CHANGELOG.md` — add entry for ENH-2047 under next release version

### Tests (Wiring Guards)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — add `("skills/adversarial-verify-loop/SKILL.md", "ENH-2047")` to `DOC_FILES_MUST_EXIST` (mirrors `("skills/verify-issue-loop/SKILL.md", "FEAT-1447")` pattern)
- `scripts/tests/test_wiring_cli_registry.py` — add assertion for `/ll:adversarial-verify-loop` in `commands/help.md` and `docs/reference/COMMANDS.md`
- `scripts/tests/test_doc_counts.py` — update skill count assertion 64 → 65 if hardcoded

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — AC #2 resolution path identified:_

#### AC #2 Resolution: Structural + Filesystem Enforcement

The go-no-go identified AC #2 ("too few break-paths attempted is FAIL") as a blocker because `output_numeric` checking a count in an LLM-written artifact satisfies MR-1 structurally but the count remains LLM self-reported.

**Research-identified resolution**: Enforce the minimum probe count at **two independent layers**:

1. **Structural (YAML generation time)** — the skill generates exactly one state per probe class from a hardcoded minimum set (`[probe-boundary, probe-malformed-hostile, probe-failure-mode]`). It refuses to generate a loop with fewer than `min_probes` states. A post-generate `exit_code` gate on `ll-loop validate <loop>` confirms the YAML is structurally valid with N states. This gate is `exit_code` → member of `NON_LLM_EVALUATOR_TYPES`; MR-1 satisfied.

2. **Runtime (filesystem artifact count)** — each probe state writes its outcome to `${context.run_dir}/probe-<N>.json`. A dedicated `count_probes` shell state runs `ls ${context.run_dir}/probe-*.json | wc -l` and `output_numeric` checks `>= min_probes`. The file count is filesystem-derived (shell `wc -l`), not LLM-reported; MR-1 satisfied.

Neither gate requires LLM self-reporting. Both `exit_code` and `output_numeric` are in `NON_LLM_EVALUATOR_TYPES`.

---

### Option A: New Sibling Skill `adversarial-verify-loop` (Recommended)

> **Selected:** Option A — New Sibling Skill `adversarial-verify-loop` — mirrors `verify-issue-loop` structure exactly, is purely additive, and keeps adversarial and confirmatory loops independently runnable and composable.

Create `skills/adversarial-verify-loop/SKILL.md` following `skills/verify-issue-loop/SKILL.md`'s structure:
- Emits `.loops/adversarial-<ISSUE-ID>-<slug>.yaml` with states: `probe-boundary`, `probe-malformed-hostile`, `probe-failure-mode` (plus optional additional categories)
- Each probe state: `action_type: prompt` (adversarial framing — "try to break criterion by…") + `llm_structured` evaluator
- A `count_probes` shell state with `output_numeric >= min_probes` satisfies MR-1
- Independently runnable; composable with `verify-issue-loop` in a two-stage pipeline

**Trade-off**: Two separate SKILL.md files to maintain; no single command does both confirmatory + adversarial.

### Option B: `--adversarial` Flag on `verify-issue-loop`

Extend `skills/verify-issue-loop/SKILL.md` with an `--adversarial` flag:
- When set, generates additional `probe-*` states appended after each `verify-criterion-N` state
- Single entry point for all verification types

**Trade-off**: Couples adversarial and confirmatory loops; harder to run probe-only independently; adds conditional complexity to an already well-defined skill. Contradicts issue's stated preference for composability.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-10.

**Selected**: Option A: New Sibling Skill `adversarial-verify-loop`

**Reasoning**: Option A scores 11/12 vs. Option B's 4/12. The codebase already has a direct precedent in `skills/verify-issue-loop/SKILL.md` — Steps 3–5 of the synthesis logic are a mirror template that can be adopted verbatim with only the adversarial framing swapped in. The skill is purely additive (one new SKILL.md, one new test file), satisfies the hard constraint about not touching the eval harness `execute` state by construction, and matches the existing convention where adversarial framing (`go-no-go`) lives as a separate skill rather than a flag on an existing one. Option B would modify a 259-line skill, add conditional logic, and risk breaking existing confirmatory verification behavior.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (sibling skill) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B (--adversarial flag) | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Option A: `skills/verify-issue-loop/SKILL.md` is a direct synthesis template; `adversarial-redesign.yaml` provides the `output_contains` sentinel pattern for MR-1-compliant adversarial routing; `go-no-go` confirms the convention of keeping adversarial framing in a separate skill
- Option B: Issue explicitly documents the trade-off as "Contradicts issue's stated preference for composability"; no existing pattern adds adversarial mode via flag to an existing confirmatory skill

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references:_

1. **Run `/ll:decide-issue ENH-2047`** to select Option A vs. Option B before writing any code
2. **(Option A)** Create `skills/adversarial-verify-loop/SKILL.md`:
   - Copy `skills/verify-issue-loop/SKILL.md`'s Step 1–2 (resolve issue, extract acceptance criteria) verbatim
   - Replace Step 3 synthesis prompts with adversarial break-path framing (boundary / malformed-hostile / failure-mode per criterion)
   - Add `count_probes` shell state using `ls ${context.run_dir}/probe-*.json | wc -l` + `output_numeric >= ${context.min_probes:-3}`
   - Wire transitions: each probe state `on_yes: probe-<next>` (or `count_probes`), `on_no: failed_with_finding`; `count_probes on_yes: done`, `on_no: failed_too_few`
3. **(Option A)** Write tests in `scripts/tests/test_adversarial_verify_loop.py` following `test_verify_issue_loop.py` pattern:
   - Fixture: 3-probe-class YAML; assert `count_probes` state present, both `failed_with_finding` and `failed_too_few` terminals exist
   - Test: all probes pass → `done`; one probe breaks feature → `failed_with_finding`; `count_probes < min_probes` → `failed_too_few`
4. **Regression**: run `python -m pytest scripts/tests/test_create_eval_from_issues.py -v` to confirm `execute` state unchanged
5. **Validate**: `ll-loop validate adversarial-<issue-id>-<slug>` on a sample generated loop; confirm no MR-1, MR-4, MR-5 violations

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Generate Codex adapter**: Run `ll-adapt-skills-for-codex --apply` to create `skills/adversarial-verify-loop/agents/openai.yaml`; CI (`test_all_real_skills_have_openai_yaml`) will fail without it
7. **Update skill counts**: Increment `"64 skills"` → `"65 skills"` in `README.md`, `CONTRIBUTING.md` (two occurrences), and `docs/ARCHITECTURE.md` (two occurrences: mermaid node + directory tree)
8. **Add command documentation**: Add `/ll:adversarial-verify-loop` entry to `commands/help.md` (AUTOMATION & LOOPS block + Quick Reference Table), `docs/reference/COMMANDS.md` (new `### /ll:adversarial-verify-loop` section), and `docs/reference/CLI.md` skill table row
9. **Update CLAUDE.md and CHANGELOG**: Add `adversarial-verify-loop`^ to `.claude/CLAUDE.md` Automation & Loops list; add ENH-2047 entry to `CHANGELOG.md`
10. **Update wiring test guards**: Add `("skills/adversarial-verify-loop/SKILL.md", "ENH-2047")` to `DOC_FILES_MUST_EXIST` in `test_wiring_skills_and_commands.py`; add `/ll:adversarial-verify-loop` registry assertion to `test_wiring_cli_registry.py`; update skill count in `test_doc_counts.py` if hardcoded

## Impact

- **Priority**: P3 — Improves verification quality but no existing workflow is blocked; confirmatory paths remain fully functional
- **Effort**: Medium — One new `SKILL.md` (mirroring `verify-issue-loop`), one new test file, plus wiring updates across docs/counts; zero Python runtime changes
- **Risk**: Low — Purely additive; hard constraint on not touching `execute` state enforced by AC #3 regression test
- **Breaking Change**: No

## Labels

verification, testing, adversarial, harness, eval

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-10_ — **NO-GO (REFINE)**

**Deciding Factor**: AC #2 ("too few break-paths attempted is FAIL") is not a minor gap — it is the feature's primary safety property, and the proposed `output_numeric` mechanism requires either LLM self-reporting (MR-1 violation, ~33% accuracy per SHOR Table 1) or unacknowledged FSM core changes to `evaluators.py`/`schema.py`; neither path is acceptable without explicit resolution before implementation.

### Key Arguments For
- Purely additive: one new SKILL.md + one test file, zero Python runtime changes; `output_numeric` evaluator already exists at `scripts/little_loops/fsm/evaluators.py:158`
- ENH-216 proved adversarial testing finds real bugs (`RouteConfig.from_dict()` crash at `scripts/little_loops/fsm/schema.py:159`) that confirmatory testing missed

### Key Arguments Against
- AC #2 has no sound FSM implementation: `output_numeric` can compare a value but cannot verify an LLM actually attempted N distinct probe categories without self-reporting, which `scripts/little_loops/fsm/validation.py:81` (`NON_LLM_EVALUATOR_TYPES`) and MR-1 flag as ~33% accurate
- Issue is 1 day old, design decision (sibling-skill vs. `--adversarial-mode`) is explicitly deferred; EPIC-1867 (FSM Decomposition), EPIC-1929 (HITL primitives), and ENH-2073 (per-state model overrides) are all upstream blockers that make implementation now guarantee churn

### Rationale
The "too few break-paths attempted" gate (AC #2) has no implementable FSM mechanism without either violating MR-1 or expanding scope into FSM core changes — a genuine blocker the pro-argument does not rebut. The infrastructure timing concern (EPIC-1867 rewriting the executor, EPIC-1929 HITL not available) adds churn risk. Refinement should explicitly resolve the AC #2 mechanism and the sibling-skill vs. flag decision before implementation begins.

## Status

done

## Session Log
- `/ll:ready-issue` - 2026-06-14T13:29:50 - `ff169e6c-e84f-47ae-8571-1012ec3c1ff5.jsonl`
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `a2394929-9a83-4ab1-97fc-e5243bc0c311.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `ef92cf80-1078-41c4-8aca-bc4d37e1afbb.jsonl`
- `/ll:wire-issue` - 2026-06-10T18:33:07 - `9de33298-3da0-44eb-8a7b-15b8da33a768.jsonl`
- `/ll:decide-issue` - 2026-06-10T18:24:32 - `66e20ece-f72d-4f7b-9576-1d8885b4263b.jsonl`
- `/ll:refine-issue` - 2026-06-10T18:22:07 - `9d980978-8e2a-4d9b-ab52-b29a954d367a.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:go-no-go` - 2026-06-10T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

- Captured - 2026-06-09 - from squid-plugin evaluation; adversarial-QA framing
  applied to feature verification, kept distinct from eval `execute`.
