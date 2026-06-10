---
id: FEAT-2041
title: Guided first-loop onboarding after ll init
type: FEAT
status: open
priority: P3
captured_at: '2026-06-09T04:40:09Z'
discovered_date: 2026-06-09
discovered_by: capture-issue
labels:
- feature
- onboarding
- init
- loops
blocked_by:
- ENH-1982
relates_to:
- FEAT-270
- FEAT-1654
parent: EPIC-1978
confidence_score: 50
outcome_confidence: 52
score_complexity: 17
score_test_coverage: 12
score_ambiguity: 5
score_change_surface: 18
decision_needed: true
---

# FEAT-2041: Guided first-loop onboarding after ll init

## Summary

After a new user finishes `ll init`, give them an optional guided "first loop"
experience that walks them through picking, understanding, and running their
very first automation loop end-to-end. Today init bootstraps config and ships
built-in loops, but the user is dropped back at the prompt with no obvious next
step — they have to already know that loops exist, what they do, and how to run
one. A short guided flow turns "setup complete" into a working, demonstrated
loop so the user sees value immediately.

## Use Case

A developer installs the little-loops plugin and runs `ll init` on a fresh
project. Init completes and prints "✅ Configured." The user has never used an
FSM loop and doesn't know `ll-loop` exists. Instead of leaving them to read
docs, init offers: "Want to run your first loop? (y/n)". On yes, it presents a
curated shortlist of 2–3 beginner-safe built-in loops (with one-line
descriptions of what each does and what it will change), the user picks one,
the flow explains what will happen, runs it (optionally in `--dry-run` first),
and shows the result plus the exact command to re-run it later. The user ends
their first session having actually completed a loop, not just configured one.

## Current Behavior

- `ll init` bootstraps `.ll/ll-config.json`, wires settings, and the plugin
  ships built-in loops (FEAT-270), but the post-init experience ends there.
- Discovering loops requires the user to already know about `ll-loop list` /
  `/ll:create-loop` / the loop-router (FEAT-1654).
- There is no curated "start here" path; a new user faces the full catalog of
  built-in loops with no guidance on which are safe/useful to try first.

## Expected Behavior

- After successful `ll init`, the user is offered (opt-in, skippable) a guided
  first-loop flow.
- The flow surfaces a small curated set of beginner-friendly built-in loops,
  each with a plain-language description and a note about what it reads/writes.
- The user selects one; the flow explains the loop's purpose and offers a
  dry-run preview before any real execution.
- The loop runs, results are summarized, and the user is shown the exact
  command to run it again unaided (`ll-loop run <name>`).
- Declining is a clean no-op; the offer never blocks or repeats nagging on
  subsequent inits.

## Motivation

First-run activation is where onboarding tools win or lose users. Loops are the
highest-leverage capability in little-loops, but they're also the least
discoverable for someone who just installed the plugin. A guided first loop
converts a passive "config written" outcome into an active "I ran something and
it worked" outcome — the moment a user understands what the tool is *for*.
Concretely it should reduce time-to-first-loop from "read several docs" to
"under a minute," and reduce the share of installs that never run a single loop.

## Proposed Solution

TBD - requires investigation. Sketch of an approach:

- Add an opt-in onboarding step at the tail of the `init` skill
  (`skills/init/`), gated so it only fires on first successful init and is
  fully skippable (and suppressible via config, e.g.
  `onboarding.first_loop_prompt: false`).
- Maintain a small curated allowlist of "starter" built-in loops (read-only or
  low-blast-radius), separate from the full `ll-loop list` catalog. Each entry
  carries a one-line description and a read/write summary.
- Reuse `AskUserQuestion` for the loop selection step (mirrors existing init
  rounds), then invoke the chosen loop via `ll-loop run <name>` — preferring a
  `--dry-run` preview first where the loop supports it.
