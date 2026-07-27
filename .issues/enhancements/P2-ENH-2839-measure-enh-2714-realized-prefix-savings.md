---
id: ENH-2839
type: ENH
title: Measure ENH-2714's realized static-prefix savings per component
priority: P2
status: done
captured_at: '2026-07-27T00:22:46Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2714
- ENH-2805
- BUG-2840
- ENH-2841
- EPIC-2456
labels:
- token-cost
- fsm
- orchestration
- measurement
completed_at: '2026-07-27T00:22:46Z'
---

# ENH-2839: Measure ENH-2714's realized static-prefix savings per component

## Summary

ENH-2714 shipped automation-context static-prefix pruning with a final
acceptance criterion that was never satisfied:

> - [ ] Measured per-invocation input-token delta on a locked trace, broken
>       down per prefix component (catalog / hook output / CLAUDE.md),
>       recorded before close.

The issue closed `done` with that box unchecked and no number recorded. This
enhancement performs the measurement, which was prompted by a design question:
*should automation pruning be enabled by default instead of opt-in?* That
question could not be answered without knowing what pruning actually saves.

The measurement produced a decisive and unexpected answer: **pruning saves
~1K tokens per invocation, not the ~17K the static prefix suggests**, because
two of the three components are not actually prunable (see BUG-2840).

## Motivation

Two gates control pruning today, and only one is a real opt-in:

- `history.automation_pruning.enabled` (`config/features.py:1033`) already
  defaults to `True` — its own docstring calls it an escape hatch to *force*
  full output, not the thing holding pruning back.
- Per-state `pruning_profile:` in loop YAML is the real opt-in, and adoption
  is thin: **3 of 90 loops** declare it (`autodev.yaml` 13 states,
  `refine-to-ready-issue.yaml` 3, `oracles/verify-confidence-scores.yaml` 2).

Flipping the default is a behavior change across the whole loop fleet. Doing
that without a measured saving would be spending migration risk on an unknown
return.

## Current Behavior

ENH-2714 is closed `done` with its measurement acceptance criterion unchecked.
No per-component token figure exists anywhere in the repo, so the cost model for
automation pruning is guesswork — the issue body itself only offers "CLAUDE.md
is likely the dominant component." Decisions about pruning defaults, adoption
across the 87 un-profiled loops, and further EPIC-2456 work all rest on an
unmeasured assumption.

## Expected Behavior

A recorded, reproducible per-component breakdown of the automation-context
static prefix, measured against the correct cost metric for the caching regime
actually in force, with limitations stated — sufficient to decide whether
pruning should be enabled by default.

## Scope Boundaries

**In scope:** measuring the existing implementation; identifying the correct
metric; answering the default-on question.

**Out of scope:** implementing catalog suppression, changing any pruning
default, altering `ll-verify-skill-budget`, and re-running arm C. Fixes that
followed from the findings were split into BUG-2840 (capability/doc
correctness) and ENH-2841 (agent-description trim) rather than folded in here.

## Method

Three-phase, cheapest-first. Phases 1 and 3 cost nothing.

### Phase 1 — static component breakdown (offline, free)

- `.claude/CLAUDE.md` token count via `session_store._estimate_tokens`.
- Frontmatter `description:` totals across `commands/*.md`,
  `skills/*/SKILL.md`, `agents/*.md` (the injected catalog).
- Direct A/B of `hooks.session_start.handle()` with `LL_AUTOMATION` unset vs.
  set, in-process, same cwd.

### Phase 2 — is prompt caching in play? (offline, free)

Scanned 1,456 session JSONL files under
`~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`,
taking **only the first usage event of each session** — a cold, fresh-session
call, which is exactly the shape of an FSM state invocation.

### Phase 3 — controlled A/B (live)

Three temporary single-state loops (`.loops/ab-arm-{a,b,c}.yaml`), each
invoking `/ll:confidence-check FEAT-2414`, differing *only* in
`pruning_profile`. Arms spaced 330s apart to let the prompt cache expire so
each arm starts cold. Per-state usage read from each run's `usage.jsonl`.

## Findings

### Static breakdown (Phase 1)

| Component | Est. tokens | Share | Nominally prunable via |
|---|---:|---:|---|
| Catalog — `agents/` (9) | 3,353 | 20% | `suppress_catalog` |
| Catalog — `skills/` (71) | 3,188 | 19% | `suppress_catalog` |
| Catalog — `commands/` (29) | 1,793 | 10% | `suppress_catalog` |
| CLAUDE.md | 7,704 | 45% | `suppress_claude_md` |
| SessionStart hook output | 970 | 6% | `LL_AUTOMATION` env signal |
| **Total** | **~17,000** | | |

The hook A/B was exact: 4,054 chars unpruned vs. 174 pruned.

CLAUDE.md is close to the ENH-2714 guess ("likely the dominant component"),
but the **catalog is actually the largest bucket at 49%** — driven mostly by
`agents/`, whose 9 descriptions embedded full `<example>` blocks
(addressed in ENH-2841).

### Caching is fully in play (Phase 2)

First usage event per session, n=1,456:

