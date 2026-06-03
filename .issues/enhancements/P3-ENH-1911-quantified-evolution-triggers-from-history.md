---
id: ENH-1911
title: Quantified evolution triggers from history (recurring feedback + skill bypass)
type: ENH
priority: P3
status: open
captured_at: "2026-06-03T20:59:38Z"
discovered_date: 2026-06-03
discovered_by: capture-issue
---

# ENH-1911: Quantified evolution triggers from history (recurring feedback + skill bypass)

## Summary

Extend `analyze-history` (and feed `improve-claude-md`) with quantified "evolution trigger"
signals modeled on `revfactory/harness`'s Phase 7: detect when the **same user correction has
recurred ≥N times** and when a user has **bypassed a skill/loop N times** (did the work
manually instead of invoking the matching skill). Both signals turn accreted history into
concrete, count-backed proposals for harness self-improvement (a CLAUDE.md rule, a sharper
skill description, or a new loop).

## Motivation

little-loops already detects recurring *manual* activity — `ManualPattern` /
`ManualPatternAnalysis` (`scripts/little_loops/issue_history/models.py`) flags activities
across ≥2 issues and suggests automation. But it does **not** quantify two signals harness
makes load-bearing:
- **Recurring feedback**: the same correction given repeatedly. little-loops captures these
  ad hoc as `memory/feedback_*` files but never counts recurrence to justify a permanent rule.
- **Skill bypass**: the user repeatedly doing by hand what a skill/loop already does — a strong
  "the trigger isn't firing or the skill is too heavy" signal.

**Why:** "Same feedback ≥2 times" and "user bypassed the orchestrator" are exactly the
evolution triggers that keep a harness from drifting. little-loops has the raw material
(`.ll/history.db`, `memory/feedback_*`) but no counter that converts recurrence into action.
**How to apply:** This is a *detector + proposer*, not an auto-editor. It surfaces ranked,
count-backed candidates; applying a change stays with `improve-claude-md` / the user.

## Motivating Signal (from this conversation)

A review of harness's Phase 7 "Evolution Triggers" (fire on: same feedback type 2+ times,
repeated failure pattern, user bypasses orchestrator) highlighted that little-loops detects
recurring manual work but not recurring *feedback* or *bypass*.

## Implementation Steps

1. **Recurring-feedback detector.** Cluster `memory/feedback_*` files + correction-shaped
   turns in `.ll/history.db` (FTS5) by topic; count recurrence; rank clusters with count ≥ N
   (default 2) as candidate permanent rules.
2. **Skill-bypass detector.** From session history, identify episodes where the user manually
   performed work that a registered skill/loop covers (match against skill descriptions /
   trigger keywords) without invoking it; count per skill.
3. **Surface in `analyze-history`.** Add an "Evolution Triggers" section to its report:
   recurring corrections (with counts + example sessions) and bypassed skills (with counts).
4. **Feed `improve-claude-md`.** Pass the ranked candidates so it can propose a CLAUDE.md rule
   or a description tweak, each annotated with its recurrence count as justification.
5. Make thresholds configurable under `analysis.*` in `.ll/ll-config.json`.

## API/Interface

- `analyze-history` report gains an `## Evolution Triggers` section.
- New model(s) alongside `ManualPattern` in `scripts/little_loops/issue_history/models.py`,
  e.g. `RecurringFeedback{topic, occurrence_count, example_sessions}` and
  `SkillBypass{skill, bypass_count, example_sessions}`.
- Config: `analysis.evolution.feedback_min_recurrence` (default 2),
  `analysis.evolution.bypass_min_count` (default 2).

## Open Questions

1. **Bypass detection precision.** Matching "user did X manually that skill Y covers" is fuzzy;
   risk of false positives. Start conservative (high-confidence keyword/file-signature matches)
   and report counts, not auto-actions.
2. **Feedback clustering.** Reuse the FTS5 / topic-excerpt machinery (`ll-history`,
   `ll-history-context`) or cluster `memory/feedback_*` directly? Probably both: memory files
   are the curated signal, history.db the raw recurrence evidence.
3. **Cross-session identity.** Recurrence must span sessions; lean on `.ll/history.db` as the
   durable store rather than single-session transcripts.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/models.py` — add `RecurringFeedback` / `SkillBypass` models
- `skills/analyze-history/SKILL.md` — add the `## Evolution Triggers` report section
- `skills/improve-claude-md/SKILL.md` — consume the ranked candidates
- `.ll/ll-config.json` schema (`config-schema.json`) — new `analysis.evolution.*` keys
- `scripts/tests/test_issue_history*.py` — detector unit tests

### Similar Patterns
- `scripts/little_loops/issue_history/models.py` — `ManualPattern` / `ManualPatternAnalysis` (≥2-issue recurrence detector to mirror)
- `ll-history` / `ll-history-context` — FTS5 + topic-excerpt machinery to reuse
- `agents/loop-specialist.md` — post-hoc failure-mode taxonomy (related "evolve the harness" surface)

### Configuration
- `analysis.evolution.feedback_min_recurrence` (default 2)
- `analysis.evolution.bypass_min_count` (default 2)

## Provenance

Surfaced while reviewing `https://github.com/revfactory/harness`. Its Phase 7 fires
self-improvement on quantified triggers (same feedback 2+ times, repeated failure, user
bypasses orchestrator). This issue ports the *signal detection*; little-loops keeps its more
rigorous "propose, don't auto-grade" stance for the action side.

## Session Log
- `/ll:capture-issue` - 2026-06-03T20:59:38Z - `b4fa1e68-4a59-49bd-949a-5a5b7533509f.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-03
