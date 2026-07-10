---
id: FEAT-2567
title: /ll:spike skill — prove unprecedented mechanisms in isolation before implementation
type: FEAT
priority: P2
status: open
labels: [skills, confidence, risk-reduction, captured]
captured_at: "2026-07-10T01:34:59Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2570
---

# FEAT-2567: /ll:spike skill — prove unprecedented mechanisms in isolation before implementation

## Summary

Add a `/ll:spike` skill that retires concentrated technical risk on an issue by planning, implementing, and verifying a code spike — a standalone library + test class proving a novel mechanism in isolation — before the real integration point is touched. On success it appends `## Spike Results` to the issue, sets `spike_completed: true` in frontmatter, and re-scoring via `/ll:confidence-check` should recover the outcome-confidence points the unproven mechanism cost.

The ENH-2565 spike plan (readiness-gated pop + concurrency core for `rn-refine` `synth_pop`) is the golden example of the deliverable shape this skill should produce.

## Current Behavior

When `/ll:confidence-check` scores outcome confidence low because a mechanism has zero precedent in the codebase and no test exercises the risky core (ENH-2565: 66/100 for exactly these two reasons), there is no `/ll:` skill that produces the correct remedy. The existing remediation skills cover other failure modes:

- `/ll:decide-issue` — unresolved Option A/B ambiguity (`decision_needed`)
- `/ll:wire-issue` + `/ll:refine-issue --gap-analysis` — absent files / unwired integration (`missing_artifacts`)
- `/ll:issue-size-review` — issue too large; decompose
- `/ll:explore-api` + Learning-Test Registry — unproven **external** API assumptions

None of these applies when the risk is a novel **internal** mechanism (e.g., a flock-guarded readiness-gated queue pop with N-worker fan-out). Today the spike is planned ad-hoc by the coding agent, with no standard plan shape, no standard spike directory, no frontmatter signal, and no write-back to the issue.

## Expected Behavior

```bash
/ll:spike ENH-2565                 # plan + implement + verify spike for the issue's risk factors
/ll:spike ENH-2565 --plan-only     # produce/refresh the spike plan file, do not implement
/ll:spike ENH-2565 --plan path.md  # use a caller-supplied plan file (skip plan generation)
/ll:spike ENH-2565 --auto          # non-interactive (automation contexts)
/ll:spike ENH-2565 --check         # FSM evaluator: exit 0 if spike ACs pass, 1 otherwise; no writes
```

Workflow: read the issue's `Outcome Risk Factors` / `Confidence Check Notes` → identify which risks a spike retires → write a spike plan (Context, Approach, Critical files, Implementation, AC-per-risk test table, Verification commands, Out of scope, Promotion) → implement in an isolated spike package → run the AC suite plus the named regression suites → on pass, write back `## Spike Results` (retired risks, spike location, verification transcript summary, promotion path) and set `spike_completed: true`.

## Use Case

An AI coding agent (or human) refining ENH-2565 gets outcome-confidence 66/100 with risk factors "(a) the flock-guarded readiness-gated pop has zero precedent in any loop YAML, (b) no existing test exercises N-worker FSM fan-out with a real barrier." Running `/ll:spike ENH-2565` produces `scripts/tests/spike/rn_refine_synth_pop/` (library + driver + `TestSynthPopReadinessGate`), runs the three verification pytest commands, appends Spike Results to the issue, and the downstream loop-YAML work proceeds against a proven core.

## Proposed Solution

New skill at `skills/spike/SKILL.md` (invocable as `/ll:spike`), following the argument-parsing, `--auto`/`--check`, session-log, and frontmatter-flag conventions of `skills/confidence-check/SKILL.md` and `commands/ready-issue.md`.

### Phases

1. **Parse args & locate issue** — `ll-issues path`, standard flag parsing (`--auto`, `--check`, `--plan-only`, `--plan <file>`; auto-enable AUTO_MODE under `LL_NON_INTERACTIVE` / `--dangerously-skip-permissions`).
2. **Risk extraction** — read `## Confidence Check Notes` → `### Outcome Risk Factors` (and `## Spike Plan` if present). Each risk factor that names an unproven mechanism becomes a row in the spike's AC table. If no risk factors exist and no `--plan` given, run standalone analysis of the Proposed Solution to identify the riskiest unprecedented mechanism; in interactive mode confirm scope with AskUserQuestion.
3. **Plan** — write `<run-artifacts>/spike-<ISSUE-ID>.md` in the ENH-2565 plan shape. Mandatory sections: Context (why confidence was low), Approach, Critical files, Implementation (package layout under `scripts/tests/spike/<slug>/`, API sketch), test-class table mapping each test → the AC/risk it retires, at least one regression-guard test (e.g., AST sniff preventing a forbidden import), Acceptance criteria, Verification (exact pytest commands incl. existing regression suites), Out of scope, Promotion (post-spike move to `scripts/little_loops/spike/<slug>/`, separate PR).
4. **Implement** — build the spike package + test class exactly as planned. Spike code lives only under `scripts/tests/spike/`; production files are read-only in this skill.
5. **Verify** — run the plan's Verification commands. All must exit 0.
6. **Write-back** — append `## Spike Results` to the issue (retired risks table, spike paths, verification summary, promotion path); set `spike_completed: true` and record `spike_attempted: true` in frontmatter (idempotent, CLI/Edit pattern per confidence-check Phase 4); append session log via `ll-issues append-log`. On failure: set only `spike_attempted: true`, append `## Spike Findings` with what was disproven — a *failed* spike is also signal (the approach is wrong; route to decide/size-review).
7. **Recommend next step** — `Run /ll:confidence-check [ID]` to re-score, then proceed to implementation.