| Metric | Median | Mean |
|---|---:|---:|
| `input_tokens` (uncached) | **2** | 4,875 |
| `cache_read_input_tokens` | 28,446 | 31,675 |
| `cache_creation_input_tokens` | 27,884 | 22,838 |

**99% of fresh sessions get a cache hit on their very first call.** Uncached
input is a rounding error. "Pruning saves ~17,000 tokens/invocation" is
therefore wrong as a *cost* claim — those tokens are already billed at cache
rates (0.1x read / 1.25x write), not sticker.

This invalidated the originally-planned metric. Measuring an `input_tokens`
delta would have read ~0 in every arm and produced the false conclusion that
pruning does nothing. The correct metric is the
**`cache_creation_input_tokens` delta**.

### Controlled A/B (Phase 3)

First-turn usage, main session of each arm:

| Arm | Profile | uncached | cache_read | **cache_write** |
|---|---|---:|---:|---:|
| A | none | 2 | 23,684 | **41,099** |
| B | `suppress_claude_md` | 2 | 23,684 | **39,467** |

Delta ≈ **1,632 tokens**. If CLAUDE.md were genuinely suppressed the expected
delta was ~7,704. The observed value is consistent with the hook layer alone
(~970) plus run-to-run noise.

Root cause confirmed in code, not just inferred from the number — see
BUG-2840.

**Arm C (`suppress_catalog`) never ran.** Its loop file was deleted mid-run by
a concurrent Claude Code session (`b1141b9c`) that classified the untracked
`.loops/ab-arm-*.yaml` files as repo pollution and ran
`rm -f .loops/ab-arm-*.yaml` at 23:58:52Z. This cost no information: BUG-2840
established that `suppress_catalog` is equally inert, so arm C would have
measured the same ~0 effect.

## Impact

Answers the design question that prompted the work: **enabling automation
pruning by default is close to moot as implemented.** Of the ~17,000-token
prefix, the only component that prunes today is ~970 tokens of hook output,
and that path is already effectively on (`automation_pruning.enabled` defaults
`True`; declaring any profile activates it). Flipping a default would buy
essentially nothing while spending fleet-wide migration risk.

Redirects effort to the two things that do pay:

1. Trimming injected description text directly (ENH-2841 recovered 1,905
   tokens — nearly 2x the entire realized benefit of the pruning feature).
2. Actually implementing catalog suppression, the largest remaining lever
   (~6,429 tokens post-ENH-2841) and still unmeasured.

## Limitations

Stated plainly so the numbers are not over-trusted:

- **Phase 3 is n=1 per arm**, one issue, and `/ll:confidence-check` is a
  multi-turn agentic skill whose trajectory varies run to run (arm A took 26
  turns, arm B 16). The 1,632 figure is soft.
- The load-bearing evidence for the conclusion is the **code inspection**
  (BUG-2840), not the A/B delta. The A/B corroborates; it does not carry the
  argument alone.
- Token counts are `_estimate_tokens` (char/4) approximations, adequate for a
  ratio decision but not exact BPE counts.
- Session-JSONL attribution in Phase 3 is muddied by subagent sessions sharing
  the arm's mtime window; the main session was identified by turn count.
- `suppress_catalog`'s real-world effect remains **unmeasured**.

## Acceptance Criteria

- [x] Per-component static breakdown of the automation-context prefix
      recorded (catalog / hook output / CLAUDE.md).
- [x] Determine whether prompt caching is in play on the CLI path for
      fresh-session invocations.
- [x] Identify the correct cost metric given the caching behavior.
- [x] Controlled A/B isolating at least one suppression flag against a
      no-profile baseline.
- [x] Record limitations and unmeasured components.
- [x] Answer the originating question: should pruning be on by default?

## Status

Completed. All six acceptance criteria met; ENH-2714's unchecked measurement
criterion is now satisfied by this record. One component (`suppress_catalog`)
remains unmeasured — deliberately, since BUG-2840 established it is inert, so
measuring it is only worthwhile once it is actually implemented.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-27T00:23:38 - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`
- interactive session - 2026-07-27T00:22:46Z - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Resolution

- **Action**: measure
- **Completed**: 2026-07-27
- **Status**: Completed
- **Implementation**: Three-phase measurement (static breakdown, cache-behavior
  scan over 1,456 sessions, live three-arm A/B). Satisfies ENH-2714's unchecked
  final acceptance criterion. Findings drove BUG-2840 and ENH-2841.

### Files Changed

No production code. Temporary measurement artifacts (`.loops/ab-arm-{a,b,c}.yaml`)
were created and are no longer present. Run data retained at
`.loops/runs/ab-arm-a-20260726T184724/` and
`.loops/runs/ab-arm-b-20260726T185508/` (`usage.jsonl`).

### Follow-ups

- `suppress_catalog` effect is unmeasured — a clean arm-C re-run is worth doing
  once catalog suppression is actually implemented (BUG-2840 follow-up).
- `ll-verify-skill-budget` reports 516/2000 tokens "under budget" while the real
  injected `skills/` listing measures ~3,188 tokens. Whatever it polices, it is
  not the catalog's true prefix cost — it gives false comfort on the largest
  bucket. Worth capturing separately.