- Consider sharing the curation/description metadata with the loop-router
  (FEAT-1654) and `loop-suggester` so "starter loops" are defined once.
- Print a "run it again with: `ll-loop run <name>`" footer so the knowledge
  transfers past the guided flow.

## Integration Map

### Files to Modify
- `skills/init/` (SKILL.md and any round logic) — add the post-init opt-in step
- `config-schema.json` — add an `onboarding` toggle (e.g. `first_loop_prompt`)
- TBD - confirm where built-in loop metadata/descriptions live for curation

### Dependent Files (Callers/Importers)
- TBD - use grep to find `ll-loop run` / loop-listing call sites and the init flow entrypoints

### Similar Patterns
- `skills/configure/` and existing init rounds (AskUserQuestion usage)
- `loop-suggester` / loop-router (FEAT-1654) for loop description/curation reuse

### Tests
- TBD - add tests for the opt-in gate (fires once, skippable, suppressed by config)
- `scripts/tests/` loop-run integration coverage for the starter-loop path

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — reference the guided first-loop entrypoint
- Getting-started docs — mention the post-init offer

### Configuration
- `config-schema.json` and `.ll/ll-config.json` onboarding toggle

## Implementation Steps

1. Define a curated "starter loops" set (metadata + safe/low-blast-radius selection)
2. Add the opt-in, skippable first-loop step to the `init` skill with a config gate
3. Wire selection → explanation → optional dry-run → `ll-loop run` → result summary
4. Add the `onboarding` config toggle to schema and respect it
5. Tests for the gate (fires once, skippable, config-suppressed) and the run path
6. Document the entrypoint in LOOPS_GUIDE and getting-started

## Impact

- **Priority**: P3 - High-value onboarding improvement but not blocking; init and loops both already work independently.
- **Effort**: Medium - Reuses existing init AskUserQuestion rounds and `ll-loop run`, but requires curating a safe starter set and a new opt-in gate with config + tests.
- **Risk**: Low - Opt-in and skippable; isolated to the tail of the init flow. Main risk is choosing starter loops that mutate state unexpectedly — mitigated by a read-only/dry-run-first curation.
- **Breaking Change**: No

## Verification Notes

**Verdict: NEEDS_UPDATE** — 2026-06-09. Issue is a recent capture with many TBD placeholders throughout (no "starter loops" metadata defined, no config-schema.json `onboarding` toggle exists, no test scaffolding). Needs a research pass to define: (1) which loops qualify as safe starters, (2) the config key name, (3) what "dry-run" means for each loop type, before implementation can begin.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 50/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 52/100 → LOW

### Concerns
- Blocker ENH-1982 (P2, open) plans to deprecate the ~1,250-line `/ll:init` skill into a thin redirect stub — implementing FEAT-2041 on top of the current skill before ENH-1982 resolves risks rework or merge conflict

### Gaps to Address
- The "Proposed Solution" is explicitly TBD: no decision on which loops qualify as safe starters, what dry-run means per loop type, or how curation metadata is structured
- Integration Map has multiple unresolved TBDs (caller grep, test file locations, built-in loop metadata location)
- No acceptance criteria or testable success conditions defined
- `config-schema.json` `onboarding` toggle does not yet exist and must be added as part of this issue

### Outcome Risk Factors
- High ambiguity across design questions (Criterion C: 5/25): starter-loop selection criteria, dry-run semantics per loop type, and metadata sharing with loop-router (FEAT-1654) are all unresolved
- Unresolved decision: whether to share curation metadata with FEAT-1654 loop-router or maintain a separate allowlist — resolve before implementing

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:capture-issue` - 2026-06-09T04:40:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a7dc4eb-c8a8-4b46-a273-e4f41f226adc.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `b3b25073-0aac-4ee9-a4b1-552f2a26b261.jsonl`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `onboarding`, `init`, `loops`, `captured`

## Status

**Open** | Created: 2026-06-09 | Priority: P3
