---
id: EPIC-2027
title: Harness evolution via session history
type: EPIC
priority: P3
status: done
captured_at: '2026-06-08T00:00:00Z'
discovered_date: '2026-06-08'
discovered_by: capture-issue
labels:
- epic
- history
- analyze-history
- improve-claude-md
- evolution
- harness
relates_to:
- EPIC-1707
- EPIC-1918
- ENH-1911
---

# EPIC-2027: Harness evolution via session history

## Summary

little-loops accumulates rich session history in `.ll/history.db` and
`memory/feedback_*` files. Two sibling EPICs already exploit this data:
EPIC-1707 injects it as runtime agent context; EPIC-1918 turns it into
development telemetry. This EPIC covers the third consumer: **harness
evolution proposals** — detecting quantified signals in accreted history
and converting them into concrete, count-backed recommendations to improve
the harness itself (CLAUDE.md rules, skill-description tweaks, new loops).

The unifying pipeline is: **detect → quantify → propose**. Nothing is
auto-applied. Recommendations land in `analyze-history` reports and are
consumed by `improve-claude-md` for human review.

## Motivation

A healthy harness should get better as it is used. Two failure modes
accumulate silently without this EPIC:

1. **Feedback drift** — the same user correction recurs across sessions
   without ever becoming a permanent rule. `memory/feedback_*` files grow
   but nothing counts recurrence or flags when a cluster is large enough
   to justify a CLAUDE.md entry.
2. **Skill bypass** — the user repeatedly does by hand what a registered
   skill/loop already covers, without invoking it. This is the strongest
   available signal that a skill's trigger description is wrong or the
   skill is too heavy — but it currently goes undetected.

Both signals are already latent in `.ll/history.db`. This EPIC builds the
detectors and surfaces them as ranked, count-backed candidates.

## Scope Boundary vs. Sibling EPICs

| Concern | Owner |
|---|---|
| Runtime agent context injection from history | EPIC-1707 |
| ll-logs tool-chain telemetry and observability | EPIC-1918 |
| **Harness evolution proposals from history** | **EPIC-2027 (this)** |

All three read from `.ll/history.db` but target different consumers and
produce different artifacts. This EPIC's output is always a ranked proposal
list for human review — never an auto-edit.

## Children

- **ENH-1911** — Quantified evolution triggers: recurring-feedback detector
  (cluster `memory/feedback_*` + correction-shaped turns by topic, count
  recurrence ≥ N) and skill-bypass detector (user performed work manually
  that a registered skill covers, counted per skill). Surfaces an
  `## Evolution Triggers` section in `analyze-history` reports; feeds
  `improve-claude-md` with count-backed candidates. **Done.**
- **ENH-2046** — Evolution-trigger consumer + correction retirement:
  `improve-claude-md --consume-triggers` (CT-0…CT-4 pipeline: candidates →
  dedup → per-candidate approval, including "Add to CLAUDE.md" with the
  recurrence count in the rationale → persist to `decisions.yaml` →
  retirement records in `correction_retirements`, schema v13). **Done.**
  Satisfies success metric 3.

## Potential Future Children

- ~~An `improve-claude-md` enhancement that consumes evolution-trigger output
  and proposes CLAUDE.md rule additions annotated with recurrence counts.~~
  **Delivered by ENH-2046.**
- A periodic FSM loop that runs the full detect → propose pipeline and
  files candidate-rule issues when thresholds are crossed.
- A "harness drift score" metric: composite of bypass rate + uncorrected
  recurrence count, tracked over time.

## Implementation Order

1. **ENH-1911** — detectors and `analyze-history` surface (prerequisite for
   all follow-on work; depends on ENH-1906 retention policy).
2. `improve-claude-md` consumer wiring (can start after ENH-1911 ships the
   ranked-candidate output format).
3. Periodic FSM loop (optional; builds on the above).

## Success Metrics

- `analyze-history` produces an `## Evolution Triggers` section with at
  least two distinct signal types (recurring feedback + skill bypass).
- At least one correction that had recurred ≥ 2 times is surfaced as a
  candidate permanent rule in a real project session.
- `improve-claude-md` can consume the ranked candidates and propose a
  CLAUDE.md edit with a recurrence count in its justification.

## Labels

epic, history, analyze-history, improve-claude-md, evolution, harness

## Status

done — closed 2026-06-12 by epic audit. Both children (ENH-1911, ENH-2046)
done; all three success metrics verified (metric 3 confirmed against
`skills/improve-claude-md/SKILL.md` `--consume-triggers` pipeline). The two
remaining "Potential Future Children" (periodic FSM loop, harness drift
score) were explicitly optional and are not carried forward.

## Session Log

- EPIC created - 2026-06-08 - conversation
