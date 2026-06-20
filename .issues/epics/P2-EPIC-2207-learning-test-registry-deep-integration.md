---
id: EPIC-2207
title: Learning Test Registry — Deep Integration Across ll Features
type: epic
priority: P2
status: done
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
relates_to: [ENH-2208, ENH-2209, ENH-2210, ENH-2212, ENH-2214, ENH-2215, ENH-2216, ENH-2217, ENH-2218, ENH-2219, ENH-2220, ENH-2221]
---

# EPIC-2207: Learning Test Registry — Deep Integration Across ll Features

## Summary

The Learning Test Registry and its gate primitives (discoverability hook, assumption-firewall, ready-to-implement-gate) were shipped as standalone infrastructure in EPIC-1694. This epic wires that infrastructure into the broader ll workflow surface: issue lifecycle, sprint orchestration, loop authoring, release management, and observability. The goal is to make proof-before-codegen the default path rather than something the user must explicitly invoke.

## Motivation

EPIC-1694 delivered the core registry, proof loops, and an opt-in discoverability gate. However several high-leverage injection points remain untapped:

- Stale records silently pass the discoverability gate (the config key exists but the check is missing)
- Authors manually declare `learning_tests_required`; refinement skills could auto-populate it
- Sprint orchestration runs issues without pre-validating their external-API assumptions
- No signal fires when a new package is `pip install`-ed into the project
- Learning test health is invisible in `ll-ctx-stats`, `ll-history-context`, and release prep

## Children

- **ENH-2208** — Enforce `stale_after_days` threshold in discoverability gate
- **ENH-2209** — Auto-populate `learning_tests_required` in refine-issue and wire-issue
- **ENH-2210** — Sprint pre-flight: batch assumption-firewall before ll-sprint execution
- **ENH-2212** — Hook on pip/npm install to nudge explore-api for new dependencies
- **ENH-2214** — Release gate: block ll-manage-release on stale/refuted active dependencies
- **ENH-2215** — create-loop wizard: auto-insert assumption-firewall for external API loops
- **ENH-2216** — Orphaned learning test record detection
- **ENH-2217** — Inject learning test records into ll-history-context output
- **ENH-2218** — ll-ctx-stats: learning test coverage dashboard section
- **ENH-2219** — ll-parallel: per-worktree proof-first-task wrapper
- **ENH-2220** — scope-epic: auto-generate learning test sub-issues for external API epics
- **ENH-2221** — Eval dimension: learning_tests_required as machine-checkable criterion

## Acceptance Signals

- All P2/P3 children are implemented and their tests pass
- `ll-learning-tests list` + `ll-ctx-stats` together give a complete health picture
- A fresh sprint with external-API issues is blocked until assumptions are proven
- Stale records are treated as gaps at gate time, not silently passed

## Status

Done — all 12 children completed (verified 2026-06-19).

## Changes from Scoping Review

- **ENH-2211** (PostToolUse debt marker) — **Cancelled**. Only fires in `warn` mode where the agent already chose to proceed; simpler to have the PreToolUse gate write the debt itself if it matters.
- **ENH-2213** (Adversarial verification loop) — **Cancelled**. Learning tests are validated by real code execution, not LLM judgment; re-running proof scripts (via existing stale detection) is the right mechanism. LLM refuters have the same failure mode as LLM provers.
- **ENH-2219** (ll-parallel wrapper) — **Consolidated**. Gating logic now extracted into a shared utility (`learning_tests/gate.py`) used by both ENH-2210 and ENH-2219, avoiding dual maintenance.

## Verification Notes

2026-06-19 (OUTDATED→DONE): All 12 children confirmed `status: done` (ENH-2208 through ENH-2221, excluding cancelled ENH-2211/ENH-2213). The Status section read "Open — no children started yet" despite full completion. Marked `status: done` and updated Status section.

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