### Budget discipline

One spike per issue by default: if `spike_attempted: true` is already set, refuse unless `--force` (mirrors `max_refine_count` discipline). The skill itself is bounded to the plan's AC suite — no open-ended exploration.

## Scope Boundaries

- **Not** the FSM/loop integration — `spike_needed` flag detection in confidence-check, autodev triage routing, and a `spike-gate.yaml` wrapper loop are ENH-2568.
- **Not** promotion — moving accepted spike code into `scripts/little_loops/spike/` stays a manual, separate-PR step documented in the plan's Promotion section.
- **Not** external-API proving — that remains `/ll:explore-api` + Learning-Test Registry; the skill should point there when a risk factor names a third-party API.
- Python/pytest spikes only in v1 (matches the ENH-2565 precedent). Other harnesses out of scope.

## API/Interface

- New skill directory `skills/spike/` (SKILL.md + `agents/openai.yaml` stub, matching sibling skills).
- New `/ll:spike` command surface: `[issue-id]` + `--auto | --check | --plan-only | --plan <file> | --force`.
- New frontmatter fields consumed/produced: `spike_attempted`, `spike_completed` (read by ENH-2568's routing later).
- Exit-code contract for `--check`: 0 = spike ACs pass, 1 = fail (FSM `evaluate: type: exit_code` compatible).

## Integration Map

### Files to Create
- `skills/spike/SKILL.md` — the skill.
- `skills/spike/plan-template.md` — the ENH-2565-shaped plan template with per-section guidance.
- `skills/spike/agents/openai.yaml` — parity stub like sibling skills.
- `scripts/tests/spike/__init__.py` — spike package root (if not already created by ENH-2565's spike).

### Files to Modify
- `commands/help.md` — register the new skill.
- `skills/ll-help/SKILL.md` (and any skill-count doc checks; see [[readme_conventions]] `ll-verify-docs` count checks) — update counts/listings.
- `docs/` skills reference — add `/ll:spike` entry.
- `.claude-plugin/` manifest if skills are enumerated there.

### Dependent Files
- ENH-2568 (autodev triage + spike-gate loop) will invoke `/ll:spike --auto` and `--check`.

### Similar Patterns
- `skills/confidence-check/SKILL.md` — flag parsing, frontmatter write-back via CLI, findings write-back, `--check` evaluator contract.
- `skills/explore-api/SKILL.md` — "prove an assumption with running code, record the proof" (external-API analogue).
- `skills/wire-issue/SKILL.md` — issue-mutating remediation skill invoked from autodev triage.
- ENH-2565 spike plan (readiness-gated pop) — golden example of the plan deliverable.

### Tests
- Doc-count / plugin-manifest checks (`ll-verify-docs`) must pass with the new skill registered.
- Optional: a fixture-level test that the plan template contains all mandatory sections.

### Documentation
- README / docs skills tables per [[readme_conventions]].
- CHANGELOG entry.

### Configuration
- Optional future key `commands.spike.*` (e.g., default spike dir) — not required for v1.

## Implementation Steps

1. Draft `skills/spike/plan-template.md` by generalizing the ENH-2565 spike plan.
2. Write `skills/spike/SKILL.md` with Phases 1–7 above, mirroring confidence-check's conventions.
3. Register the skill (help.md, docs, plugin manifest); run `ll-verify-docs`.
4. Dogfood against ENH-2565: `/ll:spike ENH-2565 --plan <existing plan>` should implement and verify the already-written plan unchanged.
5. Capture dogfood learnings back into the template.

## Impact

- **Priority**: P2 — needed now for ENH-2565; closes the only outcome-confidence failure mode with no skill-level remedy.
- **Effort**: Medium — one skill + template + registration; no engine changes.
- **Risk**: Low — additive; touches no loop YAML or Python engine code.
- **Breaking Change**: No.

## Related Issues

- **ENH-2565** — first consumer; its spike plan is the template source.
- **ENH-2569** — confidence-check phase that sets `spike_needed` (not blocked by this issue; can land in parallel).
- **ENH-2568** — downstream FSM integration (autodev routing + spike-gate loop). Blocked by this issue and ENH-2569.
- **ENH-2209 / explore-api** — external-API analogue of the same prove-before-implement principle.

## Status

**Open** | Created: 2026-07-10 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-10T01:34:59Z - `manual capture via Claude Cowork session`
