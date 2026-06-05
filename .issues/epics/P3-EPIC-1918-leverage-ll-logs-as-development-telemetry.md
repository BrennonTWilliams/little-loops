---
id: EPIC-1918
title: Leverage ll-logs as a development telemetry layer
type: EPIC
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
labels: [epic, captured, ll-logs, telemetry, observability]
relates_to: [ENH-1919, FEAT-1920, ENH-1921, ENH-1922, ENH-1923, ENH-1924, FEAT-1309, ENH-1904, FEAT-1925]
---

# EPIC-1918: Leverage ll-logs as a development telemetry layer

## Summary

`ll-logs` already captures a persisted, filterable, **tool-level** corpus of
real Claude Code sessions scoped to ll activity, spanning **every project**
under `~/.claude/projects/` (via `discover` → `extract` → `logs/`). Today that
corpus is used only for archival/extraction and live `tail`. This EPIC turns it
into a first-class development-telemetry layer: a source of real tool-chain
sequences, eval fixtures, quality dashboards, failure mining, dead-skill
detection, and behavioral diffing.

The unifying insight: little-loops is a Claude Code workflow toolkit, so its own
usage logs are the best available training/evaluation/observation data for its
own features — it can dogfood its telemetry. ll-logs sees what `ll-messages`
(user text) and `ll-history`/`ll-session` (issue outcomes) cannot: the actual
sequence of tool-use and skill invocations as they really happened.

## Motivation

The CLAUDE.md "Loop Authoring" rules insist meta-loops measure **externally**,
not via LLM self-grade — but the project has no general external-evidence source
for *interactive* sessions. ll-logs is exactly that signal and is already built
(FEAT-1001..1006, FEAT-1269..1274). Each child extracts one concrete capability
from the corpus instead of leaving it as a passive archive.

## Children

- **ENH-1919** — `ll-logs sequences`: tool-chain n-gram extraction primitive (feeds loop-suggester / FEAT-1309)
- **FEAT-1920** — `ll-logs eval-export`: turn real sessions into ll-harness / create-eval-from-issues fixtures
- **ENH-1921** — `ll-logs stats`: skill-frequency / error-rate / correction-rate telemetry dashboard
- **ENH-1922** — `ll-logs scan-failures`: mine failed `ll-*` tool calls from interactive sessions → auto-file bugs
- **ENH-1923** — Dead-skill detection: cross-reference catalog vs. logs for never-invoked skills (feeds find-dead-code)
- **ENH-1924** — `ll-logs diff`: compare two sessions to spot behavioral regressions after a prompt/config change
- **FEAT-1925** — `ll-logs-telemetry-digest` FSM loop: orchestrates all EPIC-1918 subcommands into a single periodic digest run

## Scope

### In scope

- New `ll-logs` subcommands and shared extraction helpers operating on the
  already-extracted `logs/**/*.jsonl` corpus (and `~/.claude/projects/` raw).
- Integration wiring into existing consumers: `loop-suggester`,
  `create-eval-from-issues`/`ll-harness`, `find-dead-code`, `ll-ctx-stats`.

### Out of scope

- New raw-capture mechanics (discover/extract already exist).
- The proactive *notification UX* for sequences — that is FEAT-1309's surface;
  ENH-1919 only provides the reusable extraction primitive FEAT-1309 consumes.
- User-correction *text* mining into history.db — already shipped in ENH-1904;
  ENH-1922 covers the distinct *tool-failure* angle.
- PII detection for telemetry data — already shipped as ENH-1885 under
  [[EPIC-1880]]; consume `little_loops.pii` rather than building a separate
  privacy filter.

## Implementation Order

1. ENH-1919 (sequences) and ENH-1921 (stats) first — both are read-only
   aggregations over the corpus and establish shared parsing helpers.
2. ENH-1922 (scan-failures) and ENH-1923 (dead-skill) build on the same helpers.
3. FEAT-1920 (eval-export) and ENH-1924 (diff) are the higher-effort consumers.

## Success Metrics

- At least one existing feature (loop-suggester, find-dead-code, or a meta-loop)
  consumes an ll-logs telemetry subcommand as a real input.
- A meta-loop can cite ll-logs-derived external evidence for an improvement.

## Labels

epic, captured, ll-logs, telemetry, observability

## Status

open


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
