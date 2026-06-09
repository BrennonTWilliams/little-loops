---
id: ENH-2046
title: Evolution-trigger consumer + correction retirement (close the detect→propose→persist loop)
type: ENH
priority: P3
status: open
captured_at: "2026-06-09T00:00:00Z"
discovered_date: "2026-06-09"
discovered_by: capture-issue
parent: EPIC-2027
relates_to: [ENH-1911, FEAT-949, FEAT-948, ENH-1831]
labels: [history, evolution, improve-claude-md, decisions, harness, self-improve]
---

# ENH-2046: Evolution-trigger consumer + correction retirement

## Summary

Close the last mile of EPIC-2027's `detect → quantify → propose` pipeline.
ENH-1911 (done) already detects recurring corrections and skill bypasses and
surfaces them as ranked, count-backed candidates in the `## Evolution Triggers`
section of `analyze-history` output. What is still missing is the **consumer**
that turns those candidates into a persisted rule under human review, plus a
**retirement** mechanism so an addressed correction stops re-surfacing forever.

This is the little-loops analog of squid's Self-Improve skill — but built on our
recurrence-gated signal (≥ `feedback_min_recurrence`, default 2, across sessions)
rather than squid's single-session transcript scan, which is noisier. It also
targets `decisions.yaml` (required rules → synced to `ll.local.md`) as the
primary sink, keeping `CLAUDE.md` edits in `improve-claude-md`'s existing lane.

This issue promotes two of EPIC-2027's listed **"Potential Future Children"**
into concrete scope, and adds the retirement piece the EPIC does not yet name.

## Current Behavior

The pipeline from "correction in conversation" to "recurring-feedback analysis"
is complete and working:

1. **Capture** — `user_prompt_submit` hook detects corrections (patterns in
   `scripts/little_loops/session_store.py`) → `user_corrections` table in
   `.ll/history.db`. Gated by `analytics.capture.corrections`.
2. **Analyze** — `analyze-history` → `detect_recurring_feedback()` /
   `detect_skill_bypass()` (`scripts/little_loops/issue_history/evolution.py`)
   group by topic and count recurrence.
3. **Propose** — ENH-1911 renders an `## Evolution Triggers` section with
   ranked **Candidate Rule** text
   (`scripts/little_loops/issue_history/formatting.py`).

But:

- **No consumer.** `improve-claude-md` *can* ingest Evolution Triggers output as
  rule candidates, but there is no command that chains analyze → dedup against
  existing rules → approve → persist. The user copies candidate text by hand.
- **No retirement.** Once a candidate becomes a rule, nothing marks the
  underlying correction cluster as "addressed." The same topic keeps surfacing
  in every future `analyze-history` run, indistinguishable from an open signal.
- **No dedup against `decisions.yaml`.** Candidates are not cross-checked against
  rules that already exist, so already-ruled topics reappear as fresh proposals.

## Expected Behavior

A consumer path that preserves EPIC-2027's hard stance — *nothing is
auto-applied; output is always a human-reviewed proposal* — plus retirement:

1. **Consumer (orchestration).** A way to take ENH-1911's ranked candidates and,
   for each, propose persistence as either a `decisions.yaml` required rule
   (preferred, via `ll-issues decisions add`, carrying the recurrence count and
   example sessions as provenance) or a `CLAUDE.md` edit (delegated to
   `improve-claude-md`). Each proposal requires explicit approval before write.
2. **Dedup.** Before proposing, cross-check each candidate topic against existing
   `decisions.yaml` rules and current `CLAUDE.md` content; suppress or annotate
   candidates already covered.
3. **Retirement.** When a candidate is accepted and persisted, mark the
   corresponding correction cluster as addressed (e.g. an `addressed_at` /
   linked-rule record keyed by the cluster's topic identity) so
   `detect_recurring_feedback()` excludes it (or flags it "already ruled") on
   subsequent runs. Addressing must be reversible/auditable.

Placement is a design choice for refinement: a thin new entry point
(e.g. `/ll:self-improve`) versus extending `improve-claude-md` with a
consume-and-persist mode. EPIC-2027 also lists an optional periodic FSM loop that
runs the full pipeline and files candidate-rule issues when thresholds cross —
out of scope here, tracked separately.

## Acceptance Criteria

- [ ] A documented path consumes ENH-1911's ranked Evolution Triggers candidates
      and, per candidate, proposes persistence to `decisions.yaml` (preferred) or
      `CLAUDE.md`, with recurrence count + example sessions carried as provenance.
- [ ] No write occurs without explicit human approval (consistent with
      EPIC-2027's "never an auto-edit" constraint).
- [ ] Candidates are deduplicated against existing `decisions.yaml` rules and
      current `CLAUDE.md` content before being proposed.
- [ ] Accepting a candidate marks its correction cluster addressed such that a
      subsequent `analyze-history` run no longer surfaces it as an open candidate
      (or clearly labels it "already ruled").
- [ ] Retirement is recorded durably (survives across sessions) and is auditable
      / reversible.
- [ ] Tests cover: consume→propose→approve→persist happy path, dedup suppression
      of an already-ruled topic, and retirement excluding an addressed cluster
      from the next detection run.

## Out of Scope

- The optional periodic FSM loop that auto-files candidate-rule issues
  (EPIC-2027 "Potential Future Children" #3) — separate issue.
- A composite "harness drift score" metric (EPIC-2027) — separate issue.
- Changing the detection thresholds or correction-capture patterns (owned by
  ENH-1911 / ENH-1887 / ENH-1915).

## Labels

history, evolution, improve-claude-md, decisions, harness, self-improve

## Status

open

## Session Log

- Captured - 2026-06-09 - from squid-plugin evaluation; promotes two EPIC-2027
  "Potential Future Children" into concrete scope and adds correction retirement.
